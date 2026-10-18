package com.fis.noco.views;

import com.fis.noco.service.MedalsService;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;

/** Medal table of the Olympic Winter Games. */
@Route(value = "olympic-medals", layout = MainLayout.class)
@PageTitle("Olympic Medals | FIS Nordic Combined")
public class OlympicMedalsView extends MedalTable {

    public OlympicMedalsView(MedalsService medals) {
        super(medals, "OWG", "Olympic Medals",
                "Olympic Winter Games 1924–2026; until 1980 their medals were World Championship medals too.");
    }
}
