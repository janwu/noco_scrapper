package com.fis.noco.service;

import com.fis.noco.entity.Athlete;
import com.fis.noco.entity.CombinedResult;
import com.fis.noco.repository.AthleteRepository;
import com.fis.noco.repository.CombinedResultRepository;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.Optional;

@Service
@Transactional(readOnly = true)
public class AthleteService {

    private final AthleteRepository athleteRepository;
    private final CombinedResultRepository combinedResultRepository;

    public AthleteService(AthleteRepository athleteRepository,
                          CombinedResultRepository combinedResultRepository) {
        this.athleteRepository = athleteRepository;
        this.combinedResultRepository = combinedResultRepository;
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
