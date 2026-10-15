package com.fis.noco.views;

import com.fis.noco.entity.CombinedResult;
import com.fis.noco.entity.Competition;
import com.fis.noco.entity.JumpResult;
import com.fis.noco.service.AthleteProfile;
import com.fis.noco.service.AthleteProfile.PlaceRating;
import com.fis.noco.service.AthleteProfile.VenueStats;
import com.vaadin.flow.component.Component;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.button.Button;
import com.vaadin.flow.component.dialog.Dialog;
import com.vaadin.flow.component.html.Anchor;
import com.vaadin.flow.component.grid.ColumnTextAlign;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.html.Div;
import com.vaadin.flow.component.html.H4;
import com.vaadin.flow.component.html.Paragraph;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.orderedlayout.FlexLayout;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.radiobutton.RadioButtonGroup;
import com.vaadin.flow.theme.lumo.LumoUtility;

import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.function.Function;

/**
 * The overview tab of the athlete page: career statistics, favourite hills and
 * cross-country courses and the results by venue, for one circuit at a time.
 * The highlight cards above the tabs come from {@link #highlights}.
 */
final class AthleteOverview extends VerticalLayout {

    private static final Map<String, String> SCOPES = Map.of("World Cup", "WC", "Continental Cup", "COC");

    private final AthleteProfile profile;
    private final Function<String, Component> careerBlocks;
    private final Div content = new Div();

    /** careerBlocks: the statistics blocks for a circuit ("WC", "COC"). */
    AthleteOverview(AthleteProfile profile, Function<String, Component> careerBlocks) {
        this.profile = profile;
        this.careerBlocks = careerBlocks;
        setPadding(false);
        setSpacing(false);
        setWidthFull();

        RadioButtonGroup<String> scope = new RadioButtonGroup<>();
        // one circuit at a time: World Cup, or Continental Cup for an athlete never in the World Cup
        boolean worldCup = profile.forCircuit("WC").bestResult().isPresent()
                || !profile.forCircuit("WC").venues().isEmpty();
        scope.setItems("World Cup", "Continental Cup");
        scope.setValue(worldCup ? "World Cup" : "Continental Cup");
        scope.addValueChangeListener(e -> show(SCOPES.get(e.getValue())));
        HorizontalLayout scopeRow = new HorizontalLayout(new Span("Show: "), scope);
        scopeRow.setAlignItems(Alignment.CENTER);

        content.setWidthFull();
        add(scopeRow, content);
        show(worldCup ? "WC" : "COC");
    }

