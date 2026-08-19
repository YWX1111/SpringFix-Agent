# DEV-S2: Explicit property override in application code

Development-only construction notes. The application class contains an
explicit property mutation that has higher precedence than the repository
configuration. The target test observes the channel consumed by the service;
the repair must remove the code-level override or make it agree with the
visible configuration contract.
