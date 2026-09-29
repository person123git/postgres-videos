---
type: glossary
verified: false
---

# Wiki Glossary (unverified)

## Scope

A glossary link supplies vocabulary, not proof.

## Source Pins

| Version | Checkout | Branch | Pinned commit |
|---|---|---|---|
| 18 | `raw/postgres-18/` | `REL_18_STABLE` | `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb` |

## Terms

### example_size

**Aliases:** `pgstat_example_size`. **Checked on:** PostgreSQL 18.

`example_size` is the setting that sets the byte size of each slot. The default is 1024. It accepts 100 to 1048576 bytes. The setting has context `postmaster`, so a change needs a restart ([guc_tables.c#example_size](../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5-L12)).

### SLRU

**Aliases:** `pg_subtrans`. **Checked on:** PostgreSQL 18.

An SLRU is a small buffer pool ([slru.c:1](../raw/postgres-18/src/backend/access/transam/slru.c#L1)).

### Subtransaction

**Aliases:** `pg_subtrans`. **Checked on:** PostgreSQL 18.

A subtransaction is a transaction inside another ([xact.c:1](../raw/postgres-18/src/backend/access/transam/xact.c#L1)).

### Slot scanner

**Aliases:** `SlotScannerMain`. **Checked on:** PostgreSQL 17, 18.

The slot scanner walks every slot ([scanner.c:1](../raw/postgres-17/src/backend/scanner.c#L1)).

**Version notes:**
- PostgreSQL 18: Not present in PostgreSQL 18 ([Makefile:1](../raw/postgres-18/src/backend/Makefile#L1)).
