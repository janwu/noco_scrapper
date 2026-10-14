package com.fis.noco.service;

import com.fis.noco.entity.Athlete;
import com.fis.noco.entity.CombinedResult;
import com.fis.noco.entity.JumpResult;
import com.fis.noco.entity.TeamMember;
import com.fis.noco.repository.AthleteRepository;
import com.fis.noco.repository.CombinedResultRepository;
import com.fis.noco.repository.JumpResultRepository;
import com.fis.noco.repository.TeamResultRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
@Transactional(readOnly = true)
public class AthleteService {

    private final AthleteRepository athleteRepository;
    private final CombinedResultRepository combinedResultRepository;
    private final TeamResultRepository teamResultRepository;
    private final JumpResultRepository jumpResultRepository;

    public AthleteService(AthleteRepository athleteRepository,
                          CombinedResultRepository combinedResultRepository,
                          TeamResultRepository teamResultRepository,
                          JumpResultRepository jumpResultRepository) {
        this.jumpResultRepository = jumpResultRepository;
        this.athleteRepository = athleteRepository;
        this.combinedResultRepository = combinedResultRepository;
        this.teamResultRepository = teamResultRepository;
    }

    /**
     * Results by venue, favourite hills and courses (see {@link AthleteProfile}),
     * over both circuits; {@link AthleteProfile#forCircuit} narrows it down.
     */
    public AthleteProfile getProfile(Long athleteId) {
        Map<Long, Integer[]> fields = new HashMap<>();
        for (Object[] row : combinedResultRepository.findFieldSizesForAthlete(athleteId)) {
            fields.put(((Number) row[0]).longValue(),
                    new Integer[]{toInt(row[1]), toInt(row[2]), toInt(row[3])});
        }
        List<AthleteProfile.RatedResult> rated = new ArrayList<>();
        for (String circuit : List.of("WC", "COC")) {
            for (CombinedResult r : combinedResultRepository.findByAthleteIdAndCircuit(athleteId, circuit)) {
                Integer[] f = fields.getOrDefault(r.getCompetition().getId(), new Integer[3]);
                rated.add(new AthleteProfile.RatedResult(r, f[0], f[1], f[2]));
            }
        }
        return new AthleteProfile(rated, getTeamStarts(athleteId), getJumps(athleteId));
    }

    private static Integer toInt(Object value) {
        return value == null ? null : ((Number) value).intValue();
    }

    /** All jumps of the athlete (competition rounds, qualifications, provisional rounds), newest first. */
    public List<JumpResult> getJumps(Long athleteId) {
        return jumpResultRepository.findByAthleteId(athleteId);
    }

    /** Team, Team Sprint and Mixed Team starts in both circuits, newest first. */
    public List<TeamMember> getTeamStarts(Long athleteId) {
        return teamResultRepository.findTeamStartsByAthleteId(athleteId);
    }

    public Page<Athlete> searchAthletes(String query, int page, int pageSize) {
        String q = (query == null || query.isBlank()) ? "" : query.trim();
        PageRequest pageRequest = PageRequest.of(page, pageSize, Sort.by("fullName").ascending());
        return athleteRepository.searchAthletes(q, pageRequest);
    }

    public long countAthletes(String query) {
        String q = (query == null || query.isBlank()) ? "" : query.trim();
        return athleteRepository.countSearchAthletes(q);
    }

    public Optional<Athlete> findById(Long id) {
        return athleteRepository.findById(id);
    }

    public List<CombinedResult> getWorldCupResults(Long athleteId) {
        return combinedResultRepository.findByAthleteIdAndCircuit(athleteId, "WC");
    }

    public List<CombinedResult> getContinentalCupResults(Long athleteId) {
        return combinedResultRepository.findByAthleteIdAndCircuit(athleteId, "COC");
    }
}
