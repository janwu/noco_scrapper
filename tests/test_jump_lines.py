"""The jump line parser on text lines copied from real lists (one per layout family)."""
import unittest

from fis_parser.extractors.jump_lines import parse_jump_lines

HEADER = 'Club Date of Birth [km/h] [m] Points A B C D E Points Gate Points [m/s] Points Total Diff.'


def parse(lines, hill=None):
    return parse_jump_lines([[HEADER] + lines], hill)


class JumpLinesTest(unittest.TestCase):

    def test_name_line_rank_line_club_line(self):
        rows = parse([
            'KLEMETSEN Haavard NOR',
            '2. 48 88.2 94.0 68.0 18.5 18.0 18.5 18.5 19.0 55.5 25 -3.6 -0.21 1.3 121.2 +0:02',
            'Kautokeino IL 5 JAN 1979',
        ])
        r = rows[0]
        self.assertEqual((r.rank, r.bib, r.name, r.nation), (2, 48, 'KLEMETSEN Haavard', 'NOR'))
        self.assertEqual((r.speed_kmh, r.distance_m, r.dist_points), (88.2, 94.0, 68.0))
        self.assertEqual((r.judge_a, r.judge_e, r.style_points), (18.5, 19.0, 55.5))
        self.assertEqual((r.gate, r.gate_comp_pts, r.wind_ms, r.wind_comp_pts), (25, -3.6, -0.21, 1.3))
        self.assertEqual((r.total_points, r.pursuit_time_diff), (121.2, '+0:02'))
        self.assertEqual((r.club, r.date_of_birth), ('Kautokeino IL', '1979-01-05'))

    def test_total_on_the_name_line_time_on_the_club_line(self):
        # Continental Cup by ewoxx, 2013/14-2021/22
        r = parse([
            'BOESL Wolfgang GER 118.2',
            '2. 54 84.4 95.5 71.0 17.5 18.0 17.0 18.5 18.0 53.5 23 3.2 1.49 -9.5',
            'SK Berchtesgaden 19 AUG 1989 00:05',
        ])[0]
        self.assertEqual((r.total_points, r.gate_comp_pts, r.wind_comp_pts), (118.2, 3.2, -9.5))
        self.assertEqual(r.pursuit_time_diff, '00:05')

    def test_two_jumps_with_marks_printed_without_gaps(self):
        # World Cup 2001/02: first jump on the name line, second on the club line
        rows = parse([
            'SCHMITT Thorsten 94.7 124.0 64.8 17.518.017.018.018.0 53.5 118.3 1. 223.4',
            '1. 14 GER',
            'SC Furtwangen 95.0 113.0 51.6 18.018.017.517.518.0 53.5 105.1 8. 0:00',
        ])
        self.assertEqual([r.round_number for r in rows], [1, 2])
        self.assertEqual([r.total_points for r in rows], [118.3, 105.1])
        self.assertEqual({(r.name, r.nation, r.rank, r.bib) for r in rows}, {('SCHMITT Thorsten', 'GER', 1, 14)})
        self.assertEqual(rows[1].judge_c, 17.5)

    def test_tour_points_taken_along_and_gate_changed_by_the_coach(self):
        r = parse([
            'LAMPARTER Johannes AUT 131.6',
            '2. 2 -8.0 90.5 99.0 60.0 18.0 17.0 17.0 18.0 18.0 53.0 16 -1.55 18.6 123.6 +0:06',
            'Nordic Team Absam 8 NOV 2001 5.',
        ])[0]
        self.assertEqual(r.total_points, 131.6)             # the jump, not the running total
        r = parse([
            'LAMPARTER Johannes AUT',
            '2. 52 88.9 143.5 102.3 18.0 18.5 18.5 18.5 18.5 55.5 17→©16 16.3 0.91 -10.6 163.5 +0:32',
            'Nordic Team Absam 8 NOV 2001',
        ])[0]
        self.assertEqual((r.gate, r.gate_comp_pts, r.total_points), (16, 16.3, 163.5))

    def test_three_judges(self):
        r = parse([
            'DEUSCHL Christian AUT 133.7',
            '1. 17 86.7 101.5 83.0 18.5 18.0 18.5 55.0 18 0.54 -4.3',
            'Nordic Team Absam-Tirol 20 APR 1997 00:00',
        ])[0]
        self.assertEqual((r.judge_c, r.judge_d, r.style_points, r.total_points), (18.5, None, 55.0, 133.7))

    def test_team_members_take_rank_and_nation_of_the_team(self):
        rows = parse([
            '473.9',
            '1. 9 GER - GERMANY 473.9',
            '0:00',
            'FAISST Manuel',
            '9-1 88.7 101.0 72.0 18.5 19.0 19.0 19.0 18.5 56.5 18 1.03 -7.2 121.3 2.',
            'SV Baiersbronn',
            'RYDZEK Johannes',
            '9-2 DSQ ICR 4.2.2.2 0.0',
            'SC 1906 Oberstdorf',
            '455.9',
            '2. 8 NOR - NORWAY 455.9',
            '+0:24',
            'GRAABAK Joergen',
            '8-1 88.0 99.5 69.0 18.5 18.5 18.5 18.5 18.5 55.5 18 0.80 -5.6 118.9 3.',
            'Byaasen IL',
        ])
        self.assertEqual([(r.name, r.nation, r.rank, r.bib) for r in rows],
                         [('FAISST Manuel', 'GER', 1, 9), ('RYDZEK Johannes', 'GER', 1, 9),
                          ('GRAABAK Joergen', 'NOR', 2, 8)])
        self.assertEqual((rows[0].total_points, rows[0].club), (121.3, 'SV Baiersbronn'))
        self.assertTrue(rows[1].dsq)
        self.assertEqual(rows[1].dsq_reason, 'ICR 4.2.2.2')

    def test_lists_after_the_ranking(self):
        rows = parse([
            'SEIDL Mario AUT',
            '1. 2 89.3 90.5 61.0 17.0 17.5 18.0 18.0 17.5 53.0 24 -1.25 7.8 121.8 0:00',
            'TSU St. Veit 8 DEC 1992',
            'Disqualified',
            '16 PITTIN Alessandro ITA SCE 4',
            'Did not start',
            '11 GOTTWALD Felix AUT',
        ])
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[1].dsq and rows[1].dsq_reason == 'SCE 4' and rows[1].nation == 'ITA')
        self.assertTrue(rows[2].dns and rows[2].name == 'GOTTWALD Felix' and rows[2].rank is None)

    def test_mass_start_without_marks(self):
        rows = parse_jump_lines([[
            'Club Date of Birth [km/h] [m] Points Points Rank',
            'DENIFL Wilhelm AUT',
            '1. 15 95.1 142.5 81.0 -4.8 76.2 1. 76.2',
            'SV Innsbruck - Bergisel 10 NOV 1980',
        ]])
        r = rows[0]
        self.assertEqual((r.name, r.distance_m, r.dist_points, r.total_points, r.style_points),
                         ('DENIFL Wilhelm', 142.5, 81.0, 76.2, None))


if __name__ == '__main__':
    unittest.main()
