package com.example.concurrent;

import java.util.concurrent.locks.ReentrantLock;

public class InventoryService {

    private final ReentrantLock lock = new ReentrantLock();
    private int stock = 0;

    public void reduceStock(int quantity) {
        lock.lock();
        try {
            if (stock >= quantity) {
                stock -= quantity;
            } else {
                throw new IllegalStateException("Insufficient stock");
            }
        } finally {
            lock.unlock();
        }
    }

    public synchronized int getStock() {
        return stock;
    }
}
