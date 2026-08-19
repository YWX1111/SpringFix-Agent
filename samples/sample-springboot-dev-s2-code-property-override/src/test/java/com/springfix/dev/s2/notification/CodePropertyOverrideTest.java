package com.springfix.dev.s2.notification;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CodePropertyOverrideTest {
    @Test
    void applicationCodeShouldNotOverrideConfiguredNotificationChannel() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withInitializer(new ConfigDataApplicationContextInitializer())
            .run(context -> assertEquals(
                "pager",
                context.getBean(NotificationService.class).channel(),
                "The repository configuration must remain the notification channel source"
            ));
    }
}
