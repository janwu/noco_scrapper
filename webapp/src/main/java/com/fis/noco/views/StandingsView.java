package com.fis.noco.views;

import com.fis.noco.entity.Competition;
import com.fis.noco.entity.Season;
import com.fis.noco.service.CompetitionService;
import com.fis.noco.service.StandingsEntry;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.combobox.ComboBox;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.grid.GridVariant;
import com.vaadin.flow.component.html.Anchor;
import com.vaadin.flow.component.html.Div;
import com.vaadin.flow.component.html.H2;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.radiobutton.RadioButtonGroup;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;
import com.vaadin.flow.theme.lumo.LumoUtility;

import java.util.List;

@Route(value = "standings", layout = MainLayout.class)
@PageTitle("WC Standings | FIS Nordic Combined")
public class StandingsView extends VerticalLayout {

    private final CompetitionService competitionService;
    private final ComboBox<Season> seasonBox = new ComboBox<>("Season");
    private final RadioButtonGroup<String> genderGroup = new RadioButtonGroup<>();
    private final VerticalLayout content = new VerticalLayout();

    public StandingsView(CompetitionService competitionService) {
        this.competitionService = competitionService;

        setSizeFull();
        setPadding(true);
        setSpacing(false);

        H2 title = new H2("World Cup Standings");
        title.addClassNames(LumoUtility.Margin.Bottom.MEDIUM, LumoUtility.Margin.Top.SMALL);

        List<Season> seasons = competitionService.getAllSeasons();
        seasonBox.setItems(seasons);
        seasonBox.setItemLabelGenerator(Season::getLabel);
        seasonBox.setWidth("160px");
        if (!seasons.isEmpty()) seasonBox.setValue(seasons.get(0));

        genderGroup.setItems("Men", "Women");
        genderGroup.setValue("Men");
        genderGroup.getStyle().set("flex-direction", "row");

        seasonBox.addValueChangeListener(e -> refresh());
        genderGroup.addValueChangeListener(e -> refresh());

        HorizontalLayout controls = new HorizontalLayout(seasonBox, genderGroup);
        controls.setAlignItems(Alignment.BASELINE);
        controls.setSpacing(true);
        controls.addClassNames(LumoUtility.Padding.Bottom.MEDIUM);

        content.setPadding(false);
        content.setSpacing(false);
        content.setSizeFull();

        add(title, controls, content);
        expand(content);

        refresh();
    }

    private void refresh() {
        Season season = seasonBox.getValue();
        if (season == null) return;
        String gender = "Men".equals(genderGroup.getValue()) ? "M" : "W";

        List<Competition> competitions = competitionService.getWCIndividualCompetitions(season.getId(), gender);
        List<StandingsEntry> standings = competitionService.getWCStandings(season.getId(), gender);

        content.removeAll();
        if (standings.isEmpty()) {
            content.add(new Span("No standings data available for this season."));
            return;
        }
        content.add(buildStandingsGrid(standings, competitions));
    }

    private Grid<StandingsEntry> buildStandingsGrid(List<StandingsEntry> standings,
                                                     List<Competition> competitions) {
        Grid<StandingsEntry> grid = new Grid<>(StandingsEntry.class, false);
        grid.setSizeFull();
        grid.addThemeVariants(GridVariant.LUMO_COMPACT, GridVariant.LUMO_ROW_STRIPES);

        grid.addColumn(StandingsEntry::getPosition)
                .setHeader("#")
                .setWidth("50px")
                .setFlexGrow(0)
                .setSortable(true);

        grid.addComponentColumn(entry -> {
            Anchor link = new Anchor("athlete/" + entry.getAthleteId(), entry.getAthleteName());
            link.getStyle()
                    .set("text-decoration", "none")
                    .set("color", "var(--lumo-primary-color)");
            return link;
        }).setHeader("Athlete").setWidth("200px").setFlexGrow(1).setSortable(true)
                .setComparator(StandingsEntry::getAthleteName);

        grid.addComponentColumn(e -> new NationFlag(e.getNation()))
                .setHeader("Nation")
                .setWidth("90px")
                .setFlexGrow(0)
                .setSortable(true)
                .setComparator(StandingsEntry::getNation);

        grid.addColumn(StandingsEntry::getTotalPoints)
                .setHeader("Total")
                .setWidth("80px")
                .setFlexGrow(0)
                .setSortable(true);

        for (Competition comp : competitions) {
            String header = buildCompHeader(comp);
            Long compId = comp.getId();
            grid.addComponentColumn(entry -> {
                Integer pts = entry.getPointsForCompetition(compId);
                if (pts == null) return new Span("");
                Span s = new Span(String.valueOf(pts));
                s.getStyle().set("cursor", "pointer").set("color", "var(--lumo-primary-color)");
                s.addClickListener(e -> UI.getCurrent().navigate(ResultDetailView.class, compId));
                return s;
            }).setHeader(buildCompHeaderComponent(header, compId))
              .setWidth("62px")
              .setFlexGrow(0)
              .setSortable(true)
              .setComparator((a, b) -> {
                  Integer pa = a.getPointsForCompetition(compId);
                  Integer pb = b.getPointsForCompetition(compId);
                  if (pa == null && pb == null) return 0;
                  if (pa == null) return 1;
                  if (pb == null) return -1;
                  return Integer.compare(pa, pb);
              });
        }

        grid.setItems(standings);
        return grid;
    }

    private String buildCompHeader(Competition comp) {
        String venue = comp.getDisplayLocation();
        if (venue != null && venue.length() > 8) {
            venue = venue.substring(0, 8);
        }
        String date = comp.getCompetitionDate() != null ? comp.getCompetitionDate() : "";
        if (date.length() >= 10) date = date.substring(5); // MM-DD
        return (venue != null ? venue : "") + "\n" + date;
    }

    private com.vaadin.flow.component.Component buildCompHeaderComponent(String text, Long compId) {
        String[] parts = text.split("\n", 2);
        Div header = new Div();
        header.getStyle().set("display", "flex").set("flex-direction", "column")
              .set("align-items", "center").set("cursor", "pointer");
        Span venueLine = new Span(parts[0]);
        venueLine.addClassNames(LumoUtility.FontSize.XSMALL);
        Span dateLine = new Span(parts.length > 1 ? parts[1] : "");
        dateLine.addClassNames(LumoUtility.FontSize.XSMALL, LumoUtility.TextColor.SECONDARY);
        header.add(venueLine, dateLine);
        header.addClickListener(e -> UI.getCurrent().navigate(ResultDetailView.class, compId));
        return header;
    }
}
