package com.springfix.freshv2.h08.tenant;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.ConfigDataApplicationContextInitializer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class ConfigImportTest {
    @Test
    void contextShouldUseDefaultTenantRegionWhenOverrideIsAbsent() {
        new ApplicationContextRunner()
            .withUserConfiguration(Application.class)
            .withInitializer(new ConfigDataApplicationContextInitializer())
            .run(context -> {
                assertNull(context.getStartupFailure(), "The optional tenant source should not block startup");
                assertEquals("global", context.getBean(TenantService.class).region());
            });
    }
}
