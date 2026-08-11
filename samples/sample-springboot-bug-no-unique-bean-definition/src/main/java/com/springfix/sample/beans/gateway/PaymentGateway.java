package com.springfix.sample.beans.gateway;

/** Payment provider abstraction with intentionally ambiguous implementations. */
public interface PaymentGateway {

    void pay();
}
