package com.fis.noco.views;

import com.fis.noco.service.AthleteService;
import com.vaadin.flow.component.UI;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import java.io.File;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Builds the athlete page on the server for athletes of different careers, outside a
 * transaction as in the app: a lazy association or an empty statistic fails here
 * instead of in the browser.
 */
@SpringBootTest
class AthletePageTest {

    @Autowired
    private AthleteService athleteService;
    @Autowired
    private JdbcTemplate jdbc;

    @AfterEach
    void clear() {
        UI.setCurrent(null);
    }

    @Test
    void highlightCardsLinkToTheirCompetitions() {
        Assumptions.assumeTrue(new File("../db/noco.db").exists(), "database not built");
        Long id = jdbc.queryForObject("select id from athletes where full_name = 'RIIBER Jarl Magnus'", Long.class);
        Long firstWin = jdbc.queryForObject("select c.id from combined_results r join competitions c on c.id = r.competition_id " +
                "where r.athlete_id = ? and r.rank = 1 and c.circuit = 'WC' order by c.competition_date limit 1", Long.class, id);
        UI.setCurrent(new UI());
        AthleteDetailView view = new AthleteDetailView(athleteService);
        view.setParameter(null, id);
        List<com.vaadin.flow.component.html.Anchor> anchors = new java.util.ArrayList<>();
        collect(view, anchors);
        List<String> hrefs = anchors.stream().map(com.vaadin.flow.component.html.Anchor::getHref).toList();
        assertTrue(hrefs.contains("result/" + firstWin), hrefs.toString());                  // the first World Cup win
        assertTrue(anchors.stream().anyMatch(a -> a.getText().matches("All \\d+ ›")), "list of all wins");
        long jumpLinks = hrefs.stream().filter(h -> h.startsWith("result/")).count();
        assertTrue(jumpLinks >= 2, hrefs.toString());                                       // and the longest jump
    }

    private static void collect(com.vaadin.flow.component.Component c, List<com.vaadin.flow.component.html.Anchor> out) {
        if (c instanceof com.vaadin.flow.component.html.Anchor a) out.add(a);
        c.getChildren().forEach(child -> collect(child, out));
    }

    @Test
    void pagesOfDifferentCareers() {
        Assumptions.assumeTrue(new File("../db/noco.db").exists(), "database not built");
        List<Long> ids = jdbc.queryForList(
                "select id from (" +
                " select id from athletes where full_name in ('RIIBER Jarl Magnus', 'LAMPARTER Johannes', 'WESTVOLD HANSEN Gyda')" +
                " union select athlete_id from combined_results r join competitions c on c.id = r.competition_id" +
                "   where c.circuit = 'COC' and athlete_id not in (select athlete_id from combined_results r2" +
                "   join competitions c2 on c2.id = r2.competition_id where c2.circuit = 'WC' and athlete_id is not null)" +
                "   group by athlete_id having count(*) = 1" +
                " union select min(athlete_id) from team_members where athlete_id not in" +
                "   (select athlete_id from combined_results where athlete_id is not null))" +
                " limit 6", Long.class);
        assertTrue(ids.size() >= 4);
        for (Long id : ids) {
            UI.setCurrent(new UI());
            AthleteDetailView view = new AthleteDetailView(athleteService);
            view.setParameter(null, id);
            assertTrue(view.getChildren().count() > 3, "page built for athlete " + id);
        }
    }
}
