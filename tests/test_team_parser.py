"""
Regression tests for team result lists — one reference PDF per layout family,
plus line-level tests of the team parser.

    python -m unittest discover -s tests -v
"""
import glob
import logging
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fis_parser.parser import parse_pdf                          # noqa: E402
from fis_parser.extractors.rof_team import parse_team_rof        # noqa: E402

logging.disable(logging.CRITICAL)

# (file pattern, layout, discipline, ranked teams, status counts, winner, winner's athletes)
REFERENCE_FILES = [
    ("fis_nk_pdfs/2004/*/M/4167_*ROF.pdf", "WC 2003/04 — three athletes, nation without dash, leg times",
     "Team", 13, {"DNF": 1}, ("FIN", "Finland", 742.8, "35:44.4"),
     [("LAJUNEN Samppa", 250.8, "11:56.9"), ("TALLUS Jaakko", 251.1, "12:13.5"),
      ("MANNINEN Hannu", 240.9, "11:34.0")]),
    ("fis_nk_pdfs/2020/*/M/4143_*ROF.pdf", "WC 2019/20 — four athletes with leg colours",
     "Team", 9, {}, ("NOR", "Norway", 568.0, "51:03.4"),
     [("BJOERNSTAD Espen", 140.0, "12:32.5"), ("OFTEBRO Jens Luraas", 149.2, "12:53.9"),
      ("GRAABAK Joergen", 135.5, "12:42.2"), ("RIIBER Jarl Magnus", 143.3, "12:54.8")]),
    ("fis_nk_pdfs/2016/*/M/4132_*ROF.pdf", "WC 2015/16 — team sprint with lapped, DNF and DNS teams",
     "Team Sprint", 15, {"LAP": 3, "DNF": 1, "DNS": 4}, ("GER", "GERMANY I", 223.7, "32:57.9"),
     [("RYDZEK Johannes", 118.5, "16:12.4"), ("RIESSLE Fabian", 105.2, "16:45.5")]),
    ("fis_nk_coc_pdfs/2019/*/M/4189_*ROF.pdf", "COC 2018/19 — rank and bib on lines of their own, no leg times",
     "Team", 7, {}, ("NOR", "NORWAY", 110.4, "39:41.1"),
     [("TILLER Simen", 100.4, None), ("SOETVIK Sindre Ure", 105.3, None),
      ("RIIBER Harald Johnas", 121.9, None), ("NAESVOLD Leif Torbjoern", 114.2, None)]),
    ("fis_nk_coc_pdfs/2022/*/M/4233_*ROF.pdf", "COC 2021/22 — team number printed over the points",
     "Team Sprint", 19, {}, ("AUT", "AUSTRIA I", 266.6, "33:33.3"),
     [("ORTER Philipp", 133.4, "16:46.2"), ("KLAPFER Lukas", 133.2, "16:47.1")]),
    ("fis_nk_coc_pdfs/2012/*/M/4031_*ROF.pdf", "COC 2011/12 — no nation code, athletes repeated per lap",
     "Team Sprint", 14, {}, ("AUT", "Austria II", 99.5, "38:27.1"),
     [("DIER Dominik", None, None), ("ORTER Philipp", None, None)]),
]


class ReferenceFiles(unittest.TestCase):

    def test_reference_files(self):
        for pattern, layout, discipline, ranked, status, winner, athletes in REFERENCE_FILES:
            with self.subTest(layout=layout):
                matches = glob.glob(os.path.join(ROOT, pattern))
                if not matches:
                    self.skipTest(f"PDF not downloaded: {pattern}")
                doc = parse_pdf(matches[0])
                self.assertEqual(doc.parse_errors, [])
                self.assertEqual(doc.discipline, discipline)
                self.assertEqual(doc.combined_results, [])

                teams = doc.team_results
                self.assertEqual(sum(1 for t in teams if t.rank is not None), ranked)
                counts = {}
                for t in teams:
                    if t.status:
                        counts[t.status] = counts.get(t.status, 0) + 1
                self.assertEqual(counts, status)

                first = next(t for t in teams if t.rank == 1)
                self.assertEqual((first.nation, first.team_name, first.jump_points, first.xc_time), winner)
                self.assertEqual([(m.name, m.jump_points, m.xc_time) for m in first.members], athletes)

    def test_sprint_with_a_club_called_team_is_not_a_team_event(self):
        # 'Team Tsuchiya' among the clubs used to turn sprints into team events
        matches = glob.glob(os.path.join(ROOT, "fis_nk_pdfs/2003/*/M/4154_*ROF.pdf"))
        if not matches:
            self.skipTest("PDF not downloaded")
        doc = parse_pdf(matches[0])
        self.assertEqual(doc.discipline, "Sprint")
        self.assertEqual(doc.parse_errors, [])
        ranked = [r for r in doc.combined_results if r.rank is not None]
        self.assertEqual(len(ranked), 41)
        self.assertEqual(sum(1 for r in ranked if r.rank == 3), 2)      # '=3' tie


