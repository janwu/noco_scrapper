package com.fis.noco.service;

import java.util.LinkedHashMap;
import java.util.Map;

public class StandingsEntry {

    private int position;
    private final Long athleteId;
    private final String athleteName;
    private final String nation;
    private int totalPoints;
    private final Map<Long, Integer> pointsByCompetition = new LinkedHashMap<>();

    public StandingsEntry(Long athleteId, String athleteName, String nation) {
        this.athleteId = athleteId;
        this.athleteName = athleteName != null ? athleteName : "";
        this.nation = nation != null ? nation : "";
    }

    public void addPoints(Long competitionId, int points) {
        pointsByCompetition.merge(competitionId, points, Integer::sum);
        totalPoints += points;
    }

    public int getPosition()             { return position; }
    public void setPosition(int p)       { this.position = p; }
    public Long getAthleteId()           { return athleteId; }
    public String getAthleteName()       { return athleteName; }
    public String getNation()            { return nation; }
    public int getTotalPoints()          { return totalPoints; }
    public Map<Long, Integer> getPointsByCompetition() { return pointsByCompetition; }

    public Integer getPointsForCompetition(Long competitionId) {
        return pointsByCompetition.get(competitionId);
    }
}
