package com.fis.noco.views;

import com.fis.noco.entity.Athlete;
import com.fis.noco.service.AthleteService;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.html.H2;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.textfield.TextField;
import com.vaadin.flow.data.provider.CallbackDataProvider;
import com.vaadin.flow.data.provider.DataProvider;
import com.vaadin.flow.data.value.ValueChangeMode;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;
import com.vaadin.flow.theme.lumo.LumoUtility;

@Route(value = "athletes", layout = MainLayout.class)
@PageTitle("Athletes | FIS Nordic Combined")
public class AthleteSearchView extends VerticalLayout {

    private final AthleteService athleteService;
    private final TextField searchField;
    private final Grid<Athlete> grid;

    public AthleteSearchView(AthleteService athleteService) {
        this.athleteService = athleteService;

        setSizeFull();
        setPadding(true);
        setSpacing(true);

        H2 title = new H2("Athletes");
        title.addClassNames(LumoUtility.Margin.Bottom.NONE);

        searchField = new TextField();
        searchField.setPlaceholder("Search by name or nationality...");
        searchField.setClearButtonVisible(true);
        searchField.setWidth("400px");
        searchField.setValueChangeMode(ValueChangeMode.LAZY);
        searchField.setValueChangeTimeout(300);
        searchField.addValueChangeListener(e -> refreshGrid());

        HorizontalLayout searchBar = new HorizontalLayout(searchField);
        searchBar.setWidthFull();

        grid = new Grid<>(Athlete.class, false);
        grid.setSizeFull();

        grid.addColumn(Athlete::getFullName)
                .setHeader("Name")
                .setAutoWidth(true)
                .setSortable(true);

        grid.addComponentColumn(a -> new NationFlag(a.getNationality()))
                .setHeader("Nationality")
                .setAutoWidth(true);

        grid.addColumn(Athlete::getGender)
                .setHeader("Gender")
                .setAutoWidth(true)
                .setSortable(true);

        grid.addColumn(athlete -> {
                    String bd = athlete.getBirthDate();
                    return (bd != null && bd.length() >= 4) ? bd.substring(0, 4) : "";
                })
                .setHeader("Born")
                .setAutoWidth(true)
                .setSortable(true);

        grid.addColumn(Athlete::getActiveClub)
                .setHeader("Club")
                .setAutoWidth(true);

        grid.addSelectionListener(event -> event.getFirstSelectedItem().ifPresent(athlete ->
                UI.getCurrent().navigate(AthleteDetailView.class, athlete.getId())));

        refreshGrid();

        add(title, searchBar, grid);
        expand(grid);
    }

    private void refreshGrid() {
        String query = searchField.getValue();
        CallbackDataProvider<Athlete, Void> provider = DataProvider.fromCallbacks(
                fetchCallback -> {
                    int offset = fetchCallback.getOffset();
                    int limit = fetchCallback.getLimit();
                    int page = offset / limit;
                    return athleteService.searchAthletes(query, page, limit).stream();
                },
                countCallback -> (int) athleteService.countAthletes(query)
        );
        grid.setDataProvider(provider);
    }
}
