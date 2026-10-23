"""Parsing and normalisation helpers for the recipe importer.

Pure functions only (no database, no Flask) so they are easy to test.
The same ingredient normaliser is used at import time and when matching
what a user types into the pantry, so "Tomatoes" and "1 medium tomato, diced"
end up with the same key.
"""
import re
import unicodedata
from functools import lru_cache
from difflib import SequenceMatcher

# --------------------------------------------------------------------------
# generic text helpers
# --------------------------------------------------------------------------
_FRACTIONS = {"½": " 1/2", "¼": " 1/4", "¾": " 3/4", "⅓": " 1/3", "⅔": " 2/3", "⅛": " 1/8"}


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def slugify(text: str) -> str:
    text = strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "recipe"


def name_key(text: str) -> str:
    """Loose key for matching recipe names to image file names."""
    text = strip_accents(text).lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def name_key_no_parens(text: str) -> str:
    return name_key(re.sub(r"\([^)]*\)", " ", text))


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


# --------------------------------------------------------------------------
# categorical columns
# --------------------------------------------------------------------------
_COURSE_KEYWORDS = [
    ("main", "Main Course"),
    ("soup", "Soup"),
    ("appetizer", "Appetizer"),
    ("pulutan", "Appetizer"),
    ("side", "Side Dish"),
    ("dessert", "Dessert"),
    ("breakfast", "Breakfast"),
    ("snack", "Snack"),
    ("salad", "Salad"),
    ("sauce", "Sauce/Condiment"),
    ("condiment", "Sauce/Condiment"),
    ("beverage", "Beverage"),
    ("street", "Street Food"),
]


def parse_courses(text) -> list:
    out = []
    for token in re.split(r"[/,]", str(text or "")):
        token = token.strip().lower()
        for key, label in _COURSE_KEYWORDS:
            if key in token:
                if label not in out:
                    out.append(label)
                break
    return out


_MEAL_WORDS = {
    "breakfast": "breakfast",
    "lunch": "lunch",
    "dinner": "dinner",
    "snack": "snack",
    "merienda": "snack",
    "anytime": "snack",
    "dessert": "dessert",
}
_OCCASION_WORDS = {"party": "party", "fiesta": "fiesta", "christmas": "christmas", "pulutan": "pulutan", "late-night": "late-night"}


def parse_meal_times(text, courses=()):
    """Return (meal_times, occasions) as lists of canonical lowercase words."""
    words = re.findall(r"[a-z\-]+", str(text or "").lower())
    meals, occasions = [], []
    for w in words:
        if w in _MEAL_WORDS and _MEAL_WORDS[w] not in meals:
            meals.append(_MEAL_WORDS[w])
        elif w in _OCCASION_WORDS and _OCCASION_WORDS[w] not in occasions:
            occasions.append(_OCCASION_WORDS[w])
    if "Dessert" in courses and "dessert" not in meals:
        meals.append("dessert")
    return meals, occasions


_TASTES = ["spicy", "savory", "sweet", "mild", "tangy", "sour"]


def parse_flavors(text) -> list:
    low = str(text or "").lower()
    return [t for t in _TASTES if re.search(rf"\b{t}\b", low)]


def parse_difficulty(text) -> str:
    t = str(text or "").strip().lower()
    return t.capitalize() if t in ("easy", "medium", "hard") else ""


# --------------------------------------------------------------------------
# cooking time
# --------------------------------------------------------------------------
_UNIT_MIN = {"day": 1440, "days": 1440, "hour": 60, "hours": 60, "hr": 60, "hrs": 60,
             "minute": 1, "minutes": 1, "min": 1, "mins": 1}


def parse_minutes(value):
    """'1 hour 30 minutes' -> 90, '2–3 days' -> 4320 (upper bound), None if no number."""
    text = str(value or "").lower()
    for sym, rep in _FRACTIONS.items():
        text = text.replace(sym, rep)
    total, found = 0.0, False
    for m in re.finditer(r"(\d+(?:\.\d+)?)(?:\s*(?:–|-|to)\s*(\d+(?:\.\d+)?))?\s*(days?|hours?|hrs?|minutes?|mins?)\b", text):
        number = float(m.group(2) or m.group(1))
        total += number * _UNIT_MIN[m.group(3)]
        found = True
    return int(round(total)) if found else None


