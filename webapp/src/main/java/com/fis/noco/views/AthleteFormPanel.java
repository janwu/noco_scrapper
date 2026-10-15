package com.fis.noco.views;

import com.fis.noco.entity.Athlete;
import com.fis.noco.entity.CombinedResult;
import com.fis.noco.entity.Competition;
import com.fis.noco.entity.Season;
import com.fis.noco.service.AthleteService;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.checkbox.Checkbox;
import com.vaadin.flow.component.grid.ColumnTextAlign;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.html.Div;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.orderedlayout.FlexLayout;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.select.Select;
import com.vaadin.flow.theme.lumo.LumoUtility;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * The form tab of the athlete page: one World Cup season at a time — its key
 * figures, the form chart (FormChart) and the same values as a table.
 */
final class AthleteFormPanel extends VerticalLayout {

    private final AthleteService athleteService;
    private final Athlete athlete;
    private final Map<Long, CombinedResult> results;            // competition id → result
    private final Checkbox jump = new Checkbox("Jump rank");
    private final Checkbox xc = new Checkbox("Cross-country rank");
    private final Div content = new Div();
    private Season season;

    AthleteFormPanel(AthleteService athleteService, Athlete athlete, List<CombinedResult> worldCupResults) {
        this.athleteService = athleteService;
        this.athlete = athlete;
        this.results = worldCupResults.stream().collect(Collectors.toMap(
                r -> r.getCompetition().getId(), Function.identity(), (a, b) -> a));
        setPadding(false);
        setWidthFull();

        // the seasons with a World Cup start, newest first
        Map<Long, Season> seasons = new LinkedHashMap<>();
        worldCupResults.stream()
                .map(r -> r.getCompetition().getSeason())
                .filter(Objects::nonNull)
                .sorted(Comparator.comparing(Season::getStartYear).reversed())
                .forEach(s -> seasons.putIfAbsent(s.getId(), s));

        Select<Season> select = new Select<>();
        select.setLabel("World Cup season");
        select.setItems(seasons.values());
        select.setItemLabelGenerator(Season::getLabel);
        select.addValueChangeListener(e -> { season = e.getValue(); show(); });
        jump.addValueChangeListener(e -> show());
        xc.addValueChangeListener(e -> show());

        HorizontalLayout controls = new HorizontalLayout(select, jump, xc);
        controls.setAlignItems(Alignment.BASELINE);
        controls.getStyle().set("flex-wrap", "wrap");
        content.setWidthFull();
        add(controls, content);
        if (!seasons.isEmpty()) {
            select.setValue(seasons.values().iterator().next());
        }
    }

    private void show() {
        content.removeAll();
        if (season == null) return;
        String gender = athlete.getGender() != null ? athlete.getGender() : "M";
        List<Competition> competitions = athleteService.getWorldCupCompetitions(season, gender);
        List<CombinedResult> mine = competitions.stream().map(c -> results.get(c.getId()))
                .filter(Objects::nonNull).toList();

        content.add(keyFigures(competitions, mine));

        List<FormChart.Series> series = new ArrayList<>(List.of(FormChart.FINAL));
        if (jump.getValue()) series.add(FormChart.JUMP);
        if (xc.getValue()) series.add(FormChart.XC);
        content.add(legend(series), FormChart.create(competitions, results, series), table(competitions));
    }

    private Div keyFigures(List<Competition> competitions, List<CombinedResult> mine) {
        List<Integer> ranks = mine.stream().map(CombinedResult::getRank).filter(Objects::nonNull).toList();
        FlexLayout row = new FlexLayout();
        row.setFlexWrap(FlexLayout.FlexWrap.WRAP);
        row.getStyle().set("gap", "var(--lumo-space-l)");
        row.addClassNames(LumoUtility.Padding.Vertical.SMALL);
        row.add(figure(mine.size() + " / " + competitions.size(), "Starts"));
        row.add(figure(String.valueOf(ranks.stream().filter(r -> r == 1).count()), "Wins"));
        row.add(figure(String.valueOf(ranks.stream().filter(r -> r <= 3).count()), "Podiums"));
        row.add(figure(String.valueOf(ranks.stream().filter(r -> r <= 10).count()), "Top 10"));
        ranks.stream().min(Integer::compare).ifPresent(b -> row.add(figure(String.valueOf(b), "Best")));
        if (!ranks.isEmpty()) {
            row.add(figure(String.format(Locale.ROOT, "%.1f", ranks.stream().mapToInt(Integer::intValue).average().orElse(0)), "Ø rank"));
        }
        athleteService.getWorldCupStanding(athlete.getId(), season).ifPresent(s ->
                row.add(figure(s.getRank() + "." + (s.getPoints() != null ? " · " + s.getPoints() + " pts" : ""),
                        "World Cup overall")));
        Div wrap = new Div(row);
        wrap.setWidthFull();
        return wrap;
    }

