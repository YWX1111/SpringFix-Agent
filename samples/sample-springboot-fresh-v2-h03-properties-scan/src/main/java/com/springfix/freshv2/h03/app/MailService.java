package com.springfix.freshv2.h03.app;

import com.springfix.freshv2.h03.settings.MailProperties;
import org.springframework.stereotype.Service;

@Service
public class MailService {
    private final MailProperties properties;

    public MailService(MailProperties properties) {
        this.properties = properties;
    }

    public String relay() {
        return properties.getRelay();
    }
}
