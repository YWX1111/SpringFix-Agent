package com.springfix.dev.s2.notification;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(NotificationProperties.class)
public class Application {
    static {
        System.setProperty("notification.channel", "legacy");
    }

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
