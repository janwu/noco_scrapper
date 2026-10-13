package com.fis.noco.entity;

import jakarta.persistence.*;

/**
 * One line of an official FIS cup standing: an athlete's rank and points in a
 * season, circuit and ranking (overall, or a trophy such as "Best Jumper").
 * Taken from the FIS database, not computed from the results.
 */
@Entity
@Table(name = "cup_standings")
public class CupStanding {

    @Id
    @Column(name = "id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "season_id")
    private Season season;

    @Column(name = "circuit")
    private String circuit;

    @Column(name = "gender")
    private String gender;

    @Column(name = "discipline_code")
    private String disciplineCode;

    @Column(name = "discipline_name")
    private String disciplineName;

    @Column(name = "rank")
    private Integer rank;

    @Column(name = "points")
    private Integer points;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "athlete_id")
    private Athlete athlete;

    @Column(name = "raw_name")
    private String rawName;

    @Column(name = "raw_nation")
    private String rawNation;

    @Column(name = "fis_competitor_id")
    private String fisCompetitorId;

    public Long getId() { return id; }
    public Season getSeason() { return season; }
    public String getCircuit() { return circuit; }
    public String getGender() { return gender; }
    public String getDisciplineCode() { return disciplineCode; }
    public String getDisciplineName() { return disciplineName; }
    public Integer getRank() { return rank; }
    public Integer getPoints() { return points; }
    public Athlete getAthlete() { return athlete; }
    public String getRawName() { return rawName; }
    public String getRawNation() { return rawNation; }
    public String getFisCompetitorId() { return fisCompetitorId; }
}
