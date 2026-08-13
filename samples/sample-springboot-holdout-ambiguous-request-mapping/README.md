# Ambiguous Request Mapping

The web application fails during context startup because two request handlers
claim the same route. The target test observes whether the context starts with
unambiguous mappings.
