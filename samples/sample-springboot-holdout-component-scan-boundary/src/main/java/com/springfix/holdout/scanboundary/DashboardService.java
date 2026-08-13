package com.springfix.holdout.scanboundary;

import com.springfix.holdout.external.ReportService;
import org.springframework.stereotype.Service;

@Service
public class DashboardService {
    private final ReportService reportService;

    public DashboardService(ReportService reportService) {
        this.reportService = reportService;
    }

    public String dashboard() {
        return reportService.render();
    }
}
