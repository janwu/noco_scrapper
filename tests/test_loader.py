"""
Tests for db/load_json.py — path handling, alias lists and a small end-to-end build.

    python -m unittest discover -s tests -v
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "db"))

import load_json                                    # noqa: E402


def result(rank, name, nation, **extra):
    row = dict(rank=rank, bib=rank or 50, name=name, nation=nation, club="SC Test",
               date_of_birth="1990-01-0%d" % (rank or 9), jump_points=120.0, jump_rank=rank,
               time_difference="0:10", xc_time="25:00.0", xc_rank=rank, time_behind="+1.0",
               status=None, wave_start=False)
    row.update(extra)
    return row


class Paths(unittest.TestCase):

    def meta(self, rel):
        return load_json.file_meta(os.path.join("output", *rel.split("/")), "output")

    def test_old_file_name_without_season(self):
        m = self.meta("fis_nk_pdfs/2004/20031129_20031130_RUKA_FIN/M/"
                      "4113_20031129_Individual_K120_15.0_Km_Kuusamo_FIN_M_4113ROF.json")
        self.assertEqual((m["circuit"], m["season_label"], m["codex"], m["gender"], m["file_date"]),
                         ("WC", "2003/2004", "4113", "M", "2003-11-29"))
        self.assertEqual(m["xc_distance_km"], 15.0)

    def test_modern_file_name(self):
        m = self.meta("fis_nk_coc_pdfs/2024/20231208_20231209_LILLEHAMMER_NOR/W/"
                      "4190_20231208_Gundersen_Normal_Hill_HS98_5.0_Km_COC_W_W_2024NK4190ROF.json")
        self.assertEqual((m["circuit"], m["season_start"], m["gender"], m["hill_size_m"], m["xc_distance_km"]),
                         ("COC", 2023, "W", 98.0, 5.0))
        self.assertIsNone(m["team"])

    def test_team_and_mixed(self):
        m = self.meta("fis_nk_pdfs/2024/20240315_20240317_TRONDHEIM_NOR/unknown/"
                      "4185_20240316_Team_Normal_Hill_HS105_WC_A_X_2024NK4185ROF.json")
        self.assertEqual((m["team"], m["gender"]), ("Team", "X"))

    def test_stale_nested_directory_is_ignored(self):
        self.assertIsNone(self.meta("fis_nk_pdfs/fis_nk_pdfs/2009/x/M/4123_20081129_G_M_2009NK4123ROF.json"))


class Helpers(unittest.TestCase):

    def test_split_name(self):
        self.assertEqual(load_json.split_name("WESTVOLD HANSEN Gyda"), ("WESTVOLD HANSEN", "Gyda"))
        self.assertEqual(load_json.split_name("MOAN Magnus H."), ("MOAN", "Magnus H."))
        self.assertEqual(load_json.split_name("LI Ji"), ("LI", "Ji"))

    def test_given_name_first(self):
        b = load_json.Build({("STORSVEEN Joergen Berget", "NOR"): ("BERGET STORSVEEN Joergen", "NOR")}, {})
        for name in ("BERGET STORSVEEN Joergen", "STORSVEEN Joergen Berget", "FLATLA Kasper Moen"):
            b.names_by_words[("NOR", frozenset(load_json.name_words(name)))].add(name)
        # known athlete: his spelling, through the alias list, whatever the word order
        self.assertEqual(b.surname_first("Jørgen Berget Storsveen", "NOR"), ("BERGET STORSVEEN Joergen", True))
        self.assertEqual(b.surname_first("Kasper Moen Flatla", "NOR"), ("FLATLA Kasper Moen", True))
        # unknown athlete, or known only for another nation: last word is the surname
        self.assertEqual(b.surname_first("Ingmar Wikstrøm Hilmarsen", "NOR"), ("HILMARSEN Ingmar Wikstroem", False))
        self.assertEqual(b.surname_first("Kasper Moen Flatla", "SWE"), ("FLATLA Kasper Moen", False))

    def test_alias_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "athletes.csv")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("name,nation,canonical_name,canonical_nation\n# comment\n"
                         "A One,NOR,A Two,NOR\nA Two,NOR,A Three,NOR\n")
            aliases = load_json.load_aliases(path)
        self.assertEqual(aliases[("A One", "NOR")], ("A Three", "NOR"))


class EndToEnd(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = os.path.join(self.tmp.name, "output")
        self.aliases = os.path.join(self.tmp.name, "aliases")
        os.makedirs(self.aliases)
        with open(os.path.join(self.aliases, "athletes.csv"), "w", encoding="utf-8") as fh:
            fh.write("name,nation,canonical_name,canonical_nation\nMOAN Magnus-H.,NOR,MOAN Magnus H.,NOR\n")
        with open(os.path.join(self.aliases, "venues.csv"), "w", encoding="utf-8") as fh:
            fh.write("name,country,canonical_name,canonical_country\nKuusamo,FIN,Ruka,FIN\n")

    def tearDown(self):
        if getattr(self, "conn", None):
            self.conn.close()               # Windows cannot delete an open database
        self.tmp.cleanup()

    def write(self, rel, doc):
        path = os.path.join(self.out, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(doc, fh)

    def build(self):
        db = os.path.join(self.tmp.name, "test.db")
        b = load_json.Build(load_json.load_aliases(os.path.join(self.aliases, "athletes.csv")),
                            load_json.load_aliases(os.path.join(self.aliases, "venues.csv")))
        load_json.build_database(self.out, b)
        load_json.write_sqlite(b, db)
        self.conn = sqlite3.connect(db)
        return b, self.conn

    def test_build(self):
        event = "fis_nk_pdfs/2024/20231123_20231126_RUKA_FIN/M/"
        self.write(event + "4129_20231125_Gundersen_Large_Hill_HS142_10.0_Km_WC_M_M_2024NK4129ROF.json", dict(
            doc_type="ROF", source_file="x", discipline="Gundersen", location="Kuusamo", country="FIN",
            competition_date="2023-11-25", event_name="WORLD CUP", parse_errors=[], warnings=[],
            course_info=dict(height_difference_m=44, maximum_climb_m=42, total_climb_m=89,
                             lap_length_m=2500, number_of_laps=4),
            jury=[dict(role="Race Director", name="OTTESEN Lasse", nation="FIS")],
            combined_results=[
                result(1, "RIIBER Jarl Magnus", "NOR"),
                result(2, "MOAN Magnus-H.", "NOR"),
                result(3, "LAMPARTER Johannes", "AUT", status="LAP", xc_time=None),
                result(None, "GEIGER Vinzenz", "GER", status="DNS"),
            ]))
        # Training list: nation missing for a known athlete, plus two junk rows
        self.write(event + "4129_20231124_Gundersen_Large_Hill_HS142_10.0_Km_WC_M_M_2024NK4129RLT.json", dict(
            doc_type="RLT", source_file="y", hill_data=dict(hill_size_m=142.0, k_point_m=120.0),
            jump_rounds=[
                dict(name="MOAN Magnus H.", nation=None, bib=5, round_number=1, distance_m=130.5),
                dict(name="SC Erzbergland 25", nation="APR", bib=6, round_number=1),
                dict(name="WORLD Viessmann", nation="CUP", bib=7, round_number=1),
            ]))
        # A ROF the parser flagged: document is recorded, rows are not loaded
        self.write(event + "4130_20231126_Gundersen_Large_Hill_HS142_10.0_Km_WC_M_M_2024NK4130ROF.json", dict(
            doc_type="ROF", source_file="z", discipline="Gundersen", location="Ruka", country="FIN",
            competition_date="2023-11-26", parse_errors=["no winner (rank 1 missing)"],
            combined_results=[result(2, "RIIBER Jarl Magnus", "NOR")]))

        b, conn = self.build()
        one = lambda sql: conn.execute(sql).fetchone()

        self.assertEqual(one("select count(*) from competitions")[0], 2)
        self.assertEqual(one("select name, country from venues"), ("Ruka", "FIN"))          # alias + one venue
        self.assertEqual(one("select label from seasons"), ("2023/2024",))
        self.assertEqual(one("select format, hill_size_m, xc_distance_km, gender, competition_date "
                             "from competitions where fis_codex='4129'"),
                         ("Gundersen", 142.0, 10.0, "M", "2023-11-25"))

        self.assertEqual(one("select count(*) from combined_results")[0], 4)                # flagged ROF skipped
        self.assertEqual(one("select count(*) from athletes")[0], 4)                         # no junk athletes
        self.assertEqual(one("select full_name, last_name, first_name from athletes where full_name like 'MOAN%'"),
                         ("MOAN Magnus H.", "MOAN", "Magnus H."))                            # merged by alias
        self.assertEqual(one("select count(*) from training_jump_results")[0], 1)
        self.assertEqual(one("select raw_nation from training_jump_results"), ("NOR",))      # nation recovered
        self.assertEqual(one("select status, rank from combined_results where raw_name like 'LAMPARTER%'"),
                         ("LAP", 3))
        self.assertEqual(one("select height_m, max_climb_m, total_climb_m, length_km, number_of_laps "
                             "from course_info"), (44.0, 42.0, 89.0, 2.5, 4))
        self.assertEqual(one("select last_name, first_name, nation from jury_officials"),
                         ("OTTESEN", "Lasse", "FIS"))
        self.assertEqual(conn.execute("pragma foreign_key_check").fetchall(), [])
        self.assertTrue(any("failed validation" in reason for reason, _ in b.skipped_docs))


    def test_cup_standings(self):
        event = "fis_nk_pdfs/2024/20231123_20231126_RUKA_FIN/M/"
        self.write(event + "4129_20231125_Gundersen_Large_Hill_HS142_10.0_Km_WC_M_M_2024NK4129ROF.json", dict(
            doc_type="ROF", source_file="x", discipline="Gundersen", location="Ruka", country="FIN",
            competition_date="2023-11-25", parse_errors=[],
            combined_results=[result(1, "RIIBER Jarl Magnus", "NOR"), result(2, "MOAN Magnus-H.", "NOR")]))
        standings = os.path.join(self.tmp.name, "standings")
        os.makedirs(standings)
        with open(os.path.join(standings, "WC_2024_M.json"), "w", encoding="utf-8") as fh:
            json.dump(dict(cup="WC", season=2024, gender="M",
                           disciplines={"ALL": "Overall", "BJT": "Best Jumper Trophy"},
                           rows=[
                               dict(competitor_id="157270", name="RIIBER Jarl Magnus", nation="NOR",
                                    standings={"ALL": {"rank": 1, "points": 1870}, "BJT": {"rank": 1, "points": 1830}}),
                               # spelled as in the alias list, not as in the result list
                               dict(competitor_id="33333", name="MOAN Magnus H.", nation="NOR",
                                    standings={"ALL": {"rank": 2, "points": 900}}),
                               # scored points in a race whose result list is not in the database
                               dict(competitor_id="44444", name="NOBODY Else", nation="FIN",
                                    standings={"ALL": {"rank": 3, "points": 5}}),
                               dict(competitor_id="55555", name="UNRANKED One", nation="FIN", standings={}),
                           ]), fh)

        db = os.path.join(self.tmp.name, "test.db")
        b = load_json.Build(load_json.load_aliases(os.path.join(self.aliases, "athletes.csv")), {})
        load_json.build_database(self.out, b, standings)
        load_json.write_sqlite(b, db)
        self.conn = sqlite3.connect(db)
        rows = self.conn.execute(
            "select t.discipline_code, t.rank, t.points, t.raw_name, a.full_name, a.fis_id, s.label, t.circuit, t.gender "
            "from cup_standings t join seasons s on s.id = t.season_id left join athletes a on a.id = t.athlete_id "
            "order by t.discipline_code, t.rank").fetchall()
        self.assertEqual(rows, [
            ("ALL", 1, 1870, "RIIBER Jarl Magnus", "RIIBER Jarl Magnus", "157270", "2023/2024", "WC", "M"),
            ("ALL", 2, 900, "MOAN Magnus H.", "MOAN Magnus H.", "33333", "2023/2024", "WC", "M"),
            ("ALL", 3, 5, "NOBODY Else", None, None, "2023/2024", "WC", "M"),
            ("BJT", 1, 1830, "RIIBER Jarl Magnus", "RIIBER Jarl Magnus", "157270", "2023/2024", "WC", "M"),
        ])
        self.assertEqual(self.conn.execute("select count(*) from athletes").fetchone()[0], 2)   # none invented
        self.assertEqual(b.standings_unmatched, {"NOBODY Else [FIN]", "UNRANKED One [FIN]"})

    def test_team_competition(self):
        event = "fis_nk_pdfs/2020/20200124_20200126_OBERSTDORF_GER/M/"
        # An individual result list makes NOR / GER known nations and introduces one athlete
        self.write(event + "4142_20200124_Gundersen_HS140_10.0_Km_WC_M_M_2020NK4142ROF.json", dict(
            doc_type="ROF", source_file="i", discipline="Gundersen", location="Oberstdorf", country="GER",
            competition_date="2020-01-24", parse_errors=[],
            combined_results=[result(1, "RIIBER Jarl Magnus", "NOR"), result(2, "GEIGER Vinzenz", "GER")]))
        self.write(event + "4143_20200125_Team_HS140_4x5_Km_WC_M_M_2020NK4143ROF.json", dict(
            doc_type="ROF", source_file="t", discipline="Team", location="Oberstdorf", country="GER",
            competition_date="2020-01-25", parse_errors=[], combined_results=[],
            team_results=[
                dict(rank=1, bib=1, nation="NOR", team_name="Norway", jump_points=568.0, jump_rank=1,
                     time_difference="0:00", xc_time="51:03.4", xc_rank=4, time_behind="51:03.4", status=None,
                     members=[dict(leg=1, bib="1-1", name="GRAABAK Joergen", jump_points=135.5, xc_time="12:42.2"),
                              dict(leg=2, bib="1-2", name="RIIBER Jarl Magnus", jump_points=143.3, xc_time="12:54.8")]),
                dict(rank=None, bib=4, nation="GER", team_name="Germany", jump_points=488.4, jump_rank=4,
                     time_difference="+1:46", xc_time=None, xc_rank=None, time_behind=None, status="DNF",
                     members=[dict(leg=1, bib="4-1", name="GEIGER Vinzenz", jump_points=106.5, xc_time=None)]),
            ]))

        b, conn = self.build()
        one = lambda sql: conn.execute(sql).fetchone()
        self.assertEqual(one("select format, xc_distance_km from competitions where fis_codex='4143'"), ("Team", 5.0))
        self.assertEqual(conn.execute("select rank, nation, team_name, total_time, status from team_results "
                                      "order by id").fetchall(),
                         [(1, "NOR", "Norway", "51:03.4", None), (None, "GER", "Germany", None, "DNF")])
        self.assertEqual(one("select count(*), count(athlete_id) from team_members"), (3, 3))
        # the team athlete is the same person as in the individual competition
        self.assertEqual(one("select count(*) from athletes where full_name='RIIBER Jarl Magnus'")[0], 1)
        self.assertEqual(one("select count(*) from combined_results r join competitions c on c.id=r.competition_id "
                             "where c.fis_codex='4143'")[0], 0)
        self.assertEqual(conn.execute("pragma foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
