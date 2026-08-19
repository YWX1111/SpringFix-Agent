package com.springfix.dev.s2.notification;

import org.springframework.stereotype.Service;

@Service
public class NotificationService {
    private final NotificationProperties properties;

    public NotificationService(NotificationProperties properties) {
        this.properties = properties;
    }

    public String channel() {
        return properties.getChannel();
    }
}
