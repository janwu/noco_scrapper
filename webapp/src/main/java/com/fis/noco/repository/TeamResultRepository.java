package com.fis.noco.repository;

import com.fis.noco.entity.TeamMember;
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

    /**
     * An athlete's team starts, newest first.  Team, competition and team-mates are
     * fetched along, because the views read them after the transaction has ended.
     */
    @Query("SELECT m FROM TeamMember m JOIN FETCH m.teamResult t JOIN FETCH t.competition c " +
           "LEFT JOIN FETCH c.venue LEFT JOIN FETCH c.season " +
           "LEFT JOIN FETCH t.members mate LEFT JOIN FETCH mate.athlete " +
           "WHERE m.athlete.id = :athleteId " +
           "ORDER BY c.competitionDate DESC")
    List<TeamMember> findTeamStartsByAthleteId(@Param("athleteId") Long athleteId);

    @Query("SELECT COUNT(t) FROM TeamResult t WHERE t.competition.id = :competitionId")
    long countByCompetitionId(@Param("competitionId") Long competitionId);
}
