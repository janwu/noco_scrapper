package com.fis.noco.views;

import com.fis.noco.entity.CombinedResult;
import com.fis.noco.entity.Competition;
import com.fis.noco.entity.Season;
import com.fis.noco.service.AthleteService;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.html.Div;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import java.io.File;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** The form chart of a World Cup season against the real database. */
@SpringBootTest
class FormChartTest {

    @Autowired
    private AthleteService athleteService;
    @Autowired
    private JdbcTemplate jdbc;

    @AfterEach
    void clear() {
        UI.setCurrent(null);
    }

    @Test
    void seasonOfAWorldCupWinner() throws Exception {
        Assumptions.assumeTrue(new File("../db/noco.db").exists(), "database not built");
        UI.setCurrent(new UI());
        Long id = jdbc.queryForObject("select id from athletes where full_name = 'RIIBER Jarl Magnus'", Long.class);
        List<CombinedResult> wc = athleteService.getWorldCupResults(id);
        Season season = wc.stream().map(r -> r.getCompetition().getSeason())
                .filter(s -> s.getStartYear() == 2023).findFirst().orElseThrow();
        List<Competition> competitions = athleteService.getWorldCupCompetitions(season, "M");
        Map<Long, CombinedResult> results = wc.stream().collect(Collectors.toMap(
                r -> r.getCompetition().getId(), Function.identity(), (a, b) -> a));

        Div chart = FormChart.create(competitions, results,
                List.of(FormChart.FINAL, FormChart.JUMP, FormChart.XC));
        String html = chart.getElement().getProperty("innerHTML");

        assertEquals(competitions.size(), html.split("class='fc-hit'").length - 1);   // one column per competition
        long starts = competitions.stream().filter(c -> results.containsKey(c.getId())).count();
        assertTrue(starts > 10);
        assertTrue(html.contains("viewBox"));

        // for a look at it: target/form-chart.html (styles of the app's light theme stubbed)
        Files.writeString(Path.of("target/form-chart.html"), "<!doctype html><html><head><meta charset='utf-8'><style>"
                + ":root{--lumo-base-color:#fff;--lumo-contrast-5pct:rgba(26,57,96,.05);--lumo-contrast-10pct:rgba(26,57,96,.1);"
                + "--lumo-contrast-20pct:rgba(26,57,96,.16);--lumo-contrast-30pct:rgba(26,57,96,.26);"
                + "--lumo-secondary-text-color:rgba(27,43,65,.69);--lumo-tertiary-text-color:rgba(25,39,57,.5);"
                + "--lumo-body-text-color:rgba(24,39,57,.94);--lumo-font-size-s:14px;--lumo-border-radius-m:6px}"
                + "body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:16px;background:#fff}</style></head>"
                + "<body><div class='form-chart'>" + html + "</div></body></html>");
    }
}
