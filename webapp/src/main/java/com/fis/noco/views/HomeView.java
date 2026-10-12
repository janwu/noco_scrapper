package com.fis.noco.views;

import com.fis.noco.entity.CombinedResult;
import com.fis.noco.entity.Competition;
import com.fis.noco.service.CompetitionService;
import com.vaadin.flow.component.UI;
import com.vaadin.flow.component.button.Button;
import com.vaadin.flow.component.button.ButtonVariant;
import com.vaadin.flow.component.html.Div;
import com.vaadin.flow.component.html.H2;
import com.vaadin.flow.component.html.H3;
import com.vaadin.flow.component.html.H4;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.icon.VaadinIcon;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.orderedlayout.VerticalLayout;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;
import com.vaadin.flow.router.RouteAlias;
import com.vaadin.flow.theme.lumo.LumoUtility;

import java.util.List;

@Route(value = "home", layout = MainLayout.class)
@RouteAlias(value = "", layout = MainLayout.class)
@PageTitle("FIS Nordic Combined")
public class HomeView extends VerticalLayout {

    private static final int RECENT_COMPS = 3;
    private static final int TOP3 = 3;
    private static final int TOP10 = 10;

    private final CompetitionService competitionService;

    public HomeView(CompetitionService competitionService) {
        this.competitionService = competitionService;
        setSizeFull();
        setPadding(true);
        setSpacing(false);
        addClassNames(LumoUtility.Gap.MEDIUM);

        H2 title = new H2("Recent World Cup Results");
        title.addClassNames(LumoUtility.Margin.Bottom.MEDIUM, LumoUtility.Margin.Top.SMALL);

        HorizontalLayout columns = new HorizontalLayout();
        columns.setWidthFull();
        columns.setSpacing(true);
        columns.setAlignItems(Alignment.START);
        columns.getStyle().set("flex-wrap", "wrap");

        columns.add(buildGenderColumn("Men", "M"));
        columns.add(buildGenderColumn("Women", "W"));

        add(title, columns);
        expand(columns);
    }

    private VerticalLayout buildGenderColumn(String label, String gender) {
        VerticalLayout col = new VerticalLayout();
        col.setPadding(false);
        col.setSpacing(true);
        col.setMinWidth("320px");
        col.getStyle().set("flex", "1");

        H3 heading = new H3(label);
        heading.addClassNames(LumoUtility.Margin.Bottom.XSMALL, LumoUtility.Margin.Top.NONE);
        col.add(heading);

        List<Competition> comps = competitionService.getLatestWCCompetitions(gender, RECENT_COMPS);
        for (Competition comp : comps) {
            col.add(buildCompCard(comp));
        }
        if (comps.isEmpty()) {
            col.add(new Span("No results available."));
        }
        return col;
    }

    private Div buildCompCard(Competition comp) {
        Div card = new Div();
        card.getStyle()
                .set("background", "var(--lumo-base-color)")
                .set("border", "1px solid var(--lumo-contrast-10pct)")
                .set("border-radius", "var(--lumo-border-radius-m)")
                .set("padding", "var(--lumo-space-m)")
                .set("margin-bottom", "var(--lumo-space-s)");

        // Header row: date + location
        String location = comp.getDisplayLocation();
        String country = comp.getDisplayCountry();
        String date = comp.getCompetitionDate() != null ? comp.getCompetitionDate() : "";
        String format = comp.getFormat() != null ? comp.getFormat() : "";

        Div headerRow = new Div();
        headerRow.getStyle().set("display", "flex").set("justify-content", "space-between")
                .set("align-items", "baseline").set("margin-bottom", "var(--lumo-space-xs)");

        Div locationDiv = new Div();
        Span locationSpan = new Span(new Span(location));
        if (!country.isBlank()) {
            locationSpan.add(new NationFlag(country, false));
        }
        locationSpan.getStyle().set("display", "inline-flex").set("align-items", "center").set("gap", "0.4em");
        locationSpan.addClassNames(LumoUtility.FontWeight.BOLD, LumoUtility.FontSize.MEDIUM);
        Span dateSpan = new Span(" · " + date);
        dateSpan.addClassNames(LumoUtility.TextColor.SECONDARY, LumoUtility.FontSize.SMALL);
        locationDiv.add(locationSpan, dateSpan);

        Span formatBadge = new Span(format);
        formatBadge.getStyle()
                .set("background", "var(--lumo-contrast-5pct)")
                .set("border-radius", "var(--lumo-border-radius-s)")
                .set("padding", "2px 8px")
                .set("font-size", "var(--lumo-font-size-xs)")
                .set("white-space", "nowrap");

        headerRow.add(locationDiv, formatBadge);
        card.add(headerRow);

        // Results table
        List<CombinedResult> results = competitionService.getResultsForCompetition(comp.getId());
        List<CombinedResult> ranked = results.stream()
                .filter(r -> r.getRank() != null)
                .sorted((a, b) -> Integer.compare(a.getRank(), b.getRank()))
                .toList();

        boolean isMassStart = "Mass Start".equals(format);

        Div top3Div = buildResultRows(ranked.stream().limit(TOP3).toList(), isMassStart);
        card.add(top3Div);

        // Top 10 expandable section
        List<CombinedResult> rest = ranked.stream().skip(TOP3).limit(TOP10 - TOP3).toList();
        if (!rest.isEmpty()) {
            Div top10Div = buildResultRows(rest, isMassStart);
            top10Div.setVisible(false);

            Button expandBtn = new Button("Top 10", VaadinIcon.CHEVRON_DOWN.create());
            expandBtn.addThemeVariants(ButtonVariant.LUMO_TERTIARY, ButtonVariant.LUMO_SMALL);
            expandBtn.getStyle().set("margin-top", "var(--lumo-space-xs)");
            expandBtn.addClickListener(e -> {
                boolean nowVisible = !top10Div.isVisible();
                top10Div.setVisible(nowVisible);
                expandBtn.setIcon(nowVisible
                        ? VaadinIcon.CHEVRON_UP.create()
                        : VaadinIcon.CHEVRON_DOWN.create());
            });

            card.add(top10Div, expandBtn);
        }

        // Full results link
        Button fullLink = new Button("Full results →");
        fullLink.addThemeVariants(ButtonVariant.LUMO_TERTIARY, ButtonVariant.LUMO_SMALL);
        fullLink.getStyle().set("margin-top", "var(--lumo-space-xs)");
        fullLink.addClickListener(e -> UI.getCurrent().navigate(ResultDetailView.class, comp.getId()));
        card.add(fullLink);

        return card;
    }

