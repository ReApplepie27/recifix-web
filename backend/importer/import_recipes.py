"""Load the recipe spreadsheet (exported as CSV) into MySQL.

    python import_recipes.py path/to/recipes.csv            # import
    python import_recipes.py path/to/recipes.csv --dry-run  # just parse and write the report

Safe to re-run: recipes are matched by slug and updated in place (so saved
recipes keep working). A plain-text review report is written next to the CSV.
"""
import argparse
import csv
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from importer.normalize import (
    detect_allergen_sources, is_section_header, name_key, name_key_no_parens, parse_allergens,
    parse_courses, parse_difficulty, parse_flavors, parse_ingredient_line, parse_meal_times,
    parse_times, section_title, similarity, unique_slugs,
)

REQUIRED_COLUMNS = ["Recipe Name", "Short Description", "Flavor profiles", "Meal Course", "Meal Time",
                    "Cooking Time", "Difficulty", "Servings", "Allergens", "Ingredients", "Steps"]
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
DEFAULT_IMAGES_DIR = Path(__file__).resolve().parents[2] / "images" / "recipes"


def load_rows(csv_path):
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"CSV is missing expected columns: {', '.join(missing)}")
        return [r for r in reader if (r.get("Recipe Name") or "").strip()]


def _clean_text(value):
    return " ".join((value or "").split())


def build_recipe(row, slug, report):
    """Turn one CSV row into a clean recipe dict. Problems go into `report` (a dict of lists)."""
    name = _clean_text(row["Recipe Name"])
    warn = lambda kind, msg: report[kind].append(f"{name}: {msg}")

    courses = parse_courses(row["Meal Course"])
    if not courses:
        warn("courses", f"could not read Meal Course {row['Meal Course']!r}; using 'Main Course'")
        courses = ["Main Course"]
    meals, occasions = parse_meal_times(row["Meal Time"], courses)
    if not meals:
        warn("meals", f"no meal time found in {row['Meal Time']!r}")
    flavors = parse_flavors(row["Flavor profiles"])
    if not flavors:
        warn("flavors", f"no basic taste (sweet/savory/spicy/mild/tangy/sour) in {row['Flavor profiles']!r}")
    difficulty = parse_difficulty(row["Difficulty"])
    if not difficulty:
        warn("difficulty", f"unrecognised difficulty {row['Difficulty']!r}")

    try:
        servings = int(float(row["Servings"]))
    except (TypeError, ValueError):
        servings = 2
        warn("servings", f"bad servings {row['Servings']!r}; using 2")

    t = parse_times(row["Cooking Time"])
    if t["total"] is None:
        warn("times", "no readable time in Cooking Time cell")
    else:
        parts = (t["prep"] or 0) + (t["cook"] or 0)
        if t["total"] < parts:
            warn("times", f"overall time ({t['total']} min) is less than prep+cook ({parts} min)")

    # ---- ingredients
    ingredients, section = [], None
    for line in (row["Ingredients"] or "").splitlines():
        if not line.strip():
            continue
        if is_section_header(line):
            section = section_title(line)
            continue
        p = parse_ingredient_line(line)
        groups = [g for g in p["groups"] if not g["staple"]]
        if not p["groups"]:
            warn("ingredients", f"could not understand ingredient line {line.strip()!r}")
        if any(len(g["display"].split()) > 6 for g in groups):
            warn("long_ingredients", f"{line.strip()!r}")
        clean = lambda s: s.replace(";", ",").replace("|", "/")
        ingredients.append({
            "position": len(ingredients) + 1,
            "section": section,
            "raw": p["raw"][:500],
            "display": ";".join(clean(g["display"]) for g in groups)[:600],
            "spec": ";".join("|".join(clean(k) for k in g["keys"]) for g in groups)[:1000],
            "optional": int(p["optional"]),
            "staple": int(p["staple"]),
        })
    if not ingredients:
        warn("ingredients", "no ingredients found")

    # ---- steps
    steps = []
    for line in (row["Steps"] or "").splitlines():
        text = re.sub(r"^\s*\d+[.)]\s*", "", line).strip()
        if text:
            steps.append(text)
    if not steps:
        warn("steps", "no steps found")

    # ---- allergens: what the sheet says + what the ingredients suggest (conservative union)
    declared = parse_allergens(row["Allergens"])
    detected = detect_allergen_sources(i["raw"] for i in ingredients)
    contains = set(declared["contains"])
    may = set(declared["may"])
    undeclared = {a: src for a, src in detected.items() if a not in contains and a not in may}
    # pork/chicken/etc. are not detected from ingredients, so only compare real allergens
    may |= set(undeclared)
    verified = not declared["blank"]
    if declared["blank"]:
        warn("allergens_blank", f"Allergens cell is empty -> marked unverified; ingredients suggest: "
                                f"{', '.join(sorted(detected)) or 'nothing'}")
    elif undeclared:
        shown = "; ".join(f"{a} (from {src.lstrip('- ')!r})" for a, src in sorted(undeclared.items()))
        warn("allergens_mismatch", f"sheet says {_clean_text(row['Allergens'])!r} but ingredients suggest: {shown}")
    for token in declared["unparsed"]:
        warn("allergens_unparsed", f"note not understood: {token!r}")

    tags = ([("meal", m) for m in meals] + [("flavor", f) for f in flavors] + [("course", c) for c in courses]
            + [("occasion", o) for o in occasions] + [("allergen", a) for a in sorted(contains)]
            + [("allergen_may", a) for a in sorted(may)])

    return {
        "slug": slug, "name": name, "description": _clean_text(row["Short Description"]),
        "meal_course": courses[0], "difficulty": difficulty, "servings": servings,
        "prep": t["prep"], "cook": t["cook"], "total": t["total"], "time_notes": " · ".join(t["extras"])[:600],
        "allergen_text": _clean_text(row["Allergens"] if row["Allergens"] != "nan" else "")[:1000],
        "verified": int(verified), "tags": tags, "ingredients": ingredients, "steps": steps, "image": None,
    }


