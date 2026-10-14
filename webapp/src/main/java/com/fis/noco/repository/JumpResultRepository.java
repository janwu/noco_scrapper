package com.fis.noco.repository;

import com.fis.noco.entity.JumpResult;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface JumpResultRepository extends JpaRepository<JumpResult, Long> {

    /** All jump lists of a competition, ranked rows first, the jumps of an athlete in round order. */
    @Query("SELECT j FROM JumpResult j JOIN FETCH j.document LEFT JOIN FETCH j.athlete " +
           "WHERE j.competition.id = :competitionId " +
           "ORDER BY CASE WHEN j.rank IS NULL THEN 1 ELSE 0 END, j.rank ASC, j.bib ASC, j.roundNumber ASC")
    List<JumpResult> findByCompetitionId(@Param("competitionId") Long competitionId);

    /** An athlete's jumps, newest first; competition and venue are fetched along for the views. */
    @Query("SELECT j FROM JumpResult j JOIN FETCH j.document d JOIN FETCH j.competition c " +
           "LEFT JOIN FETCH c.venue LEFT JOIN FETCH c.season " +
           "WHERE j.athlete.id = :athleteId " +
           "ORDER BY c.competitionDate DESC, d.docType ASC, j.roundNumber ASC")
    List<JumpResult> findByAthleteId(@Param("athleteId") Long athleteId);
}
