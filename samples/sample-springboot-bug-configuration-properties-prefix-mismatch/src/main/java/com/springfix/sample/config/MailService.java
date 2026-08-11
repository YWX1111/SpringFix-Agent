package com.springfix.sample.config;

import org.springframework.stereotype.Service;

/** Consumer retained to make the bound properties part of application code. */
@Service
public class MailService {

    private final MailProperties properties;

    public MailService(MailProperties properties) {
        this.properties = properties;
    }

    public int timeoutSeconds() {
        return properties.getTimeoutSeconds();
    }
}
