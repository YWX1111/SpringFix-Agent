package com.springfix.freshv2.h08.tenant;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class TenantService {
    private final String region;

    public TenantService(@Value("${tenant.region:global}") String region) {
        this.region = region;
    }

    public String region() {
        return region;
    }
}
