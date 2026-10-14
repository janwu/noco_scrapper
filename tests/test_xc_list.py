"""The cross-country list of a mass start (RLLL), on a real list."""
import glob
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUKA = glob.glob(os.path.join(ROOT, "fis_nk_pdfs", "2026", "*RUKA*", "M", "4119_*RLLL.pdf"))


@unittest.skipUnless(RUKA, "PDF not downloaded")
class XcListTest(unittest.TestCase):

    def test_ruka_2025_race_held_jump_cancelled(self):
        from fis_parser.parser import parse_pdf
        doc = parse_pdf(RUKA[0])
        self.assertEqual(doc.parse_errors, [])
        ranked = [r for r in doc.xc_results if r.rank is not None]
        self.assertEqual([r.rank for r in ranked], list(range(1, 57)))
        # the page footer '30 NOV 2025 / Ruka (FIN) / 4119' is no athlete
        self.assertFalse(any("/" in (r.name or "") for r in doc.xc_results))
        first = ranked[0]
        self.assertEqual((first.name, first.nation, first.total_time), ("RETTENEGGER Stefan", "AUT", "22:50.9"))
        self.assertEqual({r.status for r in doc.xc_results if r.rank is None}, {"DNF", "DNS"})


if __name__ == "__main__":
    unittest.main()
