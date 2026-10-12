package com.fis.noco.views;

import com.fis.noco.entity.CombinedResult;
import com.fis.noco.entity.Competition;
import com.fis.noco.service.CompetitionService;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.button.Button;
import com.vaadin.flow.component.button.ButtonVariant;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.html.H2;
import com.vaadin.flow.component.html.H3;
import com.vaadin.flow.component.html.Paragraph;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.router.BeforeEvent;
import com.vaadin.flow.router.HasUrlParameter;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;
import com.vaadin.flow.theme.lumo.LumoUtility;

import java.util.List;

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
        Button backButton = new Button("← Back to Results Browser", e ->
                UI.getCurrent().navigate(ResultsBrowserView.class));
        backButton.addThemeVariants(ButtonVariant.LUMO_TERTIARY);

        String circuitLabel = "WC".equals(competition.getCircuit()) ? "World Cup" : "Continental Cup";
        String location = competition.getDisplayLocation();
        String country = competition.getDisplayCountry();
        String date = competition.getCompetitionDate() != null ? competition.getCompetitionDate() : "";

        H2 header = new H2(location + (country.isBlank() ? "" : ", " + country));
        header.addClassNames(LumoUtility.Margin.Bottom.XSMALL);

        HorizontalLayout metaRow = new HorizontalLayout();
        metaRow.setSpacing(true);
        metaRow.setDefaultVerticalComponentAlignment(Alignment.CENTER);
        metaRow.getStyle().set("flex-wrap", "wrap");

        addMeta(metaRow, "Date", date);
        addMeta(metaRow, "Circuit", circuitLabel);
        if (competition.getFormat() != null) addMeta(metaRow, "Format", competition.getFormat());
        if (competition.getGender() != null) addMeta(metaRow, "Gender", competition.getGender());
        if (competition.getSeason() != null) addMeta(metaRow, "Season", competition.getSeason().getLabel());
        if (competition.getXcDistanceKm() != null)
            addMeta(metaRow, "XC Distance", competition.getXcDistanceKm() + " km");
        if (competition.getHillSizeM() != null)
            addMeta(metaRow, "Hill Size", competition.getHillSizeM() + " m");

        List<CombinedResult> results = competitionService.getResultsForCompetition(competition.getId());

        H3 resultsTitle = new H3("Results (" + results.size() + " athletes)");
        resultsTitle.addClassNames(LumoUtility.Margin.Top.MEDIUM, LumoUtility.Margin.Bottom.XSMALL);

        boolean isMassStart = "Mass Start".equals(competition.getFormat());
        Grid<CombinedResult> grid = createResultsGrid(results, isMassStart);

        add(backButton, header, metaRow, resultsTitle, grid);
        expand(grid);
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

        grid.addColumn(CombinedResult::getDisplayNation)
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
            grid.addColumn(CombinedResult::getTimeBehind)
                    .setHeader("Final Pts Diff").setAutoWidth(true);
        } else {
            // Gundersen / Compact / Sprint / Penalty Race: SJ is first, XC is the final phase
            grid.addColumn(CombinedResult::getJumpPoints)
                    .setHeader("Jump Pts").setAutoWidth(true).setSortable(true);
            grid.addColumn(CombinedResult::getJumpRank)
                    .setHeader("Jump Rank").setAutoWidth(true).setSortable(true);
            grid.addColumn(CombinedResult::getTimeDifference)
                    .setHeader("Time Diff").setAutoWidth(true);
            grid.addColumn(CombinedResult::getXcTime)
                    .setHeader("XC Time").setAutoWidth(true).setSortable(true);
            grid.addColumn(CombinedResult::getXcRank)
                    .setHeader("XC Rank").setAutoWidth(true).setSortable(true);
            grid.addColumn(CombinedResult::getTimeBehind)
                    .setHeader("Time Behind").setAutoWidth(true);
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
