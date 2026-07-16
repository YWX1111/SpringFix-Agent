package com.springfix.sample.transaction;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Spring Boot entrypoint for the transaction-self-invocation sample.
 * This application exists only to back the test; it is not run by the
 * SpringFix Agent itself.
 */
@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
