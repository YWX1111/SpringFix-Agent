package com.springfix.holdout.circularcase;

import org.springframework.stereotype.Service;

@Service
public class CheckoutCoordinator {
    private final ReceiptCoordinator receiptCoordinator;

    public CheckoutCoordinator(ReceiptCoordinator receiptCoordinator) {
        this.receiptCoordinator = receiptCoordinator;
    }

    public String checkout() {
        return receiptCoordinator.receipt();
    }
}
