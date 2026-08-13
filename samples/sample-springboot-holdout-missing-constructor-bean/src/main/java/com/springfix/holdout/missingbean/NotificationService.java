package com.springfix.holdout.missingbean;

import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final AuditClient auditClient;

    public NotificationService(AuditClient auditClient) {
        this.auditClient = auditClient;
    }

    public void notify(String message) {
        auditClient.record(message);
    }
}
