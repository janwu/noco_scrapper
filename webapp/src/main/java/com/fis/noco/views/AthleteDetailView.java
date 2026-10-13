package com.fis.noco.views;

import com.fis.noco.entity.Athlete;
import com.fis.noco.entity.CombinedResult;
import com.fis.noco.entity.Competition;
import com.fis.noco.entity.TeamMember;
import com.fis.noco.entity.TeamResult;
import com.fis.noco.service.AthleteService;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.button.Button;
import com.vaadin.flow.component.button.ButtonVariant;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.html.H2;
import com.vaadin.flow.component.html.H4;
import com.vaadin.flow.component.html.Paragraph;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.radiobutton.RadioButtonGroup;
import com.vaadin.flow.component.tabs.TabSheet;
import com.vaadin.flow.router.BeforeEvent;
import com.vaadin.flow.router.HasUrlParameter;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;
import com.vaadin.flow.theme.lumo.LumoUtility;

import java.time.LocalDate;
import java.time.temporal.ChronoUnit;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

@Route(value = "athlete", layout = MainLayout.class)
@PageTitle("Athlete Detail | FIS Nordic Combined")
public class AthleteDetailView extends VerticalLayout implements HasUrlParameter<Long> {

    private final AthleteService athleteService;

    public AthleteDetailView(AthleteService athleteService) {
        this.athleteService = athleteService;
        setSizeFull();
        setPadding(true);
    }

    @Override
    public void setParameter(BeforeEvent event, Long athleteId) {
        removeAll();

        athleteService.findById(athleteId).ifPresentOrElse(
                this::buildContent,
                () -> add(new Paragraph("Athlete not found."))
        );
    }

    private void buildContent(Athlete athlete) {
        Button backButton = new Button("← Back to Athletes", e ->
                UI.getCurrent().navigate(AthleteSearchView.class));
        backButton.addThemeVariants(ButtonVariant.LUMO_TERTIARY);

        H2 nameHeader = new H2(athlete.getFullName());
        nameHeader.addClassNames(LumoUtility.Margin.Bottom.XSMALL);

        HorizontalLayout infoRow = new HorizontalLayout();
        infoRow.setSpacing(true);

        if (athlete.getNationality() != null) {
            NationFlag nat = new NationFlag(athlete.getNationality());
            nat.addClassNames(LumoUtility.FontWeight.BOLD);
            infoRow.add(nat);
        }
        if (athlete.getGender() != null) {
            infoRow.add(new Span("Gender: " + athlete.getGender()));
        }
        if (athlete.getBirthDate() != null) {
            infoRow.add(new Span("Born: " + athlete.getBirthDate()));
        }
        if (athlete.getActiveClub() != null) {
            infoRow.add(new Span("Club: " + athlete.getActiveClub()));
        }

        List<CombinedResult> wcResults = athleteService.getWorldCupResults(athlete.getId());
        List<CombinedResult> cocResults = athleteService.getContinentalCupResults(athlete.getId());

        List<TeamMember> teamStarts = athleteService.getTeamStarts(athlete.getId());

        HorizontalLayout statsRow = buildStatsRow(athlete, wcResults, cocResults);
        if (!teamStarts.isEmpty()) {
            statsRow.add(buildTeamStatsBlock(teamStarts));
        }
        add(backButton, nameHeader, infoRow, statsRow);

        TabSheet tabSheet = new TabSheet();
        tabSheet.setSizeFull();
        tabSheet.add("World Cup (" + wcResults.size() + ")", createFilteredResultsPanel(wcResults));
        tabSheet.add("Continental Cup (" + cocResults.size() + ")", createFilteredResultsPanel(cocResults));
        if (!teamStarts.isEmpty()) {
            tabSheet.add("Team (" + teamStarts.size() + ")", createTeamStartsPanel(teamStarts, athlete));
        }

        add(tabSheet);
        expand(tabSheet);
    }

    private HorizontalLayout buildStatsRow(Athlete athlete, List<CombinedResult> wcResults, List<CombinedResult> cocResults) {
        HorizontalLayout row = new HorizontalLayout();
        row.setSpacing(true);
        row.setWidthFull();
        row.addClassNames(LumoUtility.Padding.Vertical.SMALL);

        row.add(buildStatsBlock("World Cup", wcResults, true, athlete.getBirthDate()));
        row.add(buildStatsBlock("Continental Cup", cocResults, false, athlete.getBirthDate()));

        return row;
    }

