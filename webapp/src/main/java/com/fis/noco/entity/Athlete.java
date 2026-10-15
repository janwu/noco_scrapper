package com.fis.noco.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "athletes")
public class Athlete {

    @Id
    @Column(name = "id")
    private Long id;

    @Column(name = "last_name")
    private String lastName;

    @Column(name = "first_name")
    private String firstName;

    @Column(name = "full_name")
    private String fullName;

    @Column(name = "nationality")
    private String nationality;

    @Column(name = "gender")
    private String gender;

    @Column(name = "birth_date")
    private String birthDate;

    @Column(name = "active_club")
    private String activeClub;

    @Column(name = "fis_id")
    private String fisId;

    public Long getId() { return id; }
    public String getLastName() { return lastName; }
    public String getFirstName() { return firstName; }
    /** The name as FIS writes it ('BJOERNSTAD Espen'); stored, searched and matched by. */
    public String getFullName() { return fullName; }

    @Column(name = "display_name")
    private String displayName;

    /** The name to show: with native letters where known ('BJØRNSTAD Espen'), else the FIS name. */
    public String getDisplayName() {
        return displayName != null && !displayName.isBlank() ? displayName : fullName;
    }
    public String getNationality() { return nationality; }
    public String getGender() { return gender; }
    public String getBirthDate() { return birthDate; }
    public String getActiveClub() { return activeClub; }
    public String getFisId() { return fisId; }
}
