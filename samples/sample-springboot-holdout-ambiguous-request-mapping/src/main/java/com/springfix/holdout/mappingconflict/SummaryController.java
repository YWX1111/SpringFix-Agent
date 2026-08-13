package com.springfix.holdout.mappingconflict;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SummaryController {
    @GetMapping("/api/reports")
    public String summary() {
        return "summary";
    }
}
