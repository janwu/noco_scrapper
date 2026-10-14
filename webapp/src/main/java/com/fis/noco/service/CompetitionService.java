package com.fis.noco.service;

import com.fis.noco.entity.Athlete;
import com.fis.noco.entity.CombinedResult;
import com.fis.noco.entity.CupStanding;
import com.fis.noco.entity.Competition;
import com.fis.noco.entity.JumpResult;
import com.fis.noco.entity.Season;
import com.fis.noco.entity.TeamResult;
import com.fis.noco.repository.CombinedResultRepository;
import com.fis.noco.repository.CompetitionRepository;
import com.fis.noco.repository.CupStandingRepository;
import com.fis.noco.repository.JumpResultRepository;
import com.fis.noco.repository.SeasonRepository;
import com.fis.noco.repository.TeamResultRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import org.springframework.data.domain.PageRequest;

import java.time.LocalDate;
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
    private final TeamResultRepository teamResultRepository;
    private final CupStandingRepository cupStandingRepository;
    private final JumpResultRepository jumpResultRepository;

    public CompetitionService(CompetitionRepository competitionRepository,
                              SeasonRepository seasonRepository,
                              CombinedResultRepository combinedResultRepository,
                              TeamResultRepository teamResultRepository,
                              CupStandingRepository cupStandingRepository,
                              JumpResultRepository jumpResultRepository) {
        this.jumpResultRepository = jumpResultRepository;
        this.cupStandingRepository = cupStandingRepository;
        this.competitionRepository = competitionRepository;
        this.seasonRepository = seasonRepository;
        this.combinedResultRepository = combinedResultRepository;
        this.teamResultRepository = teamResultRepository;
    }

    /**
     * The jump lists of a competition by kind, in the order of JumpResult.LIST_ORDER
     * (competition round, trial round, qualification, provisional round, training);
     * only those that exist.
     */
    public Map<String, List<JumpResult>> getJumpLists(Long competitionId) {
        Map<String, List<JumpResult>> lists = new LinkedHashMap<>();
        for (String label : JumpResult.LIST_ORDER) {
            lists.put(label, new ArrayList<>());
        }
        for (JumpResult j : jumpResultRepository.findByCompetitionId(competitionId)) {
            lists.get(j.getListLabel()).add(j);
        }
        lists.values().removeIf(List::isEmpty);
        competitionRepository.findByIdWithDetails(competitionId).ifPresent(c -> addEventLists(c, lists));
        return lists;
    }

    /** Kinds of lists a competition shares with the others on the same hill at the same event. */
    private static final List<String> SHARED_LISTS = List.of("Provisional Round", "Training");

    /**
     * FIS files the official training under the codex of the provisional
     * competition round, the day before the competition, and in early seasons
     * under the first competition of the weekend.  A competition without its own
     * training or provisional round gets those of the nearest competition on the
     * same hill at the same event: same venue and circuit, hill size equal or
     * unknown, matching gender, the same day or up to three days before.  The
     * label carries the date: 'Training · 2025-11-28'.
     */
    private void addEventLists(Competition c, Map<String, List<JumpResult>> lists) {
        if (c.getVenue() == null || c.getCompetitionDate() == null) return;
        LocalDate day = LocalDate.parse(c.getCompetitionDate());
        List<Competition> candidates = competitionRepository.findAtVenueBetween(
                c.getVenue().getId(), c.getCircuit(), day.minusDays(3).toString(), day.toString());
        for (String kind : SHARED_LISTS) {
            if (lists.containsKey(kind)) continue;
            for (Competition other : candidates) {               // nearest first
                if (other.getId().equals(c.getId()) || !sameHill(c, other)) continue;
                List<JumpResult> rows = jumpResultRepository.findByCompetitionId(other.getId()).stream()
                        .filter(j -> kind.equals(j.getListLabel())).toList();
                if (!rows.isEmpty()) {
                    lists.put(kind + " · " + other.getCompetitionDate(), rows);
                    break;
                }
            }
        }
        // keep the order of LIST_ORDER for the borrowed lists too
        Map<String, List<JumpResult>> ordered = new LinkedHashMap<>();
        for (String kind : JumpResult.LIST_ORDER) {
            lists.forEach((label, rows) -> { if (label.equals(kind) || label.startsWith(kind + " · ")) ordered.put(label, rows); });
        }
        lists.clear();
        lists.putAll(ordered);
    }

    private static boolean sameHill(Competition a, Competition b) {
        boolean hill = a.getHillSizeM() == null || b.getHillSizeM() == null
                || Math.abs(a.getHillSizeM() - b.getHillSizeM()) < 0.5;
        boolean gender = a.getGender() == null || b.getGender() == null || a.getGender().equals(b.getGender())
                || "X".equals(a.getGender()) || "X".equals(b.getGender());
        return hill && gender;
    }

    /** Team, Team Sprint and Mixed Team competitions are stored as teams, not as single athletes. */
    public static boolean isTeamFormat(String format) {
        return format != null && format.startsWith("Team");
    }

    /**
     * Mass Start and Super Sprint: the race comes first and is converted into points,
     * the jump decides.  Their gaps are points, not times.
     */
    public static boolean isJumpLast(String format) {
        return "Mass Start".equals(format) || "Super Sprint".equals(format);
    }

    public List<TeamResult> getTeamResultsForCompetition(Long competitionId) {
        return teamResultRepository.findByCompetitionIdOrderByRank(competitionId);
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

    /** Number of result rows: athletes in an individual competition, teams in a team competition. */
    public long countResultsForCompetition(Long competitionId) {
        long athletes = combinedResultRepository.countByCompetitionId(competitionId);
        return athletes > 0 ? athletes : teamResultRepository.countByCompetitionId(competitionId);
    }

    /**
     * The rankings FIS publishes for a season: [code, name], overall ("ALL") first,
     * then the trophies of that season (Sprint, Compact, Best Jumper, ...).
     */
    public List<String[]> getRankingsOfSeason(Long seasonId, String circuit, String gender) {
        List<String[]> rankings = new ArrayList<>();
        for (Object[] row : cupStandingRepository.findRankingsOfSeason(seasonId, circuit, gender)) {
            rankings.add(new String[]{(String) row[0], row[1] != null ? (String) row[1] : (String) row[0]});
        }
        rankings.sort(Comparator.comparing((String[] r) -> !"ALL".equals(r[0])).thenComparing(r -> r[1]));
        return rankings;
    }

    /**
     * An official FIS standing.  Ranks and points are FIS's own — the points rules
     * changed over the years and tours score differently, so they are not recomputed
     * here.  Each entry also carries the athlete's rank in every individual
     * competition of the season.
     */
    public List<StandingsEntry> getStandings(Long seasonId, String circuit, String gender, String discipline) {
        Map<Long, StandingsEntry> byAthlete = new LinkedHashMap<>();
        List<StandingsEntry> entries = new ArrayList<>();
        for (CupStanding s : cupStandingRepository.findRanking(seasonId, circuit, gender, discipline)) {
            Athlete athlete = s.getAthlete();
            StandingsEntry entry = new StandingsEntry(
                    s.getRank(),
                    athlete != null ? athlete.getId() : null,
                    athlete != null ? athlete.getFullName() : s.getRawName(),
                    s.getRawNation(),
                    s.getPoints());
            entries.add(entry);
            if (athlete != null) {
                byAthlete.put(athlete.getId(), entry);
            }
        }
        for (CombinedResult r : combinedResultRepository.findRankedResultsBySeason(seasonId, circuit, gender)) {
            if (r.getAthlete() == null) continue;
            StandingsEntry entry = byAthlete.get(r.getAthlete().getId());
            if (entry != null) {
                entry.setRank(r.getCompetition().getId(), r.getRank());
            }
        }
        return entries;
    }

    public List<Competition> getIndividualCompetitions(Long seasonId, String circuit, String gender) {
        return competitionRepository.findIndividualBySeason(seasonId, circuit, gender);
    }
}