    private void show(String circuit) {
        AthleteProfile p = profile.forCircuit(circuit);
        content.removeAll();
        content.add(careerBlocks.apply(circuit));

        FlexLayout favourites = new FlexLayout();
        favourites.setFlexWrap(FlexLayout.FlexWrap.WRAP);
        favourites.getStyle().set("gap", "var(--lumo-space-l)");
        favourites.setWidthFull();
        favourites.add(
                ratingCard("Favourite hills", "Jump", p.favouriteHills(), p.careerJumpShare().orElse(Double.NaN)),
                ratingCard("Favourite cross-country courses", "XC", p.favouriteCourses(), p.careerXcShare().orElse(Double.NaN)));
        content.add(favourites);

        List<VenueStats> venues = p.venues();
        if (!venues.isEmpty()) {
            H4 title = new H4("Results by venue (" + venues.size() + ")");
            title.addClassNames(LumoUtility.Margin.Top.LARGE, LumoUtility.Margin.Bottom.XSMALL);
            content.add(title, venueGrid(venues));
        }

        Paragraph method = new Paragraph(
                "How hills and courses are rated: each jump rank (and the rank of the cross-country time, not "
                + "the finish position) is turned into the share of the field beaten — 100 % for the best, 0 % for "
                + "the last. A hill (venue and hill size) or a course is compared with the athlete's own average: "
                + "+10 pp means 10 percentage points more of the field beaten there than usual. Places with fewer "
                + "than " + AthleteProfile.MIN_COMPETITIONS + " individual competitions are not rated.");
        method.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.TextColor.SECONDARY, LumoUtility.Margin.Top.MEDIUM);
        method.getStyle().set("max-width", "60em");
        content.add(method);
    }

    // ── favourite hills and courses ────────────────────────────────────────

    private Component ratingCard(String title, String what, List<PlaceRating> ratings, double career) {
        VerticalLayout card = card();
        card.getStyle().set("flex", "1 1 28em");
        H4 header = new H4(title);
        header.addClassNames(LumoUtility.Margin.Vertical.NONE);
        card.add(header);
        if (ratings.isEmpty()) {
            card.add(muted("Not enough competitions on one " + ("Jump".equals(what) ? "hill" : "course")
                    + " (at least " + AthleteProfile.MIN_COMPETITIONS + ")."));
            return card;
        }
        card.add(muted(String.format(Locale.ROOT, "Career average: beats %.0f %% of the field in the %s.",
                100 * career, "Jump".equals(what) ? "jump" : "cross-country race")));

        Grid<PlaceRating> grid = new Grid<>(PlaceRating.class, false);
        grid.addComponentColumn(r -> place(r.label(), r.country())).setHeader("Where").setAutoWidth(true).setFlexGrow(1);
        grid.addColumn(PlaceRating::competitions).setHeader("Comp.").setAutoWidth(true)
                .setTextAlign(ColumnTextAlign.END).setSortable(true);
        grid.addColumn(r -> String.format(Locale.ROOT, "%.1f", r.meanRank())).setHeader("Ø " + what + " rank")
                .setAutoWidth(true).setTextAlign(ColumnTextAlign.END).setComparator(PlaceRating::meanRank);
        grid.addColumn(r -> r.bestRank() == null ? "" : String.valueOf(r.bestRank())).setHeader("Best")
                .setAutoWidth(true).setTextAlign(ColumnTextAlign.END);
        grid.addColumn(r -> String.format(Locale.ROOT, "%.0f %%", 100 * r.share())).setHeader("Field beaten")
                .setAutoWidth(true).setTextAlign(ColumnTextAlign.END).setComparator(PlaceRating::share);
        grid.addComponentColumn(r -> delta(r.delta())).setHeader("vs. career").setAutoWidth(true)
                .setTextAlign(ColumnTextAlign.END).setComparator(PlaceRating::delta);
        grid.setItems(ratings);
        grid.setAllRowsVisible(ratings.size() <= 12);
        if (ratings.size() > 12) grid.setHeight("26em");
        card.add(grid);
        return card;
    }

    // ── venues ─────────────────────────────────────────────────────────────

    private Grid<VenueStats> venueGrid(List<VenueStats> venues) {
        Grid<VenueStats> grid = new Grid<>(VenueStats.class, false);
        grid.addComponentColumn(v -> place(v.label(), v.venue().getCountry())).setHeader("Venue")
                .setAutoWidth(true).setFlexGrow(1).setComparator(VenueStats::label);
        grid.addColumn(VenueStats::starts).setHeader("Starts").setAutoWidth(true)
                .setTextAlign(ColumnTextAlign.END).setSortable(true);
        grid.addColumn(VenueStats::wins).setHeader("Wins").setAutoWidth(true)
                .setTextAlign(ColumnTextAlign.END).setSortable(true);
        grid.addColumn(VenueStats::podiums).setHeader("Podiums").setAutoWidth(true)
                .setTextAlign(ColumnTextAlign.END).setSortable(true);
        grid.addColumn(VenueStats::top10).setHeader("Top 10").setAutoWidth(true)
                .setTextAlign(ColumnTextAlign.END).setSortable(true);
        grid.addColumn(v -> v.bestRank() == null ? "" : String.valueOf(v.bestRank())).setHeader("Best")
                .setAutoWidth(true).setTextAlign(ColumnTextAlign.END)
                .setComparator(v -> v.bestRank() == null ? Integer.MAX_VALUE : v.bestRank());
        grid.addColumn(v -> v.meanRank() == null ? "" : String.format(Locale.ROOT, "%.1f", v.meanRank()))
                .setHeader("Ø rank").setAutoWidth(true).setTextAlign(ColumnTextAlign.END)
                .setComparator(v -> v.meanRank() == null ? 999 : v.meanRank());
        grid.addComponentColumn(v -> delta(v.jumpDelta())).setHeader("Jump vs. career").setAutoWidth(true)
                .setTextAlign(ColumnTextAlign.END).setComparator(v -> v.jumpDelta() == null ? -9 : v.jumpDelta());
        grid.addComponentColumn(v -> delta(v.xcDelta())).setHeader("XC vs. career").setAutoWidth(true)
                .setTextAlign(ColumnTextAlign.END).setComparator(v -> v.xcDelta() == null ? -9 : v.xcDelta());
        grid.setItems(venues);
        grid.setAllRowsVisible(venues.size() <= 15);
        if (venues.size() > 15) grid.setHeight("36em");
        grid.addSelectionListener(e -> e.getFirstSelectedItem().ifPresent(v ->
                UI.getCurrent().navigate(VenueDetailView.class, v.venue().getId())));
        return grid;
    }

    // ── highlight cards ────────────────────────────────────────────────────

    /**
     * The cards above the tabs: World Cup only, so that a Continental Cup win
     * does not stand next to World Cup results.  Nothing for an athlete without
     * World Cup starts.
     */
    static Component highlights(AthleteProfile all) {
        AthleteProfile p = all.forCircuit("WC");
        FlexLayout row = new FlexLayout();
        row.setFlexWrap(FlexLayout.FlexWrap.WRAP);
        row.getStyle().set("gap", "var(--lumo-space-m)");
        row.setWidthFull();
        row.addClassNames(LumoUtility.Padding.Vertical.SMALL);

        List<CombinedResult> best = p.bestResults();
        if (!best.isEmpty()) {
            CombinedResult first = best.get(0);
            List<Competition> where = best.stream().map(CombinedResult::getCompetition).toList();
            // achieved several times: how often, where the first time, and the list of all
            row.add(linkedHighlight("Best World Cup result",
                    rankLabel(first) + (best.size() > 1 ? " · " + best.size() + "×" : ""),
                    best.size() > 1 ? "first: " : "", where,
                    c -> c.getDisplayLocation() + " " + c.getCompetitionDate(),
                    rankLabel(first) + " in the World Cup"));
        }
        List<JumpResult> longest = p.longestWorldCupJumps();
        if (!longest.isEmpty()) {
            JumpResult first = longest.get(0);
            Map<Long, String> lists = new java.util.HashMap<>();
            longest.forEach(j -> lists.putIfAbsent(j.getCompetition().getId(),
                    JumpResult.listLabel("RL").equals(j.getListLabel()) ? "" : " · " + j.getListLabel()));
            List<Competition> where = longest.stream().map(JumpResult::getCompetition).distinct().toList();
            row.add(linkedHighlight("Longest World Cup jump",
                    JumpResult.format(first.getDistanceM()) + " m" + (longest.size() > 1 ? " · " + longest.size() + "×" : ""),
                    longest.size() > 1 ? "first: " : "", where,
                    c -> c.getDisplayLocation() + " " + AthleteProfile.hillLabel(c) + " · " + c.getCompetitionDate()
                            + lists.getOrDefault(c.getId(), ""),
                    JumpResult.format(first.getDistanceM()) + " m in the World Cup"));
        }
        p.mostSuccessfulVenue().ifPresent(v -> row.add(highlight("Most successful World Cup venue", v.label(), v.venue().getCountry(),
                v.podiums() > 0 ? count(v.wins(), "win") + " · " + count(v.podiums(), "podium")
                        : count(v.top10(), "top-10 result"), null)));
        p.mostVisitedVenue().ifPresent(v -> row.add(highlight("Most World Cup starts", v.label(), v.venue().getCountry(),
                count(v.starts(), "start") + (v.starts() > v.individualStarts()
                        ? " (" + (v.starts() - v.individualStarts()) + " in teams)" : ""), null)));
        p.favouriteHills().stream().findFirst().filter(r -> r.delta() > 0).ifPresent(r -> row.add(
                highlight("Favourite World Cup hill", r.label(), r.country(), String.format(Locale.ROOT,
                        "beats %.0f %% of the field · %+.0f pp", 100 * r.share(), 100 * r.delta()), null)));
        p.favouriteCourses().stream().findFirst().filter(r -> r.delta() > 0).ifPresent(r -> row.add(
                highlight("Favourite World Cup XC course", r.label(), r.country(), String.format(Locale.ROOT,
                        "beats %.0f %% of the field · %+.0f pp", 100 * r.share(), 100 * r.delta()), null)));
        return row;
    }

    /** A card; valueCountry / detailCountry: the flag in front of the value or of the detail line, or null. */
    private static Component highlight(String title, String value, String valueCountry,
                                       String detail, String detailCountry) {
        VerticalLayout card = card();
        card.setWidth(null);
        card.getStyle().set("flex", "1 1 13em").set("max-width", "22em");
        Span t = new Span(title);
        t.addClassNames(LumoUtility.FontSize.XSMALL, LumoUtility.TextColor.SECONDARY);
        t.getStyle().set("text-transform", "uppercase").set("letter-spacing", "0.04em");
        Span v = withFlag(value, valueCountry);
        v.addClassNames(LumoUtility.FontSize.XLARGE, LumoUtility.FontWeight.BOLD);
        Span d = withFlag(detail, detailCountry);
        d.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.TextColor.SECONDARY);
        card.add(t, v, d);
        return card;
    }

    /**
     * A card whose detail line links to the competition where it was achieved; if there are
     * several, to the first one, and 'All n' opens the list of them.
     */
    private static Component linkedHighlight(String title, String value, String prefix, List<Competition> where,
                                             Function<Competition, String> label, String listTitle) {
        VerticalLayout card = (VerticalLayout) highlight(title, value, null, "", null);
        card.getComponentAt(2).getElement().removeFromParent();          // the plain detail line
        Competition first = where.get(0);
        Span detail = new Span();
        detail.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.TextColor.SECONDARY);
        detail.getStyle().set("display", "inline-flex").set("align-items", "center").set("gap", "0.4em")
                .set("flex-wrap", "wrap");
        if (!prefix.isEmpty()) detail.add(new Span(prefix));
        detail.add(new NationFlag(first.getDisplayCountry(), false), link(first, label.apply(first)));
        card.add(detail);
        if (where.size() > 1) {
            Anchor all = new Anchor();
            all.setText("All " + where.size() + " ›");
            all.addClassNames(LumoUtility.FontSize.SMALL);
            all.getStyle().set("cursor", "pointer");
            all.getElement().addEventListener("click", e -> competitionList(listTitle, where, label).open());
            card.add(all);
        }
        return card;
    }

    private static Anchor link(Competition c, String text) {
        Anchor a = new Anchor("result/" + c.getId(), text);
        a.getStyle().set("text-decoration", "none");
        return a;
    }

    /** The competitions of a highlight, newest last, each a link. */
    private static Dialog competitionList(String title, List<Competition> where, Function<Competition, String> label) {
        Dialog dialog = new Dialog();
        dialog.setHeaderTitle(title + " (" + where.size() + ")");
        VerticalLayout list = new VerticalLayout();
        list.setPadding(false);
        list.setSpacing(false);
        for (Competition c : where) {
            Span line = new Span(new NationFlag(c.getDisplayCountry(), false), link(c, label.apply(c)),
                    new Span(c.getFormat() == null ? "" : "· " + c.getFormat()));
            line.getStyle().set("display", "inline-flex").set("align-items", "center").set("gap", "0.5em")
                    .set("padding", "var(--lumo-space-xs) 0");
            line.getChildren().skip(2).forEach(x -> ((Span) x).addClassNames(LumoUtility.TextColor.SECONDARY));
            list.add(line);
        }
        dialog.add(list);
        Button close = new Button("Close", e -> dialog.close());
        dialog.getFooter().add(close);
        dialog.setMaxHeight("80vh");
        return dialog;
    }

    private static Span withFlag(String text, String country) {
        if (country == null || country.isBlank()) {
            return new Span(text);
        }
        Span s = new Span(new NationFlag(country, false), new Span(text));
        s.getStyle().set("display", "inline-flex").set("align-items", "center").set("gap", "0.4em");
        return s;
    }

    private static String rankLabel(CombinedResult r) {
        int rank = r.getRank();
        String suffix = rank % 100 >= 11 && rank % 100 <= 13 ? "th"
                : switch (rank % 10) { case 1 -> "st"; case 2 -> "nd"; case 3 -> "rd"; default -> "th"; };
        return rank + suffix + (rank == 1 ? " place" : "");
    }

    private static String where(Competition c) {
        return c.getDisplayLocation() + " " + c.getCompetitionDate();
    }


    private static String count(int n, String what) {
        return n + " " + what + (n == 1 ? "" : "s");
    }

    // ── small parts ────────────────────────────────────────────────────────

    private static VerticalLayout card() {
        VerticalLayout card = new VerticalLayout();
        card.setPadding(true);
        card.setSpacing(false);
        card.getStyle()
                .set("border", "1px solid var(--lumo-contrast-20pct)")
                .set("border-radius", "var(--lumo-border-radius-m)")
                .set("background", "var(--lumo-contrast-5pct)");
        return card;
    }

    private static Span muted(String text) {
        Span s = new Span(text);
        s.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.TextColor.SECONDARY, LumoUtility.Margin.Bottom.XSMALL);
        return s;
    }

    private static Component place(String label, String country) {
        Span s = new Span();
        if (country != null && !country.isBlank()) s.add(new NationFlag(country, false));
        s.add(new Span(label));
        s.getStyle().set("display", "inline-flex").set("align-items", "center").set("gap", "0.5em");
        return s;
    }

    /** '+12 pp' in green, '−8 pp' in red, empty if not rated. */
    private static Component delta(Double delta) {
        if (delta == null) return new Span();
        Span s = new Span(String.format(Locale.ROOT, "%+.0f pp", 100 * delta).replace("-", "−"));
        if (Math.abs(delta) >= 0.005) {
            s.getStyle().set("color", delta > 0 ? "var(--lumo-success-text-color)" : "var(--lumo-error-text-color)");
        }
        s.getStyle().set("font-variant-numeric", "tabular-nums");
        return s;
    }
}
