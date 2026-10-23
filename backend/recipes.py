"""Recipe API: pantry matching, filters, recipe details, saved recipes and ingredient suggestions."""
import threading
from collections import Counter
from datetime import datetime, timezone

from flask import g, jsonify, request

from db import INTEGRITY_ERRORS
from importer.normalize import ALLERGEN_FILTERS, clean_phrase, keys_match, name_key, user_keys

MEALS = ["breakfast", "lunch", "dinner", "snack", "dessert"]
TASTES = ["spicy", "savory", "sweet", "mild", "tangy", "sour"]
DIFFICULTIES = ["easy", "medium", "hard"]
ALLERGEN_LABELS = {
    "fish": "Fish", "shellfish": "Shellfish", "mollusk": "Mollusks", "egg": "Egg", "milk": "Dairy",
    "wheat": "Wheat/Gluten", "soy": "Soy", "peanut": "Peanuts", "tree_nut": "Tree nuts", "sesame": "Sesame",
    "coconut": "Coconut", "pork": "Pork", "chicken": "Chicken", "mustard": "Mustard", "sulfite": "Sulfites",
    "mung_bean": "Mung bean",
}
MAX_TERMS = 30


class BadRequest(Exception):
    pass


class RecipeIndex:
    """In-memory copy of what searching needs (about 500 recipes). Reloads itself when the recipes table changes."""

    def __init__(self, db):
        self.db = db
        self.version = None
        self.recipes = []
        self.by_id = {}
        self.vocab = Counter()
        self._lock = threading.Lock()

    def ensure_fresh(self):
        row = self.db.one("SELECT COUNT(*) AS n, MAX(updated_at) AS u FROM recipes")
        version = (row["n"], str(row["u"]))
        if version == self.version:
            return
        with self._lock:
            if version != self.version:
                self._load()
                self.version = version

    def _load(self):
        db = self.db
        tags = {}
        for t in db.all("SELECT recipe_id, kind, value FROM recipe_tags"):
            tags.setdefault(t["recipe_id"], {}).setdefault(t["kind"], set()).add(t["value"])
        slots = {}
        for i in db.all("SELECT recipe_id, display, match_spec FROM recipe_ingredients "
                        "WHERE is_optional = 0 AND match_spec <> '' ORDER BY recipe_id, position"):
            displays = i["display"].split(";")
            for n, spec in enumerate(i["match_spec"].split(";")):
                keys = [k for k in spec.split("|") if k]
                if keys:
                    shown = displays[n] if n < len(displays) and displays[n] else keys[0]
                    slots.setdefault(i["recipe_id"], []).append({"display": shown, "keys": keys})
        recipes, vocab = [], Counter()
        for r in db.all("SELECT * FROM recipes"):
            t = tags.get(r["id"], {})
            r["tags"] = t
            r["slots"] = slots.get(r["id"], [])
            r["allergen_all"] = t.get("allergen", set()) | t.get("allergen_may", set())
            r["name_key"] = name_key(r["name"])
            for s in r["slots"]:
                vocab[s["keys"][0]] += 1
            recipes.append(r)
        self.recipes = recipes
        self.by_id = {r["id"]: r for r in recipes}
        self.vocab = vocab


def _int_arg(args, name, default, lo, hi):
    raw = args.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except ValueError:
        raise BadRequest(f"'{name}' must be a number.")
    return max(lo, min(hi, value))


