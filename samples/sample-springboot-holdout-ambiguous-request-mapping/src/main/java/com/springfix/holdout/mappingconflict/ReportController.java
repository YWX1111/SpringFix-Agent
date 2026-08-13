package com.springfix.holdout.mappingconflict;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {
    @GetMapping("/api/reports")
    public String report() {
        return "report";
    }
}
