package com.fis.noco.repository;

import com.fis.noco.entity.TeamResult;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface TeamResultRepository extends JpaRepository<TeamResult, Long> {

    /** Teams of a competition with their athletes, ranked teams first. */
    @Query("SELECT t FROM TeamResult t LEFT JOIN FETCH t.members m LEFT JOIN FETCH m.athlete " +
           "WHERE t.competition.id = :competitionId " +
           "ORDER BY CASE WHEN t.rank IS NULL THEN 1 ELSE 0 END, t.rank ASC, t.bib ASC")
    List<TeamResult> findByCompetitionIdOrderByRank(@Param("competitionId") Long competitionId);

    @Query("SELECT COUNT(t) FROM TeamResult t WHERE t.competition.id = :competitionId")
    long countByCompetitionId(@Param("competitionId") Long competitionId);
}
