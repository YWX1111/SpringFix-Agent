package com.springfix.dev.s4.alerts;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(prefix = "alerts", name = "provider", havingValue = "webhook")
public class WebhookNotificationSender implements NotificationSender {
    @Override
    public String provider() {
        return "webhook";
    }
}
