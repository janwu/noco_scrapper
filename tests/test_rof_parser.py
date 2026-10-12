"""
Regression tests for the ROF parser — one reference PDF per layout family.

Run from the project root:

    python -m unittest discover -s tests -v

The expected values were read off the PDFs.  Every reference file must also
pass the plausibility checks in fis_parser.validate (no parse_errors).
"""
import glob
import logging
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fis_parser.parser import parse_pdf            # noqa: E402
from fis_parser.validate import validate_rof       # noqa: E402

logging.disable(logging.CRITICAL)                  # pdfminer font warnings

# (file pattern, layout, expectations)
REFERENCE_FILES = [
    ("fis_nk_pdfs/2004/*/M/4113_20031129_*ROF.pdf", "WC 2003/04 — name / data / club, no birthdate, venue without country",
     dict(location="Ruka", country="FIN", date="2003-11-29", ranked=40, status={"DNF": 3, "DNS": 6},
          winner=("ACKERMANN Ronny", "GER", 271.6, "38:38.2"), last="JEZERSEK Andrej")),
    ("fis_nk_pdfs/2005/*/M/4134_20050106_*ROF.pdf", "WC 2004/05 — lapped athlete without time",
     dict(location="Schonach", country="GER", date="2005-01-06", ranked=38, status={"LAP": 1, "DNS": 6},
          winner=("MANNINEN Hannu", "FIN", 213.0, "35:11.9"), last="HOLLENSTEIN Michael")),
    ("fis_nk_pdfs/2003/*/M/4148_20030125_*ROF.pdf", "WC 2002/03 — mass start, names printed in mixed case",
     dict(location="Sapporo", country="JPN", date="2003-01-25", ranked=38, status={},
          winner=("ACKERMANN Ronny", "GER", 135.6, "26:35.7"), last="MEHRINGER Matthias")),
    ("fis_nk_pdfs/2008/*/M/4117_20071208_*ROF.pdf", "WC 2007/08 — three lines per athlete with birthdate",
     dict(location="Trondheim", country="NOR", date="2007-12-08", ranked=34, status={"DNS": 1},
          winner=("DEMONG Bill", "USA", 240.2, "38:12.9"), last="KAEHKOENEN Ville")),
    ("fis_nk_pdfs/2009/*/M/4181_20090215_*ROF.pdf", "WC 2008/09 — 'Did Not Start' list continues on the next page",
     dict(location="Klingenthal", country="GER", date="2009-02-15", ranked=44, status={"LAP": 1, "DNF": 1, "DNS": 14},
          winner=("DEMONG Bill", "USA", 121.7, "25:49.4"), last="LEETOJA Aldo")),
    ("fis_nk_pdfs/2022/*/M/4146_20211212_*ROF.pdf", "WC 2021/22 — revision stamp '16 DEC 15:13' in the page title",
     dict(location="Otepaeae", country="EST", date="2021-12-12", ranked=49, status={"LAP": 2, "DNF": 1},
          winner=("RIIBER Jarl Magnus", "NOR", 150.3, "23:33.2"), last="AMANKELDIULY Magzhan")),
    ("fis_nk_pdfs/2022/*/M/4136_20211218_*ROF.pdf", "WC 2021/22 — DNS / DSQ lists on a page of their own, jury decision",
     dict(location="Ramsau am Dachstein", country="AUT", date="2021-12-18", ranked=41,
          status={"DNF": 1, "DSQ": 2, "DNS": 4},
          winner=("RIIBER Jarl Magnus", "NOR", 140.2, "24:02.0"), last="VALLET Edgar")),
    ("fis_nk_pdfs/2026/*/M/4117_20251128_*ROF.pdf", "WC 2025/26 — jury on the last page",
     dict(location="Ruka", country="FIN", date="2025-11-28", ranked=57, status={"DSQ": 2, "DNS": 1},
          winner=("LAMPARTER Johannes", "AUT", 131.7, "17:32.2"), last="KURTTILA Eemeli")),
    ("fis_nk_coc_pdfs/2009/*/M/4115_20081217_*ROF.pdf", "COC 2008/09 — ewoxx, FIS code instead of nation",
     dict(location="Vancouver-Whistler", country="CAN", date="2008-12-17", ranked=47, status={"DNF": 2},
          winner=("LODWICK Todd", "USA", 111.0, "26:01.5"), last="DANDURAND Sebastien")),
    ("fis_nk_coc_pdfs/2010/*/M/4153_20100110_*ROF.pdf", "COC 2009/10 — ewoxx, start difference missing",
     dict(location="Otepää", country="EST", date="2010-01-10", ranked=59, status={"DNS": 1},
          winner=("KAMMERLANDER Tobias", "AUT", 120.0, "24:45.4"), last="NOMME Martti")),
    ("fis_nk_coc_pdfs/2016/*/M/4149_20160213_*ROF.pdf", "COC 2015/16 — ewoxx, one-line DNS / DNF rows",
     dict(location="Ramsau", country="AUT", date="2016-02-13", ranked=55, status={"DNS": 1, "DNF": 1},
          winner=("GEIGER Vinzenz", "GER", 126.5, "22:14.7"), last="DURCO Dominik")),
    ("fis_nk_coc_pdfs/2023/*/M/4230_20230317_*ROF.pdf", "COC 2022/23 — photo-finish flag 'PF 11.' before the rank",
     dict(location="Lahti", country="FIN", date="2023-03-17", ranked=46, status={},
          winner=("SKOGLUND Andreas", "NOR", 125.6, "25:13.2"), last="OJALA Juho")),
]


