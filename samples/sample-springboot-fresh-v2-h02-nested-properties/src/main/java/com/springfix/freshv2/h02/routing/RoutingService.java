package com.springfix.freshv2.h02.routing;

import org.springframework.stereotype.Service;

@Service
public class RoutingService {
    private final RoutingProperties properties;

    public RoutingService(RoutingProperties properties) {
        this.properties = properties;
    }

    public String firstZoneUrl() {
        return properties.getLimits().getZones().get(0).getBaseUrl();
    }
}
