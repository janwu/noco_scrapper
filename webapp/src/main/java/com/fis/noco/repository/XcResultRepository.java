package com.fis.noco.repository;

import com.fis.noco.entity.XcResult;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface XcResultRepository extends JpaRepository<XcResult, Long> {

    /** The race of a mass start, ranked rows first. */
    @Query("SELECT x FROM XcResult x LEFT JOIN FETCH x.athlete WHERE x.competition.id = :competitionId " +
           "ORDER BY CASE WHEN x.rank IS NULL THEN 1 ELSE 0 END, x.rank ASC, x.bib ASC")
    List<XcResult> findByCompetitionId(@Param("competitionId") Long competitionId);
}