    private Div buildResultRows(List<CombinedResult> results, boolean isMassStart) {
        Div container = new Div();
        container.getStyle().set("margin-top", "var(--lumo-space-xs)");

        for (CombinedResult r : results) {
            Div row = new Div();
            row.getStyle()
                    .set("display", "flex")
                    .set("align-items", "center")
                    .set("gap", "var(--lumo-space-s)")
                    .set("padding", "3px 0")
                    .set("border-bottom", "1px solid var(--lumo-contrast-5pct)");

            // Rank
            Span rankSpan = new Span(r.getRank() != null ? String.valueOf(r.getRank()) : "-");
            rankSpan.getStyle()
                    .set("width", "24px")
                    .set("text-align", "right")
                    .set("font-weight", r.getRank() != null && r.getRank() <= 3 ? "bold" : "normal")
                    .set("color", rankColor(r.getRank()))
                    .set("flex-shrink", "0");

            // Name — link to athlete profile if available, plain span otherwise
            com.vaadin.flow.component.Component nameComponent;
            if (r.getAthlete() != null) {
                com.vaadin.flow.component.html.Anchor nameLink =
                        new com.vaadin.flow.component.html.Anchor(
                                "athlete/" + r.getAthlete().getId(), r.getDisplayName());
                nameLink.getStyle()
                        .set("flex", "1")
                        .set("font-size", "var(--lumo-font-size-s)")
                        .set("white-space", "nowrap")
                        .set("overflow", "hidden")
                        .set("text-overflow", "ellipsis")
                        .set("text-decoration", "none")
                        .set("color", "var(--lumo-primary-color)");
                nameComponent = nameLink;
            } else {
                Span nameSpan = new Span(r.getDisplayName());
                nameSpan.getStyle()
                        .set("flex", "1")
                        .set("font-size", "var(--lumo-font-size-s)")
                        .set("white-space", "nowrap")
                        .set("overflow", "hidden")
                        .set("text-overflow", "ellipsis");
                nameComponent = nameSpan;
            }

            // Nation
            NationFlag nationSpan = new NationFlag(r.getDisplayNation(), false);
            nationSpan.addClassNames(LumoUtility.TextColor.SECONDARY, LumoUtility.FontSize.XSMALL);
            nationSpan.getStyle().set("flex-shrink", "0").set("width", "30px");

            // Diff
            String diff = isMassStart ? r.getTimeBehind() : r.getTimeDifference();
            Span diffSpan = new Span(diff != null ? diff : "");
            diffSpan.addClassNames(LumoUtility.FontSize.XSMALL);
            diffSpan.getStyle()
                    .set("flex-shrink", "0")
                    .set("text-align", "right")
                    .set("min-width", "52px")
                    .set("color", "var(--lumo-secondary-text-color)");

            row.add(rankSpan, nameComponent, nationSpan, diffSpan);
            container.add(row);
        }
        return container;
    }

    private String rankColor(Integer rank) {
        if (rank == null) return "inherit";
        return switch (rank) {
            case 1 -> "#c9a227";
            case 2 -> "#9e9e9e";
            case 3 -> "#a0522d";
            default -> "inherit";
        };
    }
}
