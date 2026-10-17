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
import com.vaadin.flow.router.BeforeEnterEvent;
import com.vaadin.flow.router.BeforeEnterObserver;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.QueryParameters;
import com.vaadin.flow.router.Route;
import com.vaadin.flow.server.VaadinSession;
import com.vaadin.flow.theme.lumo.LumoUtility;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Route(value = "results", layout = MainLayout.class)
@PageTitle("Results Browser | FIS Nordic Combined")
public class ResultsBrowserView extends VerticalLayout implements BeforeEnterObserver {

    /** The last filter of the browser in this session, for the way back from a competition. */
    private static final String LAST_FILTER = "resultsBrowser.filter";

    /** Read before the defaults below overwrite it. */
    private final QueryParameters remembered = lastFilter();

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

        circuitSelect.addValueChangeListener(e -> filterChanged(e.isFromClient()));
        seasonSelect.addValueChangeListener(e -> filterChanged(e.isFromClient()));
        genderSelect.addValueChangeListener(e -> filterChanged(e.isFromClient()));

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

        competitionGrid.addComponentColumn(c -> new NationFlag(c.getDisplayCountry()))
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

    /** ?circuit=COC&season=2001&gender=M (season = its start year) selects the filter. */
    @Override
    public void beforeEnter(BeforeEnterEvent event) {
        Map<String, List<String>> params = event.getLocation().getQueryParameters().getParameters();
        if (params.isEmpty() && remembered != null) {
            params = remembered.getParameters();      // from the menu: the filter of last time
        }
        String circuit = one(params, "circuit");
        if ("WC".equals(circuit) || "COC".equals(circuit)) {
            circuitSelect.setValue(circuit);
        }
        String season = one(params, "season");
        if (season != null) {
            seasonSelect.getListDataView().getItems()
                    .filter(s -> season.equals(String.valueOf(s.getStartYear())))
                    .findFirst().ifPresent(seasonSelect::setValue);
        }
        String gender = one(params, "gender");
        if ("M".equals(gender) || "W".equals(gender) || "All".equals(gender)) {
            genderSelect.setValue(gender);
        }
    }

    private static String one(Map<String, List<String>> params, String name) {
        List<String> values = params.get(name);
        return values == null || values.isEmpty() ? null : values.get(0);
    }

    /** The query parameters of a filter; the gender only when one is chosen. */
    public static QueryParameters filter(String circuit, Season season, String gender) {
        Map<String, String> params = new LinkedHashMap<>();
        if (circuit != null) params.put("circuit", circuit);
        if (season != null && season.getStartYear() != null) params.put("season", String.valueOf(season.getStartYear()));
        if (gender != null && !"All".equals(gender)) params.put("gender", gender);
        return QueryParameters.simple(params);
    }

    /** The filter last used in the browser in this session, or null. */
    public static QueryParameters lastFilter() {
        VaadinSession session = VaadinSession.getCurrent();
        return session == null ? null : (QueryParameters) session.getAttribute(LAST_FILTER);
    }

    private void filterChanged(boolean byUser) {
        QueryParameters params = filter(circuitSelect.getValue(), seasonSelect.getValue(), genderSelect.getValue());
        VaadinSession session = VaadinSession.getCurrent();
        if (session != null) {
            session.setAttribute(LAST_FILTER, params);
        }
        if (byUser) {
            // the address shows the filter: reload and the browser's back button keep it
            UI.getCurrent().getPage().getHistory().replaceState(null, "results?" + params.getQueryString());
        }
        loadCompetitions();
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

        String circuitLabel = circuit.equals("WC") ? "World Cup"
                : season.getStartYear() != null && season.getStartYear() < 2008
                ? "Continental Cup (World Cup B)" : "Continental Cup";
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
