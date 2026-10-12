package com.fis.noco.service;

import com.fis.noco.entity.CombinedResult;
import com.fis.noco.entity.Competition;
import com.fis.noco.entity.Season;
import com.fis.noco.repository.CombinedResultRepository;
import com.fis.noco.repository.CompetitionRepository;
import com.fis.noco.repository.SeasonRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import org.springframework.data.domain.PageRequest;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

@Service
@Transactional(readOnly = true)
public class CompetitionService {

    private final CompetitionRepository competitionRepository;
    private final SeasonRepository seasonRepository;
    private final CombinedResultRepository combinedResultRepository;

    public CompetitionService(CompetitionRepository competitionRepository,
                              SeasonRepository seasonRepository,
                              CombinedResultRepository combinedResultRepository) {
        this.competitionRepository = competitionRepository;
        this.seasonRepository = seasonRepository;
        this.combinedResultRepository = combinedResultRepository;
    }

    public List<Season> getAllSeasons() {
        return seasonRepository.findAllByOrderByStartYearDesc();
    }

    public List<Competition> getLatestWCCompetitions(String gender, int limit) {
        return competitionRepository.findLatestWCByGender(gender, PageRequest.of(0, limit));
    }

    public List<Competition> getCompetitionsByCircuitAndSeason(String circuit, Long seasonId) {
        return competitionRepository.findByCircuitAndSeasonId(circuit, seasonId);
    }

    public List<Competition> getCompetitionsByCircuitSeasonAndGender(String circuit, Long seasonId, String gender) {
        if (gender == null || gender.isBlank()) {
            return competitionRepository.findByCircuitAndSeasonId(circuit, seasonId);
        }
        return competitionRepository.findByCircuitAndSeasonIdAndGender(circuit, seasonId, gender);
    }

    public Optional<Competition> findById(Long id) {
        return competitionRepository.findByIdWithDetails(id);
    }

    public List<CombinedResult> getResultsForCompetition(Long competitionId) {
        return combinedResultRepository.findByCompetitionIdOrderByRank(competitionId);
    }

    public long countResultsForCompetition(Long competitionId) {
        return combinedResultRepository.countByCompetitionId(competitionId);
    }

    // Classic FIS table (seasons up to 2022/23): top 30 score
    private static final int[] FIS_POINTS_CLASSIC = {
        100, 80, 60, 50, 45, 40, 36, 32, 29, 26,
         24, 22, 20, 18, 16, 15, 14, 13, 12, 11,
         10,  9,  8,  7,  6,  5,  4,  3,  2,  1
    };

    // New FIS table (seasons 2023/24+): top 40 score
    private static final int[] FIS_POINTS_NEW = {
        100, 90, 80, 70, 60, 55, 52, 49, 46, 43,
         40, 38, 36, 34, 32, 30, 28, 26, 24, 22,
         20, 19, 18, 17, 16, 15, 14, 13, 12, 11,
         10,  9,  8,  7,  6,  5,  4,  3,  2,  1
    };

    private int fisPoints(int rank, int[] table) {
        if (rank < 1 || rank > table.length) return 0;
        return table[rank - 1];
    }

    private int[] pointTableForSeason(Long seasonId) {
        Season season = seasonRepository.findById(seasonId).orElse(null);
        if (season != null && season.getStartYear() != null && season.getStartYear() >= 2023) {
            return FIS_POINTS_NEW;
        }
        return FIS_POINTS_CLASSIC;
    }

    public List<StandingsEntry> getWCStandings(Long seasonId, String gender) {
        List<CombinedResult> results =
                combinedResultRepository.findRankedWCResultsBySeasonAndGender(seasonId, gender);

        int[] pointTable = pointTableForSeason(seasonId);

        Map<Long, StandingsEntry> byAthlete = new LinkedHashMap<>();
        for (CombinedResult r : results) {
            if (r.getAthlete() == null || r.getRank() == null) continue;
            int pts = fisPoints(r.getRank(), pointTable);
            if (pts == 0) continue;
            Long athleteId = r.getAthlete().getId();
            byAthlete.computeIfAbsent(athleteId, id ->
                    new StandingsEntry(id, r.getAthlete().getFullName(), r.getDisplayNation()))
                    .addPoints(r.getCompetition().getId(), pts);
        }

        List<StandingsEntry> sorted = new ArrayList<>(byAthlete.values());
        sorted.sort(Comparator.comparingInt(StandingsEntry::getTotalPoints).reversed()
                .thenComparing(StandingsEntry::getAthleteName));

        for (int i = 0; i < sorted.size(); i++) {
            sorted.get(i).setPosition(i + 1);
        }
        return sorted;
    }

    public List<Competition> getWCIndividualCompetitions(Long seasonId, String gender) {
        return competitionRepository.findWCIndividualBySeasonAndGender(seasonId, gender);
    }
}
