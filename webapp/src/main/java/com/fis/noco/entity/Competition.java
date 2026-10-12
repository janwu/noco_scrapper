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

    public String getDisplayLocation() {
        if (venue != null && venue.getName() != null && !venue.getName().isBlank()) {
            return venue.getName();
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
