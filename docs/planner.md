# Planner

The planner will convert Bubble developer intent into structured, inspectable plans.

Planned flow:

```text
message -> deterministic parser -> context lookup -> structured plan -> semantic validation -> dry-run/apply
```

The planner must work without a paid model provider. Model adapters can improve routing, but deterministic paths and examples should cover common Bubble operations.
