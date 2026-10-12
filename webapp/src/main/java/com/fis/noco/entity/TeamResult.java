package com.fis.noco.entity;

import jakarta.persistence.*;

import java.util.ArrayList;
import java.util.List;

/** One team in a Team / Team Sprint / Mixed Team competition. */
@Entity
@Table(name = "team_results")
public class TeamResult {

    @Id
    @Column(name = "id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "competition_id")
    private Competition competition;

    @Column(name = "rank")
    private Integer rank;

    @Column(name = "bib")
    private Integer bib;

    @Column(name = "nation")
    private String nation;

    @Column(name = "team_name")
    private String teamName;

    @Column(name = "jump_points")
    private Double jumpPoints;

    @Column(name = "jump_rank")
    private Integer jumpRank;

    @Column(name = "time_difference")
    private String timeDifference;

    @Column(name = "total_time")
    private String xcTime;

    @Column(name = "xc_rank")
    private Integer xcRank;

    @Column(name = "time_behind")
    private String timeBehind;

    @Column(name = "status")
    private String status;

    @OneToMany(mappedBy = "teamResult", fetch = FetchType.LAZY)
    @OrderBy("leg ASC")
    private List<TeamMember> members = new ArrayList<>();

    public Long getId() { return id; }
    public Competition getCompetition() { return competition; }
    public Integer getRank() { return rank; }
    public Integer getBib() { return bib; }
    public String getNation() { return nation; }
    public String getTeamName() { return teamName; }
    public Double getJumpPoints() { return jumpPoints; }
    public Integer getJumpRank() { return jumpRank; }
    public String getTimeDifference() { return timeDifference; }
    public String getXcTime() { return xcTime; }
    public Integer getXcRank() { return xcRank; }
    public String getTimeBehind() { return timeBehind; }
    public String getStatus() { return status; }
    public List<TeamMember> getMembers() { return members; }

    /** 'Norway I' — the name as printed, or the nation code if the list has none. */
    public String getDisplayName() {
        return teamName != null && !teamName.isBlank() ? teamName : (nation != null ? nation : "");
    }
}
