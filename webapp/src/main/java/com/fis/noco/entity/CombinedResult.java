package com.fis.noco.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "combined_results")
public class CombinedResult {

    @Id
    @Column(name = "id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "competition_id")
    private Competition competition;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "document_id")
    private CompetitionDocument document;

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

    @Column(name = "club")
    private String club;

    @Column(name = "date_of_birth")
    private String dateOfBirth;

    @Column(name = "jump_points")
    private Double jumpPoints;

    @Column(name = "jump_rank")
    private Integer jumpRank;

    @Column(name = "time_difference")
    private String timeDifference;

    @Column(name = "xc_time")
    private String xcTime;

    @Column(name = "xc_rank")
    private Integer xcRank;

    @Column(name = "time_behind")
    private String timeBehind;

    @Column(name = "wave_start")
    private Integer waveStart;

    @Column(name = "status")
    private String status;

    public Long getId() { return id; }
    public Competition getCompetition() { return competition; }
    public CompetitionDocument getDocument() { return document; }
    public Athlete getAthlete() { return athlete; }
    public String getRawName() { return rawName; }
    public String getRawNation() { return rawNation; }
    public Integer getRank() { return rank; }
    public Integer getBib() { return bib; }
    public String getClub() { return club; }
    public String getDateOfBirth() { return dateOfBirth; }
    public Double getJumpPoints() { return jumpPoints; }
    public Integer getJumpRank() { return jumpRank; }
    public String getTimeDifference() { return timeDifference; }
    public String getXcTime() { return xcTime; }
    public Integer getXcRank() { return xcRank; }
    public String getTimeBehind() { return timeBehind; }
    public Integer getWaveStart() { return waveStart; }
    public String getStatus() { return status; }

    public boolean isWaveStart() { return waveStart != null && waveStart == 1; }

    public String getDisplayName() {
        if (athlete != null && athlete.getFullName() != null) {
            return athlete.getDisplayName();
        }
        return rawName != null ? rawName : "";
    }

    /**
     * Gap to the winner at the finish: "0.0" for the winner, "+41.6" for the others,
     * empty for athletes without a finish (DNS, DNF, DSQ, lapped).
     *
     * Not to be confused with {@link #getTimeDifference()}, the start gap after the
     * jumping part.  The result lists print the winner's total time where the others
     * have their gap, which is why the stored value cannot be shown as it is.
     */
    public String getFinishGap() {
        if (status != null && !status.isBlank()) {
            return "";
        }
        if (rank != null && rank == 1) {
            return "0.0";
        }
        return timeBehind != null ? timeBehind : "";
    }

    /**
     * The nation the athlete competed for here, as printed in the list: an athlete
     * who changed nation (SCHMID Jan, SUI until 2006, then NOR) is one athlete
     * under his last nation, but keeps the flag of the time in old results.
     */
    public String getDisplayNation() {
        if (rawNation != null && rawNation.matches("[A-Za-z]{3}")) {
            return rawNation.toUpperCase();
        }
        return athlete != null && athlete.getNationality() != null ? athlete.getNationality() : "";
    }
}
