package com.fis.noco.repository;

import com.fis.noco.entity.Season;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface SeasonRepository extends JpaRepository<Season, Long> {

    List<Season> findAllByOrderByStartYearDesc();

    /** The seasons with a competition of the circuit, newest first. */
    @Query("SELECT s FROM Season s WHERE EXISTS (SELECT 1 FROM Competition c WHERE c.season = s " +
           "AND c.circuit = :circuit) ORDER BY s.startYear DESC")
    List<Season> findByCircuit(@Param("circuit") String circuit);
}
