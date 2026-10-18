package com.fis.noco.views;

import com.fis.noco.entity.Competition;
import com.fis.noco.entity.Season;
import com.fis.noco.service.CompetitionService;
import com.fis.noco.service.StandingsEntry;
import com.vaadin.flow.component.Component;
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

/**
 * Official cup standings of a season as published by FIS — overall and the
 * trophies of that season — next to each athlete's rank in every competition.
 */
@Route(value = "standings", layout = MainLayout.class)
@PageTitle("Cup Standings | FIS Nordic Combined")
public class StandingsView extends VerticalLayout {

    private static final String OVERALL = "ALL";

    private final CompetitionService competitionService;
    private final RadioButtonGroup<String> circuitGroup = new RadioButtonGroup<>();
    private final ComboBox<Season> seasonBox = new ComboBox<>("Season");
    private final RadioButtonGroup<String> genderGroup = new RadioButtonGroup<>();
    private final ComboBox<String[]> rankingBox = new ComboBox<>("Ranking");
    private final VerticalLayout content = new VerticalLayout();
    private final Span note = new Span();
    private boolean updatingRankings;

    public StandingsView(CompetitionService competitionService) {
        this.competitionService = competitionService;

        setSizeFull();
        setPadding(true);
        setSpacing(false);

        H2 title = new H2("Cup Standings");
        title.addClassNames(LumoUtility.Margin.Bottom.MEDIUM, LumoUtility.Margin.Top.SMALL);

        circuitGroup.setItems("World Cup", "Continental Cup");
        circuitGroup.setValue("World Cup");

        List<Season> seasons = competitionService.getAllSeasons();
        seasonBox.setItems(seasons);
        seasonBox.setItemLabelGenerator(Season::getLabel);
        seasonBox.setWidth("160px");
        if (!seasons.isEmpty()) seasonBox.setValue(seasons.get(0));

        genderGroup.setItems("Men", "Women");
        genderGroup.setValue("Men");

        rankingBox.setItemLabelGenerator(r -> r[1]);
        rankingBox.setWidth("220px");

        circuitGroup.addValueChangeListener(e -> selectionChanged());
        seasonBox.addValueChangeListener(e -> selectionChanged());
        genderGroup.addValueChangeListener(e -> selectionChanged());
        rankingBox.addValueChangeListener(e -> {
            if (!updatingRankings) showStandings();
        });

        HorizontalLayout controls = new HorizontalLayout(circuitGroup, seasonBox, genderGroup, rankingBox);
        controls.setAlignItems(Alignment.BASELINE);
        controls.setSpacing(true);
        controls.getStyle().set("flex-wrap", "wrap");
        controls.addClassNames(LumoUtility.Padding.Bottom.SMALL);

        note.setText(NOTE);
        note.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.TextColor.SECONDARY,
                LumoUtility.Padding.Bottom.SMALL);

        content.setPadding(false);
        content.setSpacing(false);
        content.setSizeFull();

        add(title, controls, note, content);
        expand(content);

