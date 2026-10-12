package com.fis.noco.views;

import com.vaadin.flow.component.applayout.AppLayout;
import com.vaadin.flow.component.applayout.DrawerToggle;
import com.vaadin.flow.component.html.H1;
import com.vaadin.flow.component.html.Span;
import com.vaadin.flow.component.icon.VaadinIcon;
import com.vaadin.flow.component.orderedlayout.FlexComponent;
import com.vaadin.flow.component.orderedlayout.HorizontalLayout;
import com.vaadin.flow.component.sidenav.SideNav;
import com.vaadin.flow.component.sidenav.SideNavItem;
import com.vaadin.flow.theme.lumo.LumoUtility;

public class MainLayout extends AppLayout {

    public MainLayout() {
        createHeader();
        createDrawer();
    }

    private void createHeader() {
        H1 appName = new H1("FIS Nordic Combined");
        appName.addClassNames(
                LumoUtility.FontSize.LARGE,
                LumoUtility.Margin.NONE,
                LumoUtility.TextColor.BODY
        );

        DrawerToggle toggle = new DrawerToggle();

        HorizontalLayout header = new HorizontalLayout(toggle, appName);
        header.setDefaultVerticalComponentAlignment(FlexComponent.Alignment.CENTER);
        header.setWidthFull();
        header.addClassNames(LumoUtility.Padding.Vertical.NONE, LumoUtility.Padding.Horizontal.MEDIUM);

        addToNavbar(header);
    }

    private void createDrawer() {
        SideNav nav = new SideNav();

        SideNavItem homeLink = new SideNavItem("Home", HomeView.class,
                VaadinIcon.HOME.create());

        SideNavItem athletesLink = new SideNavItem("Athletes", AthleteSearchView.class,
                VaadinIcon.USER.create());

        SideNavItem resultsLink = new SideNavItem("Results Browser", ResultsBrowserView.class,
                VaadinIcon.LIST.create());

        SideNavItem standingsLink = new SideNavItem("WC Standings", StandingsView.class,
                VaadinIcon.TROPHY.create());

        SideNavItem venuesLink = new SideNavItem("Venues", VenueSearchView.class,
                VaadinIcon.MAP_MARKER.create());

        nav.addItem(homeLink, athletesLink, resultsLink, standingsLink, venuesLink);
        nav.setWidthFull();

        Span appDescription = new Span("Results from FIS Nordic Combined competitions");
        appDescription.addClassNames(
                LumoUtility.FontSize.XSMALL,
                LumoUtility.TextColor.SECONDARY,
                LumoUtility.Padding.SMALL
        );

        addToDrawer(nav, appDescription);
    }
}
