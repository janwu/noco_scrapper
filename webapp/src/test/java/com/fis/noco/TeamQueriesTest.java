package com.fis.noco;

import com.fis.noco.entity.TeamMember;
import com.fis.noco.entity.TeamResult;
import com.fis.noco.service.AthleteService;
import com.fis.noco.service.CompetitionService;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import java.io.File;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Runs the team queries against the real database (../db/noco.db) and reads
 * everything the views read — outside a transaction, as the views do.  A
 * missing fetch join shows up here as a LazyInitializationException instead
 * of a blank page.  Skipped if the database has not been built.
 */
@SpringBootTest
class TeamQueriesTest {

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
    void teamsOfACompetitionWithTheirAthletes() {
        assumeDatabase();
        Long competitionId = jdbc.queryForObject(
                "select competition_id from team_results where rank = 1 limit 1", Long.class);

        List<TeamResult> teams = competitionService.getTeamResultsForCompetition(competitionId);

        assertFalse(teams.isEmpty());
        assertEquals(1, teams.get(0).getRank());                       // ranked teams first, by rank
        assertEquals(teams.size(), teams.stream().map(TeamResult::getId).distinct().count());
        for (TeamResult team : teams) {
            assertNotNull(team.getDisplayName());
            for (TeamMember member : team.getMembers()) {
                assertFalse(member.getDisplayName().isBlank());
                if (member.getAthlete() != null) {
                    assertNotNull(member.getAthlete().getId());
                }
            }
        }
        assertTrue(teams.get(0).getMembers().size() >= 2);
        assertEquals(teams.size(), competitionService.countResultsForCompetition(competitionId));
    }

    @Test
    void officialStandingsOfASeason() {
        assumeDatabase();
        Long seasonId = jdbc.queryForObject("select id from seasons where start_year = 2023", Long.class);

        List<String[]> rankings = competitionService.getRankingsOfSeason(seasonId, "WC", "M");
        assertEquals("ALL", rankings.get(0)[0]);                       // overall first
        assertTrue(rankings.size() > 1);                               // plus the trophies of that season

        List<com.fis.noco.service.StandingsEntry> standings =
                competitionService.getStandings(seasonId, "WC", "M", "ALL");
        com.fis.noco.service.StandingsEntry winner = standings.get(0);
        assertEquals(1, winner.getPosition());
        assertEquals("RIIBER Jarl Magnus", winner.getAthleteName());   // 2023/24, as published by FIS
        assertEquals(1870, winner.getTotalPoints());
        assertNotNull(winner.getAthleteId());

        // the columns: his rank in the individual competitions of that season
        var competitions = competitionService.getIndividualCompetitions(seasonId, "WC", "M");
        assertFalse(competitions.isEmpty());
        long raced = competitions.stream().filter(c -> winner.getRankInCompetition(c.getId()) != null).count();
        assertTrue(raced > 10);
        competitions.forEach(c -> assertNotNull(c.getDisplayLocation()));
    }

    @Test
    void teamStartsOfAnAthlete() {
        assumeDatabase();
        Long athleteId = jdbc.queryForObject(
                "select athlete_id from team_members where athlete_id is not null " +
                "group by athlete_id order by count(*) desc limit 1", Long.class);
        Integer expected = jdbc.queryForObject(
                "select count(*) from team_members where athlete_id = ?", Integer.class, athleteId);

        List<TeamMember> starts = athleteService.getTeamStarts(athleteId);

        assertEquals(expected, starts.size());                         // one row per start, no duplicates
        String previousDate = null;
        for (TeamMember start : starts) {
            TeamResult team = start.getTeamResult();
            assertNotNull(team.getCompetition().getCircuit());
            assertNotNull(team.getCompetition().getDisplayLocation());
            assertNotNull(team.getCompetition().getFormat());
            assertTrue(team.getMembers().size() >= 2);                  // team-mates are loaded
            team.getMembers().forEach(TeamMember::getDisplayName);
            String date = team.getCompetition().getCompetitionDate();
            if (previousDate != null && date != null) {
                assertTrue(previousDate.compareTo(date) >= 0, "newest first");
            }
            previousDate = date;
        }
    }
}
