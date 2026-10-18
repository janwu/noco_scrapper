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


class FisDatabaseRankingTest(unittest.TestCase):
    """fis_nk_fisdb.race_ranking: after the nation a gap (blue) or, before 2000/01, World Cup points."""

    ROW = ('<a class="table-row"><div class="g-row">'
           '<div class="bold">{rank}</div><div class="gray">{code}</div><div class="bold">{name}</div>'
           '<div>{year}</div><div class="country country_flag">{nation}</div>{after}</div></a>')

    def ranking(self, *rows):
        import fis_nk_fisdb
        html = '<div id="events-info-results">' + "".join(self.ROW.format(**r) for r in rows) + "</div>"
        original = scraper.get_soup
        scraper.get_soup = lambda url, session: BeautifulSoup(html, "html.parser")
        try:
            return fis_nk_fisdb.race_ranking("111", None)
        finally:
            scraper.get_soup = original

    def test_points_of_the_early_world_cup(self):
        rows = self.ranking(dict(rank=1, code=2, name="SULZENBACHER Klaus", year=1965, nation="AUT",
                                 after='<div class="justify-right hidden-xs">25</div>'))
        self.assertEqual((rows[0]["wc_points"], rows[0]["time_behind"]), (25, None))

    def test_team_ranking(self):
        import fis_nk_fisdb
        html = ('<div id="events-info-results">'
                '<a class="table-row"><div class="g-row"><div>1</div><div>1241</div><div>DDR</div><div></div>'
                '<div class="country country_flag">GDR</div><div></div></div></a>'
                '<a class="table-row"><div class="g-row"><div></div><div>32</div><div>DOTZAUER Uwe</div>'
                '<div>1959</div><div class="country country_flag country"></div><div></div></div></a>'
                '</div>')
        original = scraper.get_soup
        scraper.get_soup = lambda url, session: BeautifulSoup(html, "html.parser")
        try:
            teams = fis_nk_fisdb.team_ranking("661", None)
        finally:
            scraper.get_soup = original
        self.assertEqual((teams[0]["rank"], teams[0]["nation"], teams[0]["team_name"]), (1, "GDR", "DDR"))
        self.assertEqual(teams[0]["members"], [{"leg": 1, "name": "DOTZAUER Uwe", "birth_year": 1959}])

    def test_race_name_of_the_early_championships(self):
        self.assertEqual(scraper.event_name_from_text("D P C C\n04 Feb 1925\n4100\nNordic Combined\nNordic Combined WSC M"),
                         "Nordic_Combined_WSC_M")

    def test_gap_to_the_winner(self):
        rows = self.ranking(dict(rank=2, code=74, name="ACKERMANN Ronny", year=1977, nation="GER",
                                 after='<div class="justify-right blue bold">0.8</div><div class="bold">+0</div>'))
        self.assertEqual((rows[0]["wc_points"], rows[0]["time_behind"]), (None, "+0.8"))


if __name__ == "__main__":
    unittest.main()
