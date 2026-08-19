package com.springfix.dev.s5.cache;

import java.time.Duration;
import org.springframework.stereotype.Service;

@Service
public class CacheService {
    private final CacheProperties properties;

    public CacheService(CacheProperties properties) {
        this.properties = properties;
    }

    public Duration ttlFor(String region) {
        return properties.getTtlByRegion().getOrDefault(region, Duration.ZERO);
    }
}