    private static VerticalLayout figure(String value, String label) {
        Span v = new Span(value);
        v.addClassNames(LumoUtility.FontSize.XLARGE, LumoUtility.FontWeight.BOLD);
        Span l = new Span(label);
        l.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.TextColor.SECONDARY);
        VerticalLayout f = new VerticalLayout(v, l);
        f.setPadding(false);
        f.setSpacing(false);
        f.setWidth(null);
        return f;
    }

    /** One key per series: a short line in the series colour, the label in text colour. */
    private static HorizontalLayout legend(List<FormChart.Series> series) {
        HorizontalLayout legend = new HorizontalLayout();
        legend.setSpacing(true);
        legend.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.Padding.Vertical.XSMALL);
        for (FormChart.Series s : series) {
            Span key = new Span();
            key.getStyle().set("display", "inline-block").set("width", "18px").set("height", "2px")
                    .set("background", s.color()).set("vertical-align", "middle").set("margin-right", "6px");
            Span item = new Span(key, new Span(s.label().equals("Rank") ? "Final rank" : s.label() + " rank"));
            item.addClassName("form-chart");          // the series colour variables live on .form-chart
            legend.add(item);
        }
        Span band = new Span();
        band.getStyle().set("display", "inline-block").set("width", "14px").set("height", "10px")
                .set("background", "var(--lumo-contrast-10pct)").set("vertical-align", "middle").set("margin-right", "6px");
        legend.add(new Span(band, new Span("Podium (1–3)")));
        Span hint = new Span("Hover a competition for its ranks, click to open it.");
        hint.addClassNames(LumoUtility.TextColor.SECONDARY);
        legend.add(hint);
        return legend;
    }

    /** The values of the chart as a table (also the way to read it without colour). */
    private Grid<Competition> table(List<Competition> competitions) {
        Grid<Competition> grid = new Grid<>(Competition.class, false);
        grid.addColumn(Competition::getCompetitionDate).setHeader("Date").setAutoWidth(true);
        grid.addColumn(Competition::getDisplayLocation).setHeader("Location").setAutoWidth(true);
        grid.addColumn(Competition::getFormat).setHeader("Format").setAutoWidth(true);
        grid.addColumn(c -> rankOrStatus(results.get(c.getId()))).setHeader("Rank").setAutoWidth(true)
                .setTextAlign(ColumnTextAlign.END);
        grid.addColumn(c -> value(results.get(c.getId()), CombinedResult::getJumpRank)).setHeader("Jump rank")
                .setAutoWidth(true).setTextAlign(ColumnTextAlign.END);
        grid.addColumn(c -> value(results.get(c.getId()), CombinedResult::getXcRank)).setHeader("XC rank")
                .setAutoWidth(true).setTextAlign(ColumnTextAlign.END);
        grid.addSelectionListener(e -> e.getFirstSelectedItem().ifPresent(c ->
                UI.getCurrent().navigate(ResultDetailView.class, c.getId())));
        grid.setItems(competitions);
        grid.setAllRowsVisible(true);
        grid.addClassNames(LumoUtility.Margin.Top.MEDIUM);
        return grid;
    }

    private static String rankOrStatus(CombinedResult r) {
        if (r == null) return "–";
        if (r.getRank() != null) return String.valueOf(r.getRank());
        return r.getStatus() != null ? r.getStatus() : "";
    }

    private static String value(CombinedResult r, Function<CombinedResult, Integer> f) {
        Integer v = r == null ? null : f.apply(r);
        return v == null ? "" : String.valueOf(v);
    }
}
