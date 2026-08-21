package com.springfix.freshv2.h06.release;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ReleaseFeatures {
    private final boolean metricsEnabled;

    public ReleaseFeatures(@Value("${feature.metrics.enabled:false}") boolean metricsEnabled) {
        this.metricsEnabled = metricsEnabled;
    }

    public boolean metricsEnabled() {
        return metricsEnabled;
    }
}
