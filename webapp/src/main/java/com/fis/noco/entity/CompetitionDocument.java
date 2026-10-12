package com.fis.noco.entity;

import jakarta.persistence.*;

@Entity
@Table(name = "competition_documents")
public class CompetitionDocument {

    @Id
    @Column(name = "id")
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "competition_id")
    private Competition competition;

    @Column(name = "doc_type")
    private String docType;

    @Column(name = "format_era")
    private String formatEra;

    @Column(name = "source_file")
    private String sourceFile;

    @Column(name = "fis_report_code")
    private String fisReportCode;

    @Column(name = "report_created")
    private String reportCreated;

    @Column(name = "start_time")
    private String startTime;

    @Column(name = "end_time")
    private String endTime;

    @Column(name = "parse_warnings")
    private String parseWarnings;

    @Column(name = "parsed_at")
    private String parsedAt;

    public Long getId() { return id; }
    public Competition getCompetition() { return competition; }
    public String getDocType() { return docType; }
    public String getFormatEra() { return formatEra; }
    public String getSourceFile() { return sourceFile; }
    public String getFisReportCode() { return fisReportCode; }
    public String getReportCreated() { return reportCreated; }
    public String getStartTime() { return startTime; }
    public String getEndTime() { return endTime; }
    public String getParseWarnings() { return parseWarnings; }
    public String getParsedAt() { return parsedAt; }
}
