package com.springfix.freshv2.h05.pricing;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class PricingService {
    private final String currency;

    public PricingService(@Value("${pricing.currency}") String currency) {
        this.currency = currency;
    }

    public String currency() {
        return currency;
    }
}
