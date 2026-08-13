package com.springfix.holdout.profilecase;

import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final ProductionCatalog catalog;

    public CatalogService(ProductionCatalog catalog) {
        this.catalog = catalog;
    }

    public String activeCatalog() {
        return catalog.name();
    }
}
