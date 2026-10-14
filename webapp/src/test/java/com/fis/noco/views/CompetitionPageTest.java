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
    void gapToTheFastest() {
        Double best = ResultDetailView.seconds("23:49.0");
        assertEquals(1429.0, best);
        assertEquals("0.0", ResultDetailView.gap(best, best));
        assertEquals("+6.5", ResultDetailView.gap(ResultDetailView.seconds("23:55.5"), best));
        assertEquals("+1:02.3", ResultDetailView.gap(ResultDetailView.seconds("24:51.3"), best));
        assertEquals("", ResultDetailView.gap(ResultDetailView.seconds("DNF"), best));
    }
}
