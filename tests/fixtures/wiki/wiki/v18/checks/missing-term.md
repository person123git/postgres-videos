---
type: question
version: 18
pinned_commit: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
verified: false
---

# What Stores the Slots in PostgreSQL 18 (unverified)

## Question

In PostgreSQL 18, what stores the slots?

## Short Answer

`missing_widget` stores every slot [status.c#slots](../../../raw/postgres-18/src/backend/status.c#L1-L6).

## Source References

- [guc_tables.c](../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c)
- [status.c](../../../raw/postgres-18/src/backend/status.c)
