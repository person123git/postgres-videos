---
type: question
version: 18
pinned_commit: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
verified: false
---

# Where Parent Links Are Recorded in PostgreSQL 18 (unverified)

## Question

In PostgreSQL 18, where are parent links recorded?

## Short Answer

`pg_subtrans` records parents [status.c#slots](../../../raw/postgres-18/src/backend/status.c#L1-L6).

## Source References

- [guc_tables.c](../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c)
- [status.c](../../../raw/postgres-18/src/backend/status.c)