def parse_times(cell) -> dict:
    """Parse the multi-line 'Cooking Time' cell."""
    result = {"prep": None, "cook": None, "total": None, "extras": []}
    parts = []
    for line in str(cell or "").splitlines():
        if ":" not in line:
            continue
        label, value = (s.strip() for s in line.split(":", 1))
        minutes = parse_minutes(value)
        low = label.lower()
        if low == "preparation time":
            result["prep"] = minutes
        elif low == "cooking time":
            result["cook"] = minutes
        elif low == "overall time":
            result["total"] = minutes
        else:
            result["extras"].append(f"{label}: {value}")
        if minutes is not None and low != "overall time":
            parts.append(minutes)
    if result["total"] is None and parts:
        result["total"] = sum(parts)
    return result


# --------------------------------------------------------------------------
# allergens
# --------------------------------------------------------------------------
_ALLERGEN_PATTERNS = [
    ("fish", r"\bfish\b|anchov|\bpatis\b"),
    ("shellfish", r"shellfish|shrimp|prawn|crab|lobster|alamang"),
    ("mollusk", r"mollus|squid|oyster|mussel|clam|scallop"),
    ("egg", r"\beggs?\b|mayonnaise"),
    ("milk", r"\bmilk\b|dairy|butter|cheese|cream|margarine"),
    ("wheat", r"wheat|gluten|flour"),
    ("soy", r"\bsoy"),
    ("peanut", r"peanut"),
    ("tree_nut", r"tree nut|cashew|\bpili\b|almond|walnut"),
    ("sesame", r"sesame"),
    ("coconut", r"coconut"),
    ("pork", r"\bpork\b"),
    ("chicken", r"\bchicken\b"),
    ("mustard", r"mustard"),
    ("sulfite", r"sulfite"),
    ("mung_bean", r"mung bean"),
]
_CONDITIONAL = re.compile(r"\b(if|possible|possibly|depend\w*|optional|may|might|brand|check|varies)\b")
_NONE = re.compile(r"^\s*none\b|\bno (major|common)\b|\bnone of\b")


def parse_allergens(text) -> dict:
    """Parse the free-text Allergens cell.

    Returns {"blank": bool, "none": bool, "contains": set, "may": set, "unparsed": [str]}
    'may' holds conditional mentions such as "Fish (if fish sauce is used)".
    """
    raw = "" if text is None or str(text).lower() == "nan" else str(text).strip()
    out = {"blank": not raw, "none": False, "contains": set(), "may": set(), "unparsed": []}
    if not raw:
        return out
    if _NONE.search(raw.lower()):
        out["none"] = True
        return out
    for token in re.split(r"[,;/]|\band\b", raw):
        low = token.strip().lower()
        if not low:
            continue
        found = [name for name, pat in _ALLERGEN_PATTERNS if re.search(pat, low)]
        if not found:
            out["unparsed"].append(token.strip())
            continue
        bucket = "may" if _CONDITIONAL.search(low) else "contains"
        out[bucket].update(found)
    out["may"] -= out["contains"]
    return out


# What each pill on the dashboard excludes. Deliberately conservative.
ALLERGEN_FILTERS = {
    "nuts": ["peanut", "tree_nut"],
    "dairy": ["milk"],
    "eggs": ["egg"],
    "seafood": ["fish", "shellfish", "mollusk"],
    "gluten": ["wheat"],
    "soy": ["soy"],
    "shellfish": ["shellfish", "mollusk"],
    "sesame": ["sesame"],
}

