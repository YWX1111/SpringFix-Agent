package com.springfix.holdout.external;

import org.springframework.stereotype.Service;

@Service
public class ReportService {
    public String render() {
        return "report";
    }
}
