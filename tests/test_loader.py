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


if __name__ == "__main__":
    unittest.main()