    private VerticalLayout buildStatsBlock(String title, List<CombinedResult> results,
                                           boolean includeTop30, String birthDate) {
        long appearances = results.size();
        long finished = results.stream().filter(r -> r.getStatus() == null || r.getStatus().isBlank()).count();
        long wins   = results.stream().filter(r -> r.getRank() != null && r.getRank() == 1).count();
        long top3   = results.stream().filter(r -> r.getRank() != null && r.getRank() <= 3).count();
        long top10  = results.stream().filter(r -> r.getRank() != null && r.getRank() <= 10).count();
        long top30  = results.stream().filter(r -> r.getRank() != null && r.getRank() <= 30).count();
        long dns    = results.stream().filter(r -> "DNS".equalsIgnoreCase(r.getStatus())).count();
        long dnf    = results.stream().filter(r -> "DNF".equalsIgnoreCase(r.getStatus())).count();
        long dsq    = results.stream().filter(r -> "DSQ".equalsIgnoreCase(r.getStatus())).count();

        Optional<CombinedResult> firstAppearance = results.stream()
                .filter(r -> r.getCompetition() != null && r.getCompetition().getCompetitionDate() != null)
                .min(Comparator.comparing(r -> r.getCompetition().getCompetitionDate()));

        Optional<CombinedResult> lastAppearance = results.stream()
                .filter(r -> r.getCompetition() != null && r.getCompetition().getCompetitionDate() != null)
                .max(Comparator.comparing(r -> r.getCompetition().getCompetitionDate()));

        long seasonCount = results.stream()
                .filter(r -> r.getCompetition() != null && r.getCompetition().getSeason() != null)
                .map(r -> r.getCompetition().getSeason().getId())
                .distinct()
                .count();

        VerticalLayout block = new VerticalLayout();
        block.setPadding(true);
        block.setSpacing(false);
        block.getStyle()
                .set("border", "1px solid var(--lumo-contrast-20pct)")
                .set("border-radius", "var(--lumo-border-radius-m)")
                .set("background", "var(--lumo-contrast-5pct)");

        H4 header = new H4(title);
        header.addClassNames(LumoUtility.Margin.Bottom.XSMALL, LumoUtility.Margin.Top.NONE);
        block.add(header);

        HorizontalLayout stats = new HorizontalLayout();
        stats.setSpacing(true);
        stats.add(statBadge("Appearances", appearances));
        stats.add(statBadge("Finished", finished));
        stats.add(statBadge("Wins", wins));
        stats.add(statBadge("Top 3", top3));
        stats.add(statBadge("Top 10", top10));
        if (includeTop30) {
            stats.add(statBadge("Top 30", top30));
        }
        stats.add(statBadge("DNS", dns));
        stats.add(statBadge("DNF", dnf));
        stats.add(statBadge("DSQ", dsq));
        stats.add(statBadge("Seasons", seasonCount));

        if (firstAppearance.isPresent()) {
            String date = firstAppearance.get().getCompetition().getCompetitionDate();
            stats.add(dateBadge("Debut", date, ageAt(birthDate, date)));
        }
        if (lastAppearance.isPresent()) {
            String date = lastAppearance.get().getCompetition().getCompetitionDate();
            stats.add(dateBadge("Last app.", date, ageAt(birthDate, date)));
        }

        block.add(stats);
        return block;
    }

    /** Team starts are counted apart: a team win is not an individual win. */
    private VerticalLayout buildTeamStatsBlock(List<TeamMember> starts) {
        long wins  = starts.stream().filter(m -> rankOf(m) != null && rankOf(m) == 1).count();
        long top3  = starts.stream().filter(m -> rankOf(m) != null && rankOf(m) <= 3).count();
        long wc    = starts.stream().filter(m -> "WC".equals(m.getTeamResult().getCompetition().getCircuit())).count();

        VerticalLayout block = new VerticalLayout();
        block.setPadding(true);
        block.setSpacing(false);
        block.setWidth(null);
        block.getStyle()
                .set("border", "1px solid var(--lumo-contrast-20pct)")
                .set("border-radius", "var(--lumo-border-radius-m)")
                .set("background", "var(--lumo-contrast-5pct)");

        H4 header = new H4("Team");
        header.addClassNames(LumoUtility.Margin.Bottom.XSMALL, LumoUtility.Margin.Top.NONE);
        block.add(header);

        HorizontalLayout stats = new HorizontalLayout();
        stats.setSpacing(true);
        stats.add(statBadge("Starts", starts.size()));
        stats.add(statBadge("Wins", wins));
        stats.add(statBadge("Top 3", top3));
        stats.add(statBadge("World Cup", wc));
        stats.add(statBadge("Cont. Cup", starts.size() - wc));
        block.add(stats);
        return block;
    }

