package com.fis.noco.repository;

import com.fis.noco.entity.CombinedResult;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface CombinedResultRepository extends JpaRepository<CombinedResult, Long> {

    @Query("SELECT r FROM CombinedResult r LEFT JOIN FETCH r.athlete LEFT JOIN FETCH r.competition c " +
           "LEFT JOIN FETCH c.venue LEFT JOIN FETCH c.season " +
           "WHERE r.competition.id = :competitionId " +
           "ORDER BY CASE WHEN r.rank IS NULL THEN 1 ELSE 0 END, r.rank ASC")
    List<CombinedResult> findByCompetitionIdOrderByRank(@Param("competitionId") Long competitionId);

    @Query("SELECT r FROM CombinedResult r LEFT JOIN FETCH r.competition c " +
           "LEFT JOIN FETCH c.venue LEFT JOIN FETCH c.season " +
           "WHERE r.athlete.id = :athleteId AND c.circuit = :circuit " +
           "ORDER BY c.competitionDate DESC")
    List<CombinedResult> findByAthleteIdAndCircuit(@Param("athleteId") Long athleteId,
                                                    @Param("circuit") String circuit);

    /**
     * The field of every competition the athlete took part in:
     * competition id, highest rank, highest jump rank, highest cross-country rank.
     */
    @Query(value = "SELECT r.competition_id, MAX(r.rank), MAX(r.jump_rank), MAX(r.xc_rank) " +
                   "FROM combined_results r WHERE r.competition_id IN " +
                   "(SELECT competition_id FROM combined_results WHERE athlete_id = :athleteId) " +
                   "GROUP BY r.competition_id", nativeQuery = true)
    List<Object[]> findFieldSizesForAthlete(@Param("athleteId") Long athleteId);

    @Query("SELECT COUNT(r) FROM CombinedResult r WHERE r.competition.id = :competitionId")
    long countByCompetitionId(@Param("competitionId") Long competitionId);

    @Query("SELECT r FROM CombinedResult r LEFT JOIN FETCH r.athlete LEFT JOIN FETCH r.competition c " +
           "LEFT JOIN FETCH c.venue " +
           "WHERE c.circuit = :circuit AND c.gender = :gender " +
           "AND c.season.id = :seasonId " +
           "AND r.rank IS NOT NULL " +
           "ORDER BY c.competitionDate ASC, r.rank ASC")
    List<CombinedResult> findRankedResultsBySeason(@Param("seasonId") Long seasonId,
                                                   @Param("circuit") String circuit,
                                                              @Param("gender") String gender);
}
