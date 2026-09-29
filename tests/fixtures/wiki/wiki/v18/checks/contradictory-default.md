---
type: question
version: 18
pinned_commit: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
verified: false
---

# The Default of example_size in PostgreSQL 18 (unverified)

## Question

In PostgreSQL 18, what is the default of `example_size`?

## Short Answer

The `example_size` setting defaults to 2048 bytes [status.c#slots](../../../raw/postgres-18/src/backend/status.c#L1-L6).

## Source References

- [status.c](../../../raw/postgres-18/src/backend/status.c)
