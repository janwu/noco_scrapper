package com.fis.noco.repository;

import com.fis.noco.entity.Competition;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface CompetitionRepository extends JpaRepository<Competition, Long> {

    /**
     * Overviews leave out the provisional competition round: it has a codex of its own
     * but is a jumping round without a result list.
     */
    String LISTED = "AND (c.format IS NULL OR c.format <> 'Provisional Round') ";

    @Query("SELECT c FROM Competition c LEFT JOIN FETCH c.season LEFT JOIN FETCH c.venue " +
           "WHERE c.circuit = :circuit AND c.season.id = :seasonId " + LISTED +
           "ORDER BY c.competitionDate ASC")
    List<Competition> findByCircuitAndSeasonId(@Param("circuit") String circuit,
                                               @Param("seasonId") Long seasonId);

    @Query("SELECT c FROM Competition c LEFT JOIN FETCH c.season LEFT JOIN FETCH c.venue " +
           "WHERE c.circuit = :circuit AND c.season.id = :seasonId AND c.gender = :gender " + LISTED +
           "ORDER BY c.competitionDate ASC")
    List<Competition> findByCircuitAndSeasonIdAndGender(@Param("circuit") String circuit,
                                                        @Param("seasonId") Long seasonId,
                                                        @Param("gender") String gender);

    @Query("SELECT c FROM Competition c LEFT JOIN FETCH c.season LEFT JOIN FETCH c.venue " +
           "WHERE c.circuit = 'WC' AND c.gender = :gender " + LISTED +
           "ORDER BY c.competitionDate DESC")
    List<Competition> findLatestWCByGender(@Param("gender") String gender,
                                           org.springframework.data.domain.Pageable pageable);

    @Query("SELECT c FROM Competition c LEFT JOIN FETCH c.season LEFT JOIN FETCH c.venue " +
           "WHERE c.venue.id = :venueId AND c.circuit = :circuit " + LISTED +
           "ORDER BY c.competitionDate DESC")
    List<Competition> findByVenueIdAndCircuit(@Param("venueId") Long venueId,
                                              @Param("circuit") String circuit);

    @Query("SELECT COUNT(c) FROM Competition c WHERE c.venue.id = :venueId " + LISTED)
    long countByVenueId(@Param("venueId") Long venueId);

    @Query("SELECT c FROM Competition c LEFT JOIN FETCH c.season LEFT JOIN FETCH c.venue " +
           "WHERE c.id = :id")
    java.util.Optional<Competition> findByIdWithDetails(@Param("id") Long id);

    @Query("SELECT c FROM Competition c LEFT JOIN FETCH c.season LEFT JOIN FETCH c.venue " +
           "WHERE c.circuit = 'WC' AND c.gender = :gender AND c.season.id = :seasonId " +
           "AND c.format IN ('Gundersen', 'Compact', 'Mass Start', 'Sprint', 'Penalty Race') " +
           "ORDER BY c.competitionDate ASC")
    List<Competition> findWCIndividualBySeasonAndGender(@Param("seasonId") Long seasonId,
                                                        @Param("gender") String gender);
}
