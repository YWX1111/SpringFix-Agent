package com.example.cache;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class UserCacheService {

    private final CacheManager cacheManager;

    public UserCacheService(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @Cacheable(value = "users", key = "#userId")
    public UserDTO getUserById(Long userId) {
        return fetchFromDatabase(userId);
    }

    @CacheEvict(value = "users", key = "#userId")
    public void invalidateUser(Long userId) {
        cacheManager.getCache("users").evict(userId);
    }

    private UserDTO fetchFromDatabase(Long userId) {
        return new UserDTO(userId, "unknown");
    }
}
