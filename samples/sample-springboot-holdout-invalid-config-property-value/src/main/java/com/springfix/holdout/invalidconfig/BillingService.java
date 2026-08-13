package com.springfix.holdout.invalidconfig;

import org.springframework.stereotype.Service;

@Service
public class BillingService {
    private final BillingProperties properties;

    public BillingService(BillingProperties properties) {
        this.properties = properties;
    }

    public int retries() {
        return properties.getMaxRetries();
    }
}
