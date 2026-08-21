package com.springfix.freshv2.h02.routing;

import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "routing")
public class RoutingProperties {
    private final Limits limits = new Limits();

    public Limits getLimits() {
        return limits;
    }

    public static class Limits {
        private final List<Zone> zones = List.of();

        public List<Zone> getZones() {
            return zones;
        }
    }

    public static class Zone {
        private String name;
        private String baseUrl;

        public String getName() {
            return name;
        }

        public void setName(String name) {
            this.name = name;
        }

        public String getBaseUrl() {
            return baseUrl;
        }

        public void setBaseUrl(String baseUrl) {
            this.baseUrl = baseUrl;
        }
    }
}