# --------------------------------------------------------------------------
# ingredients
# --------------------------------------------------------------------------
_UNITS = (
    r"g|kg|mg|ml|l|cups?|tbsps?|tsps?|tablespoons?|teaspoons?|oz|ounces?|lbs?|pounds?|kilograms?|grams?|"
    r"liters?|litres?|milliliters?|pieces?|pcs?|cloves?|cans?|packs?|packets?|bunch(?:es)?|heads?|stalks?|"
    r"sticks?|slices?|sheets?|bundles?|thumbs?|strips?|sprigs?|pinch(?:es)?|dash(?:es)?|handfuls?|bottles?|"
    r"sachets?|bars?|fillets?|wedges?|bulbs?|knobs?|inch(?:es)?|cm|loaf|loaves|sets?|jars?|boxes?|tins?|"
    r"links?|pods?|ears?|rolls?|bags?|balls?|slabs?|kilos?|packages?|pouch(?:es)?"
)
_QTY = re.compile(
    r"^(?:about\s+|around\s+|approximately\s+|roughly\s+)?"
    r"(?:\d+\s+\d+/\d+|\d+/\d+|\d*\.\d+|\d+)(?:\s*(?:-|–|to)\s*(?:\d+\s+\d+/\d+|\d+/\d+|\d*\.\d+|\d+))?\s*"
    r"|^(?:a|an|one|half|some)\s+(?=(?:small\s+|large\s+|big\s+|little\s+)?(?:" + _UNITS + r")\b)",
    re.I,
)
_UNIT = re.compile(r"^(?:" + _UNITS + r")\b(?:-sized)?(?:\s+of)?\s*", re.I)
_DESCRIPTORS = re.compile(
    r"^(?:(?:small|medium|large|big|extra|thick|thin|fresh|freshly|ripe|raw|whole|boneless|skinless|cooked|"
    r"uncooked|dried|dry|frozen|canned|peeled|chopped|minced|diced|sliced|crushed|grated|shredded|cubed|"
    r"rinsed|washed|firm|young|lean|plain|good|quality|heaping|level|packed|hard-boiled|boiled|steamed|"
    r"toasted|roasted|finely|roughly|coarsely|optional|soft|hot|cold|warm|day-old|leftover|bite-sized|"
    r"medium-sized|large-sized|small-sized|pre-cooked|precooked|sweet-ripe|melted|softened|beaten|unsalted|"
    r"sweetened|granulated|lukewarm|chilled|crispy|ground-up|thinly|little)\s+)+",
    re.I,
)
_TRAILING = re.compile(r"\s+(?:cloves?|stalks?|sprigs?|pieces?|slices?|wedges?|heads?|bulbs?|strips?|rings?|florets?)$", re.I)
_CUT_AT = re.compile(r"\s+(?:for|to|from|until|about|if|plus|as needed|or more|per|with|mixed|mixed with|combined|dissolved|soaked)\b.*$", re.I)
_OPTIONAL = re.compile(
    r"\boptional\b|\bfor (?:serving|garnish|garnishing|dipping|topping|sprinkling|dusting|brushing|greasing|"
    r"drizzling|decoration)\b|\bto (?:serve|garnish)\b|\bon the side\b|\bfor the table\b",
    re.I,
)

# Atomic multi-word ingredients (matched as a single token so "milk" != "coconut milk").
COMPOUNDS = [
    "coconut milk", "coconut cream", "coconut oil", "coconut vinegar", "coconut sugar", "coconut water",
    "rice flour", "glutinous rice flour", "sweet rice flour", "glutinous rice", "rice vinegar", "rice wine",
    "cane vinegar", "palm vinegar", "spiced vinegar", "white vinegar", "peanut butter", "sweet potato",
    "bell pepper", "black pepper", "green pepper", "bay leaf", "banana leaf", "fish sauce", "soy sauce",
    "oyster sauce", "tomato sauce", "tomato paste", "hot sauce", "bean sprout", "green onion", "brown sugar",
    "white sugar", "evaporated milk", "condensed milk", "bitter melon", "water spinach", "string bean",
    "green bean", "bok choy", "sesame oil", "cooking oil", "vegetable oil", "olive oil", "corn starch",
    "baking powder", "baking soda", "shrimp paste", "fish paste", "chicken broth", "beef broth", "pork broth",
    "chicken stock", "beef stock", "egg noodle",
    "ice cream", "sour cream", "cream cheese", "bread crumb", "green papaya", "unripe papaya", "ube halaya",
    "garlic powder", "onion powder", "chili powder", "black bean", "mung bean", "kidney bean", "all purpose flour", "cassava flour", "ginger root",
]
_COMPOUND_TOKENS = {c: c.replace(" ", "_") for c in sorted(COMPOUNDS, key=len, reverse=True)}

