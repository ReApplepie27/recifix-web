import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.pop("SMTP_HOST", None)

from app import create_app  # noqa: E402
from importer import import_recipes as imp  # noqa: E402
from importer.images import convert, match_files  # noqa: E402

COLS = ["Image", "Recipe Name", "Short Description", "Flavor profiles", "Meal Course", "Meal Time", "Cooking Time",
        "Difficulty", "Servings", "Allergens", "Ingredients", "Steps"]


def row(name, ingredients, allergens="None", flavors="Savory", course="Main Dish", meal="Lunch/Dinner",
        time="Preparation Time: 10 minutes\nCooking Time: 20 minutes\nOverall Time: 30 minutes", difficulty="Easy"):
    return {"Image": "", "Recipe Name": name, "Short Description": f"{name} description.", "Flavor profiles": flavors,
            "Meal Course": course, "Meal Time": meal, "Cooking Time": time, "Difficulty": difficulty, "Servings": "2",
            "Allergens": allergens, "Ingredients": "\n".join("- " + i for i in ingredients),
            "Steps": "1. Prep everything.\n2. Cook it.\n3. Serve."}


ROWS = [
    row("Adobong Baboy", ["500 g pork belly, cubed", "1/4 cup soy sauce", "1/4 cup vinegar", "4 cloves garlic", "2 bay leaves",
                          "Salt and pepper to taste", "1 tbsp cooking oil"], allergens="Soy"),
    row("Tortang Talong", ["2 eggplants", "2 eggs", "1 tbsp cooking oil", "Salt to taste"], allergens="Egg", flavors="Mild",
        meal="Breakfast, Lunch"),
    row("Ginataang Tilapia", ["2 tilapia, cleaned", "1 cup coconut milk", "1 thumb ginger", "For the Topping:", "2 long green chilies",
                              "calamansi, for serving"], allergens="Fish", flavors="Savory, Spicy"),
    row("Mystery Stew", ["300 g beef", "2 tbsp butter", "1 onion"], allergens="", flavors="Savory"),
    row("Leche Flan", ["6 egg yolks", "1 can condensed milk", "1/2 cup sugar"], allergens="Egg, Dairy", flavors="Sweet",
        course="Dessert", meal="Dessert", difficulty="Medium",
        time="Preparation Time: 15 minutes\nCooking Time: 45 minutes\nChilling Time: 2 hours\nOverall Time: 3 hours"),
    row("Bagoong Rice", ["2 cups cooked rice", "2 tbsp bagoong alamang (shrimp paste)", "1 egg"], allergens="Shellfish"),
]


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({"TESTING": True, "SECRET_KEY": "k", "DATABASE_URL": f"sqlite:///{self.tmp.name}/t.db"})
        self.db = self.app.extensions["db"]
        with self.app.app_context():
            self.db.init_schema()
            self.report = {k: [] for k, _ in imp.SECTIONS}
            slugs = imp.unique_slugs([r["Recipe Name"] for r in ROWS])
            self.recipes = [imp.build_recipe(r, s, self.report) for r, s in zip(ROWS, slugs)]
            imp.write_recipes(self.db, self.recipes)
        self.client = self.app.test_client()
        self.client.post("/api/auth/signup", json={"fullname": "T", "email": "t@e.co", "password": "password1"})

    def tearDown(self):
        self.tmp.cleanup()

    def search(self, **params):
        r = self.client.get("/api/recipes/search", query_string=params)
        self.assertEqual(r.status_code, 200, r.json)
        return r.json

    def names(self, **params):
        return [x["name"] for x in self.search(**params)["results"]]

    def rid(self, name):
        return next(r["id"] for r in self.search(limit=30)["results"] if r["name"] == name)


