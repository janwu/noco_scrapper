package com.fis.noco;

import com.fis.noco.entity.Athlete;
import com.fis.noco.entity.Venue;
import com.fis.noco.service.AthleteService;
import com.fis.noco.service.NameFolding;
import com.fis.noco.service.VenueService;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.io.File;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** Names with native letters are shown; the FIS spelling stays the stored name, and both are found. */
@SpringBootTest
class DisplayNamesTest {

    @Autowired
    private AthleteService athleteService;
    @Autowired
    private VenueService venueService;

    @Test
    void foldingToTheFisSpelling() {
        assertEquals("Bjoernstad", NameFolding.toFis("Bjørnstad"));
        assertEquals("Otepaeae", NameFolding.toFis("Otepää"));
        assertEquals("Strbske Pleso", NameFolding.toFis("Štrbské Pleso"));
        assertEquals("Wisla", NameFolding.toFis("Wisła"));
        assertEquals("Haavard", NameFolding.toFis("Håvard"));
    }

    @Test
    void athleteShownWithNativeLettersFoundInBothSpellings() {
        Assumptions.assumeTrue(new File("../db/noco.db").exists(), "database not built");
        for (String query : List.of("Bjørnstad", "bjoernstad", "BJØRNSTAD Espen")) {
            List<Athlete> found = athleteService.searchAthletes(query, 0, 10).getContent();
            assertEquals(1, found.size(), query);
            assertEquals("BJOERNSTAD Espen", found.get(0).getFullName());
            assertEquals("BJØRNSTAD Espen", found.get(0).getDisplayName());
        }
        Athlete riiber = athleteService.searchAthletes("Riiber Jarl", 0, 10).getContent().get(0);
        assertEquals(riiber.getFullName(), riiber.getDisplayName());           // no display name: the FIS name
    }

    @Test
    void venueShownWithNativeLetters() {
        Assumptions.assumeTrue(new File("../db/noco.db").exists(), "database not built");
        List<Venue> found = venueService.searchVenues("Otepää", 0, 10).getContent();
        assertEquals(1, found.size());
        assertEquals("Otepaeae", found.get(0).getName());
        assertEquals("Otepää", found.get(0).getDisplayName());
        assertTrue(venueService.searchVenues("otepaeae", 0, 10).getContent().size() == 1);
    }
}
