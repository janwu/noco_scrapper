package com.fis.noco.views;

import com.fis.noco.entity.CombinedResult;
import com.fis.noco.entity.Competition;
import com.fis.noco.entity.JumpResult;
import com.fis.noco.entity.TeamMember;
import com.fis.noco.entity.TeamResult;
import com.fis.noco.entity.XcResult;
import com.fis.noco.service.CompetitionService;
import com.vaadin.flow.component.Component;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.button.Button;
import com.vaadin.flow.component.button.ButtonVariant;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.html.Anchor;
import com.vaadin.flow.component.html.Div;
import com.vaadin.flow.component.html.H2;
import com.vaadin.flow.component.html.H3;
import com.vaadin.flow.component.html.Paragraph;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.tabs.TabSheet;
import com.vaadin.flow.router.BeforeEvent;
import com.vaadin.flow.router.HasUrlParameter;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.QueryParameters;
import com.vaadin.flow.router.Route;
import com.vaadin.flow.theme.lumo.LumoUtility;

import java.util.List;
import java.util.Map;

@Route(value = "result", layout = MainLayout.class)
@PageTitle("Competition Result | FIS Nordic Combined")
public class ResultDetailView extends VerticalLayout implements HasUrlParameter<Long> {

    private final CompetitionService competitionService;

    public ResultDetailView(CompetitionService competitionService) {
        this.competitionService = competitionService;
        setSizeFull();
        setPadding(true);
    }

    @Override
    public void setParameter(BeforeEvent event, Long competitionId) {
        removeAll();

        competitionService.findById(competitionId).ifPresentOrElse(
                this::buildContent,
                () -> add(new Paragraph("Competition not found."))
        );
    }

    private void buildContent(Competition competition) {
        // back to the filter chosen in the browser; without one, to the season of this competition
        QueryParameters back = ResultsBrowserView.lastFilter();
        if (back == null) {
            back = ResultsBrowserView.filter(competition.getCircuit(), competition.getSeason(), null);
        }
        QueryParameters target = back;
        Button backButton = new Button("← Back to Results Browser", e ->
                UI.getCurrent().navigate("results", target));
        backButton.addThemeVariants(ButtonVariant.LUMO_TERTIARY);

        String circuitLabel = competition.getCircuitLabel();
        String location = competition.getDisplayLocation();
        String country = competition.getDisplayCountry();
        String date = competition.getCompetitionDate() != null ? competition.getCompetitionDate() : "";

        H2 header = new H2(new Span(location));
        if (!country.isBlank()) {
            header.add(new NationFlag(country));
        }
        header.getStyle().set("display", "flex").set("align-items", "center").set("gap", "0.5em");
        header.addClassNames(LumoUtility.Margin.Bottom.XSMALL);

        HorizontalLayout metaRow = new HorizontalLayout();
        metaRow.setSpacing(true);
        metaRow.setDefaultVerticalComponentAlignment(Alignment.CENTER);
        metaRow.getStyle().set("flex-wrap", "wrap");

        addMeta(metaRow, "Date", date);
        addMeta(metaRow, "Circuit", circuitLabel);
        if (competition.getFormat() != null) addMeta(metaRow, "Format", competition.getFormat());
        if (competition.getGender() != null) addMeta(metaRow, "Gender", competition.getGender());
        if (competition.getSeason() != null && !"WSC".equals(competition.getCircuit()))
            addMeta(metaRow, "Season", competition.getSeason().getLabel());
        if (competition.getXcDistanceKm() != null)
            addMeta(metaRow, "XC Distance", competition.getXcDistanceKm() + " km");
        if (competition.getHillSizeM() != null)
            addMeta(metaRow, "Hill Size", competition.getHillSizeM() + " m");

        add(backButton, header, metaRow);
        if (competition.isOlympic()) {
            Span olympic = new Span("Olympic Winter Games " + competition.getYear()
                    + " — until 1980 the Olympic competitions were the World Championships as well.");
            olympic.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.TextColor.SECONDARY);
            add(olympic);
        }

