package com.springfix.freshv2.h01.conditional;

public class RemoteFeatureFlagStore implements FeatureFlagStore {
    @Override
    public boolean enabled(String name) {
        return "new-checkout".equals(name);
    }
}
