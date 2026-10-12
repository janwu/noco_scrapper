package com.fis.noco.repository;

import com.fis.noco.entity.Athlete;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

@Repository
public interface AthleteRepository extends JpaRepository<Athlete, Long> {

    @Query("SELECT a FROM Athlete a WHERE " +
           "(:query IS NULL OR :query = '' OR LOWER(a.fullName) LIKE LOWER(CONCAT('%', :query, '%')) " +
           "OR LOWER(a.nationality) LIKE LOWER(CONCAT('%', :query, '%')))")
    Page<Athlete> searchAthletes(@Param("query") String query, Pageable pageable);

    @Query("SELECT COUNT(a) FROM Athlete a WHERE " +
           "(:query IS NULL OR :query = '' OR LOWER(a.fullName) LIKE LOWER(CONCAT('%', :query, '%')) " +
           "OR LOWER(a.nationality) LIKE LOWER(CONCAT('%', :query, '%')))")
    long countSearchAthletes(@Param("query") String query);
}
