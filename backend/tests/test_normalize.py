import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from importer.normalize import (  # noqa: E402
    detect_allergens, is_section_header, keys_match, parse_allergens, parse_courses, parse_flavors,
    parse_ingredient_line, parse_meal_times, parse_minutes, parse_times, section_title, slugify,
    unique_slugs, user_keys,
)


def keys(line):
    return [g["keys"] for g in parse_ingredient_line(line)["groups"]]


class IngredientParsing(unittest.TestCase):
    def test_quantity_unit_and_prep_notes_are_removed(self):
        self.assertEqual(keys("- 250 g ground pork"), [["ground pork"]])
        self.assertEqual(keys("- 1 medium potato, diced"), [["potato"]])
        self.assertEqual(keys("- 1 1/2 cups coconut milk"), [["coconut milk"]])
        self.assertEqual(keys("- ½ cup brown sugar"), [["brown sugar"]])
        self.assertEqual(keys("- 4 garlic cloves, crushed"), [["garlic"]])
        self.assertEqual(keys("- 2–3 cloves garlic"), [["garlic"]])
        self.assertEqual(keys("- 1 can (155g) sardines in tomato sauce"), [["sardine in tomato sauce"]])

    def test_plurals_and_irregulars(self):
        self.assertEqual(keys("- 2 bay leaves"), [["bay leaf"]])
        self.assertEqual(keys("- 3 tomatoes"), [["tomato"]])
        self.assertEqual(keys("- 4 long green chilies"), [["long green chili"]])

    def test_local_names_in_parentheses_become_synonyms(self):
        self.assertEqual(keys("- 300 g pork belly (liempo), sliced"), [["pork belly", "liempo"]])
        self.assertEqual(keys("- patis (fish sauce), to taste"), [["fish sauce"]])

    def test_junk_in_parentheses_is_ignored(self):
        self.assertEqual(keys("- 1 egg, beaten (for sealing and egg wash)"), [["egg"]])
        self.assertEqual(keys("- 250 g squid, cleaned (reserve ink sacs)"), [["squid"]])

    def test_alternatives_are_any_of(self):
        self.assertEqual(keys("- 1 cup spinach or malunggay leaves"), [["spinach leaf", "malunggay leaf"]])

    def test_and_lines_become_separate_required_groups(self):
        self.assertEqual(keys("- 2 tbsp soy sauce and 1 tbsp calamansi juice, for dipping"),
                         [["soy sauce"], ["calamansi juice"]])
        self.assertEqual(keys("- 1 cup sweet and sour sauce"), [["sweet and sour sauce"]])

    def test_plus_quantities_and_trailing_text(self):
        self.assertEqual(keys("- 1 tablespoon + 1/2 teaspoon cooking oil"), [["cooking oil"]])
        self.assertEqual(keys("- 1 tsp cornstarch mixed with 1 tbsp water"), [["corn starch"]])
        self.assertEqual(keys("- 1 cup ground pork with some fat"), [["ground pork"]])
        self.assertEqual(keys("- Topping: 1/4 cup condensed milk"), [["condensed milk"]])

    def test_staples_and_optional(self):
        self.assertTrue(parse_ingredient_line("- Salt and pepper to taste")["staple"])
        self.assertTrue(parse_ingredient_line("- oil for deep-frying")["staple"])
        self.assertTrue(parse_ingredient_line("- salt or 1 1/2 tbsp fish sauce")["groups"][0]["staple"])
        self.assertFalse(parse_ingredient_line("- 2 cloves garlic")["staple"])
        self.assertTrue(parse_ingredient_line("- calamansi, for serving")["optional"])
        self.assertTrue(parse_ingredient_line("- 1 tsp sugar, optional")["optional"])

    def test_section_headers(self):
        self.assertTrue(is_section_header("For the Dipping Sauce:"))
        self.assertTrue(is_section_header("SIDES"))
        self.assertTrue(is_section_header("- Filling:"))
        self.assertFalse(is_section_header("- 2 cloves garlic"))
        self.assertEqual(section_title("FOR THE MARINADE"), "Marinade")
        self.assertEqual(section_title("For the Dipping Sauce:"), "Dipping Sauce")


