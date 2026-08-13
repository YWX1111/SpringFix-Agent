package com.springfix.holdout.profilecase;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("production")
public class ProductionCatalog {
    public String name() {
        return "production";
    }
}