class ImportTests(ApiTestCase):
    def test_everything_is_stored(self):
        with self.app.app_context():
            self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM recipes")["n"], 6)
            self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM recipe_steps")["n"], 18)
        detail = self.client.get(f"/api/recipes/{self.rid('Ginataang Tilapia')}").json["recipe"]
        self.assertEqual([s["section"] for s in detail["ingredients"]], [None, "Topping"])
        self.assertEqual(len(detail["steps"]), 3)
        self.assertEqual(detail["steps"][0], "Prep everything.")          # numbering stripped

    def test_times_and_tags(self):
        flan = self.client.get(f"/api/recipes/{self.rid('Leche Flan')}").json["recipe"]
        self.assertEqual((flan["prep_minutes"], flan["cook_minutes"], flan["total_minutes"]), (15, 45, 180))
        self.assertEqual(flan["time_notes"], "Chilling Time: 2 hours")
        self.assertEqual(flan["meals"], ["dessert"])
        tilapia = self.search(q="tilapia")["results"][0]
        self.assertEqual(tilapia["flavors"], ["spicy", "savory"])

    def test_reimport_updates_in_place_and_keeps_saved(self):
        rid = self.rid("Adobong Baboy")
        self.client.put(f"/api/saved/{rid}")
        with self.app.app_context():
            self.recipes[0]["description"] = "Changed."
            inserted, updated = imp.write_recipes(self.db, self.recipes)
            self.assertEqual((inserted, updated), (0, 6))
            self.assertEqual(self.db.one("SELECT COUNT(*) AS n FROM recipe_ingredients")["n"],
                             sum(len(r["ingredients"]) for r in self.recipes))
        saved = self.client.get("/api/saved").json["results"]
        self.assertEqual([s["id"] for s in saved], [rid])
        self.assertEqual(saved[0]["description"], "Changed.")             # index reloaded after import

    def test_report_flags_allergen_gaps(self):
        mismatches = "\n".join(self.report["allergens_mismatch"])
        self.assertIn("Adobong Baboy", mismatches)                          # soy sauce -> wheat not listed
        self.assertTrue(any("Mystery Stew" in x for x in self.report["allergens_blank"]))
        self.assertFalse(any("Tortang Talong" in x and "egg " in x.lower() for x in self.report["allergens_mismatch"]))


class SearchTests(ApiTestCase):
    def test_requires_login(self):
        anon = self.app.test_client()
        self.assertEqual(anon.get("/api/recipes/search").status_code, 401)
        self.assertEqual(anon.get("/api/saved").status_code, 401)
        self.assertEqual(anon.get("/api/ingredients/suggest?q=po").status_code, 401)

    def test_pantry_matching_and_ranking(self):
        d = self.search(ingredients="pork belly, garlic, vinegar, soy sauce, bay leaf")
        top = d["results"][0]
        self.assertEqual(top["name"], "Adobong Baboy")
        self.assertEqual(top["match"]["percent"], 100)                      # salt/pepper/oil are assumed staples
        self.assertEqual(top["match"]["missing"], [])
        self.assertNotIn("Leche Flan", [x["name"] for x in d["results"]])   # nothing in common -> excluded

    def test_partial_match_lists_missing_items(self):
        d = self.search(ingredients="tilapia")
        m = d["results"][0]["match"]
        self.assertEqual(d["results"][0]["name"], "Ginataang Tilapia")
        self.assertEqual(m["have"], ["tilapia"])
        self.assertEqual(m["required"], 4)
        self.assertEqual(m["percent"], 25)
        self.assertIn("coconut milk", m["missing"])

    def test_plural_case_and_local_names(self):
        self.assertEqual(self.names(ingredients="Eggplants, EGGS")[0], "Tortang Talong")
        self.assertEqual(self.names(ingredients="talong")[0], "Tortang Talong")

    def test_optional_and_staple_lines_do_not_count(self):
        m = self.search(ingredients="eggplant, egg")["results"][0]["match"]
        self.assertEqual(m["required"], 2)                                  # oil + salt are staples
        tilapia = next(x for x in self.search(ingredients="tilapia")["results"] if x["name"] == "Ginataang Tilapia")
        self.assertNotIn("calamansi", tilapia["match"]["missing"])          # "for serving" is optional

    def test_unrecognised_ingredients_reported(self):
        d = self.search(ingredients="xyzzy, pork belly")
        self.assertEqual(d["unrecognised"], ["xyzzy"])

    def test_filters(self):
        self.assertEqual(self.names(meal="dessert"), ["Leche Flan"])
        self.assertEqual(set(self.names(meal="breakfast")), {"Tortang Talong"})
        self.assertEqual(self.names(taste="sweet"), ["Leche Flan"])
        self.assertEqual(self.names(difficulty="medium"), ["Leche Flan"])
        self.assertNotIn("Leche Flan", self.names(max_minutes=60))
        self.assertEqual(self.names(q="flan"), ["Leche Flan"])

    def test_paging(self):
        page1 = self.search(limit=2)
        page2 = self.search(limit=2, offset=2)
        self.assertEqual((page1["total"], len(page1["results"])), (6, 2))
        self.assertTrue(set(x["id"] for x in page1["results"]).isdisjoint(x["id"] for x in page2["results"]))

    def test_bad_parameters_are_rejected(self):
        for q in ({"meal": "brunch"}, {"taste": "umami"}, {"allergens": "nuts,cheese"}, {"limit": "abc"}, {"difficulty": "x"}):
            self.assertEqual(self.client.get("/api/recipes/search", query_string=q).status_code, 400, q)


