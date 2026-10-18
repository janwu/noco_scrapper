package com.fis.noco;

import com.fis.noco.service.RecordsService;
import com.fis.noco.service.RecordsService.Count;
import com.fis.noco.service.RecordsService.NationMode;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.io.File;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/** World Cup records on the real database: athletes and nations, old nations counted as agreed. */
@SpringBootTest
class RecordsTest {

    @Autowired
    private RecordsService records;

    @BeforeEach
    void database() {
        Assumptions.assumeTrue(new File("../db/noco.db").exists(), "database not built");
    }

    private static Map<String, Count> byNation(List<Count> nations) {
        return nations.stream().collect(Collectors.toMap(Count::nation, Function.identity()));
    }

    @Test
    void mostWins() {
        List<Count> top = RecordsService.top(records.athletes("M"), Count::wins, 3);
        assertTrue(top.get(0).name().startsWith("RIIBER"), top.toString());
        assertTrue(top.get(0).wins() >= 76);
        assertTrue(top.get(0).podiums() >= top.get(0).wins() && top.get(0).top10() >= top.get(0).podiums());
    }

    @Test
    void westGermanyCountsForGermanyEastGermanyOnItsOwn() {
        Map<String, Count> nations = byNation(records.nations("M", NationMode.AT_THE_TIME));
        assertFalse(nations.containsKey("FRG"));
        assertTrue(nations.containsKey("GDR"));
        assertTrue(nations.containsKey("SOV"));
        assertFalse(nations.containsKey("GUS"));               // the CIS of 1992 is listed as CIS
        assertFalse(nations.containsKey("AIN"));               // Russians of the 2000s in today's FIS database
        assertEquals("NOR", records.nations("M", NationMode.AT_THE_TIME).get(0).nation());
    }

    @Test
    void athletesNationMovesSovietPodiumsToEstonia() {
        int atTheTime = byNation(records.nations("M", NationMode.AT_THE_TIME)).get("EST") == null ? 0
                : byNation(records.nations("M", NationMode.AT_THE_TIME)).get("EST").podiums();
        int byAthlete = byNation(records.nations("M", NationMode.ATHLETE)).get("EST").podiums();
        assertTrue(byAthlete > atTheTime, atTheTime + " / " + byAthlete);   // LEVANDI Allar, SOV in the 1980s
    }
}
