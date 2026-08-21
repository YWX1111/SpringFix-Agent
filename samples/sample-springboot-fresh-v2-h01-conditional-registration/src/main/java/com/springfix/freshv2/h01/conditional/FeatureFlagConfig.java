package com.springfix.freshv2.h01.conditional;

import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class FeatureFlagConfig {
    @Bean
    FeatureFlagStore featureFlagStore() {
        return new RemoteFeatureFlagStore();
    }

    @Bean
    @ConditionalOnBean(RemoteFeatureFlagStore.class)
    FeatureFlagMetrics featureFlagMetrics(FeatureFlagStore store) {
        return new FeatureFlagMetrics(store);
    }
}
