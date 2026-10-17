package com.fis.noco.views;

import com.fis.noco.service.CompetitionService;
import com.vaadin.flow.component.Component;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.tabs.Tab;
import com.vaadin.flow.component.tabs.TabSheet;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** The competition page built on the server: which tabs a mass start and a Gundersen get. */
@SpringBootTest
class CompetitionPageTest {

    @Autowired
    private CompetitionService competitionService;
    @Autowired
    private JdbcTemplate jdbc;

    @AfterEach
    void clear() {
        UI.setCurrent(null);
    }

    private List<String> tabs(Long competitionId) {
        UI.setCurrent(new UI());
        ResultDetailView view = new ResultDetailView(competitionService);
        view.setParameter(null, competitionId);
        List<String> labels = new ArrayList<>();
        view.getChildren().filter(c -> c instanceof TabSheet).forEach(sheet -> collect(sheet, labels));
        return labels;
    }

    private static void collect(Component c, List<String> labels) {
        if (c instanceof Tab tab) labels.add(tab.getLabel());
        c.getChildren().forEach(child -> collect(child, labels));
    }

    @Test
    void massStartHasItsCrossCountryRace() {
        Assumptions.assumeTrue(new File("../db/noco.db").exists(), "database not built");
        Long id = jdbc.queryForObject("select c.id from competitions c join seasons s on s.id = c.season_id " +
                "where c.circuit = 'WC' and s.start_year = 2025 and c.fis_codex = '4123'", Long.class);   // Trondheim
        List<String> labels = tabs(id);
        assertTrue(labels.get(0).startsWith("Result"), labels.toString());
        assertTrue(labels.get(1).startsWith("Cross-Country ("), labels.toString());

        Long gundersen = jdbc.queryForObject("select c.id from competitions c join seasons s on s.id = c.season_id " +
                "where c.circuit = 'WC' and s.start_year = 2025 and c.fis_codex = '4118'", Long.class);   // Ruka
        assertTrue(tabs(gundersen).stream().noneMatch(l -> l.startsWith("Cross-Country")));
    }

    @Test
    void massStartWithoutJumpShowsTheRace() {
        Assumptions.assumeTrue(new File("../db/noco.db").exists(), "database not built");
        // Ruka 30 Nov 2025: the jumping was cancelled for wind, the race was held
        Long id = jdbc.queryForObject("select c.id from competitions c join seasons s on s.id = c.season_id " +
                "where c.circuit = 'WC' and s.start_year = 2025 and c.fis_codex = '4119'", Long.class);
        List<String> labels = tabs(id);
        assertEquals("Cross-Country (56)", labels.get(0), labels.toString());
        assertTrue(labels.stream().noneMatch(l -> l.startsWith("Result")), labels.toString());
    }

    @Test
    void worldCupBIsTheContinentalCupBefore2008() {
        Assumptions.assumeTrue(new File("../db/noco.db").exists(), "database not built");
        // Bardufoss 8 Dec 2001: the list of the organiser is not read, the ranking of the FIS database is
        Long id = jdbc.queryForObject("select c.id from competitions c where c.circuit = 'COC' " +
                "and c.competition_date = '2001-12-08'", Long.class);
        var competition = competitionService.findById(id).orElseThrow();
        assertEquals("World Cup B", competition.getCircuitLabel());
        assertEquals(59, competitionService.countResultsForCompetition(id));
    }

    @Test
    void resultsBrowserFilterInTheAddress() {
        var season = competitionService.getAllSeasons().stream()
                .filter(s -> Integer.valueOf(2001).equals(s.getStartYear())).findFirst();
        Assumptions.assumeTrue(season.isPresent(), "database not built");
        assertEquals("circuit=COC&gender=W&season=2001",
                ResultsBrowserView.filter("COC", season.get(), "W").getQueryString());
        assertEquals("circuit=WC&season=2001", ResultsBrowserView.filter("WC", season.get(), "All").getQueryString());
    }

    @Test
    void gapToTheFastest() {
        Double best = ResultDetailView.seconds("23:49.0");
        assertEquals(1429.0, best);
        assertEquals("0.0", ResultDetailView.gap(best, best));
        assertEquals("+6.5", ResultDetailView.gap(ResultDetailView.seconds("23:55.5"), best));
        assertEquals("+1:02.3", ResultDetailView.gap(ResultDetailView.seconds("24:51.3"), best));
        assertEquals("", ResultDetailView.gap(ResultDetailView.seconds("DNF"), best));
    }
}
