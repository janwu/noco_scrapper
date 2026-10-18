package com.fis.noco.service;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * All-time World Cup records: the athletes and nations with the most wins, podiums
 * and top-10 places in individual competitions (team events left out).
 *
 * Until 1998/99 the FIS database has the first 15 of a competition only; wins,
 * podiums and top 10 are complete all the same.
 */
@Service
public class RecordsService {

    /** How a result of a nation that no longer exists is counted. */
    public enum NationMode {
        /**
         * The nation the result was won for.  West Germany is counted with the
         * unified Germany and Yugoslavia with Slovenia (its Nordic combined athletes
         * were Slovenes); East Germany, the Soviet Union, the CIS of 1992 and
         * Czechoslovakia are states of their own that no longer exist.
         */
        AT_THE_TIME,
        /**
         * The athlete's last nation: a Soviet result of an Estonian counts for Estonia,
         * an East German one of an athlete who later competed for Germany for Germany.
         */
        ATHLETE
    }

    /** Successor nations for {@link NationMode#AT_THE_TIME}; GUS is the German code of the CIS. */
    static final Map<String, String> SUCCESSOR = Map.of(
            "FRG", "GER", "BRD", "GER", "DDR", "GDR",
            "YUG", "SLO", "JUG", "SLO", "GUS", "CIS", "EUN", "CIS", "URS", "SOV");

    public record Count(Long athleteId, String name, String nation, int wins, int podiums, int top10,
                        String firstWin, String lastWin) {
    }

    private static final String INDIVIDUAL_WC = """
            FROM combined_results r
            JOIN competitions c ON c.id = r.competition_id
            JOIN athletes a ON a.id = r.athlete_id
            WHERE c.circuit = 'WC' AND c.gender = ? AND r.rank BETWEEN 1 AND 10
              AND (c.format IS NULL OR (c.format NOT LIKE 'Team%' AND c.format <> 'Provisional Round'))
            """;

    private final JdbcTemplate jdbc;

    public RecordsService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    /** Every athlete with a top-10 place, with wins, podiums and top 10. */
    public List<Count> athletes(String gender) {
        return jdbc.query("""
                SELECT a.id, COALESCE(a.display_name, a.full_name) AS name, a.nationality,
                       SUM(r.rank = 1) AS wins, SUM(r.rank <= 3) AS podiums, COUNT(*) AS top10,
                       MIN(CASE WHEN r.rank = 1 THEN c.competition_date END) AS first_win,
                       MAX(CASE WHEN r.rank = 1 THEN c.competition_date END) AS last_win
                """ + INDIVIDUAL_WC + "GROUP BY a.id",
                (rs, i) -> new Count(rs.getLong(1), rs.getString(2), rs.getString(3),
                        rs.getInt(4), rs.getInt(5), rs.getInt(6), rs.getString(7), rs.getString(8)),
                gender);
    }

    /** The athletes ordered by one count (then the others, then the earlier first win). */
    public static List<Count> top(List<Count> athletes, java.util.function.ToIntFunction<Count> by, int limit) {
        return athletes.stream().filter(a -> by.applyAsInt(a) > 0)
                .sorted(Comparator.comparingInt(by).reversed()
                        .thenComparing(Comparator.comparingInt(Count::wins).reversed())
                        .thenComparing(Comparator.comparingInt(Count::podiums).reversed())
                        .thenComparing(Count::top10, Comparator.reverseOrder()))
                .limit(limit).toList();
    }

    /** Wins, podiums and top 10 of each nation, most wins first. */
    public List<Count> nations(String gender, NationMode mode) {
        return nations(gender, mode, false);
    }

    /** With {@code eastGermanyWithGermany} the GDR is counted with Germany too, like the FRG. */
    public List<Count> nations(String gender, NationMode mode, boolean eastGermanyWithGermany) {
        List<Object[]> rows = jdbc.query("""
                SELECT UPPER(r.raw_nation), a.nationality, r.rank, c.competition_date
                """ + INDIVIDUAL_WC,
                (rs, i) -> new Object[]{rs.getString(1), rs.getString(2), rs.getInt(3), rs.getString(4)},
                gender);
        Map<String, int[]> counts = new LinkedHashMap<>();
        Map<String, String[]> wins = new LinkedHashMap<>();
        for (Object[] row : rows) {
            String nation = nationOf((String) row[0], (String) row[1], mode);
            if (nation == null) continue;
            if (eastGermanyWithGermany && nation.equals("GDR")) nation = "GER";
            int rank = (Integer) row[2];
            int[] n = counts.computeIfAbsent(nation, k -> new int[3]);
            if (rank == 1) {
                n[0]++;
                String day = (String) row[3];
                String[] span = wins.computeIfAbsent(nation, k -> new String[]{day, day});
                if (day.compareTo(span[0]) < 0) span[0] = day;
                if (day.compareTo(span[1]) > 0) span[1] = day;
            }
            if (rank <= 3) n[1]++;
            n[2]++;
        }
        return counts.entrySet().stream()
                .map(e -> {
                    String[] span = wins.getOrDefault(e.getKey(), new String[2]);
                    return new Count(null, e.getKey(), e.getKey(), e.getValue()[0], e.getValue()[1],
                            e.getValue()[2], span[0], span[1]);
                })
                .sorted(Comparator.comparingInt(Count::wins).reversed()
                        .thenComparing(Comparator.comparingInt(Count::podiums).reversed())
                        .thenComparing(Count::top10, Comparator.reverseOrder()))
                .toList();
    }

    static String nationOf(String printed, String athleteNation, NationMode mode) {
        // 'AIN' is how the FIS database of today gives Russians and Belarusians of past years
        boolean neutral = "AIN".equalsIgnoreCase(printed) && athleteNation != null;
        String nation = (mode == NationMode.ATHLETE || neutral) && athleteNation != null ? athleteNation : printed;
        if (nation == null) return null;
        nation = nation.toUpperCase();
        return SUCCESSOR.getOrDefault(nation, nation);
    }
}
