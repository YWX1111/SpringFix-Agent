package com.springfix.dev.s1.shipping;

import org.springframework.stereotype.Service;

@Service
public class ShippingService {
    private final ShippingProperties properties;

    public ShippingService(ShippingProperties properties) {
        this.properties = properties;
    }

    public String endpoint() {
        return properties.getEndpoint();
    }
}
