package com.fis.noco.service;

import com.fis.noco.entity.CombinedResult;
import com.fis.noco.entity.Competition;
import com.fis.noco.entity.JumpResult;
import com.fis.noco.entity.TeamMember;
import com.fis.noco.entity.Venue;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalDouble;
import java.util.function.Function;
import java.util.stream.Collectors;

/**
 * Where an athlete does well: results by venue, and the hills and cross-country
 * courses where he or she does better than usual.
 *
 * <p>A rank says little on its own: 10th of 30 is weaker than 10th of 60.  Every
 * jump rank and cross-country rank (the rank of the race time, not the finish
 * position) is therefore turned into the share of the field beaten,
 * {@code 1 - (rank - 1) / (field - 1)}: 100 % for the best, 0 % for the last.
 * A hill (venue and hill size) or course (venue) is rated by the mean share there
 * minus the athlete's mean share over all competitions in the same selection:
 * +15 pp means 15 percentage points more of the field beaten than usual.  Only
 * places with at least {@value #MIN_COMPETITIONS} competitions are rated.</p>
 */
public final class AthleteProfile {

    public static final int MIN_COMPETITIONS = 3;

    /** Results of the athlete at one venue. */
    public record VenueStats(Venue venue, String label, int starts, int individualStarts, int wins, int podiums,
                             int top10, Integer bestRank, Double meanRank, Double jumpDelta, Double xcDelta) {
    }

    /** A hill or a cross-country course and how the athlete does there compared with the rest of the career. */
    public record PlaceRating(String label, String country, int competitions, double share, double delta,
                              double meanRank, Integer bestRank) {
    }

    /** An individual result together with the size of its field (ranked athletes, jumpers, skiers). */
    public record RatedResult(CombinedResult result, Integer field, Integer jumpField, Integer xcField) {

        Competition competition() {
            return result.getCompetition();
        }

        Double jumpShare() {
            return share(result.getJumpRank(), jumpField);
        }

        Double xcShare() {
            return share(result.getXcRank(), xcField);
        }

        private static Double share(Integer rank, Integer field) {
            if (rank == null || field == null || field < 2) return null;
            return 1.0 - (rank - 1.0) / (field - 1.0);
        }
    }

    private final List<RatedResult> results;
    private final List<TeamMember> teamStarts;
    private final List<JumpResult> jumps;

    public AthleteProfile(List<RatedResult> results, List<TeamMember> teamStarts, List<JumpResult> jumps) {
        this.results = results;
        this.teamStarts = teamStarts;
        this.jumps = jumps;
    }

    /** The same profile restricted to one circuit ("WC", "COC"); null keeps all. */
    public AthleteProfile forCircuit(String circuit) {
        if (circuit == null) return this;
        return new AthleteProfile(
                results.stream().filter(r -> circuit.equals(r.competition().getCircuit())).toList(),
                teamStarts.stream().filter(m -> circuit.equals(m.getTeamResult().getCompetition().getCircuit())).toList(),
                jumps.stream().filter(j -> circuit.equals(j.getCompetition().getCircuit())).toList());
    }

    // ── highlights ─────────────────────────────────────────────────────────

    /** The best individual rank, the earliest of equal ones. */
    public Optional<CombinedResult> bestResult() {
        return results.stream().map(RatedResult::result).filter(r -> r.getRank() != null)
                .min(Comparator.comparing(CombinedResult::getRank)
                        .thenComparing(r -> r.getCompetition().getCompetitionDate(), Comparator.nullsLast(Comparator.naturalOrder())));
    }

    /** All individual results with the best rank, earliest first. */
    public List<CombinedResult> bestResults() {
        return bestResult().map(best -> results.stream().map(RatedResult::result)
                        .filter(r -> best.getRank().equals(r.getRank()))
                        .sorted(Comparator.comparing(r -> r.getCompetition().getCompetitionDate(),
                                Comparator.nullsLast(Comparator.naturalOrder())))
                        .toList())
                .orElse(List.of());
    }

    /** The longest jump in the World Cup, in any jump list (competition round, qualification, provisional round). */
    public Optional<JumpResult> longestWorldCupJump() {
        return jumps.stream()
                .filter(j -> j.getDistanceM() != null && "WC".equals(j.getCompetition().getCircuit()))
                .max(Comparator.comparing(JumpResult::getDistanceM));
    }

    /** The venue with the most podiums (then wins, top 10, mean rank). */
    public Optional<VenueStats> mostSuccessfulVenue() {
        return venues().stream()
                .filter(v -> v.top10() > 0)
                .max(Comparator.comparingInt(VenueStats::podiums)
                        .thenComparingInt(VenueStats::wins)
                        .thenComparingInt(VenueStats::top10)
                        .thenComparing(v -> -Objects.requireNonNullElse(v.meanRank(), 999.0)));
    }

    /** The venue with the most starts, individual and team. */
    public Optional<VenueStats> mostVisitedVenue() {
        return venues().stream().max(Comparator.comparingInt(VenueStats::starts)
                .thenComparingInt(VenueStats::podiums));
    }

    // ── venues ─────────────────────────────────────────────────────────────

