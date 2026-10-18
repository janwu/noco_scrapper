package com.fis.noco.views;

import com.fis.noco.service.MedalsService;
import com.vaadin.flow.router.PageTitle;
import com.vaadin.flow.router.Route;

/** Medal table of the World Championships (and the Olympic Games until 1980, which counted as such). */
@Route(value = "medals", layout = MainLayout.class)
@PageTitle("World Championship Medals | FIS Nordic Combined")
public class MedalsView extends MedalTable {

    public MedalsView(MedalsService medals) {
        super(medals, "WSC", "World Championship Medals",
                "World Championships 1925–2025 and the Olympic Winter Games 1924–1980, which counted as "
                        + "World Championships.");
    }
}
