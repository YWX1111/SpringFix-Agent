# Transaction Proxy Visibility

An order operation throws after writing to the database, but the transaction
boundary is not effective for the annotated method. The target test observes
whether the failed operation leaves the database unchanged.
