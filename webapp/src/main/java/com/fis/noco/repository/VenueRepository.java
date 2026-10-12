package com.fis.noco.repository;

import com.fis.noco.entity.Venue;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

@Repository
public interface VenueRepository extends JpaRepository<Venue, Long> {

    @Query("SELECT v FROM Venue v WHERE " +
           "(:query IS NULL OR :query = '' OR LOWER(v.name) LIKE LOWER(CONCAT('%', :query, '%')) " +
           "OR LOWER(v.country) LIKE LOWER(CONCAT('%', :query, '%')))")
    Page<Venue> searchVenues(@Param("query") String query, Pageable pageable);

    @Query("SELECT COUNT(v) FROM Venue v WHERE " +
           "(:query IS NULL OR :query = '' OR LOWER(v.name) LIKE LOWER(CONCAT('%', :query, '%')) " +
           "OR LOWER(v.country) LIKE LOWER(CONCAT('%', :query, '%')))")
    long countSearchVenues(@Param("query") String query);
}
