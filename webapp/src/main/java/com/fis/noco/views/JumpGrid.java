package com.fis.noco.views;

import com.fis.noco.entity.JumpResult;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.grid.ColumnTextAlign;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.html.Span;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.function.Function;

/**
 * The grid of one jump list, as printed by FIS: rank, athlete, speed, distance,
 * judges' marks, gate and wind compensation, points.  Columns the list does not
 * have (no marks before the mass start had them, no gate/wind before 2009/10)
 * are left out; the longest jump of the list is set in bold.
 *
 * With two rounds an athlete has a line per round: the round's points on each, the
 * total of both and the start gap on the first only.
 */
final class JumpGrid {

    private JumpGrid() {
    }

    static Grid<JumpResult> create(List<JumpResult> jumps) {
        Grid<JumpResult> grid = new Grid<>(JumpResult.class, false);
        grid.setSizeFull();

        boolean twoRounds = jumps.stream().anyMatch(j -> j.getRoundNumber() != null && j.getRoundNumber() > 1);
        double longest = jumps.stream().map(JumpResult::getDistanceM).filter(Objects::nonNull)
                .mapToDouble(Double::doubleValue).max().orElse(-1);

        grid.addColumn(j -> twoRounds && j.getRoundNumber() != null && j.getRoundNumber() > 1 ? "" : rankOf(j))
                .setHeader("Rank").setAutoWidth(true).setFlexGrow(0);
        grid.addColumn(j -> twoRounds && j.getRoundNumber() != null && j.getRoundNumber() > 1 ? "" : bibOf(j))
                .setHeader("Bib").setAutoWidth(true).setFlexGrow(0);
        grid.addColumn(j -> twoRounds && j.getRoundNumber() != null && j.getRoundNumber() > 1 ? "" : j.getDisplayName())
                .setHeader("Name").setAutoWidth(true);
        grid.addComponentColumn(j -> twoRounds && j.getRoundNumber() != null && j.getRoundNumber() > 1
                        ? new Span() : new NationFlag(j.getDisplayNation()))
                .setHeader("Nation").setAutoWidth(true);
        if (twoRounds) {
            grid.addColumn(JumpResult::getRoundNumber).setHeader("Round").setAutoWidth(true).setFlexGrow(0);
        }

        number(grid, jumps, "Speed", JumpResult::getSpeedKmh);
        grid.addComponentColumn(j -> {
                    Span d = new Span(JumpResult.format(j.getDistanceM()));
                    if (j.getDistanceM() != null && j.getDistanceM() == longest) {
                        d.getStyle().set("font-weight", "bold");
                    }
                    return d;
                }).setHeader("Distance").setAutoWidth(true).setTextAlign(ColumnTextAlign.END)
                .setComparator(j -> j.getDistanceM() == null ? -1 : j.getDistanceM());
        number(grid, jumps, "Dist. Pts", JumpResult::getDistPoints);
        if (jumps.stream().anyMatch(JumpResult::hasMarks)) {
            grid.addComponentColumn(j -> {
                Span marks = new Span(j.getMarks());
                marks.getStyle().set("font-size", "var(--lumo-font-size-s)")
                        .set("color", "var(--lumo-secondary-text-color)")
                        .set("font-variant-numeric", "tabular-nums").set("white-space", "nowrap");
                return marks;
            }).setHeader("Judges").setAutoWidth(true);
            number(grid, jumps, "Style", JumpResult::getStylePoints);
        }
        if (jumps.stream().anyMatch(j -> j.getGate() != null)) {
            grid.addColumn(JumpResult::getGateLabel).setHeader("Gate").setAutoWidth(true)
                    .setTextAlign(ColumnTextAlign.END);
            number(grid, jumps, "Gate Pts", JumpResult::getGateCompPts);
        }
        if (jumps.stream().anyMatch(j -> j.getWindMs() != null)) {
            grid.addColumn(j -> j.getWindMs() == null ? "" : String.format(java.util.Locale.ROOT, "%.2f", j.getWindMs()))
                    .setHeader("Wind m/s").setAutoWidth(true).setTextAlign(ColumnTextAlign.END);
            number(grid, jumps, "Wind Pts", JumpResult::getWindCompPts);
        }
        if (twoRounds) {
            Map<String, Double> totals = totals(jumps);
            number(grid, jumps, "Round Pts", JumpResult::getTotalPoints);
            grid.addComponentColumn(j -> {
                        Span p = new Span(laterRound(j) ? "" : JumpResult.format(totals.get(athleteKey(j))));
                        p.getStyle().set("font-weight", "bold");
                        return p;
                    }).setHeader("Total").setAutoWidth(true).setTextAlign(ColumnTextAlign.END)
                    .setComparator(j -> totals.getOrDefault(athleteKey(j), -1.0));
        } else {
            grid.addComponentColumn(j -> {
                        Span p = new Span(JumpResult.format(j.getTotalPoints()));
                        p.getStyle().set("font-weight", "bold");
                        return p;
                    }).setHeader("Points").setAutoWidth(true).setTextAlign(ColumnTextAlign.END)
                    .setComparator(j -> j.getTotalPoints() == null ? -1 : j.getTotalPoints());
        }
        if (jumps.stream().anyMatch(j -> j.getPursuitTimeDiff() != null)) {
            grid.addColumn(j -> j.getPursuitTimeDiff() == null || twoRounds && laterRound(j) ? "" : j.getPursuitTimeDiff())
                    .setHeader("Start Gap").setAutoWidth(true);
        }
        if (jumps.stream().anyMatch(j -> !j.getStatus().isEmpty())) {
            grid.addComponentColumn(j -> {
                Span s = new Span(j.getStatus() + (j.getDsqReason() != null ? " " + j.getDsqReason() : ""));
                s.getStyle().set("color", "var(--lumo-error-color)").set("font-weight", "bold");
                return s;
            }).setHeader("Status").setAutoWidth(true);
        }

        grid.addSelectionListener(event -> event.getFirstSelectedItem().ifPresent(j -> {
            if (j.getAthlete() != null) {
                UI.getCurrent().navigate(AthleteDetailView.class, j.getAthlete().getId());
            }
        }));
        grid.setItems(jumps);
        return grid;
    }

