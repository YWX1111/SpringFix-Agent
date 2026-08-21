package com.springfix.freshv2.h01.conditional;

public class FeatureFlagMetrics {
    private final FeatureFlagStore store;

    FeatureFlagMetrics(FeatureFlagStore store) {
        this.store = store;
    }

    public boolean reportsNewCheckout() {
        return store.enabled("new-checkout");
    }
}
