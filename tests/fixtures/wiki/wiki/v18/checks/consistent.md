---
type: question
version: 18
pinned_commit: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
verified: false
---

# How example_size Is Used in PostgreSQL 18 (unverified)

## Question

In PostgreSQL 18, how is `example_size` used?

## Short Answer

`example_size` sets the byte size of each slot [guc_tables.c#example_size](../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5-L12). It defaults to `1024` bytes [guc_tables.c#example_size](../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5-L12).

## Details

PostgreSQL 18 has no slot scanner [status.c#slots](../../../raw/postgres-18/src/backend/status.c#L1-L6).

## Source References

- [guc_tables.c](../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c)
- [status.c](../../../raw/postgres-18/src/backend/status.c)
