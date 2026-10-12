package com.fis.noco.views;

import com.fis.noco.entity.Competition;
import com.fis.noco.entity.Season;
import com.fis.noco.service.CompetitionService;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.html.H2;
import com.vaadin.flow.component.html.H3;
import com.vaadin.flow.component.html.Paragraph;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.select.Select;
import com.vaadin.flow.component.splitlayout.SplitLayout;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;
import com.vaadin.flow.theme.lumo.LumoUtility;

import java.util.List;

@Route(value = "results", layout = MainLayout.class)
@PageTitle("Results Browser | FIS Nordic Combined")
public class ResultsBrowserView extends VerticalLayout {

    private final CompetitionService competitionService;
    private final Grid<Competition> competitionGrid;
    private final Select<Season> seasonSelect;
    private final Select<String> circuitSelect;
    private final Select<String> genderSelect;
    private final H3 gridTitle;
    private final Paragraph noSelectionNote;

    public ResultsBrowserView(CompetitionService competitionService) {
        this.competitionService = competitionService;

        setSizeFull();
        setPadding(true);
        setSpacing(true);

        H2 title = new H2("Results Browser");
        title.addClassNames(LumoUtility.Margin.Bottom.NONE);

        // Left panel
        VerticalLayout leftPanel = new VerticalLayout();
        leftPanel.setPadding(true);
        leftPanel.setSpacing(true);
        leftPanel.setWidth("260px");
        leftPanel.setMinWidth("200px");

        H3 filterTitle = new H3("Filter");
        filterTitle.addClassNames(LumoUtility.Margin.Bottom.XSMALL);

        circuitSelect = new Select<>();
        circuitSelect.setLabel("Circuit");
        circuitSelect.setItems("WC", "COC");
        circuitSelect.setItemLabelGenerator(c -> c.equals("WC") ? "World Cup" : "Continental Cup");
        circuitSelect.setWidthFull();

        seasonSelect = new Select<>();
        seasonSelect.setLabel("Season");
        seasonSelect.setItemLabelGenerator(Season::getLabel);
        seasonSelect.setWidthFull();

        List<Season> seasons = competitionService.getAllSeasons();
        seasonSelect.setItems(seasons);

        genderSelect = new Select<>();
        genderSelect.setLabel("Gender");
        genderSelect.setItems("All", "M", "W");
        genderSelect.setItemLabelGenerator(g -> switch (g) {
            case "M" -> "Men";
            case "W" -> "Women";
            default -> "All";
        });
        genderSelect.setValue("All");
        genderSelect.setWidthFull();

        circuitSelect.addValueChangeListener(e -> loadCompetitions());
        seasonSelect.addValueChangeListener(e -> loadCompetitions());
        genderSelect.addValueChangeListener(e -> loadCompetitions());

        leftPanel.add(filterTitle, circuitSelect, seasonSelect, genderSelect);
        leftPanel.setAlignItems(Alignment.STRETCH);

        // Right panel
        VerticalLayout rightPanel = new VerticalLayout();
        rightPanel.setSizeFull();
        rightPanel.setPadding(false);
        rightPanel.setSpacing(true);

        gridTitle = new H3("Competitions");
        gridTitle.addClassNames(LumoUtility.Margin.Bottom.NONE);

        noSelectionNote = new Paragraph("Select a circuit and season to view competitions.");
        noSelectionNote.addClassNames(LumoUtility.TextColor.SECONDARY);

        competitionGrid = new Grid<>(Competition.class, false);
        competitionGrid.setSizeFull();

        competitionGrid.addColumn(Competition::getCompetitionDate)
                .setHeader("Date").setAutoWidth(true).setSortable(true);

        competitionGrid.addColumn(Competition::getDisplayLocation)
                .setHeader("Location").setAutoWidth(true).setSortable(true);

        competitionGrid.addColumn(Competition::getDisplayCountry)
                .setHeader("Country").setAutoWidth(true);

        competitionGrid.addColumn(Competition::getFormat)
                .setHeader("Format").setAutoWidth(true);

        competitionGrid.addColumn(Competition::getGender)
                .setHeader("Gender").setAutoWidth(true);

        competitionGrid.addColumn(c -> {
            long count = competitionService.countResultsForCompetition(c.getId());
            return count > 0 ? String.valueOf(count) : "-";
        }).setHeader("# Results").setAutoWidth(true);

        competitionGrid.addSelectionListener(event ->
                event.getFirstSelectedItem().ifPresent(c ->
                        UI.getCurrent().navigate(ResultDetailView.class, c.getId())));

        competitionGrid.setVisible(false);

        rightPanel.add(gridTitle, noSelectionNote, competitionGrid);
        rightPanel.expand(competitionGrid);

        SplitLayout splitLayout = new SplitLayout(leftPanel, rightPanel);
        splitLayout.setSizeFull();
        splitLayout.setSplitterPosition(22);

        add(title, splitLayout);
        expand(splitLayout);

        // Default selection
        if (!seasons.isEmpty()) {
            seasonSelect.setValue(seasons.get(0));
        }
        circuitSelect.setValue("WC");
    }

    private void loadCompetitions() {
        String circuit = circuitSelect.getValue();
        Season season = seasonSelect.getValue();

        if (circuit == null || season == null) {
            competitionGrid.setVisible(false);
            noSelectionNote.setVisible(true);
            gridTitle.setText("Competitions");
            return;
        }

        String circuitLabel = circuit.equals("WC") ? "World Cup" : "Continental Cup";
        gridTitle.setText(circuitLabel + " – " + season.getLabel());

        String gender = genderSelect.getValue();
        String genderFilter = (gender == null || "All".equals(gender)) ? null : gender;
        List<Competition> competitions = competitionService.getCompetitionsByCircuitSeasonAndGender(
                circuit, season.getId(), genderFilter);

        if (competitions.isEmpty()) {
            noSelectionNote.setText("No competitions found for this selection.");
            noSelectionNote.setVisible(true);
            competitionGrid.setVisible(false);
        } else {
            noSelectionNote.setVisible(false);
            competitionGrid.setItems(competitions);
            competitionGrid.setVisible(true);
        }
    }
}
