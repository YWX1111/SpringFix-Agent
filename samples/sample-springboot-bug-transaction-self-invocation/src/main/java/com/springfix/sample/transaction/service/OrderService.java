package com.springfix.sample.transaction.service;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

/**
 * OrderService reproduces the @Transactional self-invocation bug.
 *
 * The external entry point {@link #createOrder()} is NOT annotated
 * with @Transactional. It calls {@link #createOrderInTransaction()}
 * directly via {@code this}, which bypasses the Spring AOP proxy. As a
 * result the {@code @Transactional} on the inner method has no effect:
 * the insert is committed despite the thrown RuntimeException.
 */
@Service
public class OrderService {

    private final JdbcTemplate jdbcTemplate;

    @Autowired
    public OrderService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    /**
     * External entry point. Intentionally NOT @Transactional so that
     * callers cannot rely on a transaction being active for this call.
     */
    public void createOrder() {
        // Direct self-invocation — bypasses Spring AOP proxy.
        createOrderInTransaction();
    }

    @Transactional
    public void createOrderInTransaction() {
        jdbcTemplate.update(
            "INSERT INTO orders (id, customer, amount) VALUES (?, ?, ?)",
            1L, "alice", 100
        );
        throw new RuntimeException("simulated failure: should trigger rollback");
    }
}
