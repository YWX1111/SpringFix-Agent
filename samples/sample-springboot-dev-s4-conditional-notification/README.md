# DEV-S4: Environment-conditional Bean

Development-only construction notes. The service requires a notification
sender, while the only implementation is conditional on a provider value.
The visible runtime configuration selects a different provider, so the target
test observes a missing conditional Bean.
