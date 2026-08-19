package com.springfix.dev.s4.alerts;

import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final NotificationSender sender;

    public NotificationService(NotificationSender sender) {
        this.sender = sender;
    }

    public String provider() {
        return sender.provider();
    }
}
