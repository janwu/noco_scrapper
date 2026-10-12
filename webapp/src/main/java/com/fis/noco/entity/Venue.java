package com.fis.noco.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "venues")
public class Venue {

    @Id
    @Column(name = "id")
    private Long id;

    @Column(name = "name")
    private String name;

    @Column(name = "country")
    private String country;

    @Column(name = "region")
    private String region;

    @Column(name = "latitude")
    private Double latitude;

    @Column(name = "longitude")
    private Double longitude;

    @Column(name = "hill_name")
    private String hillName;

    public Long getId() { return id; }
    public String getName() { return name; }
    public String getCountry() { return country; }
    public String getRegion() { return region; }
    public Double getLatitude() { return latitude; }
    public Double getLongitude() { return longitude; }
    public String getHillName() { return hillName; }
}