        selectionChanged();
    }

    private String circuit() {
        return "World Cup".equals(circuitGroup.getValue()) ? "WC" : "COC";
    }

    private String gender() {
        return "Men".equals(genderGroup.getValue()) ? "M" : "W";
    }

    /** Circuit, season or gender changed: the rankings on offer change with them. */
    private void selectionChanged() {
        Season season = seasonBox.getValue();
        if (season == null) return;

        List<String[]> rankings = competitionService.getRankingsOfSeason(season.getId(), circuit(), gender());
        String previous = rankingBox.getValue() != null ? rankingBox.getValue()[0] : OVERALL;
        updatingRankings = true;
        rankingBox.setItems(rankings);
        rankingBox.setValue(rankings.stream().filter(r -> r[0].equals(previous)).findFirst()
                .orElse(rankings.isEmpty() ? null : rankings.get(0)));
        rankingBox.setVisible(rankings.size() > 1);
        updatingRankings = false;

        showStandings();
    }

    private static final String NOTE = "Official FIS standings. The columns on the right show the athlete's rank "
            + "in each individual competition of the season.";

    private void showStandings() {
        content.removeAll();
        Season season = seasonBox.getValue();
        // until 1998/99 the FIS database has the first 15 of a competition, the ones that scored
        boolean top15 = season != null && season.getStartYear() != null && season.getStartYear() < 1999;
        note.setText(top15 ? NOTE + " FIS has only the first 15 of most competitions of this season." : NOTE);
        String[] ranking = rankingBox.getValue();
        if (season == null || ranking == null) {
            content.add(new Span("FIS has no standings for this selection."));
            return;
        }
        List<StandingsEntry> standings =
                competitionService.getStandings(season.getId(), circuit(), gender(), ranking[0]);
        if (standings.isEmpty()) {
            content.add(new Span("FIS has no standings for this selection."));
            return;
        }
        List<Competition> competitions =
                competitionService.getIndividualCompetitions(season.getId(), circuit(), gender());
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
                .setFrozen(true)
                .setSortable(true);

        grid.addComponentColumn(entry -> {
            if (entry.getAthleteId() == null) {
                return new Span(entry.getAthleteName());     // no result of this athlete in the database
            }
            Anchor link = new Anchor("athlete/" + entry.getAthleteId(), entry.getAthleteName());
            link.getStyle()
                    .set("text-decoration", "none")
                    .set("color", "var(--lumo-primary-color)");
            return link;
        }).setHeader("Athlete").setWidth("220px").setFlexGrow(1).setFrozen(true).setSortable(true)
                .setComparator(StandingsEntry::getAthleteName);

        grid.addComponentColumn(e -> new NationFlag(e.getNation()))
                .setHeader("Nation")
                .setWidth("90px")
                .setFlexGrow(0)
                .setSortable(true)
                .setComparator(StandingsEntry::getNation);

        grid.addColumn(e -> e.getTotalPoints() != null ? e.getTotalPoints() : "")
                .setHeader("Points")
                .setWidth("80px")
                .setFlexGrow(0)
                .setSortable(true)
                .setComparator((a, b) -> Integer.compare(
                        a.getTotalPoints() != null ? a.getTotalPoints() : -1,
                        b.getTotalPoints() != null ? b.getTotalPoints() : -1));

        for (Competition comp : competitions) {
            Long compId = comp.getId();
            grid.addComponentColumn(entry -> {
                Integer rank = entry.getRankInCompetition(compId);
                if (rank == null) return new Span("");
                Span s = new Span(String.valueOf(rank));
                s.getStyle().set("cursor", "pointer");
                if (rank <= 3) s.getStyle().set("font-weight", "bold");
                s.addClickListener(e -> UI.getCurrent().navigate(ResultDetailView.class, compId));
                return s;
            }).setHeader(buildCompHeader(comp))
              .setWidth("62px")
              .setFlexGrow(0)
              .setSortable(true)
              .setComparator((a, b) -> {
                  Integer ra = a.getRankInCompetition(compId);
                  Integer rb = b.getRankInCompetition(compId);
                  if (ra == null && rb == null) return 0;
                  if (ra == null) return 1;
                  if (rb == null) return -1;
                  return Integer.compare(ra, rb);
              });
        }

        grid.setItems(standings);
        return grid;
    }

    /** Column header of a competition: venue (shortened) over the date, linked to its result. */
    private Component buildCompHeader(Competition comp) {
        String venue = comp.getDisplayLocation() != null ? comp.getDisplayLocation() : "";
        if (venue.length() > 8) venue = venue.substring(0, 8);
        String date = comp.getCompetitionDate() != null ? comp.getCompetitionDate() : "";
        if (date.length() >= 10) date = date.substring(5);      // MM-DD

        Div header = new Div();
        header.getStyle().set("display", "flex").set("flex-direction", "column")
              .set("align-items", "center").set("cursor", "pointer");
        header.getElement().setAttribute("title",
                comp.getDisplayLocation() + " " + comp.getCompetitionDate()
                        + (comp.getFormat() != null ? " · " + comp.getFormat() : ""));
        Span venueLine = new Span(venue);
        venueLine.addClassNames(LumoUtility.FontSize.XSMALL);
        Span dateLine = new Span(date);
        dateLine.addClassNames(LumoUtility.FontSize.XSMALL, LumoUtility.TextColor.SECONDARY);
        header.add(venueLine, dateLine);
        header.addClickListener(e -> UI.getCurrent().navigate(ResultDetailView.class, comp.getId()));
        return header;
    }
}
