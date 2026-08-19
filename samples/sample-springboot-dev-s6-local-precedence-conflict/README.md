# DEV-S6: Configuration precedence conflict

Development-only construction notes. The base configuration is valid, but the
active local profile contributes a higher-precedence value for the same key.
The target test exercises the effective runtime source and expects the context
to start with a valid retry limit.
