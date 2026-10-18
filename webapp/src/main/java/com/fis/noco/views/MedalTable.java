package com.fis.noco.views;

import com.fis.noco.service.MedalsService;
import com.fis.noco.service.MedalsService.Medals;
import com.fis.noco.service.RecordsService.NationMode;
import com.vaadin.flow.component.Component;
import com.vaadin.flow.component.checkbox.Checkbox;
import com.vaadin.flow.component.grid.ColumnTextAlign;
import com.vaadin.flow.component.grid.Grid;
import com.vaadin.flow.component.grid.GridVariant;
import com.vaadin.flow.component.html.Anchor;
import com.vaadin.flow.component.html.Div;
import com.vaadin.flow.component.html.H2;
import com.vaadin.flow.component.html.H3;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.orderedlayout.FlexLayout;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.component.radiobutton.RadioButtonGroup;
import com.vaadin.flow.theme.lumo.LumoUtility;

import java.util.List;
import java.util.function.ToIntFunction;

/**
 * A medal table page: athletes and nations of one circuit, the World Championships
 * (WSC) or the Olympic Winter Games (OWG); see {@link MedalsView}, {@link OlympicMedalsView}.
 */
abstract class MedalTable extends VerticalLayout {

    private static final String GOLD = "#d4a72c", SILVER = "#9aa4ad", BRONZE = "#b0723c";

    private final MedalsService medals;
    private final String circuit;
    private final RadioButtonGroup<String> genderGroup = new RadioButtonGroup<>();
    private final Checkbox teams = new Checkbox("Count team medals", true);
    private final RadioButtonGroup<NationMode> nationMode = new RadioButtonGroup<>();
    private final Checkbox eastGermany = new Checkbox("Count East Germany (GDR) with Germany");
    private final Span modeNote = new Span();
    private final FlexLayout tables = new FlexLayout();
    private final Div athleteTable = new Div();
    private final H3 athletesTitle = new H3();
    private final Div nationTable = new Div();

    MedalTable(MedalsService medals, String circuit, String heading, String scope) {
        this.medals = medals;
        this.circuit = circuit;
        setPadding(true);
        setSpacing(true);

        H2 title = new H2(heading);
        title.addClassNames(LumoUtility.Margin.Bottom.NONE);
        Span note = new Span(scope + " A team medal counts for each athlete of the team and once "
                + "for the nation; the column Team says how many of the medals are team medals.");
        note.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.TextColor.SECONDARY);

        genderGroup.setItems("Men", "Women", "All");
        genderGroup.setValue("Men");
        genderGroup.addValueChangeListener(e -> refresh());
        teams.addValueChangeListener(e -> refresh());
        HorizontalLayout controls = new HorizontalLayout(genderGroup, teams);
        controls.setAlignItems(Alignment.BASELINE);
        controls.getStyle().set("flex-wrap", "wrap");

        nationMode.setItems(NationMode.values());
        nationMode.setItemLabelGenerator(m -> m == NationMode.AT_THE_TIME ? "Nation at the time" : "Athlete's nation");
        nationMode.setValue(NationMode.AT_THE_TIME);
        nationMode.addValueChangeListener(e -> refreshNations());
        eastGermany.addValueChangeListener(e -> refreshNations());
        modeNote.addClassNames(LumoUtility.FontSize.SMALL, LumoUtility.TextColor.SECONDARY);

        athletesTitle.setText("Athletes");
        athletesTitle.addClassNames(LumoUtility.Margin.Bottom.XSMALL);
        VerticalLayout athletes = new VerticalLayout(athletesTitle, athleteTable);
        athletes.setPadding(false);
        athletes.setSpacing(false);
        athletes.getStyle().set("flex", "1 1 640px").set("max-width", "820px");

        H3 nationsTitle = new H3("Nations");
        nationsTitle.addClassNames(LumoUtility.Margin.Bottom.XSMALL);
        VerticalLayout nations = new VerticalLayout(nationsTitle, nationMode, eastGermany, modeNote, nationTable);
        nations.setPadding(false);
        nations.setSpacing(false);
        nations.getStyle().set("flex", "1 1 560px").set("max-width", "760px");

        tables.setFlexWrap(FlexLayout.FlexWrap.WRAP);
        tables.getStyle().set("gap", "var(--lumo-space-xl)");
        tables.setWidthFull();
        tables.add(athletes, nations);

