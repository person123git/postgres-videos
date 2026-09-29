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

The `example_size` setting defaults to 2048 bytes [guc_tables.c#example_size](../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5-L12).

## Source References

- [guc_tables.c](../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c)
- [status.c](../../../raw/postgres-18/src/backend/status.c)
