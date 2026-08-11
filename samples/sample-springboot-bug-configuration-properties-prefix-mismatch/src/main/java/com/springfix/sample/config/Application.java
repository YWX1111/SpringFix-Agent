package com.springfix.sample.config;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

/** Spring Boot entrypoint for the configuration binding sample. */
@SpringBootApplication
@EnableConfigurationProperties(MailProperties.class)
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
