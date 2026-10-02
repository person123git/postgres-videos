---
type: question
version: 18
pinned_commit: baa7b142aace6821ce085906f314a75bcc4d95c8
verified: false
verified_by_agent: not yet
---

# How Custom Cumulative Statistics Work in PostgreSQL 18 (unverified)

## Question

> Follow AGENTS.md.
> In PostgreSQL 18, how do custom cumulative statistics work?

## Answer Up Front

PostgreSQL 18 lets a C extension register a new cumulative-statistics kind by
supplying a `PgStat_KindInfo` descriptor and a custom `PgStat_Kind` ID in the
custom range, then calling `pgstat_register_kind` while the extension is being
loaded from `shared_preload_libraries`
([pgstat_kind.h](../../../../raw/postgres-18/src/include/utils/pgstat_kind.h),
[pgstat_internal.h#PgStat_KindInfo](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L202),
[pgstat.c#pgstat_register_kind](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1465)).
`shared_preload_libraries` has `PGC_POSTMASTER` context in v18, so changing it
requires a server restart
([guc_tables.c](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c),
[config.sgml#guc-shared-preload-libraries](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L11004)).

The extension then chooses one of two shapes. A variable-numbered kind stores
one shared entry per object key in the pgstat dynamic shared-memory hash table,
usually merging backend-local pending counters during `pgstat_report_stat`
([pgstat.c#pgstat_report_stat](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L693),
[pgstat.c#pgstat_prep_pending_entry](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1267),
[pgstat_shmem.c#pgstat_get_entry_ref](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L457)).
A fixed-numbered kind stores its shared state in the `custom_data[]` slots of
`PgStat_ShmemControl`, with extension-provided callbacks for shared-memory
initialization, reset, and snapshot construction
([pgstat_internal.h#PgStat_ShmemControl](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L466),
[pgstat_shmem.c#StatsShmemSize](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L127),
[pgstat_shmem.c#StatsShmemInit](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L155)).

The core system provides storage, locking, flushing, snapshot consistency, reset
and persistence mechanics; the extension owns the event-specific counters and
the SQL functions or views that expose them
([pgstat.c](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c),
[injection_stats.c](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats.c),
[injection_stats_fixed.c](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats_fixed.c),
[injection_points--1.0.sql](../../../../raw/postgres-18/src/test/modules/injection_points/injection_points--1.0.sql)).

## Core Types

`PgStat_Kind` is a `uint32`; v18 reserves built-in kind IDs `1..12` and custom
kind IDs `24..32`, with `PGSTAT_KIND_EXPERIMENTAL` defined as custom ID `24`
for extensions that have not reserved a final ID
([pgstat_kind.h](../../../../raw/postgres-18/src/include/utils/pgstat_kind.h)).

`PgStat_KindInfo` is the per-kind contract. It says whether the kind has a
fixed number of objects, whether other databases can read it, whether it is
written to the stats file, how large its shared and pending records are, where
the serializable stats payload starts, and which callbacks implement flushing,
resetting, snapshots, backend initialization, and name serialization
([pgstat_internal.h#PgStat_KindInfo](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L202)).

The common shared entry header for variable-numbered stats is
`PgStatShared_Common`; it carries a magic value and an LWLock that protects the
kind-specific data following the header
([pgstat_internal.h#PgStatShared_Common](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L121)).
The shared hash key is `(kind, dboid, objid)`, so a custom variable-numbered
kind must be addressable by a database OID plus one 64-bit object identifier
while the server is running
([pgstat_internal.h#PgStat_HashKey](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L52),
[pgstat.c](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c)).

## Registration

`pgstat_register_kind` rejects an empty name, rejects IDs outside the custom
range, rejects calls not made while `process_shared_preload_libraries` is in
progress, rejects a fixed-numbered kind with no `shared_size`, and rejects
duplicate custom IDs or duplicate names
([pgstat.c#pgstat_register_kind](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1465)).
The injection-points test module shows the intended extension boundary: `_PG_init`
returns unless shared-preload processing is active, defines a postmaster-context
GUC, and registers both custom pgstat kinds from `_PG_init`
([injection_points.c#_PG_init](../../../../raw/postgres-18/src/test/modules/injection_points/injection_points.c#L542)).

Startup order explains the restriction. The postmaster processes preload
libraries before shared-memory requests and before shared memory is initialized;
then `StatsShmemSize` includes any registered custom fixed-numbered stats, and
`StatsShmemInit` allocates and initializes their slots
([postmaster.c#PostmasterMain](../../../../raw/postgres-18/src/backend/postmaster/postmaster.c#L494),
[ipci.c#CalculateShmemSize](../../../../raw/postgres-18/src/backend/storage/ipc/ipci.c#L89),
[ipci.c#CreateSharedMemoryAndSemaphores](../../../../raw/postgres-18/src/backend/storage/ipc/ipci.c#L200),
[pgstat_shmem.c#StatsShmemSize](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L127),
[pgstat_shmem.c#StatsShmemInit](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L155)).

Each backend attaches to pgstat shared memory during `BaseInit`; `pgstat_initialize`
also allocates custom fixed-stat snapshot buffers and runs any per-kind
`init_backend_cb`
([postinit.c#BaseInit](../../../../raw/postgres-18/src/backend/utils/init/postinit.c#L612),
[pgstat.c#pgstat_initialize](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L640),
[pgstat.c#pgstat_init_snapshot_fixed](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1082)).

## Variable-Numbered Custom Stats

A variable-numbered kind that uses the normal pending-entry path sets
`.fixed_amount = false`, gives the shared entry size, data offset, data length,
pending size, and a `flush_pending_cb`
([injection_stats.c](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats.c),
[pgstat_internal.h#PgStat_KindInfo](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L202)).
The injection-points example registers kind `25` named `injection_points`,
uses a hash of the injection-point name as the `objid`, stores entries under
`InvalidOid`, marks them accessible across databases, and writes them to the
stats file
([injection_stats.c](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats.c)).

For a kind that uses pending entries, the normal reporting path is local first.
A reporter calls
`pgstat_prep_pending_entry`, which gets or creates the shared entry, allocates a
pending buffer of `pending_size`, and links the entry onto the backend-local
pending list
([pgstat.c#pgstat_prep_pending_entry](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1267),
[pgstat_shmem.c#pgstat_get_entry_ref](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L457)).
The injection-points reporter then updates only its pending data on the hot
path by incrementing `pending->numcalls`
([injection_stats.c#pgstat_report_inj](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats.c#L164)).

`pgstat_report_stat` later walks pending entries and calls each kind's
`flush_pending_cb`; on a non-forced flush, the callback may decline to wait for
the entry lock, leaving the pending data queued for a later flush
([pgstat.c#pgstat_report_stat](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L693),
[pgstat.c#pgstat_flush_pending_entries](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1341)).
The injection-point flush callback locks the shared entry, adds local `numcalls`
to shared `numcalls`, unlocks, and returns success
([injection_stats.c#injection_stats_flush_cb](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats.c#L71)).

Dropping a variable-numbered custom entry uses the same shared-hash lifetime
rules as built-in variable stats, but the extension entry point is now
`pgstat_drop_entry_ext(kind, dboid, objid, missing_ok)`. `pgstat_drop_entry()`
survives only as an ABI-preserving wrapper that passes `missing_ok = false`,
because the v15 signature had no such argument
([pgstat_shmem.c#pgstat_drop_entry](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L974-L983),
[pgstat_shmem.c#pgstat_drop_entry_ext](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L985-L1000),
[pgstat_internal.h#pgstat_drop_entry_ext](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L712-L713)).

`pgstat_drop_entry_ext()` releases the calling backend's local reference, then
`pgstat_drop_entry_internal` marks the shared entry `dropped` and decrements its
refcount; if the refcount reaches zero the entry is freed immediately and the
call returns `true`, otherwise it returns `false` and the caller is responsible
for calling `pgstat_request_entry_refs_gc` so other backends release their
cached refs
([pgstat_shmem.c#pgstat_drop_entry_internal](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L891-L906),
[pgstat_shmem.c#pgstat_request_entry_refs_gc](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L739)).

The `missing_ok` argument decides what happens when the shared entry has already
been marked `dropped`. With `missing_ok = false` — the wrapper's behavior — the
call raises `ERROR "trying to drop stats entry already dropped: ..."`; with
`missing_ok = true` it releases the dshash lock and returns `true`. That error no
longer lives in `pgstat_drop_entry_internal()`, which now only `Assert`s that the
entry is not already dropped
([pgstat_shmem.c#missing_ok-branch](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L1025-L1040),
[pgstat_shmem.c#pgstat_drop_entry_internal](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L891-L906)).
The in-tree injection-points example follows that contract with the `_ext` form
directly, passing `missing_ok = false`
([injection_stats.c#pgstat_drop_inj](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats.c#L146-L155)).

Entry creation has a related fix. When `pgstat_init_entry()` cannot allocate the
entry's shared data, `pgstat_get_entry_ref()` now releases the local reference
*before* deleting the shared hashtable entry, because releasing the dshash lock
can process a pending interrupt
([pgstat_shmem.c#pgstat_get_entry_ref-OOM](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L525-L537)).

## Fixed-Numbered Custom Stats

A fixed-numbered kind sets `.fixed_amount = true`, provides a `shared_size`,
data offset and data length, and supplies fixed-stat callbacks such as
`init_shmem_cb`, `reset_all_cb`, and `snapshot_cb`
([pgstat_internal.h#PgStat_KindInfo](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L202),
[injection_stats_fixed.c](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats_fixed.c)).
`StatsShmemSize` adds the `shared_size` of each registered custom fixed kind,
and `StatsShmemInit` assigns a slot in `PgStat_ShmemControl.custom_data[]` before
calling that kind's `init_shmem_cb`
([pgstat_shmem.c#StatsShmemSize](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L127),
[pgstat_shmem.c#StatsShmemInit](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L155),
[pgstat_internal.h#PgStat_ShmemControl](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L466)).

The fixed injection-points example registers kind `26` named
`injection_points_fixed`; its shared struct has its own LWLock, a changecount,
current stats, and reset-offset stats
([injection_stats_fixed.c](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats_fixed.c)).
Its reporter writes shared counters directly under the kind's lock and wraps the
counter changes in the pgstat changecount helpers
([injection_stats_fixed.c#pgstat_report_inj_fixed](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats_fixed.c#L141),
[pgstat_internal.h#pgstat_begin_changecount_write](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L800),
[pgstat_internal.h#pgstat_end_changecount_write](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L810)).

Its reset callback copies current stats into `reset_offset` and updates the
reset timestamp; its snapshot callback copies current stats into the backend's
custom snapshot buffer and subtracts the reset offsets
([injection_stats_fixed.c#injection_stats_fixed_reset_all_cb](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats_fixed.c#L82),
[injection_stats_fixed.c#injection_stats_fixed_snapshot_cb](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats_fixed.c#L97)).

## Reading And SQL Exposure

Core pgstat does not automatically create SQL views for a custom kind. The
extension exposes SQL-callable functions in its extension script, as the
injection-points module does for `injection_points_stats_numcalls`,
`injection_points_stats_drop`, and `injection_points_stats_fixed`
([injection_points--1.0.sql](../../../../raw/postgres-18/src/test/modules/injection_points/injection_points--1.0.sql)).

Variable-numbered readers call `pgstat_fetch_entry`, which honors the current
`stats_fetch_consistency` mode, optionally reads from a backend snapshot cache,
locks the shared entry in shared mode, and copies the kind's data payload length
into caller memory or the snapshot context
([pgstat.c#pgstat_fetch_entry](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L933)).
Full snapshots include entries for the current database, entries with
`InvalidOid`, and entries whose kind has `.accessed_across_databases = true`
([pgstat.c#pgstat_build_snapshot](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1122)).

Fixed-numbered readers call `pgstat_snapshot_fixed` and then read the backend's
custom snapshot buffer through `pgstat_get_custom_snapshot_data`
([pgstat.c#pgstat_snapshot_fixed](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1062),
[pgstat_internal.h#pgstat_get_custom_snapshot_data](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L935)).
The fixed injection-points SQL function follows that pattern before building a
five-column record
([injection_stats_fixed.c#injection_points_stats_fixed](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats_fixed.c#L173)).

`stats_fetch_consistency` has `PGC_USERSET` context in v18, so choosing
`none`, `cache`, or `snapshot` is a session or transaction-scope choice rather
than a restart or reload setting
([guc_tables.c](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c),
[pgstat.c#assign_stats_fetch_consistency](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L2067)).

## Reset And Existence Checks

`pgstat_reset` resets one variable-numbered entry by locking it and zeroing the
kind data; `pgstat_reset_of_kind` calls the fixed kind's `reset_all_cb` for
fixed-numbered stats and scans/reset entries for variable-numbered stats
([pgstat.c#pgstat_reset](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L853),
[pgstat.c#pgstat_reset_of_kind](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L875),
[pgstat_shmem.c#pgstat_reset_entry](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L1125),
[pgstat_shmem.c#shared_stat_reset_contents](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L1109)).
`pg_stat_reset_shared` exposes named reset targets only for built-in shared
stats, while `pg_stat_reset` scans and resets entries whose `dboid` is the
current database; the injection-points test extension supplies its own SQL drop
function for its `InvalidOid` variable-numbered custom entries
([pgstatfuncs.c#pg_stat_reset_shared](../../../../raw/postgres-18/src/backend/utils/adt/pgstatfuncs.c#L1884),
[pgstatfuncs.c#pg_stat_reset](../../../../raw/postgres-18/src/backend/utils/adt/pgstatfuncs.c#L1870),
[pgstat.c#pgstat_reset_counters](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L834),
[injection_stats.c#injection_points_stats_drop](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats.c#L211)).

`pg_stat_have_stats` is an undocumented test helper that maps a textual kind
name through `pgstat_get_kind_from_str`; that lookup checks built-in names first
and then registered custom names
([pgstatfuncs.c#pg_stat_have_stats](../../../../raw/postgres-18/src/backend/utils/adt/pgstatfuncs.c#L2264),
[pgstat.c#pgstat_get_kind_from_str](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1403)).
For existence, fixed-numbered stats always report true, while variable-numbered
stats report whether a shared entry currently exists
([pgstat.c#pgstat_have_entry](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1046)).

## Persistence

Stats are written to `pg_stat/pgstat.stat` only during normal shutdown after
pending stats are force-flushed, and only for kinds whose `PgStat_KindInfo`
sets `.write_to_file = true`
([pgstat.h](../../../../raw/postgres-18/src/include/pgstat.h),
[pgstat.c#pgstat_before_server_shutdown](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L561),
[pgstat.c#pgstat_write_statsfile](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1570)).
Fixed entries are serialized as a kind ID plus their data payload; variable
entries are serialized either by `PgStat_HashKey` or by a custom serialized name
callback
([pgstat.c#pgstat_write_statsfile](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1570),
[pgstat_internal.h#PgStat_KindInfo](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L202)).

On startup without crash recovery, PostgreSQL reads the stats file, recreates
fixed custom stats in their `custom_data[]` slots, recreates variable entries in
the shared hash table, and removes the file after reading it
([xlog.c#StartupXLOG](../../../../raw/postgres-18/src/backend/access/transam/xlog.c#L5467),
[pgstat.c#pgstat_read_statsfile](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1754)).
On crash recovery, PostgreSQL discards pgstat data instead of restoring it
([xlog.c#StartupXLOG](../../../../raw/postgres-18/src/backend/access/transam/xlog.c#L5467),
[pgstat.c#pgstat_discard_stats](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L518)).

The injection-points TAP test verifies both cases for custom stats: after a
clean restart, variable and fixed custom stats are still visible; after an
immediate stop and restart, the variable value is absent and the fixed counters
are zero
([001_stats.pl](../../../../raw/postgres-18/src/test/modules/injection_points/t/001_stats.pl)).

## Context Reviewed

- Registration, kind lookup, pending flush, snapshots, stats-file persistence:
  [pgstat.c](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c).
- Shared memory, shared-hash entries, locks, drops, resets:
  [pgstat_shmem.c](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c).
- Kind IDs, internal kind contract, fixed custom data helpers:
  [pgstat_kind.h](../../../../raw/postgres-18/src/include/utils/pgstat_kind.h),
  [pgstat_internal.h](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h).
- Extension example and tests:
  [injection_stats.c](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats.c),
  [injection_stats_fixed.c](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats_fixed.c),
  [injection_points.c](../../../../raw/postgres-18/src/test/modules/injection_points/injection_points.c),
  [injection_points.h](../../../../raw/postgres-18/src/test/modules/injection_points/injection_points.h)
  (new in the 18.4/18.6 range: `20a4b06a1ea` moved shared structs out of
  `injection_points.c` into this header),
  [001_stats.pl](../../../../raw/postgres-18/src/test/modules/injection_points/t/001_stats.pl).

## Evidence Map

| Claim | Source |
|---|---|
| Custom kind IDs are `24..32`; experimental ID is `24` | [pgstat_kind.h](../../../../raw/postgres-18/src/include/utils/pgstat_kind.h) |
| `PgStat_KindInfo` defines storage shape, offsets, persistence, and callbacks | [pgstat_internal.h#PgStat_KindInfo](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L202) |
| Registration must happen during `shared_preload_libraries` processing | [pgstat.c#pgstat_register_kind](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1465) |
| `shared_preload_libraries` changes require restart | [guc_tables.c](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c), [config.sgml#guc-shared-preload-libraries](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L11004) |
| Variable custom stats use pending entries and flush callbacks | [pgstat.c#pgstat_prep_pending_entry](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1267), [pgstat.c#pgstat_flush_pending_entries](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1341) |
| Fixed custom stats use `PgStat_ShmemControl.custom_data[]` | [pgstat_internal.h#PgStat_ShmemControl](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L466), [pgstat_shmem.c#StatsShmemInit](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L155) |
| Readers use `pgstat_fetch_entry` or `pgstat_snapshot_fixed` | [pgstat.c#pgstat_fetch_entry](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L933), [pgstat.c#pgstat_snapshot_fixed](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1062) |
| Clean shutdown persists writeable kinds; crash recovery discards stats | [pgstat.c#pgstat_before_server_shutdown](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L561), [xlog.c#StartupXLOG](../../../../raw/postgres-18/src/backend/access/transam/xlog.c#L5467) |
| Injection-points tests cover custom stats persistence and crash discard | [001_stats.pl](../../../../raw/postgres-18/src/test/modules/injection_points/t/001_stats.pl) |

## Source References

- [pgstat_kind.h](../../../../raw/postgres-18/src/include/utils/pgstat_kind.h) - built-in and custom kind ID ranges, including `PGSTAT_KIND_EXPERIMENTAL`.
- [pgstat_internal.h#PgStat_KindInfo](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L202) - custom kind descriptor contract.
- [pgstat_internal.h#PgStat_ShmemControl](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L466) - custom fixed-stat shared memory slots.
- [pgstat_internal.h#pgstat_get_custom_shmem_data](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L920), [pgstat_internal.h#pgstat_get_custom_snapshot_data](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L935) - fixed custom helper accessors.
- [pgstat.c#pgstat_register_kind](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1465) - custom registration validation and storage.
- [pgstat.c#pgstat_report_stat](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L693), [pgstat.c#pgstat_prep_pending_entry](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1267), [pgstat.c#pgstat_flush_pending_entries](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1341) - pending-update lifecycle.
- [pgstat.c#pgstat_fetch_entry](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L933), [pgstat.c#pgstat_snapshot_fixed](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1062), [pgstat.c#pgstat_build_snapshot](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1122) - read and snapshot behavior.
- [pgstat.c#pgstat_before_server_shutdown](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L561), [pgstat.c#pgstat_write_statsfile](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1570), [pgstat.c#pgstat_read_statsfile](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1754), [pgstat.c#pgstat_discard_stats](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L518) - stats-file persistence and discard.
- [pgstat_shmem.c#StatsShmemSize](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L127), [pgstat_shmem.c#StatsShmemInit](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L155), [pgstat_shmem.c#pgstat_get_entry_ref](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L457), [pgstat_shmem.c#pgstat_drop_entry_ext](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_shmem.c#L985-L1000) - shared memory and shared-entry mechanics.
- [postmaster.c#PostmasterMain](../../../../raw/postgres-18/src/backend/postmaster/postmaster.c#L494), [ipci.c#CalculateShmemSize](../../../../raw/postgres-18/src/backend/storage/ipc/ipci.c#L89), [ipci.c#CreateSharedMemoryAndSemaphores](../../../../raw/postgres-18/src/backend/storage/ipc/ipci.c#L200), [postinit.c#BaseInit](../../../../raw/postgres-18/src/backend/utils/init/postinit.c#L612) - startup and backend initialization boundaries.
- [injection_stats.c](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats.c), [injection_stats_fixed.c](../../../../raw/postgres-18/src/test/modules/injection_points/injection_stats_fixed.c), [injection_points.c#_PG_init](../../../../raw/postgres-18/src/test/modules/injection_points/injection_points.c#L542), [injection_points.h](../../../../raw/postgres-18/src/test/modules/injection_points/injection_points.h), [injection_points--1.0.sql](../../../../raw/postgres-18/src/test/modules/injection_points/injection_points--1.0.sql), [001_stats.pl](../../../../raw/postgres-18/src/test/modules/injection_points/t/001_stats.pl) - custom variable and fixed examples plus tests.
- [pgstatfuncs.c#pg_stat_have_stats](../../../../raw/postgres-18/src/backend/utils/adt/pgstatfuncs.c#L2264), [pgstat.c#pgstat_get_kind_from_str](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1403), [pgstat.c#pgstat_have_entry](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1046) - kind-name lookup and existence helper behavior.
- [guc_tables.c](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c), [config.sgml#guc-shared-preload-libraries](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L11004) - GUC contexts used in this page.
- [xfunc.sgml#xfunc-addin-custom-cumulative-statistics](../../../../raw/postgres-18/doc/src/sgml/xfunc.sgml#L3960) - documentation section checked against implementation.

## Open Questions

- The v18 documentation snippet declares `pgstat_register_kind` as returning
  `PgStat_Kind`, but the implementation and internal header declare it as
  returning `void`; this page follows the implementation source
  ([xfunc.sgml#xfunc-addin-custom-cumulative-statistics](../../../../raw/postgres-18/doc/src/sgml/xfunc.sgml#L3960),
  [pgstat_internal.h#pgstat_register_kind](../../../../raw/postgres-18/src/include/utils/pgstat_internal.h#L584),
  [pgstat.c#pgstat_register_kind](../../../../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1465)).
- This page explains existing PostgreSQL 18 behavior. It does not reserve a
  custom stats ID or design a new extension-specific counter layout.
