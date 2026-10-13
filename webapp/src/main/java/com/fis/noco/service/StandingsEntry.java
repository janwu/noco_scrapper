package com.fis.noco.service;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * One athlete in a cup standing: the official rank and points, and — for the
 * columns next to them — the athlete's rank in each competition of the season.
 */
public class StandingsEntry {

    private final int position;
    private final Long athleteId;            // null if the athlete has no result in the database
    private final String athleteName;
    private final String nation;
    private final Integer totalPoints;
    private final Map<Long, Integer> rankByCompetition = new LinkedHashMap<>();

    public StandingsEntry(int position, Long athleteId, String athleteName, String nation, Integer totalPoints) {
        this.position = position;
        this.athleteId = athleteId;
        this.athleteName = athleteName != null ? athleteName : "";
        this.nation = nation != null ? nation : "";
        this.totalPoints = totalPoints;
    }

    public void setRank(Long competitionId, int rank) {
        rankByCompetition.put(competitionId, rank);
    }

    public int getPosition()             { return position; }
    public Long getAthleteId()           { return athleteId; }
    public String getAthleteName()       { return athleteName; }
    public String getNation()            { return nation; }
    public Integer getTotalPoints()      { return totalPoints; }

    public Integer getRankInCompetition(Long competitionId) {
        return rankByCompetition.get(competitionId);
    }
}