# --------------------------------------------------------------------------
# images
# --------------------------------------------------------------------------
def attach_images(recipes, images_dir, report):
    """Set recipe['image'] when <slug>.<ext> exists in images_dir."""
    images_dir = Path(images_dir)
    if not images_dir.is_dir():
        report["images"].append(f"image folder not found: {images_dir} (recipes will show a placeholder)")
        return
    by_stem = {p.stem.lower(): p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS}
    used = set()
    for r in recipes:
        p = by_stem.get(r["slug"])
        if p:
            r["image"] = f"images/recipes/{p.name}"
            used.add(p.stem.lower())
        else:
            report["no_image"].append(r["name"])
    for stem in sorted(set(by_stem) - used):
        report["unused_images"].append(by_stem[stem].name)


# --------------------------------------------------------------------------
# database
# --------------------------------------------------------------------------
def write_recipes(db, recipes):
    # A running server notices new data by watching MAX(updated_at), which only has 1-second
    # resolution, so make sure every import stamps a strictly later time than the previous one.
    now_dt = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    latest = db.one("SELECT MAX(updated_at) AS u FROM recipes")["u"]
    if latest is not None:
        if isinstance(latest, str):
            latest = datetime.strptime(latest[:19], "%Y-%m-%d %H:%M:%S")
        if now_dt <= latest:
            now_dt = latest + timedelta(seconds=1)
    now = now_dt.strftime("%Y-%m-%d %H:%M:%S")
    inserted = updated = 0
    for r in recipes:
        existing = db.one("SELECT id FROM recipes WHERE slug = %s", (r["slug"],))
        values = (r["name"], r["description"], r["meal_course"], r["difficulty"], r["servings"], r["prep"],
                  r["cook"], r["total"], r["time_notes"], r["allergen_text"], r["verified"], r["image"])
        if existing:
            rid = existing["id"]
            db.execute(
                "UPDATE recipes SET name=%s, description=%s, meal_course=%s, difficulty=%s, servings=%s, "
                "prep_minutes=%s, cook_minutes=%s, total_minutes=%s, time_notes=%s, allergen_text=%s, "
                "allergens_verified=%s, image=%s, updated_at=%s WHERE id=%s", values + (now, rid))
            for table in ("recipe_ingredients", "recipe_steps", "recipe_tags"):
                db.execute(f"DELETE FROM {table} WHERE recipe_id = %s", (rid,))
            updated += 1
        else:
            rid, _ = db.execute(
                "INSERT INTO recipes (slug, name, description, meal_course, difficulty, servings, prep_minutes, "
                "cook_minutes, total_minutes, time_notes, allergen_text, allergens_verified, image, created_at, "
                "updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (r["slug"],) + values + (now, now))
            inserted += 1
        db.executemany(
            "INSERT INTO recipe_ingredients (recipe_id, position, section, raw, display, match_spec, is_optional, "
            "is_staple) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            [(rid, i["position"], i["section"], i["raw"], i["display"], i["spec"], i["optional"], i["staple"])
             for i in r["ingredients"]])
        db.executemany("INSERT INTO recipe_steps (recipe_id, position, body) VALUES (%s,%s,%s)",
                       [(rid, n, text) for n, text in enumerate(r["steps"], 1)])
        db.executemany("INSERT INTO recipe_tags (recipe_id, kind, value) VALUES (%s,%s,%s)",
                       [(rid, k, v) for k, v in dict.fromkeys(r["tags"])])
    db.commit()
    return inserted, updated


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------
SECTIONS = [
    ("allergens_blank", "ALLERGENS CELL EMPTY (recipe is marked UNVERIFIED and hidden from allergen-filtered searches)"),
    ("allergens_mismatch", "ALLERGEN CHECK: ingredients suggest an allergen the sheet does not list (treated as 'may contain')"),
    ("allergens_unparsed", "ALLERGEN NOTES THE IMPORTER DID NOT UNDERSTAND (shown to users as written)"),
    ("ingredients", "INGREDIENT LINES TO REVIEW"),
    ("long_ingredients", "LONG INGREDIENT NAMES (check these were parsed sensibly)"),
    ("flavors", "NO BASIC TASTE FOUND"),
    ("meals", "NO MEAL TIME FOUND"),
    ("courses", "MEAL COURSE NOT UNDERSTOOD"),
    ("difficulty", "DIFFICULTY NOT UNDERSTOOD"),
    ("servings", "SERVINGS"),
    ("times", "COOKING TIME"),
    ("steps", "STEPS"),
    ("no_image", "RECIPES WITH NO IMAGE FILE"),
    ("unused_images", "IMAGE FILES THAT MATCH NO RECIPE"),
    ("images", "IMAGES"),
]


