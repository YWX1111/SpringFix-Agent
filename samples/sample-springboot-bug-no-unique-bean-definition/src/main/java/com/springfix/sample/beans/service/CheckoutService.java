package com.springfix.sample.beans.service;

import com.springfix.sample.beans.gateway.PaymentGateway;
import org.springframework.stereotype.Service;

/** Service whose constructor cannot choose between two PaymentGateway beans. */
@Service
public class CheckoutService {

    private final PaymentGateway paymentGateway;

    public CheckoutService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    public PaymentGateway paymentGateway() {
        return paymentGateway;
    }
}
