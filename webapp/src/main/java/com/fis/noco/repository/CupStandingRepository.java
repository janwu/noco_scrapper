package com.fis.noco.repository;

import com.fis.noco.entity.CupStanding;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface CupStandingRepository extends JpaRepository<CupStanding, Long> {

    /** One ranking of a season, best first, with the athletes loaded. */
    @Query("SELECT s FROM CupStanding s LEFT JOIN FETCH s.athlete " +
           "WHERE s.season.id = :seasonId AND s.circuit = :circuit AND s.gender = :gender " +
           "AND s.disciplineCode = :discipline " +
           "ORDER BY s.rank ASC, s.rawName ASC")
    List<CupStanding> findRanking(@Param("seasonId") Long seasonId,
                                  @Param("circuit") String circuit,
                                  @Param("gender") String gender,
                                  @Param("discipline") String discipline);

    /** The overall World Cup / Continental Cup standing of an athlete in a season, if FIS lists one. */
    @Query("SELECT s FROM CupStanding s WHERE s.athlete.id = :athleteId AND s.season.id = :seasonId " +
           "AND s.circuit = :circuit AND s.disciplineCode = 'ALL'")
    List<CupStanding> findOverall(@Param("athleteId") Long athleteId, @Param("seasonId") Long seasonId,
                                  @Param("circuit") String circuit);

    /** The rankings that exist for a season: [code, name] — 'ALL' = overall, plus the trophies. */
    @Query("SELECT DISTINCT s.disciplineCode, s.disciplineName FROM CupStanding s " +
           "WHERE s.season.id = :seasonId AND s.circuit = :circuit AND s.gender = :gender")
    List<Object[]> findRankingsOfSeason(@Param("seasonId") Long seasonId,
                                        @Param("circuit") String circuit,
                                        @Param("gender") String gender);
}