def write_report(path, recipes, report, stats):
    lines = ["RECIFIX RECIPE IMPORT REPORT", "=" * 60, ""]
    for key, value in stats.items():
        lines.append(f"{key}: {value}")
    lines.append("")
    for key, title in SECTIONS:
        items = report.get(key, [])
        lines += [f"{title}  [{len(items)}]", "-" * 60]
        lines += [f"  {x}" for x in items] or ["  none"]
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="recipes exported from Google Sheets as CSV")
    ap.add_argument("--images", default=str(DEFAULT_IMAGES_DIR), help="folder with prepared images (<slug>.jpg)")
    ap.add_argument("--report", help="where to write the review report (default: import_report.txt next to the CSV)")
    ap.add_argument("--dry-run", action="store_true", help="parse and report only; do not touch the database")
    args = ap.parse_args(argv)

    rows = load_rows(args.csv)
    slugs = unique_slugs([_clean_text(r["Recipe Name"]) for r in rows])
    report = {k: [] for k, _ in SECTIONS}
    recipes = [build_recipe(r, s, report) for r, s in zip(rows, slugs)]
    attach_images(recipes, args.images, report)

    stats = {
        "recipes read": len(recipes),
        "ingredient lines": sum(len(r["ingredients"]) for r in recipes),
        "steps": sum(len(r["steps"]) for r in recipes),
        "recipes with image": sum(1 for r in recipes if r["image"]),
        "allergens unverified": sum(1 for r in recipes if not r["verified"]),
    }
    if not args.dry_run:
        from app import create_app
        app = create_app()
        with app.app_context():
            ins, upd = write_recipes(app.extensions["db"], recipes)
        stats["inserted"], stats["updated"] = ins, upd

    report_path = args.report or Path(args.csv).with_name("import_report.txt")
    write_report(report_path, recipes, report, stats)

    print(("DRY RUN - nothing written to the database.\n" if args.dry_run else "") + "\n".join(f"{k}: {v}" for k, v in stats.items()))
    print(f"\nReview report: {report_path}")
    for key, title in SECTIONS:
        if report[key] and key not in ("images",):
            print(f"  {len(report[key]):4d}  {title.split('(')[0].strip()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
