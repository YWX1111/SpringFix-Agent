package com.springfix.sample.transaction;

import com.springfix.sample.transaction.service.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * Gold-standard test: asserts that @Transactional rollback SHOULD have
 * occurred. The assertion fails because {@link OrderService#createOrder()}
 * self-invokes the transactional method, bypassing the AOP proxy.
 *
 * This test is INTENTIONALLY expected to fail when run via `mvn test`.
 * The failure proves the Bug exists. Do NOT "fix" by adding @Transactional
 * to createOrder or by using the injected proxy.
 */
@SpringBootTest
class TransactionSelfInvocationTest {

    @Autowired
    private OrderService orderService;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Test
    void shouldRollbackOrderWhenInnerMethodThrows() {
        jdbcTemplate.execute("DELETE FROM orders");

        assertThrows(RuntimeException.class, () -> orderService.createOrder());

        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM orders",
            Integer.class
        );
        // Expected: 0 (transaction should have rolled back the insert)
        // Actual:   1 (self-invocation bypassed the @Transactional proxy)
        assertEquals(
            0,
            count,
            "Expected rollback but data was persisted; "
                + "self-invocation bypassed the @Transactional AOP proxy"
        );
    }
}
