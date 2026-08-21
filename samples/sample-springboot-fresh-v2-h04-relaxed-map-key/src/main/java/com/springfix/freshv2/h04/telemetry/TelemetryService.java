package com.springfix.freshv2.h04.telemetry;

import org.springframework.stereotype.Service;

@Service
public class TelemetryService {
    private final TelemetryProperties properties;

    public TelemetryService(TelemetryProperties properties) {
        this.properties = properties;
    }

    public String header(String name) {
        return properties.getHeaders().get(name);
    }
}
