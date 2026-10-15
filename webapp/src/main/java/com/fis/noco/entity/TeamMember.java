package com.fis.noco.entity;

import jakarta.persistence.*;

/** One athlete of a team result. */
@Entity
@Table(name = "team_members")
public class TeamMember {

    @Id
    @Column(name = "id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "team_result_id")
    private TeamResult teamResult;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "athlete_id")
    private Athlete athlete;

    @Column(name = "raw_name")
    private String rawName;

    @Column(name = "raw_nation")
    private String rawNation;

    @Column(name = "leg")
    private Integer leg;

    @Column(name = "xc_time")
    private String xcTime;

    @Column(name = "jump_points")
    private Double jumpPoints;

    public Long getId() { return id; }
    public TeamResult getTeamResult() { return teamResult; }
    public Athlete getAthlete() { return athlete; }
    public String getRawName() { return rawName; }
    public String getRawNation() { return rawNation; }
    public Integer getLeg() { return leg; }
    public String getXcTime() { return xcTime; }
    public Double getJumpPoints() { return jumpPoints; }

    public String getDisplayName() {
        if (athlete != null && athlete.getFullName() != null) {
            return athlete.getDisplayName();
        }
        return rawName != null ? rawName : "";
    }
}