    private static Integer rankOf(TeamMember m) {
        return m.getTeamResult().getRank();
    }

    private VerticalLayout createTeamStartsPanel(List<TeamMember> starts, Athlete athlete) {
        Grid<TeamMember> grid = new Grid<>(TeamMember.class, false);
        grid.setSizeFull();
        grid.setMinHeight("400px");

        grid.addColumn(m -> m.getTeamResult().getCompetition().getCompetitionDate())
                .setHeader("Date").setAutoWidth(true).setSortable(true);
        grid.addColumn(m -> "WC".equals(m.getTeamResult().getCompetition().getCircuit()) ? "World Cup" : "Cont. Cup")
                .setHeader("Circuit").setAutoWidth(true).setSortable(true);
        grid.addColumn(m -> m.getTeamResult().getCompetition().getDisplayLocation())
                .setHeader("Location").setAutoWidth(true);
        grid.addColumn(m -> m.getTeamResult().getCompetition().getFormat())
                .setHeader("Format").setAutoWidth(true).setSortable(true);
        grid.addComponentColumn(m -> {
            TeamResult t = m.getTeamResult();
            Span team = new Span(new NationFlag(t.getNation(), false), new Span(t.getDisplayName()));
            team.getStyle().set("display", "inline-flex").set("align-items", "center").set("gap", "0.5em");
            return team;
        }).setHeader("Team").setAutoWidth(true);
        grid.addColumn(m -> m.getTeamResult().getMembers().stream()
                        .filter(mate -> mate.getAthlete() == null
                                || !mate.getAthlete().getId().equals(athlete.getId()))
                        .map(TeamMember::getDisplayName)
                        .collect(Collectors.joining(", ")))
                .setHeader("With").setAutoWidth(true).setFlexGrow(1);
        grid.addColumn(m -> m.getTeamResult().getRank())
                .setHeader("Rank").setAutoWidth(true).setSortable(true);
        grid.addColumn(m -> m.getTeamResult().getFinishGap())
                .setHeader("Behind").setAutoWidth(true);
        grid.addColumn(TeamMember::getJumpPoints)
                .setHeader("Own Jump Pts").setAutoWidth(true);
        grid.addColumn(TeamMember::getXcTime)
                .setHeader("Own Leg").setAutoWidth(true);
        grid.addComponentColumn(m -> statusBadge(m.getTeamResult().getStatus()))
                .setHeader("Status").setAutoWidth(true);

        grid.addSelectionListener(event -> event.getFirstSelectedItem().ifPresent(m ->
                UI.getCurrent().navigate(ResultDetailView.class, m.getTeamResult().getCompetition().getId())));

        RadioButtonGroup<String> filter = new RadioButtonGroup<>();
        filter.setItems("All", "Wins", "Top 3");
        filter.setValue("All");
        filter.addValueChangeListener(e -> grid.setItems(switch (e.getValue()) {
            case "Wins"  -> starts.stream().filter(m -> rankOf(m) != null && rankOf(m) == 1).toList();
            case "Top 3" -> starts.stream().filter(m -> rankOf(m) != null && rankOf(m) <= 3).toList();
            default      -> starts;
        }));
        HorizontalLayout filterRow = new HorizontalLayout(new Span("Filter: "), filter);
        filterRow.setAlignItems(Alignment.CENTER);
        filterRow.setSpacing(true);
        filterRow.addClassNames(LumoUtility.Padding.Bottom.XSMALL);

        grid.setItems(starts);
        VerticalLayout panel = new VerticalLayout(filterRow, grid);
        panel.setSizeFull();
        panel.setPadding(false);
        panel.setSpacing(false);
        panel.expand(grid);
        return panel;
    }

    private VerticalLayout statBadge(String label, long value) {
        VerticalLayout v = new VerticalLayout();
        v.setPadding(false);
        v.setSpacing(false);
        v.setAlignItems(Alignment.CENTER);
        v.setWidth(null);

        Span valueSpan = new Span(String.valueOf(value));
        valueSpan.addClassNames(LumoUtility.FontSize.XLARGE, LumoUtility.FontWeight.BOLD);

        Span labelSpan = new Span(label);
        labelSpan.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.TextColor.SECONDARY);

