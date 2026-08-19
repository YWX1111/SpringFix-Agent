package com.springfix.dev.s6.warehouse;

import org.springframework.stereotype.Service;

@Service
public class WarehouseService {
    private final WarehouseProperties properties;

    public WarehouseService(WarehouseProperties properties) {
        this.properties = properties;
    }

    public int retryLimit() {
        return properties.getRetryLimit();
    }
}