ALIASES = {
    "sibuyas": "onion", "bawang": "garlic", "bawang na puti": "garlic", "luya": "ginger",
    "kamatis": "tomato", "patatas": "potato", "karot": "carrot", "toyo": "soy sauce", "patis": "fish sauce",
    "suka": "vinegar", "talong": "eggplant", "ampalaya": "bitter melon", "sitaw": "string bean",
    "kangkong": "water spinach", "gata": "coconut milk", "baboy": "pork", "manok": "chicken", "baka": "beef",
    "itlog": "egg", "hipon": "shrimp", "prawn": "shrimp", "pusit": "squid", "asukal": "sugar", "asin": "salt",
    "paminta": "pepper", "kalabasa": "squash", "pechay": "bok choy", "petsay": "bok choy", "pak choi": "bok choy",
    "scallion": "green onion", "spring onion": "green onion", "onion leek": "green onion",
    "ground black pepper": "black pepper", "peppercorn": "black pepper", "whole peppercorn": "black pepper",
    "black peppercorn": "black pepper", "pepper": "black pepper", "chilli": "chili", "chile": "chili",
    "chilies": "chili", "capsicum": "bell pepper", "cornstarch": "corn starch", "breadcrumb": "bread crumb",
    "panko": "bread crumb", "all purpose flour": "flour", "plain flour": "flour", "wheat flour": "flour",
    "vegetable oil": "cooking oil", "oil": "cooking oil", "canola oil": "cooking oil",
    "bay leaf": "bay leaf", "laurel": "bay leaf", "dahon ng laurel": "bay leaf",
    "siling labuyo": "chili", "siling haba": "long chili", "sayote": "chayote", "taro": "gabi", "labanos": "radish",
    "labano": "radish", "lemon grass": "lemongrass", "tanglad": "lemongrass", "lard": "pork fat",
}

STAPLES = {"salt", "black pepper", "water", "cooking oil", "ice"}
GENERIC = {"sauce", "oil", "paste", "powder", "leaf", "juice", "cube", "seed", "stock", "broth", "flour",
           "green", "red", "white", "black", "yellow", "ground", "cooked", "fresh", "pepper", "water", "salt"}
_KEEP_S = {"molasses", "asparagus", "hummus", "couscous", "citrus", "swiss", "watercress", "grits", "lemongrass",
           "cheese", "rice", "juice", "glass", "bass", "tapas", "gas", "mass", "less", "swiss", "peas", "kimchis"}


_IRREGULAR = {"chilies": "chili", "leaves": "leaf", "loaves": "loaf", "knives": "knife", "halves": "half"}


def singular(word: str) -> str:
    if word in _IRREGULAR:
        return _IRREGULAR[word]
    if word in _KEEP_S or len(word) <= 3:
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("oes"):
        return word[:-2]
    if word.endswith(("ss", "us", "is")):
        return word
    if word.endswith("ches") or word.endswith("shes") or word.endswith("xes"):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def _clean_words(text: str) -> list:
    text = strip_accents(text.lower())
    text = re.sub(r"[^a-z0-9\s/-]", " ", text).replace("-", " ").replace("/", " ")
    return text.split()


def _phrase(text: str) -> str:
    return " ".join(singular(t) for t in _clean_words(text))


def canonical(phrase: str) -> str:
    """Normalise a bare ingredient phrase (no quantity) to its matching key."""
    raw = " ".join(_clean_words(phrase))
    if raw in ALIASES:                      # e.g. "sibuyas" (checked before plural stripping)
        return ALIASES[raw]
    p = _phrase(phrase)
    if p in ALIASES:
        return ALIASES[p]
    for src, dst in sorted(ALIASES.items(), key=lambda kv: -len(kv[0])):
        if " " in src and p.endswith(" " + src):
            p = p[: -len(src)] + dst
    return p


@lru_cache(maxsize=None)
def tokens(key: str) -> frozenset:
    """Tokens for matching, with atomic compounds kept together."""
    k = " " + key + " "
    for comp, joined in _COMPOUND_TOKENS.items():
        k = k.replace(" " + comp + " ", " " + joined + " ")
    return frozenset(k.split())


