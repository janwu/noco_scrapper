package com.fis.noco.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "seasons")
public class Season {

    @Id
    @Column(name = "id")
    private Long id;

    @Column(name = "start_year")
    private Integer startYear;

    @Column(name = "label")
    private String label;

    public Long getId() { return id; }
    public Integer getStartYear() { return startYear; }
    public String getLabel() { return label; }

    @Override
    public String toString() { return label != null ? label : String.valueOf(startYear); }
}