def parse(text):
    teams, unparsed = parse_team_rof([["RANK BIB NAME TIME TEAM TEAM TIME"] + text.strip().splitlines()])
    return teams, unparsed


class Lines(unittest.TestCase):

    def test_team_and_members(self):
        teams, unparsed = parse("""
            1 2 NOR - Norway I 282.8 2 +0:02 33:17.0 3 33:19.0
            2-1 r GRAABAK Joergen 137.3 16:34.7
            2-2 b RIIBER Jarl Magnus 145.5 16:42.3
            PF 2 5 GER - Germany I 266.8 5 +0:34 33:28.8 7 +43.8
            5-1 r RIESSLE Fabian 133.5 16:43.9
            5-2 b GEIGER Vinzenz 133.3 16:44.9
        """)
        self.assertEqual(unparsed, [])
        self.assertEqual([(t.rank, t.bib, t.nation, t.team_name, t.time_behind) for t in teams],
                         [(1, 2, "NOR", "Norway I", "33:19.0"), (2, 5, "GER", "Germany I", "+43.8")])
        self.assertEqual([(m.leg, m.bib, m.name, m.jump_points, m.xc_time) for m in teams[0].members],
                         [(1, "2-1", "GRAABAK Joergen", 137.3, "16:34.7"),
                          (2, "2-2", "RIIBER Jarl Magnus", 145.5, "16:42.3")])

    def test_lapped_and_sections(self):
        teams, unparsed = parse("""
            1 1 NOR - NORWAY 524.2 1 0:00 50:46.0 6 0.0
            1-1 r SCHMID Jan 121.7 12:28.0 4 +10.6 12:28.0 1 0.0
            2 16 EST - ESTONIA 193.0 19 +3:01 LAP 14 **
            16-1 r KREEN Han Hendrik 96.5
            Did Not Start
            8 CZE - CZECH REPUBLIC II 242.2 8 +0:24
            8-1 r VODSEDALEK Ales 115.3
            Disqualified
            2 JPN - JAPAN I ICR 525.2.16
            2-1 r WATABE Yoshito
            NICHOLS Evan USA Ski Jumping: SCE4 Suit
            WEATHER SNOW CONDITIONS
            3 3 XXX - NEVER READ 1.0 1 0:00 1:00.0 1 0.0
        """)
        self.assertEqual(unparsed, [])
        self.assertEqual([(t.rank, t.nation, t.status, len(t.members)) for t in teams],
                         [(1, "NOR", None, 1), (2, "EST", "LAP", 1), (None, "CZE", "DNS", 1),
                          (None, "JPN", "DSQ", 1)])
        self.assertIsNone(teams[1].xc_time)
        self.assertEqual(teams[1].xc_rank, 14)

    def test_total_time_before_the_gap(self):
        teams, _ = parse("""
            1 4 NOR - NORWAY 470.9 4 +0:32 46:59.2 1 47:31.2 47:31.2
            2 2 AUT - AUSTRIA 474.5 2 +0:27 47:16.1 2 47:43.1 +11.9
            5 FF 6 CZE - CZECH REPUBLIC 458.9 6 +0:30 52:31.3 6 53:01.3 +1:38.0
        """)
        self.assertEqual([(t.rank, t.bib, t.xc_time, t.time_behind) for t in teams],
                         [(1, 4, "46:59.2", "47:31.2"), (2, 2, "47:16.1", "+11.9"), (5, 6, "52:31.3", "+1:38.0")])

    def test_rank_and_bib_on_their_own_lines(self):
        teams, unparsed = parse("""
            1.
            NOR - NORWAY 110.4 1. 00:00 39:41.1 4. 39:41.1
            1
            1-1 TILLER Simen 100.4
            1-2 NAESVOLD Leif Torbjoern 114.2 39:41.1 2. 39:41.1 2. +39:41.1
            2.
            USA - UNITED STATES OF AMERICA2 5I3I.0 8. 00:27 36:01.3 14. +02:55.0
            8
        """)
        self.assertEqual(unparsed, [])
        self.assertEqual([(t.rank, t.bib, t.team_name, t.jump_points) for t in teams],
                         [(1, 1, "NORWAY", 110.4), (2, 8, "UNITED STATES OF AMERICA II", 253.0)])
        # the time on the last athlete's line is the team's total, not a leg time
        self.assertEqual([m.xc_time for m in teams[0].members], [None, None])

    def test_country_name_without_code(self):
        teams, _ = parse("""
            1. 2 - Austria II 99.5 2. 00:08 38:27.1 5. 38:35.1
            2-1 DIER Dominik 03:44.0 3. 03:52.0 2. +00:05.6
            2-2 ORTER Philipp 03:50.7 8. 07:42.7 2. +00:05.5
            2-1 DIER Dominik 03:54.3 9. 11:37.0 2. +00:07.0
        """)
        self.assertEqual((teams[0].nation, teams[0].team_name), ("AUT", "Austria II"))
        self.assertEqual([m.name for m in teams[0].members], ["DIER Dominik", "ORTER Philipp"])


if __name__ == "__main__":
    unittest.main()