        Component result;
        String resultTab;
        Component crossCountry = null;
        String crossCountryTab = null;
        if (CompetitionService.isTeamFormat(competition.getFormat())) {
            List<TeamResult> teams = competitionService.getTeamResultsForCompetition(competition.getId());
            resultTab = "Result (" + teams.size() + " teams)";
            result = teams.isEmpty() ? null : createTeamGrid(teams);
        } else {
            List<CombinedResult> results = competitionService.getResultsForCompetition(competition.getId());
            resultTab = "Result (" + results.size() + " athletes)";
            boolean isMassStart = CompetitionService.isJumpLast(competition.getFormat());
            result = results.isEmpty() ? null : createResultsGrid(results, isMassStart);
            // Mass start and super sprint: the race comes first and has a result of its own
            List<CombinedResult> raced = results.stream().filter(r -> r.getXcRank() != null).toList();
            if (isMassStart && !raced.isEmpty()) {
                crossCountryTab = "Cross-Country (" + raced.size() + ")";
                crossCountry = createCrossCountryGrid(results);
            } else if (isMassStart) {
                // no race data in the result list, or no result list at all (jumping cancelled):
                // the cross-country list of its own
                List<XcResult> race = competitionService.getXcResults(competition.getId());
                if (!race.isEmpty()) {
                    crossCountryTab = "Cross-Country (" + race.stream().filter(x -> x.getRank() != null).count() + ")";
                    crossCountry = createXcListGrid(race);
                    if (results.isEmpty()) {
                        Paragraph note = new Paragraph("No final result: the ski jumping did not take place. "
                                + "The cross-country race was held.");
                        note.addClassNames(LumoUtility.TextColor.SECONDARY, LumoUtility.Margin.Vertical.XSMALL);
                        add(note);
                    }
                }
            }
        }

        // The jump lists: competition round, qualification, provisional round
        Map<String, List<JumpResult>> jumpLists = competitionService.getJumpLists(competition.getId());
        if (jumpLists.isEmpty() && crossCountry == null) {
            if (result == null) {
                add(new Paragraph("No results."));
                return;
            }
            H3 title = new H3(resultTab);
            title.addClassNames(LumoUtility.Margin.Top.MEDIUM, LumoUtility.Margin.Bottom.XSMALL);
            add(title, result);
            expand(result);
            return;
        }