class ReferenceFiles(unittest.TestCase):

    def test_reference_files(self):
        for pattern, layout, want in REFERENCE_FILES:
            with self.subTest(layout=layout):
                matches = glob.glob(os.path.join(ROOT, pattern))
                if not matches:
                    self.skipTest(f"PDF not downloaded: {pattern}")
                doc = parse_pdf(matches[0])
                self.assertEqual(doc.parse_errors, [])

                self.assertEqual(doc.location, want["location"])
                self.assertEqual(doc.country, want["country"])
                self.assertEqual(doc.competition_date, want["date"])

                ranked = [r for r in doc.combined_results if r.rank is not None]
                self.assertEqual(len(ranked), want["ranked"])
                status = {}
                for r in doc.combined_results:
                    if r.status:
                        status[r.status] = status.get(r.status, 0) + 1
                self.assertEqual(status, want["status"])

                winner = next(r for r in ranked if r.rank == 1)
                self.assertEqual((winner.name, winner.nation, winner.jump_points, winner.xc_time),
                                 want["winner"])
                self.assertEqual(max(ranked, key=lambda r: r.rank).name, want["last"])


class KJump(unittest.TestCase):
    """Lillehammer lists by K-Jump: 'Firstname Surname', block rebuilt from word positions."""

    def parse(self, pattern):
        matches = glob.glob(os.path.join(ROOT, pattern))
        if not matches:
            self.skipTest(f"PDF not downloaded: {pattern}")
        return parse_pdf(matches[0])

    def test_men(self):
        doc = self.parse("fis_nk_coc_pdfs/2026/*/M/4245_20260214_*ROF.pdf")
        self.assertEqual(doc.parse_errors, [])
        self.assertEqual((doc.name_order, doc.discipline, doc.location, doc.competition_date),
                         ("given-first", "Gundersen", "Lillehammer", "2026-02-14"))
        rows = doc.combined_results
        self.assertEqual(sum(1 for r in rows if r.rank is not None), 53)
        self.assertEqual(sorted(r.status for r in rows if r.status), ["DNF", "DNS", "DSQ", "DSQ"])
        first = rows[0]
        self.assertEqual((first.rank, first.bib, first.name, first.nation, first.club, first.jump_points,
                          first.jump_rank, first.time_difference, first.xc_time, first.xc_rank),
                         (1, 8, "David Mach", "GER", "Tsv Buchenberg", 119.0, 8, "0:24", "23:44.4", 9))
        # no club: the name sits on the number line, the nation above it
        fifth = next(r for r in rows if r.rank == 5)
        self.assertEqual((fifth.name, fifth.nation, fifth.club, fifth.bib), ("Iacopo Bortolas", "ITA", None, 3))
        # second column ('Team Kollenhopp') is a sponsor team, not part of the name or club
        eighth = next(r for r in rows if r.rank == 8)
        self.assertEqual((eighth.name, eighth.club), ("Jørgen Berget Storsveen", "Elverum Hopp"))
        # a long name wraps onto the number line; the typeface tells it from the club
        wrapped = next(r for r in rows if r.rank == 31)
        self.assertEqual((wrapped.name, wrapped.club), ("Henrik Elias Wikstrøm Hilmarsen", "Tolga IL"))

    def test_club_wrapping_over_two_lines(self):
        doc = self.parse("fis_nk_coc_pdfs/2026/*/W/4244_20260214_*ROF.pdf")
        self.assertEqual(doc.parse_errors, [])
        second = next(r for r in doc.combined_results if r.rank == 2)
        self.assertEqual((second.name, second.nation, second.club, second.xc_time),
                         ("Alexa Brabec", "USA", "Steamboat Springs Winter Sports Club", "14:21.9"))

    def test_date_comes_from_the_file_name(self):
        # header says 'Mon 12 Sep 2022' for a race on 9 December (12/09 read day-first)
        doc = self.parse("fis_nk_coc_pdfs/2023/*/W/4250_20221209_*ROF.pdf")
        self.assertEqual(doc.parse_errors, [])
        self.assertEqual(doc.competition_date, "2022-12-09")
        self.assertEqual(doc.combined_results[0].date_of_birth, "2002-04-20")


