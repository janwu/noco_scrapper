package com.fis.noco;

import com.fis.noco.service.MedalsService;
import com.fis.noco.service.MedalsService.Medals;
import com.fis.noco.service.RecordsService.NationMode;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import java.io.File;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** World Championship medal tables on the real database. */
@SpringBootTest
class MedalsTest {

    @Autowired
    private MedalsService medals;
    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void database() {
        Assumptions.assumeTrue(new File("../db/noco.db").exists(), "database not built");
    }

    private int sum(List<Medals> rows, java.util.function.ToIntFunction<Medals> f) {
        return rows.stream().mapToInt(f).sum();
    }

    @Test
    void frenzel() {
        Medals frenzel = medals.athletes("WSC", "M", true).stream()
                .filter(m -> m.name().startsWith("FRENZEL Eric")).findFirst().orElseThrow();
        assertEquals(List.of(3, 1, 1, 4), List.of(frenzel.gold(), frenzel.silver(), frenzel.bronze(), frenzel.teamGold()));
    }

    @Test
    void nationsHaveEveryIndividualAndTeamMedalOnce() {
        int individualGold = jdbc.queryForObject("""
                SELECT COUNT(*) FROM combined_results r JOIN competitions c ON c.id = r.competition_id
                WHERE c.circuit = 'WSC' AND c.gender = 'M' AND r.rank = 1 AND c.format NOT LIKE 'Team%'""", Integer.class);
        int teamGold = jdbc.queryForObject("""
                SELECT COUNT(*) FROM team_results t JOIN competitions c ON c.id = t.competition_id
                WHERE c.circuit = 'WSC' AND c.gender = 'M' AND t.rank = 1 AND UPPER(t.nation) <> 'FIS'""", Integer.class);
        List<Medals> nations = medals.nations("WSC", "M", NationMode.AT_THE_TIME, false, true);
        assertEquals(individualGold, sum(nations, Medals::gold));
        assertEquals(teamGold, sum(nations, Medals::teamGold));
        assertEquals("NOR", nations.get(0).nation());
        assertFalse(nations.stream().anyMatch(m -> m.nation().equals("FRG")));
        assertTrue(nations.stream().anyMatch(m -> m.nation().equals("GDR")));
        assertFalse(medals.nations("WSC", "M", NationMode.AT_THE_TIME, true, true).stream()
                .anyMatch(m -> m.nation().equals("GDR")));
    }

    @Test
    void olympicGamesUntil1980AreWorldChampionshipsToo() {
        // the same medals in both tables for 1924-1980: the gold of 1964 (Innsbruck) in each
        String gold = """
                SELECT a.full_name FROM combined_results r JOIN competitions c ON c.id = r.competition_id
                JOIN athletes a ON a.id = r.athlete_id WHERE c.circuit = ? AND c.competition_date LIKE '1964-%'
                AND r.rank = 1""";
        assertEquals(jdbc.queryForObject(gold, String.class, "WSC"), jdbc.queryForObject(gold, String.class, "OWG"));
        List<Medals> olympic = medals.nations("OWG", "M", NationMode.AT_THE_TIME, false, true);
        int games = jdbc.queryForObject("""
                SELECT COUNT(DISTINCT SUBSTR(competition_date, 1, 4)) FROM competitions WHERE circuit = 'OWG'""",
                Integer.class);
        assertEquals(25, games);                                   // 1924-2026, none in 1940 and 1944
        assertTrue(sum(olympic, Medals::gold) >= games);
    }

    @Test
    void withoutTeamMedals() {
        List<Medals> rows = medals.athletes("WSC", "M", false);
        assertTrue(rows.stream().allMatch(m -> m.total(false) > 0));
        assertTrue(rows.get(0).gold(false) >= rows.get(1).gold(false));
    }
}