        TabSheet tabs = new TabSheet();
        tabs.setSizeFull();
        tabs.addClassNames(LumoUtility.Margin.Top.SMALL);
        if (result != null) {
            tabs.add(resultTab, result);
        }
        if (crossCountry != null) {
            tabs.add(crossCountryTab, crossCountry);
        }
        jumpLists.forEach((label, jumps) -> {
            // athletes, not jumps: in training some leave out the first round
            long athletes = jumps.stream().map(j -> j.getDisplayName() + "|" + j.getBib()).distinct().count();
            String name = JumpResult.listLabel("RL").equals(label) ? "Ski Jumping" : label;
            tabs.add(name + " (" + athletes + ")", JumpGrid.create(jumps));
        });
        add(tabs);
        expand(tabs);
    }

    private void addMeta(HorizontalLayout layout, String label, String value) {
        Span container = new Span();
        container.getStyle().set("background", "var(--lumo-contrast-5pct)");
        container.getStyle().set("padding", "2px 8px");
        container.getStyle().set("border-radius", "var(--lumo-border-radius-s)");
        container.getStyle().set("font-size", "var(--lumo-font-size-s)");
        Span labelSpan = new Span(label + ": ");
        labelSpan.getStyle().set("color", "var(--lumo-secondary-text-color)");
        Span valueSpan = new Span(value);
        valueSpan.getStyle().set("font-weight", "bold");
        container.add(labelSpan, valueSpan);
        layout.add(container);
    }

    private Grid<CombinedResult> createResultsGrid(List<CombinedResult> results, boolean isMassStart) {
        Grid<CombinedResult> grid = new Grid<>(CombinedResult.class, false);
        grid.setSizeFull();

        grid.addColumn(CombinedResult::getRank)
                .setHeader("Rank").setAutoWidth(true).setSortable(true);

        grid.addColumn(CombinedResult::getBib)
                .setHeader("Bib").setAutoWidth(true).setSortable(true);

        grid.addColumn(CombinedResult::getDisplayName)
                .setHeader("Name").setAutoWidth(true).setSortable(true);

        grid.addComponentColumn(r -> new NationFlag(r.getDisplayNation()))
                .setHeader("Nation").setAutoWidth(true);

        if (isMassStart) {
            // Mass Start: XC is first, SJ is the final phase
            // Rank / Bib / Name / Nation / XC Time / XC Rank / XC pts diff / SJ Points / SJ Rank / Final pts diff
            grid.addColumn(CombinedResult::getXcTime)
                    .setHeader("XC Time").setAutoWidth(true).setSortable(true);
            grid.addColumn(CombinedResult::getXcRank)
                    .setHeader("XC Rank").setAutoWidth(true).setSortable(true);
            grid.addColumn(CombinedResult::getTimeDifference)
                    .setHeader("XC Pts Diff").setAutoWidth(true);
            grid.addColumn(CombinedResult::getJumpPoints)
                    .setHeader("SJ Points").setAutoWidth(true).setSortable(true);
            grid.addColumn(CombinedResult::getJumpRank)
                    .setHeader("SJ Rank").setAutoWidth(true).setSortable(true);
            grid.addColumn(CombinedResult::getFinishGap)
                    .setHeader("Final Pts Diff").setAutoWidth(true);
        } else {
            // Gundersen / Compact / Sprint / Penalty Race: SJ is first, XC is the final phase
            grid.addColumn(CombinedResult::getJumpPoints)
                    .setHeader("Jump Pts").setAutoWidth(true).setSortable(true);
            grid.addColumn(CombinedResult::getJumpRank)
                    .setHeader("Jump Rank").setAutoWidth(true).setSortable(true);
            grid.addColumn(CombinedResult::getTimeDifference)
                    .setHeader("Start Gap").setAutoWidth(true);
            grid.addColumn(CombinedResult::getXcTime)
                    .setHeader("XC Time").setAutoWidth(true).setSortable(true);
            grid.addColumn(CombinedResult::getXcRank)
                    .setHeader("XC Rank").setAutoWidth(true).setSortable(true);
            grid.addColumn(CombinedResult::getFinishGap)
                    .setHeader("Behind").setAutoWidth(true);
            grid.addColumn(r -> r.isWaveStart() ? "Yes" : "")
                    .setHeader("Wave Start").setAutoWidth(true);
        }

        grid.addComponentColumn(r -> statusBadge(r.getStatus()))
                .setHeader("Status").setAutoWidth(true);

        grid.setClassNameGenerator(r -> r.isWaveStart() ? "wave-start-row" : null);

        grid.addSelectionListener(event -> event.getFirstSelectedItem().ifPresent(r -> {
            if (r.getAthlete() != null) {
                UI.getCurrent().navigate(AthleteDetailView.class, r.getAthlete().getId());
            }
        }));

        grid.setItems(results);
        return grid;
    }

    /**
     * The cross-country race of a mass start or super sprint, by the rank of the race time:
     * time, gap to the fastest, the points that gap costs in the jump, and the final rank.
     * Read from the result list; athletes without a race rank (DNF in the race) come last.
     */
    private Grid<CombinedResult> createCrossCountryGrid(List<CombinedResult> results) {
        List<CombinedResult> rows = new java.util.ArrayList<>(results);
        // the rank decides (a photo finish may rank a slower time first), then the time
        rows.sort(java.util.Comparator.comparing(CombinedResult::getXcRank,
                        java.util.Comparator.nullsLast(java.util.Comparator.naturalOrder()))
                .thenComparing(r -> seconds(r.getXcTime()), java.util.Comparator.nullsLast(java.util.Comparator.naturalOrder())));
        Double best = rows.stream().map(r -> seconds(r.getXcTime())).filter(java.util.Objects::nonNull)
                .min(Double::compare).orElse(null);

        Grid<CombinedResult> grid = new Grid<>(CombinedResult.class, false);
        grid.setSizeFull();
        grid.addColumn(CombinedResult::getXcRank).setHeader("XC Rank").setAutoWidth(true).setFlexGrow(0);
        grid.addColumn(CombinedResult::getBib).setHeader("Bib").setAutoWidth(true).setFlexGrow(0);
        grid.addColumn(CombinedResult::getDisplayName).setHeader("Name").setAutoWidth(true);
        grid.addComponentColumn(r -> new NationFlag(r.getDisplayNation())).setHeader("Nation").setAutoWidth(true);
        grid.addColumn(CombinedResult::getXcTime).setHeader("XC Time").setAutoWidth(true);
        grid.addColumn(r -> gap(seconds(r.getXcTime()), best)).setHeader("Behind fastest").setAutoWidth(true);
        grid.addColumn(CombinedResult::getTimeDifference).setHeader("Points Diff").setAutoWidth(true);
        grid.addColumn(CombinedResult::getRank).setHeader("Final Rank").setAutoWidth(true)
                .setComparator(r -> r.getRank() == null ? Integer.MAX_VALUE : r.getRank());
        grid.addComponentColumn(r -> statusBadge(r.getStatus())).setHeader("Status").setAutoWidth(true);
        grid.addSelectionListener(event -> event.getFirstSelectedItem().ifPresent(r -> {
            if (r.getAthlete() != null) {
                UI.getCurrent().navigate(AthleteDetailView.class, r.getAthlete().getId());
            }
        }));
        grid.setItems(rows);
        return grid;
    }

    /** The cross-country list of a mass start as FIS prints it: rank, time, gap, jump points it costs. */
    private Grid<XcResult> createXcListGrid(List<XcResult> race) {
        Grid<XcResult> grid = new Grid<>(XcResult.class, false);
        grid.setSizeFull();
        grid.addColumn(XcResult::getRank).setHeader("XC Rank").setAutoWidth(true).setFlexGrow(0);
        grid.addColumn(XcResult::getBib).setHeader("Bib").setAutoWidth(true).setFlexGrow(0);
        grid.addColumn(XcResult::getDisplayName).setHeader("Name").setAutoWidth(true);
        grid.addComponentColumn(x -> new NationFlag(x.getDisplayNation())).setHeader("Nation").setAutoWidth(true);
        grid.addColumn(XcResult::getTotalTime).setHeader("XC Time").setAutoWidth(true);
        grid.addColumn(XcResult::getTimeBehind).setHeader("Behind").setAutoWidth(true);
        grid.addColumn(x -> x.getPoints() == null ? "" : String.format(java.util.Locale.ROOT, "%.1f", x.getPoints()))
                .setHeader("Points").setAutoWidth(true);
        grid.addComponentColumn(x -> statusBadge(x.getStatus())).setHeader("Status").setAutoWidth(true);
        grid.addSelectionListener(event -> event.getFirstSelectedItem().ifPresent(x -> {
            if (x.getAthlete() != null) {
                UI.getCurrent().navigate(AthleteDetailView.class, x.getAthlete().getId());
            }
        }));
        grid.setItems(race);
        return grid;
    }

    /** '23:55.5' → 1435.5 seconds; null if not a time. */
    static Double seconds(String clock) {
        if (clock == null || !clock.matches("(?:\\d+:)?\\d{1,2}:\\d{2}\\.\\d")) return null;
        double total = 0;
        for (String part : clock.split(":")) total = total * 60 + Double.parseDouble(part);
        return total;
    }

    /** '+6.5', '+1:02.3'; '0.0' for the fastest; empty without a time. */
    static String gap(Double time, Double best) {
        if (time == null || best == null) return "";
        double gap = time - best;
        if (gap < 0.05) return "0.0";
        long tenths = Math.round(gap * 10);
        long minutes = tenths / 600;
        double rest = (tenths % 600) / 10.0;
        return minutes > 0 ? String.format(java.util.Locale.ROOT, "+%d:%04.1f", minutes, rest)
                           : String.format(java.util.Locale.ROOT, "+%.1f", rest);
    }

    private Grid<TeamResult> createTeamGrid(List<TeamResult> teams) {
        Grid<TeamResult> grid = new Grid<>(TeamResult.class, false);
        grid.setSizeFull();
        grid.setSelectionMode(Grid.SelectionMode.NONE);

        grid.addColumn(TeamResult::getRank)
                .setHeader("Rank").setAutoWidth(true).setFlexGrow(0);
        grid.addColumn(TeamResult::getBib)
                .setHeader("Bib").setAutoWidth(true).setFlexGrow(0);
        grid.addComponentColumn(t -> {
            Span team = new Span(new NationFlag(t.getNation(), false), new Span(t.getDisplayName()));
            team.getStyle().set("display", "inline-flex").set("align-items", "center")
                    .set("gap", "0.5em").set("font-weight", "bold");
            return team;
        }).setHeader("Team").setAutoWidth(true);
        grid.addComponentColumn(this::memberList)
                .setHeader("Athletes (jump points · leg time)").setAutoWidth(true).setFlexGrow(1);
        grid.addColumn(TeamResult::getJumpPoints)
                .setHeader("Jump Pts").setAutoWidth(true);
        grid.addColumn(TeamResult::getJumpRank)
                .setHeader("Jump Rank").setAutoWidth(true);
        grid.addColumn(TeamResult::getTimeDifference)
                .setHeader("Start Gap").setAutoWidth(true);
        grid.addColumn(TeamResult::getXcTime)
                .setHeader("XC Time").setAutoWidth(true);
        grid.addColumn(TeamResult::getXcRank)
                .setHeader("XC Rank").setAutoWidth(true);
        grid.addColumn(TeamResult::getFinishGap)
                .setHeader("Behind").setAutoWidth(true);
        grid.addComponentColumn(t -> statusBadge(t.getStatus()))
                .setHeader("Status").setAutoWidth(true);

        grid.setItems(teams);
        return grid;
    }

    /** The athletes of a team, one per line, each linked to the athlete page. */
    private Div memberList(TeamResult team) {
        Div list = new Div();
        list.getStyle().set("display", "flex").set("flex-direction", "column")
                .set("font-size", "var(--lumo-font-size-s)").set("line-height", "1.5");
        for (TeamMember m : team.getMembers()) {
            Div line = new Div();
            line.getStyle().set("display", "flex").set("gap", "0.6em").set("align-items", "baseline");
            if (m.getAthlete() != null) {
                Anchor link = new Anchor("athlete/" + m.getAthlete().getId(), m.getDisplayName());
                link.getStyle().set("text-decoration", "none");
                line.add(link);
            } else {
                line.add(new Span(m.getDisplayName()));
            }
            StringBuilder detail = new StringBuilder();
            if (m.getJumpPoints() != null) detail.append(m.getJumpPoints());
            if (m.getXcTime() != null) detail.append(detail.length() > 0 ? " · " : "").append(m.getXcTime());
            if (detail.length() > 0) {
                Span detailSpan = new Span(detail.toString());
                detailSpan.getStyle().set("color", "var(--lumo-secondary-text-color)");
                line.add(detailSpan);
            }
            list.add(line);
        }
        return list;
    }

    private Span statusBadge(String status) {
        if (status != null && !status.isBlank()) {
            Span badge = new Span(status);
            if (status.equalsIgnoreCase("DSQ") || status.equalsIgnoreCase("DNF")
                    || status.equalsIgnoreCase("DNS")) {
                badge.getStyle().set("color", "var(--lumo-error-color)");
                badge.getStyle().set("font-weight", "bold");
            } else {
                badge.getStyle().set("color", "var(--lumo-success-color)");
            }
            return badge;
        }
        Span ok = new Span("OK");
        ok.getStyle().set("color", "var(--lumo-success-color)");
        return ok;
    }
}