def keys_match(a: str, b: str) -> bool:
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    small, big = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    if small <= big:
        return not small <= GENERIC
    return False


_TRAILING_WEIGHT = re.compile(r"\s+\d+(?:\.\d+)?\s*(?:g|kg|ml|oz|lb)$", re.I)
_NO_SPLIT = re.compile(r"sweet and sour", re.I)
_BAD_PAREN = re.compile(r"^(?:for|reserve|optional|about|if|see|such|e\.g|plus|long|thin|brand|or|depending|use|any)\b|\d", re.I)


def _prepare(text: str) -> str:
    """Strip bullet, fractions, parentheses, prep notes (after comma) and 'for/with/mixed ...' tails."""
    t = text.strip().lstrip("-•* ").strip()
    t = re.sub(r"^[A-Za-z][A-Za-z ]{0,24}:\s*(?=\S)", "", t)   # "Topping: 1/4 cup milk" -> "1/4 cup milk"
    for sym, rep in _FRACTIONS.items():
        t = t.replace(sym, rep)
    t = re.sub(r"\([^)]*\)", " ", t)
    t = t.split(",")[0]
    t = _CUT_AT.sub("", t)
    return re.sub(r"\s+", " ", t).strip()


def _strip_leading(t: str) -> str:
    """Remove quantity, unit and descriptor words from the front of a fragment."""
    t = _TRAILING_WEIGHT.sub("", t.strip())
    for _ in range(3):
        t = _QTY.sub("", t).strip()
        t = _UNIT.sub("", t).strip()
        t = _DESCRIPTORS.sub("", t).strip()
    t = _TRAILING.sub("", t).strip()
    t = re.sub(r"^(?:of|the)\s+", "", t).strip()
    return t.lower().rstrip(".:")


def clean_phrase(text: str) -> str:
    """Readable lowercase ingredient name from a line or something the user typed."""
    return _strip_leading(_prepare(text))


def _alternatives(phrase: str) -> list:
    alts = [a.strip() for a in re.split(r"\s+or\s+", phrase) if a.strip()]
    # "spinach or malunggay leaves" -> "spinach leaves" | "malunggay leaves"
    if len(alts) == 2 and len(alts[0].split()) == 1 and len(alts[1].split()) >= 2 and canonical(alts[0]) not in STAPLES:
        alts[0] = alts[0] + " " + alts[1].split()[-1]
    return alts


def _group(phrase: str):
    keys = []
    for alt in _alternatives(phrase):
        k = canonical(alt)
        if k and k not in keys:
            keys.append(k)
    if not keys:
        return None
    return {"display": phrase, "keys": keys, "staple": any(k in STAPLES for k in keys)}


def parse_ingredient_line(line: str) -> dict:
    """Parse one '- 1 medium potato, diced' line (not a section header).

    Returns {"raw", "optional", "staple", "groups": [{"display", "keys", "staple"}]}.
    Several groups appear when a line lists more than one ingredient ("soy sauce and calamansi")
    - all are needed. Alternatives within a group ("spinach or malunggay") - any one is enough.
    """
    raw = line.strip().lstrip("-•* ").strip()
    optional = bool(_OPTIONAL.search(raw))
    prepared = _prepare(raw)
    parts = [prepared] if _NO_SPLIT.search(prepared) else re.split(r"\s+and\s+|\s*&\s*|\s*\+\s*", prepared)
    groups = []
    for part in parts:
        g = _group(_strip_leading(part))
        if g:
            groups.append(g)
    # local-name synonyms in parentheses, e.g. "patis (fish sauce)", "pork belly (liempo)"
    if len(groups) == 1:
        for term in re.findall(r"\(([^)]*)\)", raw):
            term = term.strip()
            if not term or _BAD_PAREN.search(term) or len(term.split()) > 3:
                continue
            k = canonical(clean_phrase(term))
            if k and k not in groups[0]["keys"]:
                groups[0]["keys"].append(k)
    return {"raw": raw, "optional": optional, "groups": groups, "staple": bool(groups) and all(g["staple"] for g in groups)}


