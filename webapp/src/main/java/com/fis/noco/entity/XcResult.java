package com.fis.noco.entity;

import jakarta.persistence.*;

/**
 * One row of the cross-country list of a mass start (RLLL): the race that comes
 * before the jump.  Loaded only from lists that pass validation.
 */
@Entity
@Table(name = "xc_results")
public class XcResult {

    @Id
    @Column(name = "id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "competition_id")
    private Competition competition;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "athlete_id")
    private Athlete athlete;

    @Column(name = "raw_name")
    private String rawName;

    @Column(name = "raw_nation")
    private String rawNation;

    @Column(name = "rank")
    private Integer rank;

    @Column(name = "bib")
    private Integer bib;

    @Column(name = "total_time")
    private String totalTime;

    @Column(name = "time_behind")
    private String timeBehind;

    @Column(name = "points")
    private Double points;

    @Column(name = "status")
    private String status;

    public Long getId() { return id; }
    public Competition getCompetition() { return competition; }
    public Athlete getAthlete() { return athlete; }
    public Integer getRank() { return rank; }
    public Integer getBib() { return bib; }
    public String getTotalTime() { return totalTime; }
    public String getTimeBehind() { return timeBehind; }
    public Double getPoints() { return points; }
    public String getStatus() { return status; }

    public String getDisplayName() {
        if (athlete != null && athlete.getFullName() != null) return athlete.getDisplayName();
        return rawName != null ? rawName : "";
    }

    /** The nation printed in the list (see CombinedResult#getDisplayNation). */
    public String getDisplayNation() {
        if (rawNation != null && rawNation.matches("[A-Za-z]{3}")) return rawNation.toUpperCase();
        return athlete != null && athlete.getNationality() != null ? athlete.getNationality() : "";
    }
}
