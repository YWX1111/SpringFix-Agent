package com.springfix.freshv2.h01.conditional;

public interface FeatureFlagStore {
    boolean enabled(String name);
}