def is_section_header(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if not s.startswith("-"):
        return True
    return s.lstrip("- ").rstrip().endswith(":")


def section_title(line: str) -> str:
    s = line.strip().lstrip("- ").rstrip(":").strip()
    s = re.sub(r"^for the\s+", "", s, flags=re.I)
    return s.title() if s.isupper() else s[:1].upper() + s[1:]


def user_keys(text: str) -> list:
    """Keys for something the user typed into the pantry (may include quantity)."""
    phrase = clean_phrase(text)
    if not phrase:
        return []
    out = []
    for alt in re.split(r"\s+or\s+", phrase):
        k = canonical(alt)
        if k and k not in out:
            out.append(k)
    return out


# --------------------------------------------------------------------------
# allergens detected from ingredient text (cross-check for the Allergens column)
# --------------------------------------------------------------------------
_FLOUR_NOT_WHEAT = re.compile(r"\b(?:rice|glutinous|sweet rice|cassava|tapioca|corn|potato|coconut|mung bean|almond|mochiko) flour\b")
_DAIRY_NOT = re.compile(r"coconut (?:milk|cream)|peanut butter|cocoa butter|cream of tartar|butter bean|kakang gata|ice cream cone")
_DETECT = [
    ("egg", r"\beggs?\b|\byolk|mayonnaise|\bmayo\b|itlog|salted egg"),
    ("milk", r"\bmilk\b|\bbutter\b|cheese|\bcream\b|margarine|evaporada|condensada|yogurt|\bghee\b|whipped topping"),
    ("soy", r"soy|\btoyo\b|tofu|tokwa|\btaho\b|\bmiso\b|tausi|fermented black bean|hoisin|oyster sauce|worcestershire|knorr|liquid seasoning|maggi"),
    ("wheat", r"soy sauce|\btoyo\b|\bbread\b|bread ?crumb|panko|noodle|pancit|canton|\bmiki\b|macaroni|spaghetti|pasta|lasagna|wrapper|"
              r"pandesal|biscuit|cracker|\bwheat\b|hoisin|oyster sauce|worcestershire|\bflour\b|batter|cake mix|\bsiopao|\bsiomai"),
    ("fish", r"\bfish\b|patis|bagoong(?! alamang| shrimp)|bagoong isda|tilapia|bangus|milkfish|\btuna\b|sardine|galunggong|\bdilis\b|anchov|\btuyo\b|\bdaing\b|salmon|"
             r"tinapa|mackerel|lapu|tanigue|hasa|\bdorado\b|\bpampano\b|\bsapsap\b|\bbalao\b|\bhalang\b"),
    ("shellfish", r"shrimp|prawn|hipon|alamang|bagoong(?! isda)(?!.*\bfish\b)|\bcrab|alimango|alimasag|lobster|crayfish|\bebi\b|\blobster"),
    ("mollusk", r"squid|pusit|mussel|tahong|oyster|talaba|clam|halaan|scallop|kuhol|octopus|abalone|\bsnail"),
    ("peanut", r"peanut|\bmani\b"),
    ("tree_nut", r"cashew|\bpili\b|almond|walnut|pistachio|hazelnut|macadamia|pecan|tree nut"),
    ("sesame", r"sesame|\blinga\b|tahini"),
    ("coconut", r"coconut|\bgata\b|\bbuko\b|macapuno|\blatik\b|nata de coco|kakang"),
    ("mustard", r"\bmustard\b"),
]


def detect_allergen_sources(ingredient_texts) -> dict:
    """{allergen: first ingredient line that suggests it}"""
    found = {}
    for text in ingredient_texts:
        t = strip_accents(text.lower())
        t = _FLOUR_NOT_WHEAT.sub(" ", t)
        t_dairy = _DAIRY_NOT.sub(" ", t)
        for name, pat in _DETECT:
            target = t_dairy if name == "milk" else t
            if name not in found and re.search(pat, target):
                found[name] = text.strip()
    return found


def detect_allergens(ingredient_texts) -> set:
    return set(detect_allergen_sources(ingredient_texts))


def unique_slugs(names) -> list:
    """Stable, unique URL slugs for a list of recipe names (same order)."""
    seen, out = {}, []
    for name in names:
        base = slugify(name)[:110]
        seen[base] = seen.get(base, 0) + 1
        out.append(base if seen[base] == 1 else f"{base}-{seen[base]}")
    return out
