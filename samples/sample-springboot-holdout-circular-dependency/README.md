# Constructor Circular Dependency

The application context fails during startup while constructing two
cooperating services. The target test observes whether the context can start
without the startup failure.
