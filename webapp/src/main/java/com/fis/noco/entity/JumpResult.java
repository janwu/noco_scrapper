package com.fis.noco.entity;

import jakarta.persistence.*;

import java.util.Locale;
import java.util.Objects;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * One jump from a jump list: the competition round (RL, RL1), a qualification
 * (RLQ) or the provisional round (PCR).  Lists with two jumps per athlete have
 * one row per jump; rank is the rank of the list.  In team lists each member
 * carries the rank of his team.
 */
@Entity
@Table(name = "jump_round_results")
public class JumpResult {

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

    @Column(name = "round_number")
    private Integer roundNumber;

    @Column(name = "speed_kmh")
    private Double speedKmh;

    @Column(name = "distance_m")
    private Double distanceM;

    @Column(name = "dist_points")
    private Double distPoints;

    @Column(name = "judge_a")
    private Double judgeA;

    @Column(name = "judge_b")
    private Double judgeB;

    @Column(name = "judge_c")
    private Double judgeC;

    @Column(name = "judge_d")
    private Double judgeD;

    @Column(name = "judge_e")
    private Double judgeE;

    @Column(name = "style_points")
    private Double stylePoints;

    /** A gate may be a half gate (8.5, Val di Fiemme 2012). */
    @Column(name = "gate")
    private Double gate;

    @Column(name = "gate_comp_pts")
    private Double gateCompPts;

    @Column(name = "wind_ms")
    private Double windMs;

    @Column(name = "wind_comp_pts")
    private Double windCompPts;

    @Column(name = "total_points")
    private Double totalPoints;

    @Column(name = "pursuit_time_diff")
    private String pursuitTimeDiff;

    @Column(name = "dns")
    private Integer dns;

    @Column(name = "dsq")
    private Integer dsq;

    @Column(name = "dsq_reason")
    private String dsqReason;

    public Long getId() { return id; }
    public Competition getCompetition() { return competition; }
    public CompetitionDocument getDocument() { return document; }
    public Athlete getAthlete() { return athlete; }
    public Integer getRank() { return rank; }
    public Integer getBib() { return bib; }
    public String getClub() { return club; }
    public Integer getRoundNumber() { return roundNumber; }
    public Double getSpeedKmh() { return speedKmh; }
    public Double getDistanceM() { return distanceM; }
    public Double getDistPoints() { return distPoints; }
    public Double getStylePoints() { return stylePoints; }
    public Double getGate() { return gate; }
    public Double getGateCompPts() { return gateCompPts; }
    public Double getWindMs() { return windMs; }
    public Double getWindCompPts() { return windCompPts; }
    public Double getTotalPoints() { return totalPoints; }
    public String getPursuitTimeDiff() { return pursuitTimeDiff; }
    public String getDsqReason() { return dsqReason; }

    public boolean hasMarks() { return judgeA != null; }

    /** The judges' marks as printed: '18.5 19.0 18.5 18.5 19.0' (three in 2020/21). */
    public String getMarks() {
        return Stream.of(judgeA, judgeB, judgeC, judgeD, judgeE)
                .filter(Objects::nonNull)
                .map(JumpResult::format)
                .collect(Collectors.joining(" "));
    }

    public String getGateLabel() {
        if (gate == null) return "";
        return gate == Math.floor(gate) ? String.valueOf(gate.intValue()) : format(gate);
    }

    /** DNS / DSQ, or empty. */
    public String getStatus() {
        if (dsq != null && dsq == 1) return "DSQ";
        if (dns != null && dns == 1) return "DNS";
        return "";
    }

    /** Competition round, Qualification or Provisional round. */
    public String getListLabel() {
        return listLabel(document != null ? document.getDocType() : null);
    }

    public static String listLabel(String docType) {
        if ("RLQ".equals(docType)) return "Qualification";
        if ("PCR".equals(docType)) return "Provisional Round";
        return "Competition Round";
    }

    public String getDisplayName() {
        if (athlete != null && athlete.getFullName() != null) {
            return athlete.getFullName();
        }
        return rawName != null ? rawName : "";
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

    public static String format(Double value) {
        return value == null ? "" : String.format(Locale.ROOT, "%.1f", value);
    }
}