        v.add(valueSpan, labelSpan);
        return v;
    }

    private VerticalLayout dateBadge(String label, String date, String age) {
        VerticalLayout v = new VerticalLayout();
        v.setPadding(false);
        v.setSpacing(false);
        v.setAlignItems(Alignment.CENTER);
        v.setWidth(null);

        Span dateSpan = new Span(date);
        dateSpan.addClassNames(LumoUtility.FontSize.MEDIUM, LumoUtility.FontWeight.BOLD);

        String subText = age != null ? label + " · age " + age : label;
        Span labelSpan = new Span(subText);
        labelSpan.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.TextColor.SECONDARY);

        v.add(dateSpan, labelSpan);
        return v;
    }

    private String ageAt(String birthDateStr, String eventDateStr) {
        if (birthDateStr == null || birthDateStr.isBlank()
                || eventDateStr == null || eventDateStr.isBlank()) return null;
        try {
            LocalDate birth = LocalDate.parse(birthDateStr);
            LocalDate event = LocalDate.parse(eventDateStr);
            return String.valueOf(ChronoUnit.YEARS.between(birth, event));
        } catch (Exception e) {
            return null;
        }
    }

    private VerticalLayout createFilteredResultsPanel(List<CombinedResult> results) {
        Grid<CombinedResult> grid = createResultsGrid(results);

        RadioButtonGroup<String> filter = new RadioButtonGroup<>();
        filter.setItems("All", "Wins", "Top 3", "Top 10");
        filter.setValue("All");
        filter.addValueChangeListener(e -> {
            List<CombinedResult> filtered = switch (e.getValue()) {
                case "Wins"   -> results.stream().filter(r -> r.getRank() != null && r.getRank() == 1).toList();
                case "Top 3"  -> results.stream().filter(r -> r.getRank() != null && r.getRank() <= 3).toList();
                case "Top 10" -> results.stream().filter(r -> r.getRank() != null && r.getRank() <= 10).toList();
                default       -> results;
            };
            grid.setItems(filtered);
        });

        HorizontalLayout filterRow = new HorizontalLayout(new Span("Filter: "), filter);
        filterRow.setAlignItems(Alignment.CENTER);
        filterRow.setSpacing(true);
        filterRow.addClassNames(LumoUtility.Padding.Bottom.XSMALL);

        VerticalLayout panel = new VerticalLayout(filterRow, grid);
        panel.setSizeFull();
        panel.setPadding(false);
        panel.setSpacing(false);
        panel.expand(grid);
        return panel;
    }

    private Grid<CombinedResult> createResultsGrid(List<CombinedResult> results) {
        Grid<CombinedResult> grid = new Grid<>(CombinedResult.class, false);
        grid.setSizeFull();
        grid.setMinHeight("400px");

        grid.addColumn(r -> {
            Competition c = r.getCompetition();
            return c != null ? c.getCompetitionDate() : "";
        }).setHeader("Date").setAutoWidth(true).setSortable(true).setKey("date");

        grid.addColumn(r -> {
            Competition c = r.getCompetition();
            return c != null ? c.getDisplayLocation() : "";
        }).setHeader("Location").setAutoWidth(true).setKey("location");

        grid.addColumn(r -> {
            Competition c = r.getCompetition();
            return c != null ? c.getFormat() : "";
        }).setHeader("Format").setAutoWidth(true).setKey("format");

        grid.addColumn(CombinedResult::getRank)
                .setHeader("Rank").setAutoWidth(true).setSortable(true);

        // Gap to the winner at the finish: time, or points in a Mass Start
        grid.addColumn(CombinedResult::getFinishGap)
                .setHeader("Behind").setAutoWidth(true).setKey("diff");

        grid.addComponentColumn(r -> statusBadge(r.getStatus()))
                .setHeader("Status").setAutoWidth(true);

        grid.setClassNameGenerator(r -> r.isWaveStart() ? "wave-start-row" : null);

        grid.addSelectionListener(event -> event.getFirstSelectedItem().ifPresent(r ->
                UI.getCurrent().navigate(ResultDetailView.class, r.getCompetition().getId())));

        grid.setItems(results);
        return grid;
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
