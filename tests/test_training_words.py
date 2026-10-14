"""The word-position parser of training and trial lists, on words placed as in real lists."""
import unittest

from fis_parser.extractors.training_words import parse_training_page


def line(top, *words):
    """words: (text, x centre) pairs; the width of a word does not matter here."""
    return [{'text': t, 'x0': x - 5, 'x1': x + 5, 'top': top} for t, x in words]


class TrainingWordsTest(unittest.TestCase):

    def test_trial_round_two_athletes_per_line(self):
        # FIS 2019/20 trial round: one athlete in each half of the page
        words = (line(204, ('BIB', 39), ('NAME', 57), ('NSA', 150), ('[km/h]', 179), ('[m]', 212), ('GATE', 234),
                      ('[m/s]', 259), ('BIB', 313), ('NAME', 331), ('NSA', 424), ('[km/h]', 453), ('[m]', 485),
                      ('GATE', 508), ('[m/s]', 532))
                 + line(211, ('RANK', 184), ('RANK', 213), ('RANK', 457), ('RANK', 486))
                 + line(220.7, ('89.4', 181), ('95.5', 210), ('21', 237), ('1.11', 259), ('2.9', 285),
                        ('120.0', 481), ('21', 511), ('0.67', 532), ('52.2', 557))
                 + line(224.2, ('1', 41), ('SALMELA', 67), ('Olli', 92), ('FIN', 151),
                        ('31', 312), ('KUPCZAK', 338), ('Szczepan', 363), ('POL', 425))
                 + line(231, ('52.', 184), ('48.', 213), ('2.', 457), ('13.', 486)))
        rows = parse_training_page(words, 595)
        self.assertEqual([(r.name, r.nation, r.bib, r.speed_kmh, r.distance_m, r.gate, r.wind_ms) for r in rows],
                         [('SALMELA Olli', 'FIN', 1, 89.4, 95.5, 21, 1.11),
                          ('KUPCZAK Szczepan', 'POL', 31, None, 120.0, 21, 0.67)])

    def test_training_round_left_out(self):
        # three rounds; the athlete jumped the first and the third only
        words = (line(230, ('Speed', 218), ('Distance', 257), ('Gate', 296), ('Speed', 336), ('Distance', 375),
                      ('Gate', 414), ('Speed', 454), ('Distance', 493), ('Gate', 533))
                 + line(235, ('Bib', 47), ('Name', 74), ('Nat', 187))
                 + line(248, ('Club', 72), ('Rank', 218), ('Rank', 257), ('Rank', 296))
                 + line(260.8, ('KITAMURA', 84), ('Takashi', 120), ('JPN', 185), ('92.3', 224), ('73.0', 263),
                        ('14', 306), ('92.0', 460), ('96.0', 500), ('12', 543))
                 + line(265.6, ('1', 51))
                 + line(270.8, ('Tokyo', 73), ('Biso', 90), ('5', 158), ('MAY', 169), ('1977', 185), ('46.', 226)))
        rows = parse_training_page(words, 595)
        self.assertEqual([(r.round_number, r.distance_m, r.speed_kmh, r.gate) for r in rows],
                         [(1, 73.0, 92.3, 14), (3, 96.0, 92.0, 12)])
        self.assertEqual({(r.name, r.nation, r.bib) for r in rows}, {('KITAMURA Takashi', 'JPN', 1)})

    def test_nation_is_not_the_month_of_the_birth_date(self):
        words = (line(205, ('BIB', 39), ('NAME', 59), ('NSA', 177), ('[km/h]', 203), ('[m]', 230), ('GATE', 258),
                      ('[m/s]', 281))
                 + line(213.5, ('RANK', 204), ('RANK', 227))
                 + line(222.9, ('LUND', 59), ('Even', 81), ('Leinan', 105), ('NOR', 178), ('92.6', 205),
                        ('112.0', 226), ('28', 262), ('-0.24', 280))
                 + line(226, ('1', 41))
                 + line(230.5, ('Tolga', 55), ('Il', 65), ('7', 160), ('APR', 168), ('2005', 180)))
        rows = parse_training_page(words, 595)
        self.assertEqual([(r.name, r.nation, r.distance_m) for r in rows], [('LUND Even Leinan', 'NOR', 112.0)])

    def test_page_without_column_header(self):
        self.assertEqual(parse_training_page(line(100, ('Weather', 50), ('Information', 100)), 595), [])


if __name__ == '__main__':
    unittest.main()
