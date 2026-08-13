package com.springfix.holdout.circularcase;

import org.springframework.stereotype.Service;

@Service
public class ReceiptCoordinator {
    private final CheckoutCoordinator checkoutCoordinator;

    public ReceiptCoordinator(CheckoutCoordinator checkoutCoordinator) {
        this.checkoutCoordinator = checkoutCoordinator;
    }

    public String receipt() {
        return checkoutCoordinator.getClass().getSimpleName();
    }
}
