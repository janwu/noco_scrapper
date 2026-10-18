package com.fis.noco.service;

import com.fis.noco.entity.Competition;
import com.fis.noco.entity.Venue;
import com.fis.noco.repository.CompetitionRepository;
import com.fis.noco.repository.VenueRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

@Service
@Transactional(readOnly = true)
public class VenueService {

    private final VenueRepository venueRepository;
    private final CompetitionRepository competitionRepository;

    public VenueService(VenueRepository venueRepository,
                        CompetitionRepository competitionRepository) {
        this.venueRepository = venueRepository;
        this.competitionRepository = competitionRepository;
    }

    public Page<Venue> searchVenues(String query, int page, int pageSize) {
        String q = (query == null || query.isBlank()) ? "" : NameFolding.toFis(query.trim());
        PageRequest pageRequest = PageRequest.of(page, pageSize, Sort.by("name").ascending());
        return venueRepository.searchVenues(q, pageRequest);
    }

    public long countVenues(String query) {
        String q = (query == null || query.isBlank()) ? "" : NameFolding.toFis(query.trim());
        return venueRepository.countSearchVenues(q);
    }

    public Optional<Venue> findById(Long id) {
        return venueRepository.findById(id);
    }

    public long countCompetitionsAtVenue(Long venueId) {
        return competitionRepository.countByVenueId(venueId);
    }

    public List<Competition> getWorldCupCompetitionsAtVenue(Long venueId) {
        return competitionRepository.findByVenueIdAndCircuit(venueId, "WC");
    }

    public List<Competition> getContinentalCupCompetitionsAtVenue(Long venueId) {
        return competitionRepository.findByVenueIdAndCircuit(venueId, "COC");
    }

    public List<Competition> getChampionshipCompetitionsAtVenue(Long venueId) {
        return competitionRepository.findByVenueIdAndCircuit(venueId, "WSC");
    }
}
