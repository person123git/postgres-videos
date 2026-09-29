---
type: question
version: 18
pinned_commit: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
verified: false
---

# Where the Slot Table Lives in PostgreSQL 18 (unverified)

## Question

In PostgreSQL 18, where does the slot table live?

## Short Answer

`example_size` sets the byte size of each slot [guc_tables.c#example_size](../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5-L12). The slot table is in [status.c#table](../../../raw/postgres-18/src/backend/status.c#L1-L99) and [missing.c#table](../../../raw/postgres-18/src/backend/missing.c#L1).

## Source References

- [guc_tables.c](../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c)
- [status.c](../../../raw/postgres-18/src/backend/status.c)
