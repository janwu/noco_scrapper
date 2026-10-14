"""The PDF scraper's pure functions (no network) and the hill size of the list headers."""
import datetime
import unittest

from bs4 import BeautifulSoup

import fis_nk_pdf_scraper as scraper
from fis_parser.extractors.base import BaseExtractor


class _Response:
    def __init__(self, disposition):
        self.headers = {"Content-Disposition": disposition} if disposition else {}


# A race row and its attachment drop-down as on the event pages since 2026
EVENT_PAGE = """
<h1>Ruka (FIN)</h1>
<a href="https://www.fis-ski.com/DB/general/results.html?sectorcode=NK&raceid=3474">28 Nov 2025 13:15</a>
<a href="https://www.fis-ski.com/DB/general/results.html?sectorcode=NK&raceid=3474">4117</a>
<a href="https://www.fis-ski.com/DB/general/results.html?sectorcode=NK&raceid=3474">Individual Compact Large Hill/7.5 km WC M</a>
<div class="drop-btn__item"><span>Official Results (280.77 kb)</span>
  <a href="https://www.fis-ski.com/DB/v2/download/competition-attachment/c349f7ce-64da-11f1-b635-1866da7ef77e.pdf"
     data-ga-codex="4117" data-ga-gender="M" data-ga-download="Official Results">download</a></div>
<div class="drop-btn__item"><span>Start List (20 kb)</span>
  <a href="https://www.fis-ski.com/DB/v2/download/competition-attachment/c349ee2b-64da-11f1-b635-1866da7ef77e.pdf"
     data-ga-codex="4117" data-ga-gender="M" data-ga-download="Start List">download</a></div>
"""


class ScraperTest(unittest.TestCase):

    def test_season_is_named_after_the_year_it_ends_in(self):
        self.assertEqual(scraper.current_season(datetime.date(2026, 10, 14)), 2027)
        self.assertEqual(scraper.current_season(datetime.date(2027, 3, 1)), 2027)

    def test_file_name_from_the_download(self):
        self.assertEqual(scraper.filename_from_response(_Response("inline; filename=2026NK4117ROF.pdf")),
                         "2026NK4117ROF.pdf")
        self.assertEqual(scraper.filename_from_response(_Response('attachment; filename="2026NK4117RL.pdf"')),
                         "2026NK4117RL.pdf")
        self.assertEqual(scraper.filename_from_response(_Response(None)), "")

    def test_event_page(self):
        session = type("S", (), {})()
        original = scraper.get_soup
        scraper.get_soup = lambda url, s: BeautifulSoup(EVENT_PAGE, "html.parser")
        try:
            pdfs, folder = scraper.parse_event_page(
                {"url": "x", "eventid": "58151", "season": 2026, "place": "Ruka", "nation": "FIN"}, session)
        finally:
            scraper.get_soup = original
        self.assertEqual(folder, "20251128_20251128_RUKA_FIN")
        results = [p for p in pdfs if scraper.is_result_pdf(p)]
        self.assertEqual(len(pdfs), 2)
        self.assertEqual(len(results), 1)
        pdf = results[0]
        self.assertEqual((pdf["codex"], pdf["gender"], pdf["race_date"]), ("4117", "M", "20251128"))
        self.assertEqual(pdf["attachment_id"], "c349f7ce-64da-11f1-b635-1866da7ef77e")
        self.assertEqual(scraper.prefixed_filename(pdf, "2026NK4117ROF.pdf"),
                         "4117_20251128_Individual_Compact_Large_Hill_7.5_km_WC_M_M_2026NK4117ROF.pdf")
        self.assertEqual(scraper.fallback_filename(pdf, 2026), "2026NK4117ROF.pdf")

    def test_result_labels(self):
        for label in ("Official Results", "Results List Ski Jumping", "Results Provisional Competition Round",
                      "Results Cross Country", "Results Trial Round", "Results List Official Training",
                      "Results 1st Round"):
            self.assertTrue(scraper.is_result_pdf({"label": label}), label)
        for label in ("Start List", "World Cup Standings", "Nations Cup Ranking", "Best Jumper Trophy",
                      "Event Program", "Prize Money Standings", "Equipment Control Report"):
            self.assertFalse(scraper.is_result_pdf({"label": label}), label)


class HillDataTest(unittest.TestCase):

    def hill(self, text):
        hd = BaseExtractor.__new__(BaseExtractor).extract_hill_data(text)
        return hd.hill_size_m, hd.k_point_m

    def test_hill_size_is_not_the_95_percent(self):
        self.assertEqual(self.hill("HILL SIZE / (95%) 142m (134.5m) Gate Factor 7.00\nK-POINT 120m")[0], 142.0)
        self.assertEqual(self.hill("HILL-SIZE / (95%) 109m (103.5m)")[0], 109.0)
        self.assertEqual(self.hill("Hill Size / (95%) 106 m / (100.5 m)")[0], 106.0)
        self.assertEqual(self.hill("Hill Size 140 m")[0], 140.0)
        self.assertEqual(self.hill("Hill Size: 100 m")[0], 100.0)

    def test_kjump(self):
        self.assertEqual(self.hill("K-point / Hill size 90 m / 98 m"), (98.0, 90.0))

    def test_label_without_value(self):
        # ewoxx: labels and values in separate blocks
        self.assertIsNone(self.hill("TD Assistant C Hill Size\nK-Point 120 m")[0])


if __name__ == "__main__":
    unittest.main()
