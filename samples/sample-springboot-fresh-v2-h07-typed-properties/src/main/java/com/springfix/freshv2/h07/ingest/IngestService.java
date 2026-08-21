package com.springfix.freshv2.h07.ingest;

import org.springframework.stereotype.Service;

@Service
public class IngestService {
    private final IngestProperties properties;

    public IngestService(IngestProperties properties) {
        this.properties = properties;
    }

    public int recipientCount() {
        return properties.getRecipients().size();
    }
}
