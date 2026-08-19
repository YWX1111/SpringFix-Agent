# DEV-S5: Property name and binding-path mismatch

Development-only construction notes. The properties class exposes a nested
map of Duration values. The repository contains the intended region value, but
its key does not match the Java binding path, so the runtime consumer receives
its empty-map default.
