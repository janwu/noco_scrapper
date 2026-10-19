"""
Tests for fis_nk_wcb_1990s.py: the World Cup B lists of weltcup-b.org of the 1990s.

    python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import fis_nk_wcb_1990s as wcb                       # noqa: E402


class ListTest(unittest.TestCase):

    def read(self, text: str, suffix=".htm"):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / f"list{suffix}"
            path.write_text(f"<html><body><pre>{text}</pre></body></html>", encoding="utf-8")
            return wcb.read(path)

    def test_text_table_with_ties_and_a_place_left_out(self):
        rows = self.read(
            "Rang Name, Vorname          Nat   Punkte Rg Laufzeit Rg     E-Dif\n"
            "  1  SPILLANE, Johnny       USA   110.0  13 19:22.9  6      00.0    31\n"
            "  2  CARSON, Demian         CAN   115.0   1 19:42.5  9      00.6    27\n"
            "  2  BRYNEMO, Preben        NOR   107.5  16 19:19.3  3      05.4    24\n"
            "  5  FREY, Marc             GER   104.0  26 19:25.3  7      24.4    21\n"
            " 40  NOBODY, Late           GER   104.0  26 19:25.3  7      24.4    21\n")
        self.assertEqual([(r["rank"], r["name"], r["nation"]) for r in rows],
                         [(1, "SPILLANE Johnny", "USA"), (2, "CARSON Demian", "CAN"),
                          (2, "BRYNEMO Preben", "NOR"), (5, "FREY Marc", "GER")])
        self.assertEqual((rows[0]["jump_points"], rows[0]["jump_rank"], rows[0]["xc_time"], rows[0]["xc_rank"]),
                         (110.0, 13, "19:22.9", 6))

    def test_bib_second_us_team_and_mixed_case_surname(self):
        rows = self.read(
            "Place Bib Name                 Nat    Pts:    Pl.    Time:  Pl.  Time Back\n"
            "1     16 HASENEY Sebastian     GER    104.6   16    16:46.6  2    00:00.0\n"
            "2     21 GERHART Nathan        USA-D  100.7   21    19:40.9 34    03:08.3\n"
            "3     2  Arnould, Kevin  FRA  224.4  2  0:47  44:36.9  32  1:46.2\n")
        self.assertEqual([(r["name"], r["nation"], r["bib"]) for r in rows],
                         [("HASENEY Sebastian", "GER", 16), ("GERHART Nathan", "USA", 21), ("ARNOULD Kevin", "FRA", 2)])
        self.assertEqual(rows[2]["xc_time"], "44:36.9")          # the start gap 0:47 is not the time

    def test_a_name_does_not_reach_into_the_next_row(self):
        # rows broken over lines, read as one text (the HTML of 1997 and 1998)
        rows = self.read("1 5 SCHMITT, \nThorsten GER 218,0 5 01:18 50:17,4 14 00:00,0 2 11 CECON, Andrea "
                         "ITA 209,5 11 02:09 49:36,2 9 00:09,8 3 9 ROTEVATN, Sverre NOR 211,5 9 01:57 "
                         "49:50,0 11 00:11,6 4 19 OGIWARA, Tsugiharu JPN 202,0 19 02:54 49:04,7 4 00:23,3 "
                         "5 2 TOMII, Gen JPN 226,5 2 00:20 50:01,0 13 00:30,0 6 1 A, Bc DEF 226,5 2 00:20 "
                         "50:01,0 13 00:30,0 7 3 GH, Ij KLM 226,5 2 00:20 50:01,0 13 00:30,0 8 4 NO, Pq RST "
                         "226,5 2 00:20 50:01,0 13 00:30,0 9 6 UV, Wx YZA 226,5 2 00:20 50:01,0 13 00:30,0 "
                         "10 7 BC, De FGH 226,5 2 00:20 50:01,0 13 00:30,0")
        self.assertEqual([(r["name"], r["nation"]) for r in rows[:3]],
                         [("SCHMITT Thorsten", "GER"), ("CECON Andrea", "ITA"), ("ROTEVATN Sverre", "NOR")])

    def test_dates_of_the_head(self):
        self.assertEqual(wcb.all_dates("Klingenthal, 06./ 07.03.1999 OFFIZIELLE"), ["1999-03-06", "1999-03-07"])
        self.assertEqual(wcb.all_dates("Thursday, Jan 21, \n1999 -- 90 meter Sunday, Jan \n24, 1999"),
                         ["1999-01-21", "1999-01-24"])


if __name__ == "__main__":
    unittest.main()
