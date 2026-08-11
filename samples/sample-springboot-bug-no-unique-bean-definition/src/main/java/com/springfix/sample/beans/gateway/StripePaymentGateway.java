package com.springfix.sample.beans.gateway;

import org.springframework.stereotype.Component;

/** First PaymentGateway bean. */
@Component
public class StripePaymentGateway implements PaymentGateway {

    @Override
    public void pay() {
        // Deliberately empty: only bean registration matters for this sample.
    }
}
