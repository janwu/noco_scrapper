package com.fis.noco.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "competitions")
public class Competition {

    @Id
    @Column(name = "id")
    private Long id;

    @Column(name = "event_id")
    private Long eventId;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "season_id")
    private Season season;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "venue_id")
    private Venue venue;

    @Column(name = "fis_codex")
    private String fisCodex;

    @Column(name = "circuit")
    private String circuit;

    @Column(name = "gender")
    private String gender;

    @Column(name = "competition_date")
    private String competitionDate;

    @Column(name = "raw_location")
    private String rawLocation;

    @Column(name = "raw_country")
    private String rawCountry;

    @Column(name = "format")
    private String format;

    @Column(name = "hill_spec")
    private String hillSpec;

    @Column(name = "hill_size_m")
    private Double hillSizeM;

    @Column(name = "xc_distance_km")
    private Double xcDistanceKm;

    @Column(name = "event_name")
    private String eventName;

    public Long getId() { return id; }
    public Long getEventId() { return eventId; }
    public Season getSeason() { return season; }
    public Venue getVenue() { return venue; }
    public String getFisCodex() { return fisCodex; }
    public String getCircuit() { return circuit; }
    public String getGender() { return gender; }
    public String getCompetitionDate() { return competitionDate; }
    public String getRawLocation() { return rawLocation; }
    public String getRawCountry() { return rawCountry; }
    public String getFormat() { return format; }
    public String getHillSpec() { return hillSpec; }
    public Double getHillSizeM() { return hillSizeM; }
    public Double getXcDistanceKm() { return xcDistanceKm; }
    public String getEventName() { return eventName; }

    /**
     * The Winter Olympics that were the World Championships as well: every Olympic
     * Nordic combined until 1980 (from 1982 the World Championships are held apart).
     */
    public static final java.util.Set<Integer> OLYMPIC_CHAMPIONSHIPS = java.util.Set.of(
            1924, 1928, 1932, 1936, 1948, 1952, 1956, 1960, 1964, 1968, 1972, 1976, 1980);

    /** "World Cup", "World Championships", or "Continental Cup", which was called "World Cup B" until 2007/08. */
    public String getCircuitLabel() {
        if ("WC".equals(circuit)) return "World Cup";
        if ("WSC".equals(circuit)) return "World Championships";
        return season != null && season.getStartYear() != null && season.getStartYear() < 2008
                ? "World Cup B" : "Continental Cup";
    }

    /** The label for a table column: "World Cup", "World Ch.", "Cont. Cup". */
    public String getCircuitShortLabel() {
        if ("WC".equals(circuit)) return "World Cup";
        if ("WSC".equals(circuit)) return isOlympic() ? "World Ch. (OWG)" : "World Ch.";
        return "Cont. Cup";
    }

    /** The year of the competition, '1924'. */
    public Integer getYear() {
        return competitionDate != null && competitionDate.length() >= 4
                ? Integer.valueOf(competitionDate.substring(0, 4)) : null;
    }

    /** World Championships held as the Olympic Winter Games (until 1980). */
    public boolean isOlympic() {
        return "WSC".equals(circuit) && getYear() != null && OLYMPIC_CHAMPIONSHIPS.contains(getYear());
    }

    public String getDisplayLocation() {
        if (venue != null && venue.getName() != null && !venue.getName().isBlank()) {
            return venue.getDisplayName();
        }
        return rawLocation != null ? rawLocation : "";
    }

    public String getDisplayCountry() {
        if (venue != null && venue.getCountry() != null) {
            return venue.getCountry();
        }
        return rawCountry != null ? rawCountry : "";
    }
}