class AllergenSafetyTests(ApiTestCase):
    def test_declared_allergen_is_excluded(self):
        self.assertNotIn("Leche Flan", self.names(allergens="dairy", limit=30))
        self.assertNotIn("Tortang Talong", self.names(allergens="eggs", limit=30))

    def test_undeclared_allergen_found_in_ingredients_is_excluded(self):
        # Adobong Baboy declares only Soy, but regular soy sauce also contains wheat.
        self.assertNotIn("Adobong Baboy", self.names(allergens="gluten", limit=30))
        # "Bagoong Rice" lists Shellfish but also has an egg the sheet does not mention.
        self.assertNotIn("Bagoong Rice", self.names(allergens="eggs", limit=30))

    def test_unverified_recipes_hidden_when_filtering(self):
        self.assertIn("Mystery Stew", self.names(limit=30))
        d = self.search(allergens="shellfish", limit=30)
        self.assertNotIn("Mystery Stew", [x["name"] for x in d["results"]])
        self.assertTrue(d["unverified_hidden"])
        shown = self.search(allergens="shellfish", include_unverified=1, limit=30)
        self.assertIn("Mystery Stew", [x["name"] for x in shown["results"]])

    def test_seafood_covers_fish_and_shellfish(self):
        names = self.names(allergens="seafood", limit=30)
        self.assertNotIn("Ginataang Tilapia", names)
        self.assertNotIn("Bagoong Rice", names)

    def test_conditional_mentions_are_treated_as_may_contain(self):
        row_ = row("Pancit", ["200 g noodles", "1 onion"], allergens="Wheat or soy depending on noodle type")
        with self.app.app_context():
            rep = {k: [] for k, _ in imp.SECTIONS}
            imp.write_recipes(self.db, [imp.build_recipe(row_, "pancit", rep)])
        self.assertNotIn("Pancit", self.names(allergens="soy", limit=30))
        card = next(x for x in self.search(q="pancit")["results"])
        self.assertTrue(all(a["level"] == "may" for a in card["allergens"] if a["id"] in ("soy", "wheat")))

    def test_card_reports_allergens_and_verification(self):
        card = next(x for x in self.search(q="mystery")["results"])
        self.assertFalse(card["allergens_verified"])
        self.assertIn({"id": "milk", "label": "Dairy", "level": "may"}, card["allergens"])


