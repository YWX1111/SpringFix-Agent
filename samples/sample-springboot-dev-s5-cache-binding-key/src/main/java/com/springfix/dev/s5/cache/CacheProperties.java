package com.springfix.dev.s5.cache;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "cache")
public class CacheProperties {
    private Map<String, Duration> ttlByRegion = new LinkedHashMap<>();

    public Map<String, Duration> getTtlByRegion() {
        return ttlByRegion;
    }

    public void setTtlByRegion(Map<String, Duration> ttlByRegion) {
        this.ttlByRegion = ttlByRegion;
    }
}
