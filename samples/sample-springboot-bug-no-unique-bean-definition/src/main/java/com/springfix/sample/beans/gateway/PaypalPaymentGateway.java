package com.springfix.sample.beans.gateway;

import org.springframework.stereotype.Component;

/** Second PaymentGateway bean. */
@Component
public class PaypalPaymentGateway implements PaymentGateway {

    @Override
    public void pay() {
        // Deliberately empty: only bean registration matters for this sample.
    }
}
