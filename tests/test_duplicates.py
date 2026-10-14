"""Athletes that may be one person, and gender markers in mixed team lists."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "db"))

import load_json                                    # noqa: E402
from fis_parser.utils import clean_name             # noqa: E402
from fis_parser.validate import row_identity_problem  # noqa: E402


class DuplicatesTest(unittest.TestCase):

    def found(self, *athletes):
        build = load_json.Build.__new__(load_json.Build)
        build.athletes = {i: {"name": n, "nation": c} for i, (n, c) in enumerate(athletes)}
        return load_json.possible_duplicates(build)

    def test_spellings_and_nation_changes(self):
        self.assertEqual(self.found(("UVSLOKK Einar", "NOR"), ("UVSLOEKK Einar", "NOR")),
                         [("UVSLOKK Einar", "UVSLOEKK Einar", "NOR")])
        self.assertEqual(self.found(("VIACHESLAV Barkov", "RUS"), ("BARKOV Viacheslav", "RUS")),
                         [("VIACHESLAV Barkov", "BARKOV Viacheslav", "RUS")])
        self.assertEqual(len(self.found(("SKJAERET STROMHAUG", "NOR"), ("SKJAERET STROMHAUG Per Einar", "NOR"))), 1)
        self.assertEqual(self.found(("SCHMID Jan", "SUI"), ("SCHMID Jan", "NOR")),
                         [("SCHMID Jan", "SCHMID Jan", "SUI / NOR")])

    def test_different_people(self):
        self.assertEqual(self.found(("OFTEBRO Jens Luraas", "NOR"), ("OFTEBRO Einar Luraas", "NOR")), [])
        self.assertEqual(self.found(("KASAI Yuna", "JPN"), ("KASAI Haruka", "JPN")), [])

    def test_gender_marker_of_mixed_teams(self):
        self.assertEqual(clean_name("ARMBRUSTER Nathalie (F)"), "ARMBRUSTER Nathalie")
        self.assertEqual(clean_name("LAMPARTER Johannes (M)"), "LAMPARTER Johannes")
        self.assertIn("bracket", row_identity_problem({"name": "HIRNER Lisa (F)", "nation": "AUT"}))


if __name__ == "__main__":
    unittest.main()