def parse_search_args(args):
    terms = [t.strip()[:60] for t in args.get("ingredients", "").split(",") if t.strip()][:MAX_TERMS]
    meal = args.get("meal", "").strip().lower()
    taste = args.get("taste", "").strip().lower()
    difficulty = args.get("difficulty", "").strip().lower()
    if meal and meal not in MEALS:
        raise BadRequest(f"Unknown meal type '{meal}'.")
    if taste and taste not in TASTES:
        raise BadRequest(f"Unknown taste '{taste}'.")
    if difficulty and difficulty not in DIFFICULTIES:
        raise BadRequest(f"Unknown difficulty '{difficulty}'.")
    allergens = [a.strip().lower() for a in args.get("allergens", "").split(",") if a.strip()]
    unknown = [a for a in allergens if a not in ALLERGEN_FILTERS]
    if unknown:  # never silently ignore an allergen the user asked to avoid
        raise BadRequest(f"Unknown allergen filter: {', '.join(unknown)}.")
    return {
        "terms": terms, "meal": meal, "taste": taste, "difficulty": difficulty, "allergens": allergens,
        "max_minutes": _int_arg(args, "max_minutes", None, 1, 100000),
        "q": name_key(args.get("q", "")),
        "limit": _int_arg(args, "limit", 9, 1, 30),
        "offset": _int_arg(args, "offset", 0, 0, 100000),
        "include_unverified": args.get("include_unverified", "") in ("1", "true", "yes"),
    }


def _order(values, canonical):
    return [v for v in canonical if v in values]


def make_card(r, saved_ids, match=None):
    t = r["tags"]
    allergens = [{"id": a, "label": ALLERGEN_LABELS.get(a, a), "level": "contains"} for a in sorted(t.get("allergen", ()))]
    allergens += [{"id": a, "label": ALLERGEN_LABELS.get(a, a), "level": "may"}
                  for a in sorted(t.get("allergen_may", ())) if a not in t.get("allergen", ())]
    return {
        "id": r["id"], "slug": r["slug"], "name": r["name"], "description": r["description"],
        "meal_course": r["meal_course"], "meals": _order(t.get("meal", ()), MEALS),
        "flavors": _order(t.get("flavor", ()), TASTES), "difficulty": r["difficulty"], "servings": r["servings"],
        "prep_minutes": r["prep_minutes"], "cook_minutes": r["cook_minutes"], "total_minutes": r["total_minutes"],
        "image": ("/" + r["image"]) if r["image"] else None,
        "allergens": allergens, "allergens_verified": bool(r["allergens_verified"]),
        "saved": r["id"] in saved_ids, "match": match,
    }


def _pantry_rank(item):
    """Cookable-now recipes first (using more of your ingredients is better); then
    recipes that use many of your ingredients while needing few extras. Tiny recipes
    that merely need little no longer outrank real dishes."""
    r, m = item
    have, missing = len(m["have"]), len(m["missing"])
    if m["percent"] == 100:
        return (0, -have, 0, r["name"])
    return (1, -(have - 0.75 * missing), -m["percent"], r["name"])


def run_search(index, p):
    excluded = set()
    for a in p["allergens"]:
        excluded.update(ALLERGEN_FILTERS[a])
    pantry = [k for term in p["terms"] for k in user_keys(term)]
    results = []
    for r in index.recipes:
        t = r["tags"]
        if p["meal"] and p["meal"] not in t.get("meal", ()):
            continue
        if p["taste"] and p["taste"] not in t.get("flavor", ()):
            continue
        if p["difficulty"] and r["difficulty"].lower() != p["difficulty"]:
            continue
        if p["max_minutes"] and (r["total_minutes"] is None or r["total_minutes"] > p["max_minutes"]):
            continue
        if p["q"] and p["q"] not in r["name_key"]:
            continue
        if excluded:
            if r["allergen_all"] & excluded:
                continue
            if not r["allergens_verified"] and not p["include_unverified"]:
                continue
        match = None
        if pantry:
            have, missing = [], []
            for slot in r["slots"]:
                ok = any(keys_match(sk, uk) for sk in slot["keys"] for uk in pantry)
                (have if ok else missing).append(slot["display"])
            required = len(r["slots"])
            if not have and required:
                continue  # nothing in common with the pantry
            percent = 100 if not required else round(100 * len(have) / required)
            match = {"have": have, "missing": missing, "required": required, "percent": percent}
        results.append((r, match))
    if pantry:
        results.sort(key=_pantry_rank)
    else:
        results.sort(key=lambda x: x[0]["name"])
    return pantry, results