    /** All venues of the athlete, most starts first. */
    public List<VenueStats> venues() {
        double jumpCareer = mean(results, RatedResult::jumpShare).orElse(Double.NaN);
        double xcCareer = mean(results, RatedResult::xcShare).orElse(Double.NaN);

        Map<Long, List<RatedResult>> byVenue = results.stream()
                .filter(r -> r.competition().getVenue() != null)
                .collect(Collectors.groupingBy(r -> r.competition().getVenue().getId(), LinkedHashMap::new, Collectors.toList()));
        Map<Long, Long> teamByVenue = teamStarts.stream()
                .map(m -> m.getTeamResult().getCompetition().getVenue())
                .filter(Objects::nonNull)
                .collect(Collectors.groupingBy(Venue::getId, Collectors.counting()));
        Map<Long, Venue> venues = new LinkedHashMap<>();
        results.forEach(r -> { if (r.competition().getVenue() != null) venues.put(r.competition().getVenue().getId(), r.competition().getVenue()); });
        teamStarts.forEach(m -> { Venue v = m.getTeamResult().getCompetition().getVenue(); if (v != null) venues.put(v.getId(), v); });

        List<VenueStats> stats = new ArrayList<>();
        for (Venue venue : venues.values()) {
            List<RatedResult> here = byVenue.getOrDefault(venue.getId(), List.of());
            List<Integer> ranks = here.stream().map(r -> r.result().getRank()).filter(Objects::nonNull).toList();
            int team = teamByVenue.getOrDefault(venue.getId(), 0L).intValue();
            stats.add(new VenueStats(venue, venue.getDisplayName(), here.size() + team, here.size(),
                    (int) ranks.stream().filter(r -> r == 1).count(),
                    (int) ranks.stream().filter(r -> r <= 3).count(),
                    (int) ranks.stream().filter(r -> r <= 10).count(),
                    ranks.stream().min(Integer::compare).orElse(null),
                    ranks.isEmpty() ? null : ranks.stream().mapToInt(Integer::intValue).average().orElse(0),
                    delta(here, RatedResult::jumpShare, jumpCareer),
                    delta(here, RatedResult::xcShare, xcCareer)));
        }
        stats.sort(Comparator.comparingInt(VenueStats::starts).reversed()
                .thenComparing(VenueStats::label, Comparator.nullsLast(Comparator.naturalOrder())));
        return stats;
    }

    // ── favourite hills and courses ────────────────────────────────────────

    /** Hills (venue + hill size) rated by the jump; best first. */
    public List<PlaceRating> favouriteHills() {
        return rate(r -> r.competition().getVenue() == null ? null
                        : r.competition().getVenue().getId() + "/" + hillSize(r.competition()),
                r -> r.competition().getDisplayLocation() + " " + hillLabel(r.competition()),
                RatedResult::jumpShare, r -> r.result().getJumpRank());
    }

    /** Cross-country courses (venue) rated by the rank of the race time; best first. */
    public List<PlaceRating> favouriteCourses() {
        return rate(r -> r.competition().getVenue() == null ? null : String.valueOf(r.competition().getVenue().getId()),
                r -> r.competition().getDisplayLocation(),
                RatedResult::xcShare, r -> r.result().getXcRank());
    }

    /** The athlete's mean share of the field beaten in the jump and in the race. */
    public OptionalDouble careerJumpShare() {
        return mean(results, RatedResult::jumpShare);
    }

    public OptionalDouble careerXcShare() {
        return mean(results, RatedResult::xcShare);
    }

    private List<PlaceRating> rate(Function<RatedResult, String> key, Function<RatedResult, String> label,
                                   Function<RatedResult, Double> share, Function<RatedResult, Integer> rank) {
        OptionalDouble career = mean(results, share);
        if (career.isEmpty()) return List.of();
        Map<String, List<RatedResult>> groups = results.stream()
                .filter(r -> share.apply(r) != null && key.apply(r) != null)
                .collect(Collectors.groupingBy(key, LinkedHashMap::new, Collectors.toList()));
        List<PlaceRating> ratings = new ArrayList<>();
        for (List<RatedResult> group : groups.values()) {
            if (group.size() < MIN_COMPETITIONS) continue;
            double here = mean(group, share).orElseThrow();
            RatedResult first = group.get(0);
            ratings.add(new PlaceRating(label.apply(first), first.competition().getDisplayCountry(), group.size(),
                    here, here - career.getAsDouble(),
                    group.stream().map(rank).filter(Objects::nonNull).mapToInt(Integer::intValue).average().orElse(0),
                    group.stream().map(rank).filter(Objects::nonNull).min(Integer::compare).orElse(null)));
        }
        ratings.sort(Comparator.comparingDouble(PlaceRating::delta).reversed());
        return ratings;
    }

    private static Double delta(List<RatedResult> rows, Function<RatedResult, Double> share, double career) {
        if (Double.isNaN(career)) return null;
        List<Double> values = rows.stream().map(share).filter(Objects::nonNull).toList();
        if (values.size() < MIN_COMPETITIONS) return null;
        return values.stream().mapToDouble(Double::doubleValue).average().orElse(0) - career;
    }

    private static OptionalDouble mean(List<RatedResult> rows, Function<RatedResult, Double> share) {
        return rows.stream().map(share).filter(Objects::nonNull).mapToDouble(Double::doubleValue).average();
    }

    private static String hillSize(Competition c) {
        return c.getHillSizeM() == null ? "?" : String.valueOf(Math.round(c.getHillSizeM()));
    }

    public static String hillLabel(Competition c) {
        return c.getHillSizeM() == null ? "(hill size unknown)" : "HS" + Math.round(c.getHillSizeM());
    }
}