    /** The points of all rounds of each athlete (athleteKey), rounded to a tenth like the lists. */
    static Map<String, Double> totals(List<JumpResult> jumps) {
        Map<String, Double> totals = new HashMap<>();
        for (JumpResult j : jumps) {
            if (j.getTotalPoints() != null) totals.merge(athleteKey(j), j.getTotalPoints(), Double::sum);
        }
        totals.replaceAll((k, v) -> Math.round(v * 10) / 10.0);
        return totals;
    }

    /** The second round's line of an athlete (the first carries total and start gap). */
    private static boolean laterRound(JumpResult j) {
        return j.getRoundNumber() != null && j.getRoundNumber() > 1;
    }

    /** One athlete in one list: the rounds of a jump list belong together by name and bib. */
    static String athleteKey(JumpResult j) {
        return j.getDisplayName() + "|" + j.getBib();
    }

    private static String rankOf(JumpResult j) {
        return j.getRank() == null ? "" : String.valueOf(j.getRank());
    }

    private static String bibOf(JumpResult j) {
        return j.getBib() == null ? "" : String.valueOf(j.getBib());
    }

    /** A right-aligned number column, left out if the list has no value in it. */
    private static void number(Grid<JumpResult> grid, List<JumpResult> jumps, String header,
                               Function<JumpResult, Double> value) {
        if (jumps.stream().map(value).allMatch(Objects::isNull)) {
            return;
        }
        grid.addColumn(j -> JumpResult.format(value.apply(j)))
                .setHeader(header).setAutoWidth(true).setTextAlign(ColumnTextAlign.END)
                .setComparator(j -> value.apply(j) == null ? -1e9 : value.apply(j));
    }
}
