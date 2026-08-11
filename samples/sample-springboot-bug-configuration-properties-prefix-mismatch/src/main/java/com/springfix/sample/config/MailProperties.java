package com.springfix.sample.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

/** Configuration object whose declared prefix intentionally disagrees with YAML. */
@ConfigurationProperties(prefix = "springfix.mail")
public class MailProperties {

    private int timeoutSeconds;

    public int getTimeoutSeconds() {
        return timeoutSeconds;
    }

    public void setTimeoutSeconds(int timeoutSeconds) {
        this.timeoutSeconds = timeoutSeconds;
    }
}
