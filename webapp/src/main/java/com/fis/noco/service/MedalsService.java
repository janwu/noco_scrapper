package com.fis.noco.service;

import com.fis.noco.service.RecordsService.NationMode;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * Medal tables of the World Championships (with the Olympic Games until 1980):
 * gold, silver and bronze of athletes and nations, individual and team.
 *
 * A team medal counts once for its nation and once for each athlete of the team.
 * Nations that no longer exist are counted as in {@link RecordsService.NationMode}.
 */
@Service
public class MedalsService {

    public record Medals(Long athleteId, String name, String nation,
                         int gold, int silver, int bronze, int teamGold, int teamSilver, int teamBronze,
                         String firstYear, String lastYear) {

        public int total(boolean teams) {
            return gold + silver + bronze + (teams ? teamGold + teamSilver + teamBronze : 0);
        }

        public int gold(boolean teams) { return gold + (teams ? teamGold : 0); }
        public int silver(boolean teams) { return silver + (teams ? teamSilver : 0); }
        public int bronze(boolean teams) { return bronze + (teams ? teamBronze : 0); }
    }

    /** One medal: who, of which nation, which colour (1-3), team or not, when. */
    private record Medal(Long athleteId, String name, String athleteNation, String printedNation,
                         int rank, boolean team, String date) {
    }

    private static final String GENDER = "AND (? IS NULL OR c.gender = ?) ";

    private final JdbcTemplate jdbc;

    public MedalsService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** gender "M", "W", or null for all (mixed teams only then). */
    private List<Medal> individual(String gender) {
        return jdbc.query("""
                SELECT a.id, COALESCE(a.display_name, a.full_name), a.nationality, UPPER(r.raw_nation),
                       r.rank, c.competition_date
                FROM combined_results r
                JOIN competitions c ON c.id = r.competition_id
                JOIN athletes a ON a.id = r.athlete_id
                WHERE c.circuit = 'WSC' AND r.rank BETWEEN 1 AND 3
                  AND (c.format IS NULL OR c.format NOT LIKE 'Team%')
                """ + GENDER,
                (rs, i) -> new Medal(rs.getLong(1), rs.getString(2), rs.getString(3), rs.getString(4),
                        rs.getInt(5), false, rs.getString(6)),
                gender, gender);
    }

    /** Team medals, one line per athlete of the team (athlete null for a team without its athletes). */
    private List<Object[]> teamLines(String gender) {
        return jdbc.query("""
                SELECT t.id, UPPER(t.nation), t.rank, c.competition_date,
                       a.id, COALESCE(a.display_name, a.full_name), a.nationality
                FROM team_results t
                JOIN competitions c ON c.id = t.competition_id
                LEFT JOIN team_members m ON m.team_result_id = t.id
                LEFT JOIN athletes a ON a.id = m.athlete_id
                WHERE c.circuit = 'WSC' AND t.rank BETWEEN 1 AND 3
                """ + GENDER,
                (rs, i) -> new Object[]{rs.getLong(1), rs.getString(2), rs.getInt(3), rs.getString(4),
                        rs.getObject(5) == null ? null : rs.getLong(5), rs.getString(6), rs.getString(7)},
                gender, gender);
    }

    /** Every athlete with a medal, best first (gold, silver, bronze; with or without team medals). */
    public List<Medals> athletes(String gender, boolean teams) {
        List<Medal> medals = new ArrayList<>(individual(gender));
        for (Object[] line : teamLines(gender)) {
            if (line[4] != null) {
                medals.add(new Medal((Long) line[4], (String) line[5], (String) line[6], (String) line[1],
                        (Integer) line[2], true, (String) line[3]));
            }
        }
        Map<Long, List<Medal>> byAthlete = medals.stream()
                .collect(Collectors.groupingBy(Medal::athleteId, LinkedHashMap::new, Collectors.toList()));
        List<Medals> table = new ArrayList<>();
        byAthlete.forEach((id, list) -> table.add(count(id, list.get(0).name(), list.get(0).athleteNation(), list)));
        return sorted(table.stream().filter(m -> m.total(teams) > 0).toList(), teams);
    }

    /** Medals of each nation; a team medal once per team. */
    public List<Medals> nations(String gender, NationMode mode, boolean eastGermanyWithGermany, boolean teams) {
        List<Medal> medals = new ArrayList<>();
        for (Medal m : individual(gender)) {
            medals.add(new Medal(null, null, null, nation(m.printedNation(), m.athleteNation(), mode,
                    eastGermanyWithGermany), m.rank(), false, m.date()));
        }
        // a team: its printed nation, or (athlete's nation) the nation most of its athletes ended with
        Map<Long, List<Object[]>> byTeam = teamLines(gender).stream()
                .collect(Collectors.groupingBy(l -> (Long) l[0], LinkedHashMap::new, Collectors.toList()));
        for (List<Object[]> lines : byTeam.values()) {
            Object[] first = lines.get(0);
            String printed = (String) first[1];
            if ("FIS".equals(printed)) continue;                 // a team of two nations
            String athletes = lines.stream().map(l -> (String) l[6]).filter(n -> n != null)
                    .collect(Collectors.groupingBy(Function.identity(), Collectors.counting()))
                    .entrySet().stream().max(Map.Entry.comparingByValue()).map(Map.Entry::getKey).orElse(null);
            medals.add(new Medal(null, null, null, nation(printed, athletes, mode, eastGermanyWithGermany),
                    (Integer) first[2], true, (String) first[3]));
        }
        Map<String, List<Medal>> byNation = medals.stream().filter(m -> m.printedNation() != null)
                .collect(Collectors.groupingBy(Medal::printedNation, HashMap::new, Collectors.toList()));
        List<Medals> table = new ArrayList<>();
        byNation.forEach((nation, list) -> table.add(count(null, nation, nation, list)));
        return sorted(table.stream().filter(m -> m.total(teams) > 0).toList(), teams);
    }

    private static String nation(String printed, String athleteNation, NationMode mode, boolean eastGermany) {
        String nation = RecordsService.nationOf(printed, athleteNation, mode);
        return eastGermany && "GDR".equals(nation) ? "GER" : nation;
    }

    private static Medals count(Long id, String name, String nation, List<Medal> list) {
        int[] n = new int[6];
        for (Medal m : list) n[(m.team() ? 3 : 0) + m.rank() - 1]++;
        String first = list.stream().map(Medal::date).min(String::compareTo).orElse("").substring(0, 4);
        String last = list.stream().map(Medal::date).max(String::compareTo).orElse("").substring(0, 4);
        return new Medals(id, name, nation, n[0], n[1], n[2], n[3], n[4], n[5], first, last);
    }

    /** Gold first, then silver, then bronze (the Olympic way). */
    public static List<Medals> sorted(List<Medals> table, boolean teams) {
        return table.stream().sorted(Comparator.comparingInt((Medals m) -> m.gold(teams)).reversed()
                .thenComparing(Comparator.comparingInt((Medals m) -> m.silver(teams)).reversed())
                .thenComparing(Comparator.comparingInt((Medals m) -> m.bronze(teams)).reversed())
                .thenComparing(Medals::name)).toList();
    }
}
