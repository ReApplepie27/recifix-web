"""Resize and rename recipe photos so the site loads fast.

    python prepare_images.py --csv recipes.csv --source "D:/recipe-originals"

Reads originals named after the recipe (e.g. "Adobong Baboy.png"), and writes
web-sized JPEGs named by slug into ../images/recipes/. Near-matches are only
suggested in the report; they are never applied automatically.
"""
import argparse
import sys
from pathlib import Path

from importer.import_recipes import DEFAULT_IMAGES_DIR, IMAGE_EXTS, _clean_text, load_rows
from importer.normalize import name_key, name_key_no_parens, similarity, unique_slugs

MAX_SIDE = 1000
JPEG_QUALITY = 82
SUGGEST_THRESHOLD = 0.88


def match_files(names, files):
    """Return (matches {index: Path}, suggestions [(name, file, score)], unmatched [name], unused [Path])."""
    index = {}
    for f in files:
        index.setdefault(name_key(f.stem), f)
    index_np = {}
    for f in files:
        index_np.setdefault(name_key_no_parens(f.stem), f)
    matches, used, suggestions, unmatched = {}, set(), [], []
    for i, name in enumerate(names):
        f = index.get(name_key(name)) or index.get(name_key_no_parens(name)) \
            or index_np.get(name_key(name)) or index_np.get(name_key_no_parens(name))
        if f and f not in used:
            matches[i] = f
            used.add(f)
    for i, name in enumerate(names):
        if i in matches:
            continue
        best = max(((similarity(name_key(name), name_key(f.stem)), f) for f in files if f not in used),
                   default=(0, None), key=lambda x: x[0])
        if best[1] is not None and best[0] >= SUGGEST_THRESHOLD:
            suggestions.append((name, best[1], round(best[0], 2)))
        unmatched.append(name)
    return matches, suggestions, unmatched, [f for f in files if f not in used]


def convert(src: Path, dest: Path):
    from PIL import Image  # imported here so the rest of the tooling works without Pillow
    with Image.open(src) as img:
        img = img.convert("RGBA") if img.mode in ("P", "LA", "RGBA") else img.convert("RGB")
        if img.mode == "RGBA":
            background = Image.new("RGB", img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1])
            img = background
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        dest.parent.mkdir(parents=True, exist_ok=True)
        img.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True, help="the recipes CSV (used for recipe names)")
    ap.add_argument("--source", required=True, help="folder with the full-size original photos")
    ap.add_argument("--out", default=str(DEFAULT_IMAGES_DIR), help="where to write the web-sized JPEGs")
    ap.add_argument("--force", action="store_true", help="re-create images that already exist")
    args = ap.parse_args(argv)

    rows = load_rows(args.csv)
    names = [_clean_text(r["Recipe Name"]) for r in rows]
    slugs = unique_slugs(names)
    source = Path(args.source)
    if not source.is_dir():
        raise SystemExit(f"Source folder not found: {source}")
    files = sorted(p for p in source.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    matches, suggestions, unmatched, unused = match_files(names, files)

    out = Path(args.out)
    done = skipped = failed = 0
    for i, f in matches.items():
        dest = out / f"{slugs[i]}.jpg"
        if dest.exists() and not args.force:
            skipped += 1
            continue
        try:
            convert(f, dest)
            done += 1
        except Exception as exc:  # corrupt/unsupported file: keep going
            failed += 1
            print(f"  could not convert {f.name}: {exc}")

    print(f"Recipes: {len(names)} | image files found: {len(files)} | matched: {len(matches)}")
    print(f"Converted: {done} | already existed: {skipped} | failed: {failed}")
    print(f"Recipes without an image: {len(unmatched)}")
    for name in unmatched[:15]:
        print(f"   - {name}")
    if len(unmatched) > 15:
        print(f"   ... and {len(unmatched) - 15} more")
    if suggestions:
        print("\nPossible near-matches (NOT applied; rename the file if they are right):")
        for name, f, score in suggestions:
            print(f"   {name!r}  <-  {f.name!r}  (similarity {score})")
    if unused:
        print(f"\nImage files that match no recipe: {len(unused)}")
        for f in unused[:15]:
            print(f"   - {f.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