def _doc(rows, **extra):
    doc = dict(doc_type="ROF", location="Ruka", country="FIN", competition_date="2024-11-29",
               discipline="Gundersen", combined_results=rows, competitor_stats=None)
    doc.update(extra)
    return doc


def _row(rank, name="ACKERMANN Ronny", nation="GER", status=None, **extra):
    row = dict(rank=rank, name=name, nation=nation, status=status, bib=rank or 99,
               jump_points=100.0, xc_time="25:00.0", time_behind="+1.0")
    row.update(extra)
    return row


class Validation(unittest.TestCase):

    def errors(self, doc):
        return validate_rof(doc)[0]

    def test_clean_list_with_tie(self):
        rows = [_row(1, "ALFA Bo"), _row(2, "CHARLIE Di"), _row(2, "ECHO Fi"), _row(4, "GOLF Hi"),
                _row(None, "INDIA Jo", status="DNS")]
        self.assertEqual(self.errors(_doc(rows)), [])

    def test_empty_list(self):
        self.assertEqual(self.errors(_doc([])), ["no result rows"])

    def test_only_non_finishers_parsed(self):
        errors = self.errors(_doc([_row(None, status="DNS")], competitor_stats={"ranked_athletes": 34}))
        self.assertTrue(any("no ranked rows" in e for e in errors))
        self.assertTrue(any("statistics say 34" in e for e in errors))

    def test_rank_gap(self):
        errors = self.errors(_doc([_row(1, "ALFA Bo"), _row(2, "CHARLIE Di"), _row(5, "ECHO Fi")]))
        self.assertTrue(any("rank sequence broken" in e for e in errors))

    def test_lapped_counted_either_way(self):
        rows = [_row(1, "ALFA Bo"), _row(2, "CHARLIE Di", status="LAP", xc_time=None, time_behind=None)]
        for stated in (1, 2):
            self.assertEqual(self.errors(_doc(rows, competitor_stats={"ranked_athletes": stated})), [])

    def test_junk_rows(self):
        for name, nation in (("Bib Name", None), ("SC Erzbergland 25", "APR"),
                             ("Timing and Data Service by EWOXX fis-ski.com", "FIS"),
                             ("DEC", "GER"), ("WESTVOLD HANSEN Gyda", None)):
            with self.subTest(name=name):
                self.assertNotEqual(self.errors(_doc([_row(1, "ALFA Bo"), _row(2, name, nation)])), [])

    def test_location_is_an_official(self):
        errors = self.errors(_doc([_row(1, "ALFA Bo")], location="Race Director WEHLING Ulrich"))
        self.assertTrue(any("not a place" in e for e in errors))


if __name__ == "__main__":
    unittest.main()