class SavedAndDetailTests(ApiTestCase):
    def test_save_list_unsave(self):
        rid = self.rid("Leche Flan")
        self.assertEqual(self.client.put(f"/api/saved/{rid}").json, {"ok": True, "saved": True})
        self.assertEqual(self.client.put(f"/api/saved/{rid}").status_code, 200)    # idempotent
        self.assertEqual([x["name"] for x in self.client.get("/api/saved").json["results"]], ["Leche Flan"])
        self.assertTrue(next(x for x in self.search(q="flan")["results"])["saved"])
        self.client.delete(f"/api/saved/{rid}")
        self.assertEqual(self.client.get("/api/saved").json["total"], 0)

    def test_saved_lists_are_private(self):
        rid = self.rid("Leche Flan")
        self.client.put(f"/api/saved/{rid}")
        other = self.app.test_client()
        other.post("/api/auth/signup", json={"fullname": "O", "email": "o@e.co", "password": "password1"})
        self.assertEqual(other.get("/api/saved").json["total"], 0)
        other.delete(f"/api/saved/{rid}")                                           # cannot remove someone else's
        self.assertEqual(self.client.get("/api/saved").json["total"], 1)

    def test_unknown_recipe(self):
        self.assertEqual(self.client.put("/api/saved/9999").status_code, 404)
        self.assertEqual(self.client.get("/api/recipes/9999").status_code, 404)

    def test_suggestions(self):
        names = [s["name"] for s in self.client.get("/api/ingredients/suggest?q=por").json["suggestions"]]
        self.assertEqual(names[0], "pork belly")
        self.assertEqual(self.client.get("/api/ingredients/suggest?q=").json["suggestions"], [])


class ImageTests(unittest.TestCase):
    def test_matching_ignores_case_accents_and_parentheses(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for n in ["Adobong Baboy.png", "adobong-talong.PNG", "Atchara (Pickled Green Papaya).png", "Pâté.jpg", "Random.png",
                      "Pinakbett.png"]:
                (d / n).write_bytes(b"x")
            files = sorted(d.iterdir())
            names = ["Adobong Baboy", "Adobong Talong (Eggplant Adobo)", "Atchara", "Pate", "Pinakbet", "Missing One"]
            matches, suggestions, unmatched, unused = match_files(names, files)
            self.assertEqual({names[i]: f.name for i, f in matches.items()},
                             {"Adobong Baboy": "Adobong Baboy.png", "Atchara": "Atchara (Pickled Green Papaya).png",
                              "Pate": "Pâté.jpg", "Adobong Talong (Eggplant Adobo)": "adobong-talong.PNG"})
            self.assertEqual([(n, f.name) for n, f, _ in suggestions], [("Pinakbet", "Pinakbett.png")])   # suggested only
            self.assertEqual(sorted(unmatched), ["Missing One", "Pinakbet"])
            self.assertEqual(sorted(f.name for f in unused), ["Pinakbett.png", "Random.png"])

    def test_convert_shrinks_and_flattens_transparency(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            src, dest = Path(d) / "a.png", Path(d) / "out" / "a.jpg"
            Image.new("RGBA", (3000, 1500), (255, 0, 0, 0)).save(src)
            convert(src, dest)
            with Image.open(dest) as img:
                self.assertEqual(img.format, "JPEG")
                self.assertEqual(max(img.size), 1000)
                self.assertEqual(img.size, (1000, 500))

    def test_import_links_images_by_slug(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "adobong-baboy.jpg").write_bytes(b"x")
            report = {k: [] for k, _ in imp.SECTIONS}
            recipes = [imp.build_recipe(ROWS[0], "adobong-baboy", report), imp.build_recipe(ROWS[1], "tortang-talong", report)]
            imp.attach_images(recipes, d, report)
            self.assertEqual(recipes[0]["image"], "images/recipes/adobong-baboy.jpg")
            self.assertIsNone(recipes[1]["image"])
            self.assertEqual(report["no_image"], ["Tortang Talong"])


if __name__ == "__main__":
    unittest.main()
