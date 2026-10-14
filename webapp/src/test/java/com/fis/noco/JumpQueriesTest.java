package com.fis.noco;

import com.fis.noco.entity.JumpResult;
import com.fis.noco.service.AthleteService;
import com.fis.noco.service.CompetitionService;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import java.io.File;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** The jump list queries against the real database, read outside a transaction as the views do. */
@SpringBootTest
class JumpQueriesTest {

    @Autowired
    private CompetitionService competitionService;
    @Autowired
    private AthleteService athleteService;
    @Autowired
    private JdbcTemplate jdbc;

    private static void assumeDatabase() {
        Assumptions.assumeTrue(new File("../db/noco.db").exists(), "database not built");
    }

    @Test
    void jumpListsOfACompetition() {
        assumeDatabase();
        // a World Cup competition with a qualification round
        Long competitionId = jdbc.queryForObject(
                "select j.competition_id from jump_round_results j join competition_documents d on d.id = j.document_id " +
                "where d.doc_type = 'RLQ' limit 1", Long.class);

        Map<String, List<JumpResult>> lists = competitionService.getJumpLists(competitionId);

        assertTrue(lists.containsKey("Competition Round"));
        assertTrue(lists.containsKey("Qualification"));
        List<JumpResult> round = lists.get("Competition Round");
        assertEquals(1, round.get(0).getRank());
        for (JumpResult j : round) {
            assertFalse(j.getDisplayName().isBlank());
            assertNotNull(j.getListLabel());
            if (j.getRank() != null) {
                assertNotNull(j.getDistanceM());
                assertEquals(5, j.getMarks().split(" ").length);
            }
        }
    }

    @Test
    void trainingAndTrialRoundsOfACompetition() {
        assumeDatabase();
        Long competitionId = jdbc.queryForObject(
                "select c.id from competitions c where exists (select 1 from training_jump_results t where t.competition_id = c.id)" +
                " and exists (select 1 from trial_round_results t where t.competition_id = c.id)" +
                " and exists (select 1 from jump_round_results t where t.competition_id = c.id) limit 1", Long.class);
        Map<String, List<JumpResult>> lists = competitionService.getJumpLists(competitionId);
        assertEquals(List.of("Competition Round", "Trial Round", "Training"),
                lists.keySet().stream().filter(k -> !k.equals("Provisional Round") && !k.equals("Qualification")).toList());
        Integer training = jdbc.queryForObject(
                "select count(*) from training_jump_results where competition_id = ?", Integer.class, competitionId);
        assertEquals(training, lists.get("Training").size());
        for (JumpResult j : lists.get("Training")) {
            assertNotNull(j.getDistanceM());
            assertNotNull(j.getRoundNumber());
        }
    }

    @Test
    void jumpsOfAnAthlete() {
        assumeDatabase();
        Long athleteId = jdbc.queryForObject(
                "select athlete_id from v_all_jumps group by athlete_id order by count(*) desc limit 1", Long.class);
        Integer expected = jdbc.queryForObject(
                "select count(*) from v_all_jumps where athlete_id = ?", Integer.class, athleteId);

        List<JumpResult> jumps = athleteService.getJumps(athleteId);

        assertEquals(expected, jumps.size());
        String previous = null;
        for (JumpResult j : jumps) {
            assertNotNull(j.getCompetition().getDisplayLocation());
            assertNotNull(j.getCompetition().getCircuit());
            String date = j.getCompetition().getCompetitionDate();
            if (previous != null && date != null) {
                assertTrue(previous.compareTo(date) >= 0, "newest first");
            }
            previous = date;
        }
    }
}