class Matching(unittest.TestCase):
    def test_matches(self):
        for a, b in [("pork", "ground pork"), ("pork", "pork belly"), ("tomato", "cherry tomato"),
                     ("calamansi", "calamansi juice"), ("banana", "saba banana"), ("onion", "red onion")]:
            self.assertTrue(keys_match(a, b), (a, b))
            self.assertTrue(keys_match(b, a), (b, a))

    def test_non_matches(self):
        for a, b in [("milk", "coconut milk"), ("sauce", "soy sauce"), ("pork belly", "pork shoulder"),
                     ("garlic", "garlic powder"), ("onion", "green onion"), ("rice", "rice flour"),
                     ("pepper", "bell pepper"), ("oil", "sesame oil")]:
            self.assertFalse(keys_match(a, b), (a, b))

    def test_user_input_is_normalised_like_ingredients(self):
        self.assertEqual(user_keys("Tomatoes"), ["tomato"])
        self.assertEqual(user_keys("  2 cloves Garlic "), ["garlic"])
        self.assertEqual(user_keys("sibuyas"), ["onion"])
        self.assertEqual(user_keys(""), [])


class Columns(unittest.TestCase):
    def test_minutes(self):
        self.assertEqual(parse_minutes("15 minutes"), 15)
        self.assertEqual(parse_minutes("1 hour 30 minutes"), 90)
        self.assertEqual(parse_minutes("About 2 hours"), 120)
        self.assertEqual(parse_minutes("30–45 minutes"), 45)
        self.assertEqual(parse_minutes("2–3 days"), 3 * 1440)
        self.assertEqual(parse_minutes("1 day and 15 minutes"), 1455)
        self.assertIsNone(parse_minutes("n/a"))

    def test_times_cell(self):
        t = parse_times("Preparation Time: 10 minutes\nCooking Time: 10 minutes\nMarinating Time: 15 minutes\nOverall Time: 35 minutes")
        self.assertEqual((t["prep"], t["cook"], t["total"]), (10, 10, 35))
        self.assertEqual(t["extras"], ["Marinating Time: 15 minutes"])

    def test_courses_meals_flavors(self):
        self.assertEqual(parse_courses("Main Course / Soup"), ["Main Course", "Soup"])
        self.assertEqual(parse_courses("Main Entree"), ["Main Course"])
        self.assertEqual(parse_meal_times("Lunch / Dinner")[0], ["lunch", "dinner"])
        self.assertEqual(parse_meal_times("Merienda, Party"), (["snack"], ["party"]))
        self.assertIn("dessert", parse_meal_times("Snack", ["Dessert"])[0])
        self.assertEqual(parse_flavors("Savory, tangy, garlicky"), ["savory", "tangy"])
        self.assertEqual(parse_flavors("Mildly sweet, savory"), ["savory", "sweet"])   # 'mildly' is not 'mild'
        self.assertEqual(parse_flavors("sweet-savory"), ["savory", "sweet"])

    def test_slugs(self):
        self.assertEqual(slugify("Adobong Talong (Eggplant Adobo)"), "adobong-talong-eggplant-adobo")
        self.assertEqual(unique_slugs(["Biko", "Biko", "Pâté"]), ["biko", "biko-2", "pate"])


class Allergens(unittest.TestCase):
    def test_declared(self):
        a = parse_allergens("Shellfish/Mollusk, Soy")
        self.assertEqual(a["contains"], {"shellfish", "mollusk", "soy"})
        self.assertTrue(parse_allergens("None of the common allergens")["none"])
        self.assertTrue(parse_allergens("None")["none"])
        self.assertTrue(parse_allergens("")["blank"])
        self.assertTrue(parse_allergens("nan")["blank"])

    def test_conditional_mentions_are_may(self):
        a = parse_allergens("Fish (if fish sauce is used)")
        self.assertEqual((a["contains"], a["may"]), (set(), {"fish"}))
        a = parse_allergens("Wheat or soy depending on noodle type")
        self.assertEqual(a["may"], {"wheat", "soy"})
        self.assertEqual(parse_allergens("Dairy; possible allergens depend on canned toppings")["contains"], {"milk"})

    def test_detect_from_ingredients(self):
        self.assertEqual(detect_allergens(["1 cup coconut milk"]), {"coconut"})            # not dairy
        self.assertEqual(detect_allergens(["2 eggplants"]), set())                          # not egg
        self.assertEqual(detect_allergens(["1 cup rice flour"]), set())                     # not wheat
        self.assertEqual(detect_allergens(["2 tbsp soy sauce"]), {"soy", "wheat"})
        self.assertEqual(detect_allergens(["1 tbsp oyster sauce"]), {"mollusk", "soy", "wheat"})
        self.assertEqual(detect_allergens(["1 tbsp bagoong alamang (shrimp paste)"]), {"shellfish"})
        self.assertEqual(detect_allergens(["2 tbsp butter"]), {"milk"})
        self.assertEqual(detect_allergens(["1/2 cup peanut butter"]), {"peanut"})           # not dairy


if __name__ == "__main__":
    unittest.main()
