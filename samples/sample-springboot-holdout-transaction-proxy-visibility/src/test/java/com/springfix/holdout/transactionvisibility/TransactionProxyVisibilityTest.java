package com.springfix.holdout.transactionvisibility;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class TransactionProxyVisibilityTest {
    @Autowired
    private OrderService orderService;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void failedOperationShouldRollbackInsertedOrder() {
        assertThrows(IllegalStateException.class, orderService::createOrder);
        Integer rows = jdbcTemplate.queryForObject("select count(*) from orders", Integer.class);
        assertEquals(0, rows, "Expected rollback, but the private transactional method committed");
    }
}
