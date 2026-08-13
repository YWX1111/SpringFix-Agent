package com.springfix.holdout.transactionvisibility;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final JdbcTemplate jdbcTemplate;

    public OrderService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public void createOrder() {
        persistOrder();
    }

    @Transactional
    private void persistOrder() {
        jdbcTemplate.update("insert into orders(description) values (?)", "holdout");
        throw new IllegalStateException("simulated failure after insert");
    }
}
