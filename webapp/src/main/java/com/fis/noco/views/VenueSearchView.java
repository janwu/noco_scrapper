package com.fis.noco.views;

import com.fis.noco.entity.Venue;
import com.fis.noco.service.VenueService;
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

@Route(value = "venues", layout = MainLayout.class)
@PageTitle("Venues | FIS Nordic Combined")
public class VenueSearchView extends VerticalLayout {

    private final VenueService venueService;
    private final TextField searchField;
    private final Grid<Venue> grid;

    public VenueSearchView(VenueService venueService) {
        this.venueService = venueService;

        setSizeFull();
        setPadding(true);
        setSpacing(true);

        H2 title = new H2("Venues");
        title.addClassNames(LumoUtility.Margin.Bottom.NONE);

        searchField = new TextField();
        searchField.setPlaceholder("Search by venue name or country...");
        searchField.setClearButtonVisible(true);
        searchField.setWidth("400px");
        searchField.setValueChangeMode(ValueChangeMode.LAZY);
        searchField.setValueChangeTimeout(300);
        searchField.addValueChangeListener(e -> refreshGrid());

        HorizontalLayout searchBar = new HorizontalLayout(searchField);
        searchBar.setWidthFull();

        grid = new Grid<>(Venue.class, false);
        grid.setSizeFull();

        grid.addColumn(Venue::getName)
                .setHeader("Venue Name").setAutoWidth(true).setSortable(true);

        grid.addColumn(Venue::getCountry)
                .setHeader("Country").setAutoWidth(true).setSortable(true);

        grid.addColumn(Venue::getRegion)
                .setHeader("Region").setAutoWidth(true);

        grid.addColumn(v -> {
            long count = venueService.countCompetitionsAtVenue(v.getId());
            return count > 0 ? String.valueOf(count) : "0";
        }).setHeader("# Competitions").setAutoWidth(true);

        grid.addSelectionListener(event -> event.getFirstSelectedItem().ifPresent(venue ->
                UI.getCurrent().navigate(VenueDetailView.class, venue.getId())));

        refreshGrid();

        add(title, searchBar, grid);
        expand(grid);
    }

    private void refreshGrid() {
        String query = searchField.getValue();
        CallbackDataProvider<Venue, Void> provider = DataProvider.fromCallbacks(
                fetchCallback -> {
                    int offset = fetchCallback.getOffset();
                    int limit = fetchCallback.getLimit();
                    int page = offset / limit;
                    return venueService.searchVenues(query, page, limit).stream();
                },
                countCallback -> (int) venueService.countVenues(query)
        );
        grid.setDataProvider(provider);
    }
}