def register_recipe_routes(app, db, login_required, error):
    index = RecipeIndex(db)
    app.extensions["recipe_index"] = index

    def saved_ids(user_id):
        return {row["recipe_id"] for row in db.all("SELECT recipe_id FROM saved_recipes WHERE user_id = %s", (user_id,))}

    @app.errorhandler(BadRequest)
    def bad_request(exc):
        return error(str(exc), 400)

    @app.get("/api/recipes/search")
    @login_required
    def search_recipes():
        p = parse_search_args(request.args)
        index.ensure_fresh()
        pantry, results = run_search(index, p)
        saved = saved_ids(g.user["id"])
        page = results[p["offset"]: p["offset"] + p["limit"]]
        unrecognised = [t for t in p["terms"]
                        if not any(keys_match(vk, uk) for uk in user_keys(t) for vk in index.vocab)]
        return jsonify({
            "total": len(results),
            "results": [make_card(r, saved, m) for r, m in page],
            "unrecognised": unrecognised,
            "allergen_filter_active": bool(p["allergens"]),
            "unverified_hidden": bool(p["allergens"]) and not p["include_unverified"],
        })

    @app.get("/api/recipes/<int:recipe_id>")
    @login_required
    def recipe_detail(recipe_id):
        index.ensure_fresh()
        r = index.by_id.get(recipe_id)
        if r is None:
            return error("Recipe not found.", 404)
        sections = []
        for i in db.all("SELECT section, raw, is_optional FROM recipe_ingredients WHERE recipe_id = %s ORDER BY position",
                        (recipe_id,)):
            if not sections or sections[-1]["section"] != i["section"]:
                sections.append({"section": i["section"], "items": []})
            sections[-1]["items"].append({"text": i["raw"], "optional": bool(i["is_optional"])})
        steps = [s["body"] for s in db.all("SELECT body FROM recipe_steps WHERE recipe_id = %s ORDER BY position", (recipe_id,))]
        card = make_card(r, saved_ids(g.user["id"]))
        card.update({"ingredients": sections, "steps": steps, "time_notes": r["time_notes"], "allergen_note": r["allergen_text"]})
        return jsonify({"recipe": card})

    @app.get("/api/saved")
    @login_required
    def list_saved():
        index.ensure_fresh()
        rows = db.all("SELECT recipe_id FROM saved_recipes WHERE user_id = %s ORDER BY created_at DESC, recipe_id DESC",
                      (g.user["id"],))
        cards = [make_card(index.by_id[x["recipe_id"]], {x["recipe_id"]}) for x in rows if x["recipe_id"] in index.by_id]
        return jsonify({"results": cards, "total": len(cards)})

    @app.put("/api/saved/<int:recipe_id>")
    @login_required
    def save_recipe(recipe_id):
        if not db.one("SELECT id FROM recipes WHERE id = %s", (recipe_id,)):
            return error("Recipe not found.", 404)
        try:
            db.execute("INSERT INTO saved_recipes (user_id, recipe_id, created_at) VALUES (%s, %s, %s)",
                       (g.user["id"], recipe_id, datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")))
            db.commit()
        except INTEGRITY_ERRORS:
            db.conn().rollback()  # already saved: that's fine
        return jsonify({"ok": True, "saved": True})

    @app.delete("/api/saved/<int:recipe_id>")
    @login_required
    def unsave_recipe(recipe_id):
        db.execute("DELETE FROM saved_recipes WHERE user_id = %s AND recipe_id = %s", (g.user["id"], recipe_id))
        db.commit()
        return jsonify({"ok": True, "saved": False})

    @app.get("/api/ingredients/suggest")
    @login_required
    def suggest_ingredients():
        index.ensure_fresh()
        q = clean_phrase(request.args.get("q", "")[:60])
        if not q:
            return jsonify({"suggestions": []})
        ranked = []
        for key, count in index.vocab.items():
            if key.startswith(q):
                rank = 0
            elif any(w.startswith(q) for w in key.split()):
                rank = 1
            elif q in key:
                rank = 2
            else:
                continue
            ranked.append((rank, -count, len(key), key))
        ranked.sort()
        return jsonify({"suggestions": [{"name": k, "count": -c} for _, c, _, k in ranked[:8]]})
