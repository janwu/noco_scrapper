package com.fis.noco;

import com.fis.noco.service.AthleteProfile;
import com.fis.noco.service.AthleteService;
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

/** The venue statistics of the athlete page against the real database, read outside a transaction. */
@SpringBootTest
class AthleteProfileTest {

    @Autowired
    private AthleteService athleteService;
    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void profileOfAWorldCupWinner() {
        Assumptions.assumeTrue(new File("../db/noco.db").exists(), "database not built");
        Long id = jdbc.queryForObject("select id from athletes where full_name = 'RIIBER Jarl Magnus'", Long.class);
        AthleteProfile profile = athleteService.getProfile(id);

        assertEquals(1, profile.bestResult().orElseThrow().getRank());
        List<com.fis.noco.entity.CombinedResult> wins = profile.bestResults();
        Integer winCount = jdbc.queryForObject(
                "select count(*) from combined_results where athlete_id = ? and rank = 1", Integer.class, id);
        assertEquals(winCount, wins.size());
        assertEquals(profile.bestResult().get().getId(), wins.get(0).getId());     // the first win
        for (int i = 1; i < wins.size(); i++) {
            assertTrue(wins.get(i - 1).getCompetition().getCompetitionDate()
                    .compareTo(wins.get(i).getCompetition().getCompetitionDate()) <= 0);
        }
        System.out.printf("RIIBER %d wins, first %s %s%n", wins.size(),
                wins.get(0).getCompetition().getDisplayLocation(), wins.get(0).getCompetition().getCompetitionDate());
        assertTrue(profile.longestWorldCupJump().orElseThrow().getDistanceM() > 140);

        List<AthleteProfile.VenueStats> venues = profile.venues();
        assertFalse(venues.isEmpty());
        int starts = venues.stream().mapToInt(AthleteProfile.VenueStats::starts).sum();
        Integer expected = jdbc.queryForObject(
                "select (select count(*) from combined_results where athlete_id = ?) + " +
                "(select count(*) from team_members where athlete_id = ?)", Integer.class, id, id);
        assertEquals(expected, starts);                                   // every start counted once
        AthleteProfile.VenueStats best = profile.mostSuccessfulVenue().orElseThrow();
        assertTrue(best.podiums() >= venues.stream().mapToInt(AthleteProfile.VenueStats::podiums).max().orElse(0));
        assertNotNull(best.venue().getName());

        for (List<AthleteProfile.PlaceRating> ratings : List.of(profile.favouriteHills(), profile.favouriteCourses())) {
            assertFalse(ratings.isEmpty());
            for (AthleteProfile.PlaceRating r : ratings) {
                assertTrue(r.competitions() >= AthleteProfile.MIN_COMPETITIONS);
                assertTrue(r.share() >= 0 && r.share() <= 1);
            }
            for (int i = 1; i < ratings.size(); i++) {
                assertTrue(ratings.get(i - 1).delta() >= ratings.get(i).delta(), "best first");
            }
        }

        AthleteProfile wc = profile.forCircuit("WC");
        assertTrue(wc.venues().size() <= venues.size());
        print("RIIBER", profile);
    }

    private static void print(String who, AthleteProfile p) {
        System.out.printf("%s best %s, longest WC jump %.1f m at %s%n", who, p.bestResult().get().getRank(),
                p.longestWorldCupJump().get().getDistanceM(), p.longestWorldCupJump().get().getCompetition().getDisplayLocation());
        System.out.printf("  most successful %s, most visited %s (%d)%n", p.mostSuccessfulVenue().get().label(),
                p.mostVisitedVenue().get().label(), p.mostVisitedVenue().get().starts());
        p.favouriteHills().stream().limit(4).forEach(r -> System.out.printf("  hill %-22s n=%2d %.0f%% %+.0fpp avg %.1f%n",
                r.label(), r.competitions(), 100 * r.share(), 100 * r.delta(), r.meanRank()));
        p.favouriteCourses().stream().limit(4).forEach(r -> System.out.printf("  xc   %-22s n=%2d %.0f%% %+.0fpp avg %.1f%n",
                r.label(), r.competitions(), 100 * r.share(), 100 * r.delta(), r.meanRank()));
    }
}
