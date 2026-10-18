package com.fis.noco.views;

import com.fis.noco.service.RecordsService;
import com.fis.noco.service.RecordsService.Count;
import com.fis.noco.service.RecordsService.NationMode;
import com.vaadin.flow.component.Component;
import com.vaadin.flow.component.grid.ColumnTextAlign;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.grid.GridVariant;
import com.vaadin.flow.component.html.Anchor;
import com.vaadin.flow.component.html.Div;
import com.vaadin.flow.component.html.H2;
import com.vaadin.flow.component.html.H3;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.orderedlayout.FlexLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.radiobutton.RadioButtonGroup;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;
import com.vaadin.flow.theme.lumo.LumoUtility;

import java.util.List;
import java.util.function.ToIntFunction;

/** All-time World Cup records of athletes and nations (individual competitions). */
@Route(value = "records", layout = MainLayout.class)
@PageTitle("World Cup Records | FIS Nordic Combined")
public class RecordsView extends VerticalLayout {

    private static final int LIMIT = 25;

    private final RecordsService records;
    private final RadioButtonGroup<String> genderGroup = new RadioButtonGroup<>();
    private final RadioButtonGroup<NationMode> nationMode = new RadioButtonGroup<>();
    private final FlexLayout athleteTables = new FlexLayout();
    private final Div nationTable = new Div();

    public RecordsView(RecordsService records) {
        this.records = records;
        setPadding(true);
        setSpacing(true);

        H2 title = new H2("World Cup Records");
        title.addClassNames(LumoUtility.Margin.Bottom.NONE);
        Span note = new Span("Individual World Cup competitions since 1983/84; team events are not counted.");
        note.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.TextColor.SECONDARY);

        genderGroup.setItems("Men", "Women");
        genderGroup.setValue("Men");
        genderGroup.addValueChangeListener(e -> refresh());

        athleteTables.setFlexWrap(FlexLayout.FlexWrap.WRAP);
        athleteTables.getStyle().set("gap", "var(--lumo-space-l)");
        athleteTables.setWidthFull();

        H3 nationsTitle = new H3("Nations");
        nationsTitle.addClassNames(LumoUtility.Margin.Bottom.NONE, LumoUtility.Margin.Top.LARGE);
        nationMode.setItems(NationMode.values());
        nationMode.setItemLabelGenerator(m -> m == NationMode.AT_THE_TIME ? "Nation at the time" : "Athlete's nation");
        nationMode.setValue(NationMode.AT_THE_TIME);
        nationMode.addValueChangeListener(e -> refreshNations());
        Span modeNote = new Span();
        modeNote.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.TextColor.SECONDARY);
        modeNote.setText(MODE_NOTE.get(NationMode.AT_THE_TIME));
        nationMode.addValueChangeListener(e -> modeNote.setText(MODE_NOTE.get(e.getValue())));
        nationTable.setWidth("min(100%, 640px)");

        add(title, note, genderGroup, athleteTables, nationsTitle, nationMode, modeNote, nationTable);
        refresh();
    }

    private static final java.util.Map<NationMode, String> MODE_NOTE = java.util.Map.of(
            NationMode.AT_THE_TIME, "Counted for the nation the result was won for. West Germany (FRG) is "
                    + "counted with Germany and Yugoslavia with Slovenia; East Germany (GDR), the Soviet Union "
                    + "(SOV), the CIS of 1992 and Czechoslovakia (TCH) are listed as states of their own.",
            NationMode.ATHLETE, "Counted for the athlete's last nation: a Soviet podium of an Estonian counts "
                    + "for Estonia, an East German one of an athlete who later competed for Germany for Germany.");

    private String gender() {
        return "Women".equals(genderGroup.getValue()) ? "W" : "M";
    }

    private void refresh() {
        List<Count> athletes = records.athletes(gender());
        athleteTables.removeAll();
        athleteTables.add(
                athleteTable("Most wins", "Wins", RecordsService.top(athletes, Count::wins, LIMIT), Count::wins),
                athleteTable("Most podiums", "Top 3", RecordsService.top(athletes, Count::podiums, LIMIT), Count::podiums),
                athleteTable("Most top-10 places", "Top 10", RecordsService.top(athletes, Count::top10, LIMIT), Count::top10));
        refreshNations();
    }

    private Component athleteTable(String title, String header, List<Count> rows, ToIntFunction<Count> value) {
        Grid<Count> grid = new Grid<>(Count.class, false);
        grid.addThemeVariants(GridVariant.LUMO_COMPACT, GridVariant.LUMO_ROW_STRIPES);
        grid.addColumn(c -> place(rows, c, value)).setHeader("#").setWidth("50px").setFlexGrow(0);
        grid.addComponentColumn(c -> {
            Anchor link = new Anchor("athlete/" + c.athleteId(), c.name());
            link.getStyle().set("text-decoration", "none").set("color", "var(--lumo-primary-color)");
            return link;
        }).setHeader("Athlete").setFlexGrow(1);
        grid.addComponentColumn(c -> new NationFlag(c.nation(), false)).setHeader("").setWidth("50px").setFlexGrow(0);
        grid.addColumn(value::applyAsInt).setHeader(header).setWidth("80px").setFlexGrow(0)
                .setTextAlign(ColumnTextAlign.END);
        grid.setItems(rows);
        grid.setAllRowsVisible(true);

        H3 h = new H3(title);
        h.addClassNames(LumoUtility.Margin.Bottom.XSMALL, LumoUtility.FontSize.LARGE);
        VerticalLayout box = new VerticalLayout(h, rows.isEmpty() ? new Span("No results.") : grid);
        box.setPadding(false);
        box.setSpacing(false);
        box.getStyle().set("flex", "1 1 320px").set("min-width", "280px").set("max-width", "460px");
        return box;
    }

    /** The place in the list; equal counts share it ('1, 2, 2, 4'). */
    private static int place(List<Count> rows, Count c, ToIntFunction<Count> value) {
        int v = value.applyAsInt(c);
        int better = 0;
        for (Count other : rows) if (value.applyAsInt(other) > v) better++;
        return better + 1;
    }

    private void refreshNations() {
        List<Count> nations = records.nations(gender(), nationMode.getValue());
        Grid<Count> grid = new Grid<>(Count.class, false);
        grid.addThemeVariants(GridVariant.LUMO_COMPACT, GridVariant.LUMO_ROW_STRIPES);
        grid.addColumn(c -> place(nations, c, Count::wins)).setHeader("#").setWidth("50px").setFlexGrow(0);
        grid.addComponentColumn(c -> new NationFlag(c.nation())).setHeader("Nation").setFlexGrow(1)
                .setComparator(Count::nation);
        grid.addColumn(Count::wins).setHeader("Wins").setTextAlign(ColumnTextAlign.END).setSortable(true);
        grid.addColumn(Count::podiums).setHeader("Top 3").setTextAlign(ColumnTextAlign.END).setSortable(true);
        grid.addColumn(Count::top10).setHeader("Top 10").setTextAlign(ColumnTextAlign.END).setSortable(true);
        grid.addColumn(c -> c.firstWin() == null ? "" : c.firstWin().substring(0, 4) + "–" + c.lastWin().substring(0, 4))
                .setHeader("Wins from–to").setAutoWidth(true);
        grid.setItems(nations);
        grid.setAllRowsVisible(true);
        nationTable.removeAll();
        nationTable.add(grid);
    }
}
