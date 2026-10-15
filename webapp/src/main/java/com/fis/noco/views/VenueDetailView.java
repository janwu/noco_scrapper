package com.fis.noco.views;

import com.fis.noco.entity.Competition;
import com.fis.noco.entity.Venue;
import com.fis.noco.service.CompetitionService;
import com.fis.noco.service.VenueService;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.button.Button;
import com.vaadin.flow.component.button.ButtonVariant;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.html.H2;
import com.vaadin.flow.component.html.Paragraph;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.tabs.TabSheet;
import com.vaadin.flow.router.BeforeEvent;
import com.vaadin.flow.router.HasUrlParameter;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;
import com.vaadin.flow.theme.lumo.LumoUtility;

import java.util.List;

@Route(value = "venue", layout = MainLayout.class)
@PageTitle("Venue Detail | FIS Nordic Combined")
public class VenueDetailView extends VerticalLayout implements HasUrlParameter<Long> {

    private final VenueService venueService;
    private final CompetitionService competitionService;

    public VenueDetailView(VenueService venueService, CompetitionService competitionService) {
        this.venueService = venueService;
        this.competitionService = competitionService;
        setSizeFull();
        setPadding(true);
    }

    @Override
    public void setParameter(BeforeEvent event, Long venueId) {
        removeAll();

        venueService.findById(venueId).ifPresentOrElse(
                this::buildContent,
                () -> add(new Paragraph("Venue not found."))
        );
    }

    private void buildContent(Venue venue) {
        Button backButton = new Button("← Back to Venues", e ->
                UI.getCurrent().navigate(VenueSearchView.class));
        backButton.addThemeVariants(ButtonVariant.LUMO_TERTIARY);

        H2 header = new H2(venue.getDisplayName());
        header.addClassNames(LumoUtility.Margin.Bottom.XSMALL);

        HorizontalLayout infoRow = new HorizontalLayout();
        infoRow.setSpacing(true);

        if (venue.getCountry() != null) {
            NationFlag country = new NationFlag(venue.getCountry());
            country.addClassNames(LumoUtility.FontWeight.BOLD);
            infoRow.add(country);
        }
        if (venue.getRegion() != null && !venue.getRegion().isBlank()) {
            infoRow.add(new Span("Region: " + venue.getRegion()));
        }
        if (venue.getHillName() != null && !venue.getHillName().isBlank()) {
            infoRow.add(new Span("Hill: " + venue.getHillName()));
        }

        long totalComps = venueService.countCompetitionsAtVenue(venue.getId());
        infoRow.add(new Span("Total competitions: " + totalComps));

        List<Competition> wcComps = venueService.getWorldCupCompetitionsAtVenue(venue.getId());
        List<Competition> cocComps = venueService.getContinentalCupCompetitionsAtVenue(venue.getId());

        TabSheet tabSheet = new TabSheet();
        tabSheet.setSizeFull();

        tabSheet.add("World Cup (" + wcComps.size() + ")", createCompetitionsGrid(wcComps));
        tabSheet.add("Continental Cup (" + cocComps.size() + ")", createCompetitionsGrid(cocComps));

        add(backButton, header, infoRow, tabSheet);
        expand(tabSheet);
    }

    private Grid<Competition> createCompetitionsGrid(List<Competition> competitions) {
        Grid<Competition> grid = new Grid<>(Competition.class, false);
        grid.setSizeFull();
        grid.setMinHeight("400px");

        grid.addColumn(Competition::getCompetitionDate)
                .setHeader("Date").setAutoWidth(true).setSortable(true);

        grid.addColumn(c -> c.getSeason() != null ? c.getSeason().getLabel() : "")
                .setHeader("Season").setAutoWidth(true).setSortable(true);

        grid.addColumn(Competition::getFormat)
                .setHeader("Format").setAutoWidth(true);

        grid.addColumn(Competition::getGender)
                .setHeader("Gender").setAutoWidth(true);

        grid.addColumn(c -> {
            long count = competitionService.countResultsForCompetition(c.getId());
            return count > 0 ? String.valueOf(count) : "-";
        }).setHeader("# Results").setAutoWidth(true);

        grid.addSelectionListener(event -> event.getFirstSelectedItem().ifPresent(c ->
                UI.getCurrent().navigate(ResultDetailView.class, c.getId())));

        grid.setItems(competitions);
        return grid;
    }
}
