package com.springfix.dev.s3.storage;

import org.springframework.stereotype.Service;

@Service
public class StorageService {
    private final StorageProperties properties;

    public StorageService(StorageProperties properties) {
        this.properties = properties;
    }

    public int maxEntries() {
        return properties.getMaxEntries();
    }
}