        add(title, note, controls, tables);
        refresh();
    }

    private String gender() {
        return switch (genderGroup.getValue()) {
            case "Women" -> "W";
            case "All" -> null;
            default -> "M";
        };
    }

    private void refresh() {
        List<Medals> rows = medals.athletes(circuit, gender(), teams.getValue());
        athleteTable.removeAll();
        athleteTable.setWidthFull();
        athleteTable.add(rows.isEmpty() ? new Span("No medals.")
                : grid(rows, true));
        athletesTitle.setText("Athletes (" + rows.size() + ")");
        refreshNations();
    }

    private void refreshNations() {
        List<Medals> rows = medals.nations(circuit, gender(), nationMode.getValue(), eastGermany.getValue(),
                teams.getValue());
        nationTable.removeAll();
        nationTable.setWidthFull();
        nationTable.add(rows.isEmpty() ? new Span("No medals.") : grid(rows, false));
        modeNote.setText(nationMode.getValue() == NationMode.AT_THE_TIME
                ? (eastGermany.getValue()
                    ? "Counted for the nation the medal was won for. West and East Germany are counted with "
                      + "Germany, Yugoslavia with Slovenia; the Soviet Union, the CIS and Czechoslovakia stand alone."
                    : "Counted for the nation the medal was won for. West Germany (FRG) is counted with Germany, "
                      + "Yugoslavia with Slovenia; East Germany (GDR), the Soviet Union (SOV), the CIS and "
                      + "Czechoslovakia (TCH) stand alone.")
                : "Counted for the athlete's last nation; a team for the nation most of its athletes ended with."
                  + (eastGermany.getValue() ? " East Germany (GDR) is counted with Germany." : ""));
    }

    private Component grid(List<Medals> rows, boolean athletes) {
        boolean t = teams.getValue();
        Grid<Medals> grid = new Grid<>(Medals.class, false);
        grid.addThemeVariants(GridVariant.LUMO_COMPACT, GridVariant.LUMO_ROW_STRIPES);
        grid.addColumn(m -> place(rows, m, t)).setHeader("#").setWidth("50px").setFlexGrow(0);
        if (athletes) {
            grid.addComponentColumn(m -> {
                Anchor link = new Anchor("athlete/" + m.athleteId(), m.name());
                link.getStyle().set("text-decoration", "none").set("color", "var(--lumo-primary-color)");
                return link;
            }).setHeader("Athlete").setAutoWidth(true).setFlexGrow(1);
            grid.addComponentColumn(m -> new NationFlag(m.nation(), false)).setHeader("").setWidth("50px").setFlexGrow(0);
        } else {
            grid.addComponentColumn(m -> new NationFlag(m.nation())).setHeader("Nation").setFlexGrow(1);
        }
        medalColumn(grid, "Gold", GOLD, m -> m.gold(t));
        medalColumn(grid, "Silver", SILVER, m -> m.silver(t));
        medalColumn(grid, "Bronze", BRONZE, m -> m.bronze(t));
        grid.addColumn(m -> m.total(t)).setHeader("Total").setWidth("70px").setFlexGrow(0)
                .setTextAlign(ColumnTextAlign.END).setSortable(true).setComparator(m -> m.total(t));
        if (t) {
            grid.addColumn(m -> m.teamGold() + m.teamSilver() + m.teamBronze()).setHeader("Team")
                    .setWidth("70px").setFlexGrow(0).setTextAlign(ColumnTextAlign.END);
        }
        grid.addColumn(m -> m.firstYear().equals(m.lastYear()) ? m.firstYear() : m.firstYear() + "–" + m.lastYear())
                .setHeader("Years").setWidth("110px").setFlexGrow(0);
        grid.setItems(rows);
        // every medallist; a long list scrolls in its own box
        if (rows.size() > 40) {
            grid.setHeight("1000px");
        } else {
            grid.setAllRowsVisible(true);
        }
        return grid;
    }

    private static void medalColumn(Grid<Medals> grid, String header, String color, ToIntFunction<Medals> value) {
        Span dot = new Span();
        dot.getStyle().set("display", "inline-block").set("width", "0.8em").set("height", "0.8em")
                .set("border-radius", "50%").set("background", color).set("margin-right", "0.3em");
        HorizontalLayout h = new HorizontalLayout(dot, new Span(header));
        h.setSpacing(false);
        h.setAlignItems(Alignment.CENTER);
        grid.addColumn(value::applyAsInt).setHeader(h).setWidth("100px").setFlexGrow(0)
                .setTextAlign(ColumnTextAlign.END).setSortable(true).setComparator(value::applyAsInt);
    }

    /** Equal medals (gold, silver, bronze) share the place. */
    private static int place(List<Medals> rows, Medals m, boolean teams) {
        int better = 0;
        for (Medals o : rows) {
            int c = Integer.compare(o.gold(teams), m.gold(teams));
            if (c == 0) c = Integer.compare(o.silver(teams), m.silver(teams));
            if (c == 0) c = Integer.compare(o.bronze(teams), m.bronze(teams));
            if (c > 0) better++;
        }
        return better + 1;
    }
}
