---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# The I/O Consequences of Changing a Column From integer to bigint in PostgreSQL 17, Whether a Very Large Table Needs a Migration Strategy, and What Changed Since PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Short answer](#short-answer)
  - [Why the change always rewrites the table](#why-the-change-always-rewrites-the-table)
  - [What the statement does, phase by phase](#what-the-statement-does-phase-by-phase)
  - [The locks it takes, and for how long](#the-locks-it-takes-and-for-how-long)
  - [Read side: the old heap once, then the new heap once per index](#read-side-the-old-heap-once-then-the-new-heap-once-per-index)
  - [Write side: a second copy of everything, and WAL for all of it](#write-side-a-second-copy-of-everything-and-wal-for-all-of-it)
  - [Disk space: two copies until commit](#disk-space-two-copies-until-commit)
  - [TOAST is rewritten too](#toast-is-rewritten-too)
  - [Foreign keys: the referencing table is rescanned](#foreign-keys-the-referencing-table-is-rescanned)
  - [Does the table get bigger? Column order decides, not the column](#does-the-table-get-bigger-column-order-decides-not-the-column)
  - [Indexes are rebuilt, and a reuse test exists but cannot help here](#indexes-are-rebuilt-and-a-reuse-test-exists-but-cannot-help-here)
  - [What the rewrite leaves behind](#what-the-rewrite-leaves-behind)
  - [There is no progress view and no throttle](#there-is-no-progress-view-and-no-throttle)
  - [What refuses to run at all](#what-refuses-to-run-at-all)
  - [The control case: what a no-rewrite type change costs](#the-control-case-what-a-no-rewrite-type-change-costs)
  - [Is a migration strategy needed for a very large table?](#is-a-migration-strategy-needed-for-a-very-large-table)
  - [Settings that affect the rewrite, with apply scope](#settings-that-affect-the-rewrite-with-apply-scope)
  - [Test coverage in the pinned tree](#test-coverage-in-the-pinned-tree)
  - [What changed since PostgreSQL 12](#what-changed-since-postgresql-12)
- [Measurement Script](#measurement-script)
  - [PostgreSQL 17.11 leg](#postgresql-1711-leg)
  - [PostgreSQL 12.2 leg](#postgresql-122-leg)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Follow `AGENTS.md`. In PostgreSQL 17, question: what are the I/O consequences of changing a column from `integer` to `bigint`? What happens, and is a migration strategy needed if the table is very large? What has changed since PostgreSQL 12?

## Answer

### Short answer

`ALTER TABLE t ALTER COLUMN c TYPE bigint` rewrites the whole table and rebuilds every
index on it, inside one transaction that holds `AccessExclusiveLock` from the first
statement to commit. The I/O is not proportional to how many rows change - all of them
are rewritten - and it is not proportional to the 4 bytes per row either. It is:

| Cost | Size |
|---|---|
| Reads | the old heap once, plus the new heap once per index, plus the whole TOAST table if any value is stored out of line |
| Writes | a second copy of the heap, of every index, and of the TOAST table |
| WAL | roughly the size of everything written, because the copy emits one `XLOG_HEAP_INSERT` per row |
| Disk high-water mark | old plus new, together, until commit |
| Lock | `AccessExclusiveLock` on the table for the whole duration, plus `AccessExclusiveLock` on every table whose constraints have to be rebuilt |

Measured on an isolated 17.11 server, a 208,642,048-byte table with 4,000,000 rows and
two indexes totalling 118,243,328 bytes: **72,413 blocks read**, **427,512,848 bytes of
WAL**, a **327,442,432-byte** rise in the data directory that is given back at commit,
and **3,951 ms** of exclusive lock. The same statement on 12.2 wrote **484,674,144**
bytes of WAL and needed **72,373** read system calls where 17.11 needed **4,576**.

So yes: on a very large table a migration strategy is needed, because the cost is a
full rewrite under an exclusive lock, there is no progress view for it, and nothing
throttles it. The alternative measured here - add a `bigint` column, backfill it in
batches, build a unique index `CONCURRENTLY`, then swap the columns - cut the exclusive
lock to a **305 ms** window but cost **1,634,508,136 bytes of WAL**, 3.8x the single
`ALTER`, and left the table 2.15x its original size.

Everything below is the mechanism behind those numbers, then the strategies, then what
changed since PostgreSQL 12.

### Why the change always rewrites the table

`integer` to `bigint` is not a free catalog change in v17, and it never can be: the
cast is a function cast.

`pg_cast` stores `int4` -> `int8` with `castmethod => 'f'` and `castfunc =>
'int8(int4)'`
[pg_cast.dat#int4-int8](../../../../raw/postgres-17/src/include/catalog/pg_cast.dat#L41-L42).
`ATPrepAlterColumnType` builds a transform expression for the column, plans it, and
asks `ATColumnChangeRequiresRewrite` whether the expression is a no-op
[tablecmds.c#ATPrepAlterColumnType](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L12910-L12977).
That function walks the expression and returns `false` only for a bare `Var`, a
`RelabelType` chain, an unconstrained `CoerceToDomain`, and the one
`timestamp`/`timestamptz` pair; every other `FuncExpr` falls to `default: return true`
[tablecmds.c#ATColumnChangeRequiresRewrite](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13099-L13153).
A `FuncExpr` calling `int8(int4)` is exactly that case, so `tab->rewrite` gets
`AT_REWRITE_COLUMN_REWRITE`
[tablecmds.c:12975-12976](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L12975-L12976).

The documentation states the same rule and its two exceptions - a `USING` clause that
does not change the contents plus a binary-coercible old type or an unconstrained
domain - and warns that a rewrite "will temporarily require as much as double the disk
space"
[ref/alter_table.sgml#Notes](../../../../raw/postgres-17/doc/src/sgml/ref/alter_table.sgml#L1408-L1425).
Widening `int` does not qualify for either exception. There is also no supported
catalog-only shortcut: the on-disk tuple is decoded through the current
`TupleDesc`, so `attlen`/`attalign` are read at tuple-access time
[heaptuple.c#heap_deform_tuple](../../../../raw/postgres-17/src/backend/access/common/heaptuple.c#L1343-L1420),
and forcing `pg_attribute` to say 8 bytes over 4-byte stored data would misread every
existing row.

### What the statement does, phase by phase

`ALTER TABLE` runs in three phases, and a type change touches all of them.

| Phase | What happens for `id int` -> `bigint` | Evidence |
|---|---|---|
| 1, prep | Coerce, plan the transform, set `AT_REWRITE_COLUMN_REWRITE`, refuse typed tables and partition-key columns, recurse to inheritance children | [tablecmds.c#ATPrepAlterColumnType](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L12822-L13097) |
| 2, catalog | Clear missing values, rewrite the `pg_attribute` row (`atttypid`, `attlen`, `attbyval`, `attalign`, `attstorage`), re-add type/collation dependencies, drop the column's `pg_statistic` rows, rebuild the default | [tablecmds.c#ATExecAlterColumnType](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13184-L13197), [tablecmds.c:13391-13418](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13391-L13418) |
| 2, dependents | Every index and constraint on the column is remembered, dropped, and recreated from its deparsed definition; extended statistics objects likewise | [tablecmds.c#RememberAllDependentForRebuilding](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13477-L13690), [tablecmds.c#ATPostAlterTypeCleanup](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13869-L14004) |
| 3, rewrite | `make_new_heap` creates a transient heap, `ATRewriteTable` copies every live row into it, `finish_heap_swap` swaps the files, rebuilds all indexes, and drops the transient relation | [tablecmds.c#ATRewriteTables](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L5747-L5881) |
| 3, foreign keys | A final pass validates every foreign key queued during the rebuild | [tablecmds.c:5924-5973](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L5924-L5973) |

The transient heap is an ordinary table named `pg_temp_<old table OID>` in the same
namespace, created from the already-updated tuple descriptor, with its own TOAST table
when the original had one
[cluster.c#make_new_heap](../../../../raw/postgres-17/src/backend/commands/cluster.c#L687-L800).
Nothing about it is a temporary table in the `pg_temp` sense; it is a permanent
relation whose catalog row is uncommitted, so other sessions cannot see it in
`pg_class` while the rewrite runs.

`finish_heap_swap` then swaps the relation files, and rebuilds the indexes *before*
dropping the old storage, with the comment stating why that ordering costs nothing:
"this is all transactional, so no chance to reclaim disk space before commit"
[cluster.c#finish_heap_swap](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1476-L1508).
The old file is unlinked at commit by the deletion queued through `performDeletion`
[cluster.c:1547-1557](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1547-L1557).

### The locks it takes, and for how long

`AT_AlterColumnType` is in the group of subcommands that "rewrite the heap, so require
full locks": `AccessExclusiveLock`
[tablecmds.c#AlterTableGetLockLevel](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L4494-L4506).
The lock is held until the transaction commits, so for the whole rewrite, the whole
index rebuild, and the whole foreign-key validation pass. Readers and writers queue
behind it, and so does anything that queues behind *them*.

Three further locks are worth planning for:

- Any other table carrying a constraint that has to be rebuilt is locked
  `AccessExclusiveLock` too, explicitly because the DROP CONSTRAINT step will need it
  [tablecmds.c:13939-13951](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13939-L13951),
  and the same for an index on another relation
  [tablecmds.c:13960-13973](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13960-L13973).
  Widening a referenced primary-key column therefore takes an exclusive lock on every
  referencing table.
- A table owning an extended statistics object that must be rebuilt is locked
  `ShareUpdateExclusiveLock`, after all the exclusive locks, to avoid a lock upgrade
  deadlock
  [tablecmds.c:13985-14000](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13985-L14000).
- The referenced table of a foreign key being validated is opened `RowShareLock`
  during the final pass
  [tablecmds.c:5956-5967](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L5956-L5967).

Two more consequences of the rewrite being non-MVCC-safe and snapshot-bounded:

- The rewriting forms of `ALTER TABLE` "are not MVCC-safe": after the rewrite, the
  table looks empty to a transaction holding an older snapshot
  [ref/alter_table.sgml#MVCC](../../../../raw/postgres-17/doc/src/sgml/ref/alter_table.sgml#L1487-L1492).
- Predicate locks on the old tuples and pages are promoted to a relation-level
  predicate lock before the copy starts, because the rows move
  [tablecmds.c:6125-6133](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L6125-L6133).

### Read side: the old heap once, then the new heap once per index

`ATRewriteTable` registers a fresh MVCC snapshot and opens an ordinary sequential scan
of the old heap
[tablecmds.c:6181-6194](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L6181-L6194).
Two properties follow. Only rows visible to that snapshot are copied, so dead rows and
the free space they left are dropped on the floor - the rewrite compacts the table like
`VACUUM FULL` does. And because it is a plain sequential scan, it picks up the two
v17-relevant scan mechanics:

- If the relation is larger than `NBuffers / 4`, `initscan` allocates a `BAS_BULKREAD`
  strategy, so the scan runs in a 256 kB ring instead of evicting the buffer pool
  [heapam.c#initscan](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L433-L465),
  [freelist.c#GetAccessStrategy](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L551-L573).
- The scan is driven by a read stream, which combines neighbouring blocks into larger
  read calls up to `io_combine_limit`
  [heapam.c#read_stream_begin_relation](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1237-L1259),
  [guc_tables.c#io_combine_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3138-L3150).

The index rebuild then reads the *new* heap once per index. `finish_heap_swap` calls
`reindex_relation` for every index on the table
[cluster.c:1490-1508](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1490-L1508),
and each build scans the heap and sorts with `maintenance_work_mem`
[nbtsort.c:365-431](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L365-L430).
So the read volume of the whole statement is approximately

```text
heap_size + (number of indexes) * new_heap_size
```

plus the TOAST table, which is read in full whenever the rows carry out-of-line values
(see below).

Measured, that formula is exact. The 25,469-page fixture with two indexes touched
**76,541** heap blocks on 17.11 (`heap_blks_read` 72,413 plus `heap_blks_hit` 4,128),
and 25,469 + 2 x 25,536 = 76,541. On 12.2 the same arithmetic gives
25,469 + 2 x 25,478 = **76,425**, and the server reported 72,297 plus 4,128 = 76,425.
`pg_stat_io` attributed all 72,413 of the 17.11 misses to the `bulkread` context, which
is the `BAS_BULKREAD` ring.

The read *shape* is where v17 differs. The same 593,007,616 bytes of heap took **4,576**
read system calls on 17.11 and **72,373** on 12.2 - 129,591 bytes per call against
8,193, i.e. one 8 kB block per call on 12.2 and about 15.8 blocks per call on 17.11.
A controlled pair on two identical index-free 5,406-block tables pins the mechanism:

| Run | `io_combine_limit` | Blocks read | Read system calls |
|---|---|---|---|
| 17.11 default | 128 kB | 5,406 | **341** |
| 17.11 forced | 8 kB | 5,406 | **5,407** |
| 12.2 | does not exist | 5,406 | **5,406** |

Setting `io_combine_limit = '8kB'` on 17.11 reproduces 12.2's call count to the call.
`io_combine_limit` is `PGC_USERSET`, so that is a session-scope setting
[guc_tables.c#io_combine_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3138-L3150).

### Write side: a second copy of everything, and WAL for all of it

The copy loop inserts one tuple at a time with a bulk-insert state and
`TABLE_INSERT_SKIP_FSM`
[tablecmds.c:6026-6042](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L6026-L6042),
[tablecmds.c:6337-6345](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L6337-L6345).
That choice decides the write shape:

- `GetBulkInsertState` takes a `BAS_BULKWRITE` strategy, a 16 MB ring capped at
  `shared_buffers / 8`
  [heapam.c#GetBulkInsertState](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2037-L2052),
  [freelist.c#BAS_BULKWRITE](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L551-L573),
  [freelist.c:598-600](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L598-L600).
  The rewriting backend therefore writes out most of its own dirty pages rather than
  leaving them for the checkpointer.
- Relation extension goes through `RelationAddBlocks`, which extends by up to
  `MAX_BUFFERS_TO_EXTEND_BY` = 64 blocks in one `ExtendBufferedRelBy` call and hands
  the extra blocks to the bulk-insert state
  [hio.c#RelationAddBlocks](../../../../raw/postgres-17/src/backend/access/heap/hio.c#L225-L348).
- Every inserted tuple emits its own `XLOG_HEAP_INSERT` record when the relation needs
  WAL [heapam.c#heap_insert](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2196-L2279).
  There is no batching: `heap_multi_insert` is not on this path.

On top of that, the index rebuilds WAL-log the new index pages, and the dropped and
recreated catalog rows produce their own WAL. The practical rule is that a rewrite
writes a second copy of the table and of every index, and writes roughly that same
volume again into WAL.

`wal_level = minimal` is the one exception, and it is a big one.
`RelationNeedsWAL` is false for a relation whose storage was created in the current
transaction when `wal_level = minimal`
[rel.h#RelationNeedsWAL](../../../../raw/postgres-17/src/include/utils/rel.h#L620-L631),
so the copy emits no WAL at all. At commit, `smgrDoPendingSyncs` either fsyncs the new
files or, for files smaller than `wal_skip_threshold`, WAL-logs them page by page with
`log_newpage_range`
[storage.c#smgrDoPendingSyncs](../../../../raw/postgres-17/src/backend/catalog/storage.c#L769-L847),
[storage.c:39](../../../../raw/postgres-17/src/backend/catalog/storage.c#L39).

Measured write volumes for the 208,642,048-byte fixture with two indexes:

| Metric | 17.11 | 12.2 |
|---|---|---|
| WAL bytes (`pg_wal_lsn_diff` over the statement) | 427,512,848 | 484,674,144 |
| `write_bytes` reaching the block layer | 523,526,144 | 688,824,320 |
| Write system calls (`syscw`) | 80,398 | 120,613 |
| `pg_stat_io` `bulkwrite` blocks written | 23,488 | no `pg_stat_io` |
| `pg_stat_io` `extends` | 25,536 | no `pg_stat_io` |

The WAL figure is 2.05x the new heap and 1.31x the heap plus indexes, which is what one
record per row plus index-build WAL looks like. 12.2 wrote 57,161,296 bytes more WAL for
the same rows, because its two indexes are 61,612,032 bytes larger - B-tree
deduplication, new in v13, shrank this fixture's indexes from 179,855,360 to
118,243,328 bytes, and the rewrite rebuilds them at the new size.

Under `wal_level = minimal` on a restarted cluster, a 22,142,976-byte table measured:

| Run | WAL bytes |
|---|---|
| 17.11, `wal_skip_threshold` at its 2 MB default | 161,016 |
| 17.11, `SET wal_skip_threshold = '4GB'` | 26,315,416 |
| 12.2, no such setting | 151,928 |

That is the v13 mechanism in one table: the copy itself never writes WAL at
`wal_level = minimal`, and at commit the new files are either fsynced (both defaults
here) or WAL-logged page by page when they are smaller than `wal_skip_threshold`.
`wal_skip_threshold` is `PGC_USERSET`
[guc_tables.c#wal_skip_threshold](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2924-L2933),
so it is a session-scope knob; `wal_level` is `PGC_POSTMASTER` and needs a restart
[guc_tables.c#wal_level](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4986-L4994).

### Disk space: two copies until commit

Nothing is freed early. The new heap, the new TOAST table, and every rebuilt index are
created while the old ones still exist, and the old files are unlinked only at commit
[cluster.c:1476-1490](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1476-L1490),
[cluster.c:1547-1557](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1547-L1557).
The documentation's "as much as double the disk space"
[ref/alter_table.sgml:1422-1424](../../../../raw/postgres-17/doc/src/sgml/ref/alter_table.sgml#L1422-L1424)
should be read as double the *table plus indexes plus TOAST*, and on top of that the
WAL that has to be retained until the next checkpoint, plus whatever replication slots
hold.

Measured by taking `du -sb` of the data directory from inside the still-open
transaction, then again after commit:

| Data directory | 17.11 | 12.2 |
|---|---|---|
| Before the statement | 4,026,933,511 | 4,198,206,803 |
| Peak, transaction still open | 4,354,375,943 (**+327,442,432**) | 4,586,786,131 (**+388,579,328**) |
| After commit | 4,027,400,455 (+466,944) | 4,198,198,611 (-8,192) |

The peak rise is the new heap plus the new indexes almost exactly: 209,190,912 +
118,243,328 = 327,434,240 against 327,442,432 measured on 17.11. After commit the
directory is back where it started, because the old files are unlinked and the WAL was
recycled. This is the number that decides whether the statement can run at all: a
480 GB table with 200 GB of indexes needs 680 GB free, not 4 bytes per row.

### TOAST is rewritten too

The rewrite inserts through `heap_insert`, which calls the toaster whenever the tuple
has external values
[heapam.c#heap_prepare_insert](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2348-L2362).
On the insert path `toast_tuple_init` treats any external datum as "someone else's that
we cannot reuse", fetches it back with `detoast_external_attr`, and pushes it out again
as a new external value
[toast_helper.c#toast_tuple_init](../../../../raw/postgres-17/src/backend/access/table/toast_helper.c#L129-L147).
The new value lands in the transient heap's own TOAST table, which `make_new_heap`
created for the purpose
[cluster.c:772-800](../../../../raw/postgres-17/src/backend/commands/cluster.c#L772-L800).
So a table whose bytes live mostly in TOAST pays the full TOAST volume in reads, in
writes, and in WAL, even though its main fork is small.

Measured on a deliberately lopsided fixture - 8,000 rows, a 417,792-byte main fork, and
a 109,232,128-byte TOAST table holding 12.8 kB per row with `SET STORAGE EXTERNAL`:

| Metric | 17.11 | 12.2 |
|---|---|---|
| Main fork before / after | 417,792 / 524,288 | 417,792 / 483,328 |
| TOAST relation before / after | 109,232,128 / 114,688,000 | 109,232,128 / 114,688,000 |
| TOAST relfilenode changed | yes | yes |
| Bytes read by the backend (`rchar`) | **110,927,872** | **110,927,872** |
| WAL bytes | **111,148,848** | **111,126,768** |
| Statement duration | 293 ms | 295 ms |

A 408 kB table cost 111 MB of WAL. The TOAST table is not a detail to leave out of the
estimate: it is a second full relation that the rewrite reads, re-toasts row by row,
and WAL-logs, and its new copy came out 5,455,872 bytes larger than the old one on both
versions.

### Foreign keys: the referencing table is rescanned

When the widened column is the referenced side of a foreign key, the constraint is
dropped and recreated, and whether it is revalidated is decided by `old_check_ok`:

- `old_check_ok` starts true only because `TryReuseForeignKey` stashed the old
  `conpfeqop` array
  [tablecmds.c:9808-9813](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L9808-L9813),
  [tablecmds.c#TryReuseForeignKey](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14347-L14387).
- It is cleared as soon as the primary-key-to-foreign-key equality operator changes:
  "When a pfeqop changes, revalidate the constraint"
  [tablecmds.c:9922-9934](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L9922-L9934),
  and also if the cast pathway from the referencing type changes
  [tablecmds.c:9934-9993](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L9934-L9993).
- With `old_check_ok` false, `addFkRecurseReferencing` queues a phase-3 check
  [tablecmds.c:10476-10500](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L10476-L10500),
  and `validateForeignKeyConstraint` runs `RI_Initial_Check`
  [tablecmds.c#validateForeignKeyConstraint](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L12253-L12300),
  a single `SELECT fk.keycols FROM child fk LEFT OUTER JOIN parent pk ON ... WHERE
  pk.key IS NULL` executed through SPI
  [ri_triggers.c#RI_Initial_Check](../../../../raw/postgres-17/src/backend/utils/adt/ri_triggers.c#L1441-L1476),
  [ri_triggers.c:1563-1578](../../../../raw/postgres-17/src/backend/utils/adt/ri_triggers.c#L1563-L1578).

Widening `parent.id` from `int` to `bigint` while `child.p_id` stays `int` changes the
operator from `=(int4,int4)` to `=(int8,int4)`
[pg_operator.dat#int84eq](../../../../raw/postgres-17/src/include/catalog/pg_operator.dat#L281-L285),
so the child is scanned in full. That scan is charged to the referencing table, not to
the table being altered.

Measured with an 885-page parent of 200,000 rows and an 8,850-page child of 2,000,000
rows:

| Metric | 17.11 | 12.2 |
|---|---|---|
| `pg_constraint.conpfeqop` after the statement | `{416}` = `=(int8,int4)` | `{416}` |
| `convalidated` | `t` | `t` |
| Child `seq_scan` count | **1** | **1** |
| Child blocks touched (`heap_blks_read` + `heap_blks_hit`) | 7,182 + 1,668 = **8,850** | 335 + 8,515 = **8,850** |
| Child relfilenode changed | no | no |
| Parent WAL bytes | 17,106,816 | 17,088,128 |
| Statement duration | 360 ms | 431 ms |

The child was read in its entirety - all 8,850 of its pages - and never rewritten. So a
referenced column on a small lookup table can still cost a full scan of a very large
referencing table, and that table is held at `AccessExclusiveLock` while it happens.

### Does the table get bigger? Column order decides, not the column

`int4` has `typlen 4` and `typalign 'i'`; `int8` has `typlen 8` and `typalign 'd'`
[pg_type.dat#int4](../../../../raw/postgres-17/src/include/catalog/pg_type.dat#L72-L76),
[pg_type.dat#int8](../../../../raw/postgres-17/src/include/catalog/pg_type.dat#L55-L59).
`heap_compute_data_size` aligns each attribute's offset with `att_align_nominal` before
adding its length
[heaptuple.c#heap_compute_data_size](../../../../raw/postgres-17/src/backend/access/common/heaptuple.c#L211-L256),
[tupmacs.h#att_align_nominal](../../../../raw/postgres-17/src/include/access/tupmacs.h#L114-L138),
and the finished tuple length is `MAXALIGN`ed. The four extra bytes therefore land in a
padding hole, or they do not, depending on what follows the column.

Four fixtures, each widened with the same statement, measured as
`pg_relation_size` before and after:

| Fixture | Columns | Bytes before | 17.11 after | 12.2 after | Derived slot bytes per row, before -> after |
|---|---|---|---|---|---|
| `t_pad_hole` | `(a int, d float8)` | 44,285,952 | 44,564,480 | 44,285,952 | 44 -> 44 |
| `t_alter` | `(id int, grp int, txt text)` | 208,642,048 | 209,190,912 | 208,715,776 | 52 -> 52 |
| `t_iocl_a` | `(id int, txt text)` | 44,285,952 | 52,428,800 | 52,101,120 | 44 -> 52 |
| `t_pad_tail` | `(a int, b int)` | 36,249,600 | 44,564,480 | 44,285,952 | 36 -> 44 |

The last column is arithmetic, not a reading: `(8192 - 24) / (rows / pages)`, which
gives the tuple plus its 4-byte line pointer.

The first two did not grow: `float8` already forced 8-byte alignment, so the `int`
column sat in front of four wasted bytes that the `bigint` now uses, and in `t_alter`
the trailing `MAXALIGN` of the tuple absorbed the difference. The last two grew by
about 18% and 23%, which is the same 8 bytes per row in both cases, expressed against
different row widths. None of them grew by "4 bytes per row".

On 17.11 every rewritten file came out 34 blocks larger than the arithmetic predicts -
visible as +278,528 bytes on `t_pad_hole`, whose rows did not change size at all. That
is consistent with bulk relation extension handing the bulk-insert state up to 64
blocks at a time and the copy finishing before it uses them all
[hio.c:405-431](../../../../raw/postgres-17/src/backend/access/heap/hio.c#L405-L431),
but this page did not prove the attribution; see [Open Questions](#open-questions).

### Indexes are rebuilt, and a reuse test exists but cannot help here

`TryReuseIndex` asks `CheckIndexCompatible` whether the recreated index would be
logically identical and, if so, hands the old relfilenode to the new `IndexStmt`
[tablecmds.c#TryReuseIndex](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14320-L14345);
`ATExecAddIndex` then sets `skip_build` when the table is being rewritten or a
relfilenode was inherited
[tablecmds.c:9207](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L9203-L9210).
That is what makes `varchar(10)` -> `varchar(20)` cheap, and what the regression suite
pins with `skip_wal_skip_rewrite_index`
[alter_table.sql:1421-1426](../../../../raw/postgres-17/src/test/regress/sql/alter_table.sql#L1421-L1426).
For `int` -> `bigint` the opclass changes, so no index can be reused: every index on the
altered table is rebuilt from the new heap.

### What the rewrite leaves behind

| Left behind | Why | Evidence |
|---|---|---|
| No per-column statistics for the altered column | `RemoveStatistics` drops its `pg_statistic` rows, "since it's now wrong type" | [tablecmds.c:13415-13418](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13415-L13418) |
| Extended statistics objects present but empty | The object is dropped and recreated from its definition, so its `pg_statistic_ext_data` row is gone until the next `ANALYZE` | [tablecmds.c#RememberStatisticsForRebuilding](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13826-L13867), [tablecmds.c:13975-14004](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13975-L14004) |
| An empty visibility map | The new heap is written by `heap_insert` with a live xid and no `TABLE_INSERT_FROZEN`, so no page is all-visible and index-only scans stop working until a `VACUUM` | [tablecmds.c:6026-6042](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L6026-L6042), [heapam.c#heap_prepare_insert](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2323-L2346) |
| `relpages`/`reltuples` from the index build, `relallvisible` = 0 | `swap_relation_files` swaps in the transient relation's zeroed statistics, then each index build overwrites them through `index_update_stats`, which recomputes `relallvisible` with `visibilitymap_count` | [cluster.c:1222-1239](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1222-L1239), [heap.c:1004-1016](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1004-L1016), [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2788-L2857) |
| A table with no index left at `reltuples = -1` | Nothing overwrites the swapped-in sentinel, so the planner falls back to an estimate from the file size | [heap.c:1004-1016](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1004-L1016) |
| An unchanged sequence behind a `serial` column | The dependency walk finds the sequence and deliberately does nothing: "This must be a SERIAL column's sequence. We need not do anything to it." | [tablecmds.c:13527-13534](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13527-L13534) |

The last row is the classic trap: widening the column does not widen the sequence, and
`nextval` will still fail at 2147483647 until `ALTER SEQUENCE ... AS bigint` is run
separately, which rewrites `seqtypid` and lifts the min/max bounds only when they were
still the old type's limits
[sequence.c#init_params](../../../../raw/postgres-17/src/backend/commands/sequence.c#L1373-L1402).

### There is no progress view and no throttle

`pg_stat_progress_cluster` is started only by `cluster_rel`
[cluster.c:323](../../../../raw/postgres-17/src/backend/commands/cluster.c#L323);
`ALTER TABLE` never calls `pgstat_progress_start_command`, even though
`finish_heap_swap` updates progress parameters. So the phase updates it writes are not
reported anywhere. The rewrite also has no cost-delay point of its own:
`vacuum_delay_point` appears 0 times in `commands/tablecmds.c`, `commands/cluster.c`,
`access/heap/heapam.c` and `catalog/index.c` in the pinned tree, so `vacuum_cost_delay`
and `vacuum_cost_limit` cannot slow it down - their only nbtree caller is the vacuum
scan
[nbtree.c:1095-1096](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1095-L1096).
What is observable from another session is the growing file behind the transient relation,
`pg_database_size`, WAL generation, and - new since v12 - `pg_stat_io` in the
`bulkread` and `bulkwrite` contexts
[freelist.c#IOContextForStrategy](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L757-L784).

### What refuses to run at all

The dependency walk turns several dependencies into hard errors rather than rebuilding
them, all in `RememberAllDependentForRebuilding`
[tablecmds.c:13515-13690](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13515-L13690):

| Dependency | Error |
|---|---|
| View or rule | `cannot alter type of a column used by a view or rule` |
| New-style SQL function or procedure body | `cannot alter type of a column used by a function or procedure` |
| Trigger definition (`WHEN`, update target) | `cannot alter type of a column used in a trigger definition` |
| Row-level security policy | `cannot alter type of a column used in a policy definition` |
| Generated column expression | `cannot alter type of a column used by a generated column` |
| Publication `WHERE` clause | `cannot alter type of a column used by a publication WHERE clause` |

Also refused: the column is part of the partition key
[tablecmds.c:12886-12893](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L12886-L12893);
the table is a typed table
[tablecmds.c:12843-12846](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L12843-L12846);
the column is inherited and the parent was not altered
[tablecmds.c:12880-12884](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L12880-L12884);
a composite type built on the row type is used as a column type somewhere
[tablecmds.c:5738-5745](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L5738-L5745);
and the relation is a system catalog or is used as a catalog table
[tablecmds.c:5769-5795](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L5769-L5795).

On a partitioned table the statement is not one rewrite but many: `ATPrepAlterColumnType`
recurses through `find_all_inheritors` and queues the same subcommand for every child
[tablecmds.c:13003-13093](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13003-L13093),
so every partition is rewritten inside the one transaction, under
`AccessExclusiveLock` on the whole hierarchy. Doing partitions one at a time is not
possible either: a partition's column type must match the parent's, which
`MergeAttributesIntoExisting` enforces on `ATTACH PARTITION`
[tablecmds.c#MergeAttributesIntoExisting](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L15931-L15968).

### The control case: what a no-rewrite type change costs

To keep the rewrite cost in perspective, the same script widens a `varchar(32)` column
to `text` on a 177,127,424-byte table. `varchar` -> `text` is binary coercible, so the
transform collapses to a `RelabelType` and `ATColumnChangeRequiresRewrite` returns
false:

| Metric | 17.11 | 12.2 |
|---|---|---|
| relfilenode changed | no | no |
| Blocks read | 0 | 0 |
| WAL bytes | 114,832 | 111,576 |
| Duration | 2 ms | 4 ms |
| `rewriting table` DEBUG1 lines | 0 | 0 |

That is the shape of a catalog-only type change, and it is exactly what `int` ->
`bigint` cannot be.

### Is a migration strategy needed for a very large table?

Yes, and the reason is the lock rather than the bytes. The bytes scale linearly and
predictably; the exclusive lock scales with them.

On this hardware the single `ALTER` moved 327,442,432 bytes of new relation in 3,951 ms.
Scaling that rate arithmetically, a 480 GB table with 200 GB of indexes is about
2.3 hours of `AccessExclusiveLock`, and that is with `fsync = off` and no concurrent
load, so it is a floor rather than an estimate. Nothing in v17 can shorten it: the
rewrite has no parallel worker, no progress view, and no cost delay.

Three strategies, with what the pinned tree says about each.

#### One `ALTER` in a maintenance window

Right when the table is small enough that the window fits, and it is the only route
that ends with a compact table, correct statistics after `ANALYZE`, and no leftovers.
Make it survivable:

- Set `lock_timeout` before the statement so the DDL gives up instead of queueing in
  front of every reader; `lock_timeout` is `PGC_USERSET`
  [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631).
- Combine every change to the table into one `ALTER TABLE` statement, because "multiple
  table scans or rewrites can thereby be combined into a single pass over the table"
  [ref/alter_table.sgml:1438-1442](../../../../raw/postgres-17/doc/src/sgml/ref/alter_table.sgml#L1438-L1442).
- Expect to `VACUUM` and `ANALYZE` afterwards: the visibility map is empty and the
  column's statistics were dropped (measured: `relallvisible` 0 and a 0-byte `vm` fork
  right after the rewrite, 25,478 and 8,192 bytes after a plain `VACUUM`; the altered
  column had 0 `pg_statistic` rows on both versions).

#### New column, batched backfill, concurrent index, catalog swap

This is the route that keeps the table writable. The script runs it end to end and
measures every step:

| Step | 17.11 | 12.2 | Lock on the table |
|---|---|---|---|
| `ADD COLUMN id_new bigint` | 23,904 B WAL, 1 ms | 23,688 B WAL, 2 ms | `AccessExclusiveLock`, but instant |
| Backfill in 8 batched `UPDATE`s | **1,543,691,840 B WAL**, 17,241 ms | 1,566,647,088 B WAL, 16,066 ms | `RowExclusiveLock` |
| `CREATE UNIQUE INDEX CONCURRENTLY` | 90,729,400 B WAL, 1,163 ms | 91,148,064 B WAL, 1,194 ms | `ShareUpdateExclusiveLock` |
| `DROP COLUMN` + `RENAME` + `ADD PRIMARY KEY USING INDEX` | 62,992 B WAL, **305 ms** | 38,440 B WAL, 247 ms | `AccessExclusiveLock` |
| Total WAL | **1,634,508,136** | 1,657,857,280 | |
| Heap size after | 449,495,040 (2.15x) | 449,495,040 | |
| Indexes after | 147,496,960 | 262,717,440 | |
| Data directory, permanent rise | +265,609,216 | +323,215,360 | |

The `ADD COLUMN` itself is free because a nullable column with no default is stored as
metadata; a non-volatile `DEFAULT` is also metadata, through `attmissingval`, and only
a volatile default forces `AT_REWRITE_DEFAULT_VAL`
[tablecmds.c#ATExecAddColumn](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L7326-L7370).

What it costs: 3.8x the WAL of the single `ALTER`, a table that ends 2.15x its original
size, and a permanently larger data directory until a rewrite is done anyway. The
`UPDATE`s cannot be HOT here - measured `n_tup_hot_upd` = 0 of 4,000,000 on both
versions, because the pages were full at the default `fillfactor`, so each update also
inserts index entries. A plain `VACUUM` afterwards reclaimed nothing measurable
(449,495,040 bytes before and after), because `VACUUM` marks free space rather than
shrinking the file. Also note the dropped column is not gone: its `pg_attribute` row
survives as `attisdropped` (measured: 1), and its bytes stay in every existing row
until that row is updated
[ref/alter_table.sgml:1470-1485](../../../../raw/postgres-17/doc/src/sgml/ref/alter_table.sgml#L1470-L1485).

What it buys: the exclusive lock drops from 3,951 ms to a 305 ms swap, and the heavy
work happens under locks that let reads and writes through.

#### Logical replication into an already-widened copy

A subscriber's column type does not have to match the publisher's.
`logicalrep_rel_open` maps columns by *name* and records no type check
[relation.c#logicalrep_rel_open](../../../../raw/postgres-17/src/backend/replication/logical/relation.c#L407-L438),
and in the default text format the apply worker converts each value with the *local*
type's input function
[worker.c#slot_store_data](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L807-L839).
So a publisher with `id integer` can feed a subscriber with `id bigint`, and the switch
over is a promotion rather than a rewrite.

Measured on one cluster with two databases, 100,000 rows:

| Check | 17.11 | 12.2 |
|---|---|---|
| Publisher column type | `integer` | `integer` |
| Subscriber column type | `bigint` | `bigint` |
| Rows after initial copy | **100,000** | **100,000** |
| A later `INSERT` arrives | yes | yes |
| `SET (binary = true)` accepted | yes | **rejected: unrecognized subscription parameter** |
| Rows arriving while `binary = true` | **0**, with 6 `insufficient data left in message` errors | n/a |
| Row arrives after `binary = false` | yes | n/a |

The trap is `binary = true`: the apply worker calls the *local* type's receive function
on the publisher's bytes
[worker.c:840-855](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L840-L862),
so `int8recv` is handed 4 bytes and the worker errors out in a loop. A widening
migration over logical replication must stay in text format. The option does not exist
at all on 12.2, which is why this failure mode is new since then.

#### What does not work

- Editing `pg_attribute` by hand. `attlen` and `attalign` are read when the tuple is
  decoded
  [heaptuple.c#heap_deform_tuple](../../../../raw/postgres-17/src/backend/access/common/heaptuple.c#L1343-L1420),
  so the change would misread existing rows rather than convert them.
- Widening one partition at a time. The types must match the parent
  [tablecmds.c#MergeAttributesIntoExisting](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L15931-L15968).
- Relying on the sequence to follow. `serial`/identity sequences are left alone
  [tablecmds.c:13527-13534](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13527-L13534);
  measured, `pg_sequence.seqtypid` stayed `integer` and `seqmax` stayed 2147483647
  after the column became `bigint`, and only `ALTER SEQUENCE ... AS bigint` moved it to
  9223372036854775807, on both versions.
- Counting on `VACUUM FULL` or `CLUSTER` to do it. They rewrite the table but cannot
  change a column's type.

### Settings that affect the rewrite, with apply scope

| Setting | Context | Apply scope | Effect on this statement |
|---|---|---|---|
| `lock_timeout` | `PGC_USERSET` | session/transaction | caps how long the DDL waits for its `AccessExclusiveLock` [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631) |
| `statement_timeout` | `PGC_USERSET` | session/transaction | caps the whole rewrite; a timeout rolls everything back [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620) |
| `maintenance_work_mem` | `PGC_USERSET` | session/transaction | sort memory for every index rebuilt [nbtsort.c:365-431](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L365-L430) |
| `max_parallel_maintenance_workers` | `PGC_USERSET` | session/transaction | parallel workers for B-tree index rebuilds [guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417) |
| `io_combine_limit` | `PGC_USERSET` | session/transaction | read-call size for the old-heap scan [guc_tables.c#io_combine_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3138-L3150) |
| `wal_skip_threshold` | `PGC_USERSET` | session/transaction | at `wal_level = minimal`, fsync instead of WAL above this size [guc_tables.c#wal_skip_threshold](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2924-L2933) |
| `wal_compression` |  `PGC_SUSET` | session/transaction | compresses full-page images only, not the per-row insert records [guc_tables.c#wal_compression](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4976-L4984) |
| `wal_level` | `PGC_POSTMASTER` | restart | `minimal` removes the copy's WAL entirely [guc_tables.c#wal_level](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4986-L4994) |
| `shared_buffers` | `PGC_POSTMASTER` | restart | caps the bulk-write ring at `NBuffers / 8` [freelist.c:598-600](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L598-L600) |
| `max_wal_size`, `checkpoint_timeout` | `PGC_SIGHUP` | reload | decide how many checkpoints the rewrite's WAL triggers [guc_tables.c#max_wal_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2842-L2851) |

Not controls, despite being asked for: `vacuum_cost_delay` and friends (no
`vacuum_delay_point` on this path), `BUFFER_USAGE_LIMIT` (a `VACUUM`/`ANALYZE` option,
not an `ALTER TABLE` one), and any progress view.

### Test coverage in the pinned tree

The regression suite pins the behaviour this page describes, without measuring its
cost:

- `check_ddl_rewrite` compares `pg_class.relfilenode` before and after a DDL statement,
  and the `rewrite_test` block asserts which `ADD COLUMN` forms rewrite and which do
  not
  [alter_table.sql:1662-1720](../../../../raw/postgres-17/src/test/regress/sql/alter_table.sql#L1662-L1720).
- `alter a type bigint` is used to pin that foreign-key validation is delayed until
  after the rewrite
  [alter_table.sql:791-796](../../../../raw/postgres-17/src/test/regress/sql/alter_table.sql#L791-L796).
- `skip_wal_skip_rewrite_index` pins the index-reuse path for a `varchar` widening
  [alter_table.sql:1421-1426](../../../../raw/postgres-17/src/test/regress/sql/alter_table.sql#L1421-L1426).
- A partitioned table's no-rewrite type change, with comments preserved, is pinned
  from line 1461
  [alter_table.sql:1461-1470](../../../../raw/postgres-17/src/test/regress/sql/alter_table.sql#L1461-L1470).
- `fast_default` covers the `attmissingval` path that makes `ADD COLUMN` cheap
  [fast_default.sql:1-40](../../../../raw/postgres-17/src/test/regress/sql/fast_default.sql#L1-L10).

There is no test of the I/O volume, the WAL volume, or the disk high-water mark of a
rewrite; those are only measurable from outside, which is what this page's script does.

### What changed since PostgreSQL 12

Nothing changed about *whether* `int` -> `bigint` rewrites: `ATColumnChangeRequiresRewrite`
had the same three exemptions in 12.0, including the `timestamp`/`timestamptz` pair, and
`pg_cast` still records a function cast. What changed is the cost and the aftermath.
Each row below was checked by testing for the symbol at each release tag in this
checkout rather than by `git tag --contains`.

| Change | Commit | First release | Effect here | Measured |
|---|---|---|---|---|
| WAL skipping for new relfilenodes reworked, `wal_skip_threshold` added | `c6b92041d38` (after `cb2fd7eac28` and its revert `de9396326ed`) | 13.0 | v12 passed `TABLE_INSERT_SKIP_WAL` and synced the heap itself; v13+ defers to `smgrDoPendingSyncs`, which fsyncs large files and WAL-logs small ones | 17.11 wrote 26,315,416 B of WAL with `wal_skip_threshold = '4GB'` against 161,016 B at the default; 12.2 wrote 151,928 B either way, having no such setting |
| B-tree deduplication | `0d861bbb702` | 13.0 | the rebuilt indexes are smaller, so the rewrite writes and WAL-logs less | the same two indexes measured 118,243,328 B on 17.11 and 179,855,360 B on 12.2 |
| `pg_class.reltuples = -1` as "never vacuumed" | `3d351d916b2` | 14.0 | a rewritten table with no index is left at -1 instead of 0 | `reltuples` after the rewrite: -1 on 17.11, 0 on 12.2, with `relpages` 0 on both |
| Extended statistics dropped and recreated instead of patched | `a4d75c86bf1` | 14.0 | v12's `UpdateStatisticsForTypeChange` only nulled the MCV list and kept ndistinct; v14+ recreates the object, so all its data is gone until `ANALYZE` | after the rewrite the object existed on both, but its `pg_statistic_ext_data` row was gone on 17.11 and present with non-null `stxdndistinct` on 12.2 |
| Bulk relation extension | `31966b151e6`, `00d1e02be24` | 16.0 | the copy extends by up to 64 blocks per call instead of one | 17.11's new files came out 34 blocks larger than 12.2's on identical fixtures |
| `pg_stat_io` | `a9c70b46dbe` | 16.0 | the rewrite's reads and writes are attributable to the `bulkread` and `bulkwrite` contexts | 72,413 `bulkread` blocks and 23,488 `bulkwrite` blocks on 17.11; the view does not exist on 12.2 |
| Read stream for sequential scans, with `io_combine_limit` | `b7b0f3f2724` | 17.0 | the old-heap scan issues far fewer, larger read calls | 4,576 read calls against 12.2's 72,373 for the same 593,007,616 bytes; forcing `io_combine_limit = '8kB'` reproduced 12.2 exactly |
| `cannot alter type of a column used by a function or procedure` | `42b041243c0` | 17.0 | a new-style SQL function body that references the column now blocks the statement with a clear error | not measured |
| `cannot alter type of a column used by a publication WHERE clause` | `91e7115b177` | 17.0 | a row-filter publication on the column blocks the statement | not measured |
| `SET ACCESS METHOD` became a rewrite reason (`AT_REWRITE_ACCESS_METHOD`) | v15 scaffolding | 15.0 | more ways to reach the same rewrite machinery | not measured |
| Subscription `binary` option | v14 subscription options | 14.0 | creates the widening trap over logical replication | `binary = true` broke apply on 17.11 (6 `insufficient data left in message` errors); 12.2 rejects the option outright |
| Shared-memory cumulative statistics | v15 statistics rework | 15.0 | `pg_statio_all_tables` is readable immediately after a short statement | on 12.2 the TOAST case read back 0 blocks because the collector had not flushed yet; 17.11 reported 55,999 |

Two things did *not* change and are worth stating because they are often assumed to
have: the rewrite still emits one WAL record per row rather than batching
[heapam.c#heap_insert](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2196-L2279),
and `ALTER TABLE` still starts no progress command, so `pg_stat_progress_cluster` stays
empty for it
[cluster.c:323](../../../../raw/postgres-17/src/backend/commands/cluster.c#L323).

## Measurement Script

Every number on this page comes from the two scripts below, one per version leg. They
build PostgreSQL out of tree from this repository's own pins, run an isolated cluster
on a non-default port, measure, and delete themselves.

| Item | Value |
|---|---|
| Purpose | measures the I/O, WAL, disk high-water mark, lock duration and resulting sizes of `ALTER TABLE ... ALTER COLUMN ... TYPE bigint`, of a no-rewrite control, of four alignment fixtures, of a TOAST-heavy table, of a foreign-key parent, of the add-column/backfill/swap route, of `wal_level = minimal`, and of a widening logical-replication migration. It backs every figure in [Answer](#answer). |
| Invocation | `bash leg17.sh [stage ...]` and `bash leg12.sh [stage ...]`, run from the directory holding the script. With no stage argument each script runs its full default list. |
| Stages | `build`, `check`, `init`, `fixture`, `alter`, `catalog`, `control`, `align`, `toast`, `iocl`, `fk`, `addcol`, `minimal`, `logrep`, `report`, `clean`. The default order is every stage except `clean`. `build` configures and compiles out of tree and installs; `check` runs `make check`; `init` initdbs and starts the cluster, stopping a postmaster this sandbox left behind first; `fixture` creates the eleven disposable tables; `alter` measures the headline statement; `catalog` reads what the rewrite left behind and probes the `serial` sequence and the view blocker; `control` measures `varchar` -> `text`; `align` measures the two alignment fixtures; `toast` measures the TOAST-heavy table; `iocl` measures the read-shape pair; `fk` measures the foreign-key parent and its child; `addcol` runs the four-step add-column route; `minimal` restarts at `wal_level = minimal` and measures both `wal_skip_threshold` cases; `logrep` runs the intra-cluster logical replication test; `report` writes `out*/report.txt`; `clean` stops the server. |
| Environment | `REPO` (default `$HOME/repos/postgres-llm-wiki`), `SRC` (default `$REPO/raw/postgres-17` or `raw/postgres-12`), `SANDBOX` (default `$REPO/.wiki-runtime/tmp/intbigint`), `PORT` (55417 / 55412), `JOBS` (20), `ROWS` (4000000), `CHILDROWS` (2000000), `BATCHES` (8), and on the 12 leg `EXTRA_CFLAGS` (default `-O2 -g -DTRUE=1 -DFALSE=0`). |
| Prerequisites | a C toolchain and `make`; no contrib module and no extension is needed. Both legs configure `--enable-debug --without-readline --without-zlib --without-icu`, and the clusters run `--locale=C --encoding=UTF8` at the default 8 kB block size. Linux is required for the `/proc/<pid>/io` counters. |
| Output | `$SANDBOX/out17/` and `$SANDBOX/out12/`. Read `report.txt` first; `results.tsv` is the raw `case`/`metric`/`value` log, `checks.txt` the regression-suite result, `fixture_sizes.txt` the starting geometry, `server.log` the cluster log, and one `<case>.log` per measured statement. |
| Runtime | about 3 minutes for `build` plus `check` per leg, then about 6 minutes for the 12 leg's measurement stages and about 7 minutes for the 17 leg's, on 22 cores with `JOBS=20`. |
| Cleanup | `bash leg17.sh clean` and `bash leg12.sh clean` stop the postmasters; deleting `$SANDBOX` removes both builds, both data directories and all output. Both were run and the sandbox was deleted before this page was filed. |

Isolation: the scripts only ever write under `$SANDBOX`, treat `raw/postgres-NN/` as
read-only, run with `set -uo pipefail`, call `psql` with `-X -v ON_ERROR_STOP=1`, take a
`mkdir` lock so two runs cannot re-initdb one data directory, and tag every statement
with an inline `/* wiki_... */` comment after the leading verb. Every fixture statement
is disposable: the tables are created and dropped by the script and are not meant for a
database anyone cares about. Each measuring session sets `statement_timeout = '60min'`
and `lock_timeout = '30s'`.

Last run: 2026-09-17, on the pins recorded in `wiki/versions.md`
(`786db8dcf168bd9df8f55047337525ac19118b1c` for 17.11 and
`45b88269a353ad93744772791feb6d01bc7e1e42` for 12.2), Ubuntu 24.04 on WSL2
(Linux 6.18.33.2-microsoft-standard-WSL2), x86_64, gcc 13.3.0, 22 cores, 31 GiB RAM,
one local SSD-backed filesystem. `block_size` 8192, `wal_block_size` 8192,
`max_data_alignment` 8, `data_checksums` off, `shared_buffers` 256MB,
`maintenance_work_mem` 256MB, `fsync` off, `autovacuum` off,
`max_parallel_maintenance_workers` 0, `wal_level` logical except in the `minimal`
stage. `make check`: **All 225 tests passed** on 17.11 and **All 192 tests passed** on
12.2, both with exit status 0.

### PostgreSQL 17.11 leg

```bash
#!/usr/bin/env bash
# Measurement leg for PostgreSQL 17.11: I/O cost of ALTER TABLE ... ALTER COLUMN TYPE
# int -> bigint, and of the add-column/backfill and logical-replication alternatives.
# Disposable: every object this script creates is meant to be thrown away.
set -uo pipefail

REPO="${REPO:-$HOME/repos/postgres-llm-wiki}"
SRC="${SRC:-$REPO/raw/postgres-17}"
SANDBOX="${SANDBOX:-$REPO/.wiki-runtime/tmp/intbigint}"
BUILD="$SANDBOX/build17"
INSTALL="$SANDBOX/install17"
PGDATA="$SANDBOX/data17"
SOCK="$SANDBOX/sock17"
OUT="$SANDBOX/out17"
PORT="${PORT:-55417}"
JOBS="${JOBS:-20}"
ROWS="${ROWS:-4000000}"
CHILDROWS="${CHILDROWS:-2000000}"
BATCHES="${BATCHES:-8}"
DB=iobig

RES="$OUT/results.tsv"

die() { echo "FATAL: $*" >&2; exit 1; }
say() { echo "== $* =="; }

PSQL() { "$INSTALL/bin/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" "$@"; }
Q() { PSQL -d "$DB" -A -t -c "$1"; }

# record <case> <metric> <value>
record() { printf '%s\t%s\t%s\n' "$1" "$2" "$3" >>"$RES"; }

# iofield <file> <key>  -> value from a /proc/<pid>/io snapshot
iofield() {
  local f="$1" k="$2" key val
  while read -r key val; do
    if [ "$key" = "$k:" ]; then echo "$val"; return 0; fi
  done <"$f"
  echo 0
}

# iodelta <case> <before-file> <after-file>
iodelta() {
  local c="$1" b="$2" a="$3" k
  for k in rchar wchar syscr syscw read_bytes write_bytes; do
    record "$c" "io_$k" "$(( $(iofield "$a" "$k") - $(iofield "$b" "$k") ))"
  done
}

stage_build() {
  say "build 17.11 out of tree from $SRC"
  [ -x "$SRC/configure" ] || die "no configure in $SRC"
  mkdir -p "$BUILD" "$INSTALL" "$OUT" || die mkdir
  ( cd "$BUILD" && "$SRC/configure" --prefix="$INSTALL" --enable-debug \
      --without-readline --without-zlib --without-icu >"$OUT/configure.log" 2>&1 )
  [ $? -eq 0 ] || die "configure failed, see $OUT/configure.log"
  ( cd "$BUILD" && make -s -j"$JOBS" >"$OUT/make.log" 2>&1 )
  [ $? -eq 0 ] || die "make failed, see $OUT/make.log"
  ( cd "$BUILD" && make -s install >"$OUT/install.log" 2>&1 )
  [ $? -eq 0 ] || die "make install failed, see $OUT/install.log"
  "$INSTALL/bin/postgres" --version | tee "$OUT/version.txt"
}

stage_check() {
  say "make check"
  ( cd "$BUILD" && make check >"$OUT/check_core.log" 2>&1 )
  local rc=$?
  grep -E 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests failed' "$OUT/check_core.log" \
    | tee "$OUT/checks.txt"
  echo "core check exit status: $rc" | tee -a "$OUT/checks.txt"
}

stage_init() {
  say "initdb + start on port $PORT"
  # stop a postmaster this sandbox left behind: its shutdown would otherwise unlink
  # the socket of the cluster this stage is about to start
  if [ -f "$PGDATA/postmaster.pid" ]; then
    say "stopping the postmaster already running in $PGDATA"
    "$INSTALL/bin/pg_ctl" -D "$PGDATA" -m fast -w stop || die "could not stop it"
  fi
  rm -rf "$PGDATA" "$SOCK"
  mkdir -p "$SOCK" "$OUT" || die mkdir
  "$INSTALL/bin/initdb" -D "$PGDATA" --locale=C --encoding=UTF8 \
    >"$OUT/initdb.log" 2>&1 || die "initdb failed"
  # GUC contexts: shared_buffers/wal_level/max_wal_senders/max_replication_slots/fsync
  # are postmaster (restart); autovacuum/max_wal_size/checkpoint_timeout are sighup
  # (reload); maintenance_work_mem/work_mem are user (session scope).
  cat >>"$PGDATA/postgresql.conf" <<EOF
port = $PORT
unix_socket_directories = '$SOCK'
listen_addresses = ''
shared_buffers = 256MB
maintenance_work_mem = 256MB
work_mem = 64MB
fsync = off
autovacuum = off
max_wal_size = 16GB
min_wal_size = 1GB
checkpoint_timeout = 1h
wal_level = logical
max_wal_senders = 8
max_replication_slots = 8
max_parallel_maintenance_workers = 0
max_parallel_workers_per_gather = 0
log_min_messages = warning
log_checkpoints = on
EOF
  "$INSTALL/bin/pg_ctl" -D "$PGDATA" -l "$OUT/server.log" -w start || die "start failed"
  "$INSTALL/bin/psql" -X -h "$SOCK" -p "$PORT" -d postgres -c \
    "DROP /* wiki_iobig_reset */ DATABASE IF EXISTS $DB" >/dev/null
  "$INSTALL/bin/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d postgres -c \
    "CREATE /* wiki_iobig_db */ DATABASE $DB" || die "createdb failed"
  : >"$RES"
  Q "SELECT version()" >"$OUT/serverversion.txt"
  Q "SELECT name || '=' || setting FROM pg_settings
     WHERE name IN ('block_size','wal_block_size','data_checksums','shared_buffers',
                    'wal_level','fsync','full_page_writes','wal_compression',
                    'io_combine_limit','wal_skip_threshold','maintenance_work_mem',
                    'autovacuum','max_parallel_maintenance_workers')
     ORDER BY name" >"$OUT/settings.txt"
  cat "$OUT/settings.txt"
}

sql_header() {
  cat <<'EOF'
\set ON_ERROR_STOP on
SET statement_timeout = '60min';
SET lock_timeout = '30s';
SET client_min_messages = debug1;
EOF
}

stage_fixture() {
  say "fixtures ($ROWS rows in the main table)"
  PSQL -d "$DB" >"$OUT/fixture.log" 2>&1 <<EOF
$(sql_header)
-- disposable fixtures
DROP /* wiki_iobig_fixture */ TABLE IF EXISTS t_alter, t_add, t_ctl, fk_child, fk_parent,
  t_pad_tail, t_pad_hole, t_iocl_a, t_iocl_b, t_min_a, t_min_b, t_toast CASCADE;

CREATE /* wiki_iobig_fixture */ TABLE t_alter (
  id int NOT NULL,
  grp int NOT NULL,
  txt text NOT NULL
);
INSERT /* wiki_iobig_fixture */ INTO t_alter
  SELECT g, g % 1000, 'row' || g FROM generate_series(1, $ROWS) g;
ALTER /* wiki_iobig_fixture */ TABLE t_alter ADD PRIMARY KEY (id);
CREATE /* wiki_iobig_fixture */ INDEX t_alter_grp_idx ON t_alter (grp);

-- byte-identical twin for the add-column + backfill route
CREATE /* wiki_iobig_fixture */ TABLE t_add (LIKE t_alter INCLUDING ALL);
INSERT /* wiki_iobig_fixture */ INTO t_add SELECT * FROM t_alter;

-- control: varchar -> text is binary coercible, so no rewrite is expected
CREATE /* wiki_iobig_fixture */ TABLE t_ctl (
  id int NOT NULL PRIMARY KEY,
  v varchar(32) NOT NULL
);
INSERT /* wiki_iobig_fixture */ INTO t_ctl
  SELECT g, 'row' || g FROM generate_series(1, $ROWS) g;

-- alignment pair: (int,int) grows, (int,float8) has a padding hole to spend
CREATE /* wiki_iobig_fixture */ TABLE t_pad_tail (a int NOT NULL, b int NOT NULL);
INSERT /* wiki_iobig_fixture */ INTO t_pad_tail
  SELECT g, g FROM generate_series(1, 1000000) g;
CREATE /* wiki_iobig_fixture */ TABLE t_pad_hole (a int NOT NULL, d float8 NOT NULL);
INSERT /* wiki_iobig_fixture */ INTO t_pad_hole
  SELECT g, g::float8 FROM generate_series(1, 1000000) g;

-- read-shape pair for the v17 read stream: two identical tables, one altered at
-- the default io_combine_limit and one at 8kB
CREATE /* wiki_iobig_fixture */ TABLE t_iocl_a (id int NOT NULL, txt text NOT NULL);
INSERT /* wiki_iobig_fixture */ INTO t_iocl_a
  SELECT g, 'row' || g FROM generate_series(1, 1000000) g;
CREATE /* wiki_iobig_fixture */ TABLE t_iocl_b (LIKE t_iocl_a INCLUDING ALL);
INSERT /* wiki_iobig_fixture */ INTO t_iocl_b SELECT * FROM t_iocl_a;

-- small table for the wal_level = minimal legs
CREATE /* wiki_iobig_fixture */ TABLE t_min_a (id int NOT NULL, txt text NOT NULL);
INSERT /* wiki_iobig_fixture */ INTO t_min_a
  SELECT g, 'row' || g FROM generate_series(1, 500000) g;
CREATE /* wiki_iobig_fixture */ TABLE t_min_b (LIKE t_min_a INCLUDING ALL);
INSERT /* wiki_iobig_fixture */ INTO t_min_b SELECT * FROM t_min_a;

-- a tiny heap with a large TOAST table: 8000 rows of about 12.8 kB, stored
-- out of line and uncompressed so the toast bytes are what they look like
CREATE /* wiki_iobig_fixture */ TABLE t_toast (id int NOT NULL, blob text NOT NULL);
ALTER /* wiki_iobig_fixture */ TABLE t_toast ALTER COLUMN blob SET STORAGE EXTERNAL;
INSERT /* wiki_iobig_fixture */ INTO t_toast
  SELECT g, (SELECT string_agg(md5(random()::text), '')
             FROM generate_series(1, 400))
  FROM generate_series(1, 8000) g;

-- extended statistics over the column that will be widened
CREATE /* wiki_iobig_fixture */ STATISTICS t_alter_stx (ndistinct)
  ON id, grp FROM t_alter;

-- foreign key pair: child keeps int, parent widens to bigint
CREATE /* wiki_iobig_fixture */ TABLE fk_parent (id int PRIMARY KEY);
INSERT /* wiki_iobig_fixture */ INTO fk_parent
  SELECT g FROM generate_series(1, 200000) g;
CREATE /* wiki_iobig_fixture */ TABLE fk_child (
  id int PRIMARY KEY,
  p_id int NOT NULL REFERENCES fk_parent (id)
);
INSERT /* wiki_iobig_fixture */ INTO fk_child
  SELECT g, 1 + (g % 200000) FROM generate_series(1, $CHILDROWS) g;

VACUUM /* wiki_iobig_fixture */ (ANALYZE) t_alter, t_add, t_ctl, t_pad_tail,
  t_pad_hole, t_iocl_a, t_iocl_b, t_min_a, t_min_b, t_toast, fk_parent, fk_child;
CHECKPOINT /* wiki_iobig_fixture */;
EOF
  [ $? -eq 0 ] || die "fixture failed, see $OUT/fixture.log"
  Q "SELECT c.relname || '|' || pg_relation_size(c.oid) || '|' ||
            pg_table_size(c.oid) || '|' || pg_indexes_size(c.oid) || '|' ||
            c.relpages || '|' || c.reltuples || '|' || c.relallvisible
     FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1" >"$OUT/fixture_sizes.txt"
  cat "$OUT/fixture_sizes.txt"
}

# measure_ddl <case> <relation> <ddl statement>
# Runs one DDL statement with before/after snapshots of size, WAL, buffer and
# /proc/<backend pid>/io counters, and the peak data-directory size taken while
# the statement's transaction is still open.
measure_ddl() {
  local c="$1" rel="$2" ddl="$3" extra="${4:-}"
  say "case $c: $ddl"
  Q "SELECT pg_stat_reset()" >/dev/null
  Q "SELECT pg_stat_reset_shared('io')" >/dev/null
  Q "CHECKPOINT /* wiki_iobig_${c} */" >/dev/null
  record "$c" "size_before" "$(Q "SELECT pg_relation_size('$rel')")"
  record "$c" "index_count" "$(Q "SELECT count(*) FROM pg_index WHERE indrelid = '$rel'::regclass")"
  record "$c" "table_size_before" "$(Q "SELECT pg_table_size('$rel')")"
  record "$c" "indexes_size_before" "$(Q "SELECT pg_indexes_size('$rel')")"
  record "$c" "filenode_before" "$(Q "SELECT pg_relation_filenode('$rel')")"
  record "$c" "db_size_before" "$(Q "SELECT pg_database_size(current_database())")"
  record "$c" "datadir_before" "$(du -sb "$PGDATA" | cut -f1)"

  export CASE="$c" OUTDIR="$OUT" PGDATA
  PSQL -d "$DB" >"$OUT/${c}.log" 2>&1 <<EOF
$(sql_header)
$extra
SELECT pg_backend_pid() AS bpid \gset
\setenv BPID :bpid
SELECT pg_current_wal_lsn() AS lsn0 \gset
\! cat /proc/\$BPID/io > \$OUTDIR/\$CASE.io.before
\! date +%s%N > \$OUTDIR/\$CASE.t0
BEGIN;
$ddl
\! date +%s%N > \$OUTDIR/\$CASE.t1
\! du -sb \$PGDATA > \$OUTDIR/\$CASE.datadir_peak
COMMIT;
\! date +%s%N > \$OUTDIR/\$CASE.t2
\! cat /proc/\$BPID/io > \$OUTDIR/\$CASE.io.after
SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), :'lsn0') AS wal_bytes \gset
\setenv WALB :wal_bytes
\! echo \$WALB > \$OUTDIR/\$CASE.wal
EOF
  [ $? -eq 0 ] || die "case $c failed, see $OUT/${c}.log"

  iodelta "$c" "$OUT/${c}.io.before" "$OUT/${c}.io.after"
  record "$c" "wal_bytes" "$(cat "$OUT/${c}.wal")"
  record "$c" "ddl_ms" "$(( ( $(cat "$OUT/${c}.t1") - $(cat "$OUT/${c}.t0") ) / 1000000 ))"
  record "$c" "commit_ms" "$(( ( $(cat "$OUT/${c}.t2") - $(cat "$OUT/${c}.t1") ) / 1000000 ))"
  record "$c" "datadir_peak" "$(cut -f1 "$OUT/${c}.datadir_peak")"
  record "$c" "datadir_after" "$(du -sb "$PGDATA" | cut -f1)"
  record "$c" "size_after" "$(Q "SELECT pg_relation_size('$rel')")"
  record "$c" "table_size_after" "$(Q "SELECT pg_table_size('$rel')")"
  record "$c" "indexes_size_after" "$(Q "SELECT pg_indexes_size('$rel')")"
  record "$c" "filenode_after" "$(Q "SELECT pg_relation_filenode('$rel')")"
  record "$c" "db_size_after" "$(Q "SELECT pg_database_size(current_database())")"
  record "$c" "relpages_after" "$(Q "SELECT relpages FROM pg_class WHERE oid = '$rel'::regclass")"
  record "$c" "reltuples_after" "$(Q "SELECT reltuples FROM pg_class WHERE oid = '$rel'::regclass")"
  record "$c" "relallvisible_after" "$(Q "SELECT relallvisible FROM pg_class WHERE oid = '$rel'::regclass")"
  record "$c" "rewrite_debug_lines" "$(grep -c 'rewriting table' "$OUT/${c}.log")"
  record "$c" "heap_blks_read" "$(Q "SELECT coalesce(heap_blks_read,0) FROM pg_statio_all_tables WHERE relid = '$rel'::regclass")"
  record "$c" "heap_blks_hit" "$(Q "SELECT coalesce(heap_blks_hit,0) FROM pg_statio_all_tables WHERE relid = '$rel'::regclass")"
  record "$c" "idx_blks_read" "$(Q "SELECT coalesce(idx_blks_read,0) FROM pg_statio_all_tables WHERE relid = '$rel'::regclass")"
  record "$c" "bulkread_blocks" "$(Q "SELECT coalesce(sum(reads),0)::bigint FROM pg_stat_io WHERE context = 'bulkread' AND object = 'relation'")"
  record "$c" "bulkwrite_blocks" "$(Q "SELECT coalesce(sum(writes),0)::bigint FROM pg_stat_io WHERE context = 'bulkwrite' AND object = 'relation'")"
  record "$c" "extends_all" "$(Q "SELECT coalesce(sum(extends),0)::bigint FROM pg_stat_io WHERE object = 'relation'")"
}

stage_alter() {
  measure_ddl alter_int_to_bigint t_alter \
    "ALTER /* wiki_alter_int_to_bigint */ TABLE t_alter ALTER COLUMN id TYPE bigint;"
}

stage_control() {
  measure_ddl control_varchar_to_text t_ctl \
    "ALTER /* wiki_alter_varchar_to_text */ TABLE t_ctl ALTER COLUMN v TYPE text;"
}

stage_align() {
  measure_ddl align_tail t_pad_tail \
    "ALTER /* wiki_alter_align_tail */ TABLE t_pad_tail ALTER COLUMN a TYPE bigint;"
  measure_ddl align_hole t_pad_hole \
    "ALTER /* wiki_alter_align_hole */ TABLE t_pad_hole ALTER COLUMN a TYPE bigint;"
}

stage_fk() {
  # the FK revalidation scan lands on fk_child, so record its counters too
  Q "SELECT pg_stat_reset()" >/dev/null
  measure_ddl fk_parent_widen fk_parent \
    "ALTER /* wiki_alter_fk_parent */ TABLE fk_parent ALTER COLUMN id TYPE bigint;"
  record fk_parent_widen child_heap_blks_read \
    "$(Q "SELECT coalesce(heap_blks_read,0) FROM pg_statio_all_tables WHERE relid = 'fk_child'::regclass")"
  record fk_parent_widen child_heap_blks_hit \
    "$(Q "SELECT coalesce(heap_blks_hit,0) FROM pg_statio_all_tables WHERE relid = 'fk_child'::regclass")"
  record fk_parent_widen child_idx_blks_read \
    "$(Q "SELECT coalesce(idx_blks_read,0) FROM pg_statio_all_tables WHERE relid = 'fk_child'::regclass")"
  record fk_parent_widen child_filenode \
    "$(Q "SELECT pg_relation_filenode('fk_child')")"
  record fk_parent_widen child_seq_scan \
    "$(Q "SELECT coalesce(seq_scan,0) FROM pg_stat_all_tables WHERE relid = 'fk_child'::regclass")"
  record fk_parent_widen fk_pfeqop \
    "$(Q "SELECT conpfeqop::text FROM pg_constraint WHERE conname LIKE 'fk_child_p_id%'")"
  record fk_parent_widen fk_convalidated \
    "$(Q "SELECT convalidated FROM pg_constraint WHERE conname LIKE 'fk_child_p_id%'")"
}

stage_addcol() {
  say "add-column + batched backfill route on t_add"
  local lsn0 pre_size pre_idx t0 t1
  Q "SELECT pg_stat_reset()" >/dev/null
  Q "CHECKPOINT /* wiki_iobig_addcol */" >/dev/null
  record addcol_backfill size_before "$(Q "SELECT pg_relation_size('t_add')")"
  record addcol_backfill table_size_before "$(Q "SELECT pg_table_size('t_add')")"
  record addcol_backfill indexes_size_before "$(Q "SELECT pg_indexes_size('t_add')")"
  record addcol_backfill filenode_before "$(Q "SELECT pg_relation_filenode('t_add')")"
  record addcol_backfill datadir_before "$(du -sb "$PGDATA" | cut -f1)"

  export OUTDIR="$OUT" PGDATA
  PSQL -d "$DB" -v batches="$BATCHES" -v rows="$ROWS" >"$OUT/addcol.log" 2>&1 <<'EOF'
\set ON_ERROR_STOP on
SET statement_timeout = '60min';
SET lock_timeout = '30s';
SET client_min_messages = debug1;
SET iobig.batches = :batches;
SET iobig.rows = :rows;
SELECT pg_backend_pid() AS bpid \gset
\setenv BPID :bpid
SELECT pg_current_wal_lsn() AS lsn0 \gset
\! cat /proc/$BPID/io > $OUTDIR/addcol.io.before
\! date +%s%N > $OUTDIR/addcol.t0

-- step 1: metadata-only add
ALTER /* wiki_addcol_new_bigint */ TABLE t_add ADD COLUMN id_new bigint;
SELECT pg_current_wal_lsn() AS lsn_add \gset
\! date +%s%N > $OUTDIR/addcol.t_add

-- step 2: batched backfill, one transaction per batch
DO /* wiki_addcol_backfill */ $$
DECLARE
  batches int := current_setting('iobig.batches')::int;
  total   bigint := current_setting('iobig.rows')::bigint;
  lo bigint; hi bigint; step bigint;
BEGIN
  step := (total / batches) + 1;
  lo := 1;
  WHILE lo <= total LOOP
    hi := lo + step - 1;
    UPDATE /* wiki_addcol_backfill */ t_add SET id_new = id
      WHERE id BETWEEN lo AND hi AND id_new IS DISTINCT FROM id;
    lo := hi + 1;
  END LOOP;
END $$;
SELECT pg_current_wal_lsn() AS lsn_fill \gset
\! date +%s%N > $OUTDIR/addcol.t_fill
\! du -sb $PGDATA > $OUTDIR/addcol.datadir_peak

-- step 3: the new column needs its own unique index; CONCURRENTLY keeps writers in
CREATE /* wiki_addcol_index */ UNIQUE INDEX CONCURRENTLY t_add_id_new_uq ON t_add (id_new);
SELECT pg_current_wal_lsn() AS lsn_idx \gset
\! date +%s%N > $OUTDIR/addcol.t_idx

-- step 4: swap the columns and promote the new index to the primary key
BEGIN;
ALTER /* wiki_addcol_swap */ TABLE t_add DROP COLUMN id;
ALTER /* wiki_addcol_swap */ TABLE t_add RENAME COLUMN id_new TO id;
ALTER /* wiki_addcol_swap */ TABLE t_add
  ADD CONSTRAINT t_add_pkey2 PRIMARY KEY USING INDEX t_add_id_new_uq;
COMMIT;
SELECT pg_current_wal_lsn() AS lsn_swap \gset
\! date +%s%N > $OUTDIR/addcol.t1
\! cat /proc/$BPID/io > $OUTDIR/addcol.io.after

SELECT pg_wal_lsn_diff(:'lsn_add', :'lsn0')     AS w_add,
       pg_wal_lsn_diff(:'lsn_fill', :'lsn_add') AS w_fill,
       pg_wal_lsn_diff(:'lsn_idx', :'lsn_fill') AS w_idx,
       pg_wal_lsn_diff(:'lsn_swap', :'lsn_idx') AS w_swap \gset
\setenv WADD :w_add
\setenv WFILL :w_fill
\setenv WIDX :w_idx
\setenv WSWAP :w_swap
\! echo $WADD > $OUTDIR/addcol.wal_add
\! echo $WFILL > $OUTDIR/addcol.wal_fill
\! echo $WIDX > $OUTDIR/addcol.wal_idx
\! echo $WSWAP > $OUTDIR/addcol.wal_swap
EOF
  [ $? -eq 0 ] || die "addcol failed, see $OUT/addcol.log"
  iodelta addcol_backfill "$OUT/addcol.io.before" "$OUT/addcol.io.after"
  record addcol_backfill wal_add_column "$(cat "$OUT/addcol.wal_add")"
  record addcol_backfill wal_backfill "$(cat "$OUT/addcol.wal_fill")"
  record addcol_backfill wal_index_build "$(cat "$OUT/addcol.wal_idx")"
  record addcol_backfill wal_swap "$(cat "$OUT/addcol.wal_swap")"
  record addcol_backfill add_ms "$(( ( $(cat "$OUT/addcol.t_add") - $(cat "$OUT/addcol.t0") ) / 1000000 ))"
  record addcol_backfill backfill_ms "$(( ( $(cat "$OUT/addcol.t_fill") - $(cat "$OUT/addcol.t_add") ) / 1000000 ))"
  record addcol_backfill index_ms "$(( ( $(cat "$OUT/addcol.t_idx") - $(cat "$OUT/addcol.t_fill") ) / 1000000 ))"
  record addcol_backfill swap_ms "$(( ( $(cat "$OUT/addcol.t1") - $(cat "$OUT/addcol.t_idx") ) / 1000000 ))"
  record addcol_backfill datadir_peak "$(cut -f1 "$OUT/addcol.datadir_peak")"
  record addcol_backfill datadir_after "$(du -sb "$PGDATA" | cut -f1)"
  record addcol_backfill size_after "$(Q "SELECT pg_relation_size('t_add')")"
  record addcol_backfill table_size_after "$(Q "SELECT pg_table_size('t_add')")"
  record addcol_backfill indexes_size_after "$(Q "SELECT pg_indexes_size('t_add')")"
  record addcol_backfill filenode_after "$(Q "SELECT pg_relation_filenode('t_add')")"
  record addcol_backfill n_dead_tup "$(Q "SELECT n_dead_tup FROM pg_stat_all_tables WHERE relid = 't_add'::regclass")"
  record addcol_backfill n_tup_upd "$(Q "SELECT n_tup_upd FROM pg_stat_all_tables WHERE relid = 't_add'::regclass")"
  record addcol_backfill n_tup_hot_upd "$(Q "SELECT n_tup_hot_upd FROM pg_stat_all_tables WHERE relid = 't_add'::regclass")"
  record addcol_backfill dropped_col_still_there \
    "$(Q "SELECT count(*) FROM pg_attribute WHERE attrelid = 't_add'::regclass AND attisdropped")"
  # after a VACUUM FULL the add-column route would match the rewrite's size; record
  # the plain-VACUUM outcome instead, which is what an operator actually gets
  Q "VACUUM /* wiki_addcol_after */ (ANALYZE) t_add" >/dev/null
  record addcol_backfill size_after_vacuum "$(Q "SELECT pg_relation_size('t_add')")"
  record addcol_backfill indexes_size_after_vacuum "$(Q "SELECT pg_indexes_size('t_add')")"
}

stage_catalog() {
  say "catalog aftermath of the rewrite (run after 'alter')"
  record catalog_after pg_statistic_rows_altered_col \
    "$(Q "SELECT count(*) FROM pg_statistic WHERE starelid = 't_alter'::regclass
          AND staattnum = (SELECT attnum FROM pg_attribute
                           WHERE attrelid = 't_alter'::regclass AND attname = 'id')")"
  record catalog_after extstats_object_present \
    "$(Q "SELECT count(*) FROM pg_statistic_ext WHERE stxrelid = 't_alter'::regclass")"
  record catalog_after extstats_data_rows \
    "$(Q "SELECT count(*) FROM pg_statistic_ext_data d JOIN pg_statistic_ext s ON s.oid = d.stxoid
          WHERE s.stxrelid = 't_alter'::regclass")"
  record catalog_after extstats_ndistinct_null \
    "$(Q "SELECT coalesce(bool_and(d.stxdndistinct IS NULL), true)::text
          FROM pg_statistic_ext_data d JOIN pg_statistic_ext s ON s.oid = d.stxoid
          WHERE s.stxrelid = 't_alter'::regclass")"
  record catalog_after reltuples "$(Q "SELECT reltuples FROM pg_class WHERE oid = 't_alter'::regclass")"
  record catalog_after relpages "$(Q "SELECT relpages FROM pg_class WHERE oid = 't_alter'::regclass")"
  record catalog_after relallvisible "$(Q "SELECT relallvisible FROM pg_class WHERE oid = 't_alter'::regclass")"
  record catalog_after vm_pages_on_disk \
    "$(Q "SELECT pg_relation_size('t_alter', 'vm')")"
  record catalog_after atttypid_is_int8 \
    "$(Q "SELECT (atttypid = 'bigint'::regtype)::text FROM pg_attribute
          WHERE attrelid = 't_alter'::regclass AND attname = 'id'")"
  record catalog_after attlen \
    "$(Q "SELECT attlen FROM pg_attribute WHERE attrelid = 't_alter'::regclass AND attname = 'id'")"
  record catalog_after attalign \
    "$(Q "SELECT attalign FROM pg_attribute WHERE attrelid = 't_alter'::regclass AND attname = 'id'")"
  # planner estimate before and after ANALYZE
  Q "EXPLAIN /* wiki_iobig_est */ SELECT * FROM t_alter" >"$OUT/explain_before_analyze.txt"
  record catalog_after explain_before_analyze \
    "$(grep -o 'rows=[0-9]*' "$OUT/explain_before_analyze.txt" | head -1)"
  Q "ANALYZE /* wiki_iobig_est */ t_alter" >/dev/null
  Q "EXPLAIN /* wiki_iobig_est */ SELECT * FROM t_alter" >"$OUT/explain_after_analyze.txt"
  record catalog_after explain_after_analyze \
    "$(grep -o 'rows=[0-9]*' "$OUT/explain_after_analyze.txt" | head -1)"
  record catalog_after reltuples_after_analyze \
    "$(Q "SELECT reltuples FROM pg_class WHERE oid = 't_alter'::regclass")"
  record catalog_after relallvisible_after_analyze \
    "$(Q "SELECT relallvisible FROM pg_class WHERE oid = 't_alter'::regclass")"
  Q "VACUUM /* wiki_iobig_est */ t_alter" >/dev/null
  record catalog_after relallvisible_after_vacuum \
    "$(Q "SELECT relallvisible FROM pg_class WHERE oid = 't_alter'::regclass")"
  record catalog_after vm_pages_after_vacuum \
    "$(Q "SELECT pg_relation_size('t_alter', 'vm')")"
  # sequence attached to a serial column is NOT widened by ALTER COLUMN TYPE
  Q "DROP /* wiki_iobig_seq */ TABLE IF EXISTS t_serial" >/dev/null
  Q "CREATE /* wiki_iobig_seq */ TABLE t_serial (id serial PRIMARY KEY, v int)" >/dev/null
  record catalog_after serial_seqtypid_before \
    "$(Q "SELECT format_type(seqtypid,null) FROM pg_sequence WHERE seqrelid = 't_serial_id_seq'::regclass")"
  Q "ALTER /* wiki_iobig_seq */ TABLE t_serial ALTER COLUMN id TYPE bigint" >/dev/null
  record catalog_after serial_seqtypid_after \
    "$(Q "SELECT format_type(seqtypid,null) FROM pg_sequence WHERE seqrelid = 't_serial_id_seq'::regclass")"
  record catalog_after serial_seqmax_after \
    "$(Q "SELECT seqmax FROM pg_sequence WHERE seqrelid = 't_serial_id_seq'::regclass")"
  Q "ALTER /* wiki_iobig_seq */ SEQUENCE t_serial_id_seq AS bigint" >/dev/null
  record catalog_after serial_seqmax_after_alter_sequence \
    "$(Q "SELECT seqmax FROM pg_sequence WHERE seqrelid = 't_serial_id_seq'::regclass")"
  # a view on the column blocks the ALTER outright
  Q "DROP /* wiki_iobig_view */ TABLE IF EXISTS t_view CASCADE" >/dev/null
  Q "CREATE /* wiki_iobig_view */ TABLE t_view (id int)" >/dev/null
  Q "CREATE /* wiki_iobig_view */ VIEW v_view AS SELECT id FROM t_view" >/dev/null
  PSQL -d "$DB" -c "ALTER /* wiki_iobig_view */ TABLE t_view ALTER COLUMN id TYPE bigint" \
    >"$OUT/view_block.log" 2>&1
  record catalog_after view_block_exit "$?"
  record catalog_after view_block_msg "$(grep -c 'used by a view or rule' "$OUT/view_block.log")"
}

stage_toast() {
  say "a 400 kB heap with a 100 MB TOAST table"
  record toast_widen toast_size_before \
    "$(Q "SELECT pg_relation_size(reltoastrelid) FROM pg_class WHERE oid = 't_toast'::regclass")"
  record toast_widen toast_filenode_before \
    "$(Q "SELECT pg_relation_filenode(reltoastrelid) FROM pg_class WHERE oid = 't_toast'::regclass")"
  record toast_widen total_size_before "$(Q "SELECT pg_total_relation_size('t_toast')")"
  measure_ddl toast_widen t_toast \
    "ALTER /* wiki_alter_toast_widen */ TABLE t_toast ALTER COLUMN id TYPE bigint;"
  record toast_widen toast_size_after \
    "$(Q "SELECT pg_relation_size(reltoastrelid) FROM pg_class WHERE oid = 't_toast'::regclass")"
  record toast_widen toast_filenode_after \
    "$(Q "SELECT pg_relation_filenode(reltoastrelid) FROM pg_class WHERE oid = 't_toast'::regclass")"
  record toast_widen toast_blks_read \
    "$(Q "SELECT coalesce(toast_blks_read,0) FROM pg_statio_all_tables WHERE relid = 't_toast'::regclass")"
  record toast_widen toast_blks_hit \
    "$(Q "SELECT coalesce(toast_blks_hit,0) FROM pg_statio_all_tables WHERE relid = 't_toast'::regclass")"
  record toast_widen tidx_blks_read \
    "$(Q "SELECT coalesce(tidx_blks_read,0) FROM pg_statio_all_tables WHERE relid = 't_toast'::regclass")"
  record toast_widen total_size_after "$(Q "SELECT pg_total_relation_size('t_toast')")"
}

stage_iocl() {
  say "read shape: default io_combine_limit against 8kB"
  measure_ddl iocl_default t_iocl_a \
    "ALTER /* wiki_alter_iocl_default */ TABLE t_iocl_a ALTER COLUMN id TYPE bigint;"
  measure_ddl iocl_8kb t_iocl_b \
    "ALTER /* wiki_alter_iocl_8kb */ TABLE t_iocl_b ALTER COLUMN id TYPE bigint;" \
    "SET io_combine_limit = '8kB';"
  record iocl_default io_combine_limit "$(Q "SHOW io_combine_limit")"
}

stage_minimal() {
  say "wal_level = minimal: WAL skipping and wal_skip_threshold"
  # wal_level and max_wal_senders are PGC_POSTMASTER, so this needs a restart
  cp "$PGDATA/postgresql.conf" "$PGDATA/postgresql.conf.logical" || die cp
  cat >>"$PGDATA/postgresql.conf" <<EOF
wal_level = minimal
max_wal_senders = 0
EOF
  "$INSTALL/bin/pg_ctl" -D "$PGDATA" -l "$OUT/server.log" -w restart || die "restart failed"
  record minimal wal_level "$(Q "SHOW wal_level")"
  measure_ddl minimal_default t_min_a \
    "ALTER /* wiki_alter_minimal_default */ TABLE t_min_a ALTER COLUMN id TYPE bigint;"
  # wal_skip_threshold is PGC_USERSET, so session scope is enough
  measure_ddl minimal_thresh_high t_min_b \
    "ALTER /* wiki_alter_minimal_thresh */ TABLE t_min_b ALTER COLUMN id TYPE bigint;" \
    "SET wal_skip_threshold = '4GB';"
  cp "$PGDATA/postgresql.conf.logical" "$PGDATA/postgresql.conf" || die cp
  "$INSTALL/bin/pg_ctl" -D "$PGDATA" -l "$OUT/server.log" -w restart || die "restart failed"
  record minimal wal_level_restored "$(Q "SHOW wal_level")"
}

stage_logrep() {
  say "logical replication from an int publisher to a bigint subscriber"
  PSQL -d postgres >"$OUT/logrep_setup.log" 2>&1 <<EOF
$(sql_header)
DROP /* wiki_logrep */ DATABASE IF EXISTS lr_pub;
DROP /* wiki_logrep */ DATABASE IF EXISTS lr_sub;
CREATE /* wiki_logrep */ DATABASE lr_pub;
CREATE /* wiki_logrep */ DATABASE lr_sub;
EOF
  [ $? -eq 0 ] || die "logrep databases failed"
  PSQL -d lr_pub >>"$OUT/logrep_setup.log" 2>&1 <<EOF
$(sql_header)
CREATE /* wiki_logrep */ TABLE widen (id int PRIMARY KEY, v text NOT NULL);
INSERT /* wiki_logrep */ INTO widen
  SELECT g, 'row' || g FROM generate_series(1, 100000) g;
CREATE /* wiki_logrep */ PUBLICATION widen_pub FOR TABLE widen;
-- publisher and subscriber are the same cluster here, so the slot must be created
-- outside the CREATE SUBSCRIPTION transaction: that transaction has an xid of its
-- own, and the slot's snapshot build would wait for it forever
SELECT /* wiki_logrep */ slot_name
  FROM pg_create_logical_replication_slot('widen_slot', 'pgoutput');
EOF
  [ $? -eq 0 ] || die "publisher failed"
  PSQL -d lr_sub >>"$OUT/logrep_setup.log" 2>&1 <<EOF
$(sql_header)
CREATE /* wiki_logrep */ TABLE widen (id bigint PRIMARY KEY, v text NOT NULL);
CREATE /* wiki_logrep */ SUBSCRIPTION widen_sub
  CONNECTION 'host=$SOCK port=$PORT dbname=lr_pub'
  PUBLICATION widen_pub
  WITH (create_slot = false, slot_name = 'widen_slot');
EOF
  [ $? -eq 0 ] || die "subscription failed"
  local i rows=0
  for i in $(seq 1 60); do
    rows=$(PSQL -d lr_sub -A -t -c "SELECT count(*) FROM widen")
    [ "$rows" = "100000" ] && break
    sleep 1
  done
  record logrep initial_copy_rows "$rows"
  record logrep publisher_type "$(PSQL -d lr_pub -A -t -c \
    "SELECT format_type(atttypid,atttypmod) FROM pg_attribute
     WHERE attrelid='widen'::regclass AND attname='id'")"
  record logrep subscriber_type "$(PSQL -d lr_sub -A -t -c \
    "SELECT format_type(atttypid,atttypmod) FROM pg_attribute
     WHERE attrelid='widen'::regclass AND attname='id'")"
  # incremental change replicates too
  PSQL -d lr_pub -c "INSERT /* wiki_logrep */ INTO widen VALUES (2000000001, 'big')" >/dev/null
  for i in $(seq 1 30); do
    rows=$(PSQL -d lr_sub -A -t -c "SELECT count(*) FROM widen WHERE id = 2000000001")
    [ "$rows" = "1" ] && break
    sleep 1
  done
  record logrep incremental_row_arrived "$rows"
  record logrep subscriber_max_id "$(PSQL -d lr_sub -A -t -c "SELECT max(id) FROM widen")"
  # binary mode is the trap: the subscriber calls its own type's receive function
  PSQL -d lr_sub -c "ALTER /* wiki_logrep_binary */ SUBSCRIPTION widen_sub SET (binary = true)" \
    >>"$OUT/logrep_setup.log" 2>&1
  record logrep binary_option_accepted "$?"
  PSQL -d lr_pub -c "INSERT /* wiki_logrep_binary */ INTO widen VALUES (2000000002, 'bin')" >/dev/null
  sleep 8
  record logrep binary_row_arrived "$(PSQL -d lr_sub -A -t -c \
    "SELECT count(*) FROM widen WHERE id = 2000000002")"
  record logrep binary_error_lines "$(grep -c 'insufficient data left in message' "$OUT/server.log")"
  PSQL -d lr_sub -c "ALTER /* wiki_logrep */ SUBSCRIPTION widen_sub SET (binary = false)" >/dev/null 2>&1
  sleep 5
  record logrep after_binary_off_row "$(PSQL -d lr_sub -A -t -c \
    "SELECT count(*) FROM widen WHERE id = 2000000002")"
  PSQL -d lr_sub -c "ALTER /* wiki_logrep */ SUBSCRIPTION widen_sub DISABLE" >/dev/null 2>&1
  PSQL -d lr_sub -c "ALTER /* wiki_logrep */ SUBSCRIPTION widen_sub SET (slot_name = NONE)" >/dev/null 2>&1
  PSQL -d lr_sub -c "DROP /* wiki_logrep */ SUBSCRIPTION widen_sub" >/dev/null 2>&1
  PSQL -d lr_pub -c "SELECT /* wiki_logrep */ pg_drop_replication_slot('widen_slot')" >/dev/null 2>&1
  record logrep slots_left "$(PSQL -d postgres -A -t -c "SELECT count(*) FROM pg_replication_slots")"
  PSQL -d postgres -c "DROP /* wiki_logrep */ DATABASE lr_sub" >/dev/null 2>&1
  PSQL -d postgres -c "DROP /* wiki_logrep */ DATABASE lr_pub" >/dev/null 2>&1
}

stage_report() {
  say "report"
  {
    echo "# PostgreSQL 17 leg: int -> bigint I/O measurements"
    echo "# $(cat "$OUT/serverversion.txt" 2>/dev/null)"
    echo "# rows=$ROWS childrows=$CHILDROWS batches=$BATCHES port=$PORT"
    echo
    printf '%-26s %-26s %s\n' CASE METRIC VALUE
    sort -k1,1 -s "$RES" | while IFS=$'\t' read -r a b c; do
      printf '%-26s %-26s %s\n' "$a" "$b" "$c"
    done
  } >"$OUT/report.txt"
  cat "$OUT/report.txt"
}

stage_clean() {
  say "clean: stop server and delete sandbox pieces"
  if [ -f "$PGDATA/postmaster.pid" ]; then
    "$INSTALL/bin/pg_ctl" -D "$PGDATA" -m fast -w stop
  fi
  sleep 1
  if [ -f "$PGDATA/postmaster.pid" ]; then echo "WARNING: postmaster.pid survives"; fi
  pgrep -a postgres
  echo "pgrep exit: $?"
}

# one run at a time: a second concurrent run would re-initdb the data directory
# under the first one's postmaster
LOCK="$SANDBOX/.lock17"
mkdir "$LOCK" 2>/dev/null || die "another leg17 run holds $LOCK"
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

stages=("$@")
[ ${#stages[@]} -eq 0 ] && stages=(build check init fixture alter catalog control align toast
                                   iocl fk addcol minimal logrep report)
for s in "${stages[@]}"; do
  case "$s" in
    build) stage_build ;;
    check) stage_check ;;
    init) stage_init ;;
    fixture) stage_fixture ;;
    alter) stage_alter ;;
    catalog) stage_catalog ;;
    control) stage_control ;;
    align) stage_align ;;
    toast) stage_toast ;;
    iocl) stage_iocl ;;
    fk) stage_fk ;;
    addcol) stage_addcol ;;
    minimal) stage_minimal ;;
    logrep) stage_logrep ;;
    report) stage_report ;;
    clean) stage_clean ;;
    *) die "unknown stage: $s" ;;
  esac
done
date +%FT%T%z >"$OUT/STAGES_DONE"
say "all stages done: ${stages[*]}"
```

### PostgreSQL 12.2 leg

```bash
#!/usr/bin/env bash
# Measurement leg for PostgreSQL 12.2: I/O cost of ALTER TABLE ... ALTER COLUMN TYPE
# int -> bigint, and of the add-column/backfill and logical-replication alternatives.
# Disposable: every object this script creates is meant to be thrown away.
set -uo pipefail

REPO="${REPO:-$HOME/repos/postgres-llm-wiki}"
SRC="${SRC:-$REPO/raw/postgres-12}"
SANDBOX="${SANDBOX:-$REPO/.wiki-runtime/tmp/intbigint}"
BUILD="$SANDBOX/build12"
INSTALL="$SANDBOX/install12"
PGDATA="$SANDBOX/data12"
SOCK="$SANDBOX/sock12"
OUT="$SANDBOX/out12"
PORT="${PORT:-55412}"
JOBS="${JOBS:-20}"
ROWS="${ROWS:-4000000}"
CHILDROWS="${CHILDROWS:-2000000}"
BATCHES="${BATCHES:-8}"
DB=iobig

RES="$OUT/results.tsv"

die() { echo "FATAL: $*" >&2; exit 1; }
say() { echo "== $* =="; }

PSQL() { "$INSTALL/bin/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" "$@"; }
Q() { PSQL -d "$DB" -A -t -c "$1"; }

# record <case> <metric> <value>
record() { printf '%s\t%s\t%s\n' "$1" "$2" "$3" >>"$RES"; }

# iofield <file> <key>  -> value from a /proc/<pid>/io snapshot
iofield() {
  local f="$1" k="$2" key val
  while read -r key val; do
    if [ "$key" = "$k:" ]; then echo "$val"; return 0; fi
  done <"$f"
  echo 0
}

# iodelta <case> <before-file> <after-file>
iodelta() {
  local c="$1" b="$2" a="$3" k
  for k in rchar wchar syscr syscw read_bytes write_bytes; do
    record "$c" "io_$k" "$(( $(iofield "$a" "$k") - $(iofield "$b" "$k") ))"
  done
}

stage_build() {
  say "build 12.2 out of tree from $SRC"
  [ -x "$SRC/configure" ] || die "no configure in $SRC"
  mkdir -p "$BUILD" "$INSTALL" "$OUT" || die mkdir
  # -DTRUE=1 -DFALSE=0 is what this host's headers need to compile the 12 tree
  ( cd "$BUILD" && "$SRC/configure" --prefix="$INSTALL" --enable-debug \
      --without-readline --without-zlib --without-icu \
      CFLAGS="${EXTRA_CFLAGS:--O2 -g -DTRUE=1 -DFALSE=0}" >"$OUT/configure.log" 2>&1 )
  [ $? -eq 0 ] || die "configure failed, see $OUT/configure.log"
  ( cd "$BUILD" && make -s -j"$JOBS" >"$OUT/make.log" 2>&1 )
  [ $? -eq 0 ] || die "make failed, see $OUT/make.log"
  ( cd "$BUILD" && make -s install >"$OUT/install.log" 2>&1 )
  [ $? -eq 0 ] || die "make install failed, see $OUT/install.log"
  "$INSTALL/bin/postgres" --version | tee "$OUT/version.txt"
}

stage_check() {
  say "make check"
  ( cd "$BUILD" && make check >"$OUT/check_core.log" 2>&1 )
  local rc=$?
  grep -E 'All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests failed' "$OUT/check_core.log" \
    | tee "$OUT/checks.txt"
  echo "core check exit status: $rc" | tee -a "$OUT/checks.txt"
}

stage_init() {
  say "initdb + start on port $PORT"
  # stop a postmaster this sandbox left behind: its shutdown would otherwise unlink
  # the socket of the cluster this stage is about to start
  if [ -f "$PGDATA/postmaster.pid" ]; then
    say "stopping the postmaster already running in $PGDATA"
    "$INSTALL/bin/pg_ctl" -D "$PGDATA" -m fast -w stop || die "could not stop it"
  fi
  rm -rf "$PGDATA" "$SOCK"
  mkdir -p "$SOCK" "$OUT" || die mkdir
  "$INSTALL/bin/initdb" -D "$PGDATA" --locale=C --encoding=UTF8 \
    >"$OUT/initdb.log" 2>&1 || die "initdb failed"
  # GUC contexts: shared_buffers/wal_level/max_wal_senders/max_replication_slots/fsync
  # are postmaster (restart); autovacuum/max_wal_size/checkpoint_timeout are sighup
  # (reload); maintenance_work_mem/work_mem are user (session scope).
  cat >>"$PGDATA/postgresql.conf" <<EOF
port = $PORT
unix_socket_directories = '$SOCK'
listen_addresses = ''
shared_buffers = 256MB
maintenance_work_mem = 256MB
work_mem = 64MB
fsync = off
autovacuum = off
max_wal_size = 16GB
min_wal_size = 1GB
checkpoint_timeout = 1h
wal_level = logical
max_wal_senders = 8
max_replication_slots = 8
max_parallel_maintenance_workers = 0
max_parallel_workers_per_gather = 0
log_min_messages = warning
log_checkpoints = on
EOF
  "$INSTALL/bin/pg_ctl" -D "$PGDATA" -l "$OUT/server.log" -w start || die "start failed"
  "$INSTALL/bin/psql" -X -h "$SOCK" -p "$PORT" -d postgres -c \
    "DROP /* wiki_iobig_reset */ DATABASE IF EXISTS $DB" >/dev/null
  "$INSTALL/bin/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK" -p "$PORT" -d postgres -c \
    "CREATE /* wiki_iobig_db */ DATABASE $DB" || die "createdb failed"
  : >"$RES"
  Q "SELECT version()" >"$OUT/serverversion.txt"
  Q "SELECT name || '=' || setting FROM pg_settings
     WHERE name IN ('block_size','wal_block_size','data_checksums','shared_buffers',
                    'wal_level','fsync','full_page_writes','wal_compression',
                    'maintenance_work_mem',
                    'autovacuum','max_parallel_maintenance_workers')
     ORDER BY name" >"$OUT/settings.txt"
  cat "$OUT/settings.txt"
}

sql_header() {
  cat <<'EOF'
\set ON_ERROR_STOP on
SET statement_timeout = '60min';
SET lock_timeout = '30s';
SET client_min_messages = debug1;
EOF
}

stage_fixture() {
  say "fixtures ($ROWS rows in the main table)"
  PSQL -d "$DB" >"$OUT/fixture.log" 2>&1 <<EOF
$(sql_header)
-- disposable fixtures
DROP /* wiki_iobig_fixture */ TABLE IF EXISTS t_alter, t_add, t_ctl, fk_child, fk_parent,
  t_pad_tail, t_pad_hole, t_iocl_a, t_iocl_b, t_min_a, t_min_b, t_toast CASCADE;

CREATE /* wiki_iobig_fixture */ TABLE t_alter (
  id int NOT NULL,
  grp int NOT NULL,
  txt text NOT NULL
);
INSERT /* wiki_iobig_fixture */ INTO t_alter
  SELECT g, g % 1000, 'row' || g FROM generate_series(1, $ROWS) g;
ALTER /* wiki_iobig_fixture */ TABLE t_alter ADD PRIMARY KEY (id);
CREATE /* wiki_iobig_fixture */ INDEX t_alter_grp_idx ON t_alter (grp);

-- byte-identical twin for the add-column + backfill route
CREATE /* wiki_iobig_fixture */ TABLE t_add (LIKE t_alter INCLUDING ALL);
INSERT /* wiki_iobig_fixture */ INTO t_add SELECT * FROM t_alter;

-- control: varchar -> text is binary coercible, so no rewrite is expected
CREATE /* wiki_iobig_fixture */ TABLE t_ctl (
  id int NOT NULL PRIMARY KEY,
  v varchar(32) NOT NULL
);
INSERT /* wiki_iobig_fixture */ INTO t_ctl
  SELECT g, 'row' || g FROM generate_series(1, $ROWS) g;

-- alignment pair: (int,int) grows, (int,float8) has a padding hole to spend
CREATE /* wiki_iobig_fixture */ TABLE t_pad_tail (a int NOT NULL, b int NOT NULL);
INSERT /* wiki_iobig_fixture */ INTO t_pad_tail
  SELECT g, g FROM generate_series(1, 1000000) g;
CREATE /* wiki_iobig_fixture */ TABLE t_pad_hole (a int NOT NULL, d float8 NOT NULL);
INSERT /* wiki_iobig_fixture */ INTO t_pad_hole
  SELECT g, g::float8 FROM generate_series(1, 1000000) g;

-- read-shape pair for the v17 read stream: two identical tables, one altered at
-- the default io_combine_limit and one at 8kB
CREATE /* wiki_iobig_fixture */ TABLE t_iocl_a (id int NOT NULL, txt text NOT NULL);
INSERT /* wiki_iobig_fixture */ INTO t_iocl_a
  SELECT g, 'row' || g FROM generate_series(1, 1000000) g;
CREATE /* wiki_iobig_fixture */ TABLE t_iocl_b (LIKE t_iocl_a INCLUDING ALL);
INSERT /* wiki_iobig_fixture */ INTO t_iocl_b SELECT * FROM t_iocl_a;

-- small table for the wal_level = minimal legs
CREATE /* wiki_iobig_fixture */ TABLE t_min_a (id int NOT NULL, txt text NOT NULL);
INSERT /* wiki_iobig_fixture */ INTO t_min_a
  SELECT g, 'row' || g FROM generate_series(1, 500000) g;
CREATE /* wiki_iobig_fixture */ TABLE t_min_b (LIKE t_min_a INCLUDING ALL);
INSERT /* wiki_iobig_fixture */ INTO t_min_b SELECT * FROM t_min_a;

-- a tiny heap with a large TOAST table: 8000 rows of about 12.8 kB, stored
-- out of line and uncompressed so the toast bytes are what they look like
CREATE /* wiki_iobig_fixture */ TABLE t_toast (id int NOT NULL, blob text NOT NULL);
ALTER /* wiki_iobig_fixture */ TABLE t_toast ALTER COLUMN blob SET STORAGE EXTERNAL;
INSERT /* wiki_iobig_fixture */ INTO t_toast
  SELECT g, (SELECT string_agg(md5(random()::text), '')
             FROM generate_series(1, 400))
  FROM generate_series(1, 8000) g;

-- extended statistics over the column that will be widened
CREATE /* wiki_iobig_fixture */ STATISTICS t_alter_stx (ndistinct)
  ON id, grp FROM t_alter;

-- foreign key pair: child keeps int, parent widens to bigint
CREATE /* wiki_iobig_fixture */ TABLE fk_parent (id int PRIMARY KEY);
INSERT /* wiki_iobig_fixture */ INTO fk_parent
  SELECT g FROM generate_series(1, 200000) g;
CREATE /* wiki_iobig_fixture */ TABLE fk_child (
  id int PRIMARY KEY,
  p_id int NOT NULL REFERENCES fk_parent (id)
);
INSERT /* wiki_iobig_fixture */ INTO fk_child
  SELECT g, 1 + (g % 200000) FROM generate_series(1, $CHILDROWS) g;

VACUUM /* wiki_iobig_fixture */ (ANALYZE) t_alter, t_add, t_ctl, t_pad_tail,
  t_pad_hole, t_iocl_a, t_iocl_b, t_min_a, t_min_b, t_toast, fk_parent, fk_child;
CHECKPOINT /* wiki_iobig_fixture */;
EOF
  [ $? -eq 0 ] || die "fixture failed, see $OUT/fixture.log"
  Q "SELECT c.relname || '|' || pg_relation_size(c.oid) || '|' ||
            pg_table_size(c.oid) || '|' || pg_indexes_size(c.oid) || '|' ||
            c.relpages || '|' || c.reltuples || '|' || c.relallvisible
     FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relkind = 'r' ORDER BY 1" >"$OUT/fixture_sizes.txt"
  cat "$OUT/fixture_sizes.txt"
}

# measure_ddl <case> <relation> <ddl statement>
# Runs one DDL statement with before/after snapshots of size, WAL, buffer and
# /proc/<backend pid>/io counters, and the peak data-directory size taken while
# the statement's transaction is still open.
measure_ddl() {
  local c="$1" rel="$2" ddl="$3" extra="${4:-}"
  say "case $c: $ddl"
  Q "SELECT pg_stat_reset()" >/dev/null
  # 12.2 has no pg_stat_io, so there is no shared I/O view to reset here
  Q "CHECKPOINT /* wiki_iobig_${c} */" >/dev/null
  record "$c" "size_before" "$(Q "SELECT pg_relation_size('$rel')")"
  record "$c" "index_count" "$(Q "SELECT count(*) FROM pg_index WHERE indrelid = '$rel'::regclass")"
  record "$c" "table_size_before" "$(Q "SELECT pg_table_size('$rel')")"
  record "$c" "indexes_size_before" "$(Q "SELECT pg_indexes_size('$rel')")"
  record "$c" "filenode_before" "$(Q "SELECT pg_relation_filenode('$rel')")"
  record "$c" "db_size_before" "$(Q "SELECT pg_database_size(current_database())")"
  record "$c" "datadir_before" "$(du -sb "$PGDATA" | cut -f1)"

  export CASE="$c" OUTDIR="$OUT" PGDATA
  PSQL -d "$DB" >"$OUT/${c}.log" 2>&1 <<EOF
$(sql_header)
$extra
SELECT pg_backend_pid() AS bpid \gset
\setenv BPID :bpid
SELECT pg_current_wal_lsn() AS lsn0 \gset
\! cat /proc/\$BPID/io > \$OUTDIR/\$CASE.io.before
\! date +%s%N > \$OUTDIR/\$CASE.t0
BEGIN;
$ddl
\! date +%s%N > \$OUTDIR/\$CASE.t1
\! du -sb \$PGDATA > \$OUTDIR/\$CASE.datadir_peak
COMMIT;
\! date +%s%N > \$OUTDIR/\$CASE.t2
\! cat /proc/\$BPID/io > \$OUTDIR/\$CASE.io.after
SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), :'lsn0') AS wal_bytes \gset
\setenv WALB :wal_bytes
\! echo \$WALB > \$OUTDIR/\$CASE.wal
EOF
  [ $? -eq 0 ] || die "case $c failed, see $OUT/${c}.log"

  iodelta "$c" "$OUT/${c}.io.before" "$OUT/${c}.io.after"
  record "$c" "wal_bytes" "$(cat "$OUT/${c}.wal")"
  record "$c" "ddl_ms" "$(( ( $(cat "$OUT/${c}.t1") - $(cat "$OUT/${c}.t0") ) / 1000000 ))"
  record "$c" "commit_ms" "$(( ( $(cat "$OUT/${c}.t2") - $(cat "$OUT/${c}.t1") ) / 1000000 ))"
  record "$c" "datadir_peak" "$(cut -f1 "$OUT/${c}.datadir_peak")"
  record "$c" "datadir_after" "$(du -sb "$PGDATA" | cut -f1)"
  record "$c" "size_after" "$(Q "SELECT pg_relation_size('$rel')")"
  record "$c" "table_size_after" "$(Q "SELECT pg_table_size('$rel')")"
  record "$c" "indexes_size_after" "$(Q "SELECT pg_indexes_size('$rel')")"
  record "$c" "filenode_after" "$(Q "SELECT pg_relation_filenode('$rel')")"
  record "$c" "db_size_after" "$(Q "SELECT pg_database_size(current_database())")"
  record "$c" "relpages_after" "$(Q "SELECT relpages FROM pg_class WHERE oid = '$rel'::regclass")"
  record "$c" "reltuples_after" "$(Q "SELECT reltuples FROM pg_class WHERE oid = '$rel'::regclass")"
  record "$c" "relallvisible_after" "$(Q "SELECT relallvisible FROM pg_class WHERE oid = '$rel'::regclass")"
  record "$c" "rewrite_debug_lines" "$(grep -c 'rewriting table' "$OUT/${c}.log")"
  record "$c" "heap_blks_read" "$(Q "SELECT coalesce(heap_blks_read,0) FROM pg_statio_all_tables WHERE relid = '$rel'::regclass")"
  record "$c" "heap_blks_hit" "$(Q "SELECT coalesce(heap_blks_hit,0) FROM pg_statio_all_tables WHERE relid = '$rel'::regclass")"
  record "$c" "idx_blks_read" "$(Q "SELECT coalesce(idx_blks_read,0) FROM pg_statio_all_tables WHERE relid = '$rel'::regclass")"
  record "$c" "pg_stat_io_present" \
    "$(Q "SELECT count(*) FROM pg_views WHERE viewname = 'pg_stat_io'")"
}

stage_alter() {
  measure_ddl alter_int_to_bigint t_alter \
    "ALTER /* wiki_alter_int_to_bigint */ TABLE t_alter ALTER COLUMN id TYPE bigint;"
}

stage_control() {
  measure_ddl control_varchar_to_text t_ctl \
    "ALTER /* wiki_alter_varchar_to_text */ TABLE t_ctl ALTER COLUMN v TYPE text;"
}

stage_align() {
  measure_ddl align_tail t_pad_tail \
    "ALTER /* wiki_alter_align_tail */ TABLE t_pad_tail ALTER COLUMN a TYPE bigint;"
  measure_ddl align_hole t_pad_hole \
    "ALTER /* wiki_alter_align_hole */ TABLE t_pad_hole ALTER COLUMN a TYPE bigint;"
}

stage_fk() {
  # the FK revalidation scan lands on fk_child, so record its counters too
  Q "SELECT pg_stat_reset()" >/dev/null
  measure_ddl fk_parent_widen fk_parent \
    "ALTER /* wiki_alter_fk_parent */ TABLE fk_parent ALTER COLUMN id TYPE bigint;"
  record fk_parent_widen child_heap_blks_read \
    "$(Q "SELECT coalesce(heap_blks_read,0) FROM pg_statio_all_tables WHERE relid = 'fk_child'::regclass")"
  record fk_parent_widen child_heap_blks_hit \
    "$(Q "SELECT coalesce(heap_blks_hit,0) FROM pg_statio_all_tables WHERE relid = 'fk_child'::regclass")"
  record fk_parent_widen child_idx_blks_read \
    "$(Q "SELECT coalesce(idx_blks_read,0) FROM pg_statio_all_tables WHERE relid = 'fk_child'::regclass")"
  record fk_parent_widen child_filenode \
    "$(Q "SELECT pg_relation_filenode('fk_child')")"
  record fk_parent_widen child_seq_scan \
    "$(Q "SELECT coalesce(seq_scan,0) FROM pg_stat_all_tables WHERE relid = 'fk_child'::regclass")"
  record fk_parent_widen fk_pfeqop \
    "$(Q "SELECT conpfeqop::text FROM pg_constraint WHERE conname LIKE 'fk_child_p_id%'")"
  record fk_parent_widen fk_convalidated \
    "$(Q "SELECT convalidated FROM pg_constraint WHERE conname LIKE 'fk_child_p_id%'")"
}

stage_addcol() {
  say "add-column + batched backfill route on t_add"
  local lsn0 pre_size pre_idx t0 t1
  Q "SELECT pg_stat_reset()" >/dev/null
  Q "CHECKPOINT /* wiki_iobig_addcol */" >/dev/null
  record addcol_backfill size_before "$(Q "SELECT pg_relation_size('t_add')")"
  record addcol_backfill table_size_before "$(Q "SELECT pg_table_size('t_add')")"
  record addcol_backfill indexes_size_before "$(Q "SELECT pg_indexes_size('t_add')")"
  record addcol_backfill filenode_before "$(Q "SELECT pg_relation_filenode('t_add')")"
  record addcol_backfill datadir_before "$(du -sb "$PGDATA" | cut -f1)"

  export OUTDIR="$OUT" PGDATA
  PSQL -d "$DB" -v batches="$BATCHES" -v rows="$ROWS" >"$OUT/addcol.log" 2>&1 <<'EOF'
\set ON_ERROR_STOP on
SET statement_timeout = '60min';
SET lock_timeout = '30s';
SET client_min_messages = debug1;
SET iobig.batches = :batches;
SET iobig.rows = :rows;
SELECT pg_backend_pid() AS bpid \gset
\setenv BPID :bpid
SELECT pg_current_wal_lsn() AS lsn0 \gset
\! cat /proc/$BPID/io > $OUTDIR/addcol.io.before
\! date +%s%N > $OUTDIR/addcol.t0

-- step 1: metadata-only add
ALTER /* wiki_addcol_new_bigint */ TABLE t_add ADD COLUMN id_new bigint;
SELECT pg_current_wal_lsn() AS lsn_add \gset
\! date +%s%N > $OUTDIR/addcol.t_add

-- step 2: batched backfill, one transaction per batch
DO /* wiki_addcol_backfill */ $$
DECLARE
  batches int := current_setting('iobig.batches')::int;
  total   bigint := current_setting('iobig.rows')::bigint;
  lo bigint; hi bigint; step bigint;
BEGIN
  step := (total / batches) + 1;
  lo := 1;
  WHILE lo <= total LOOP
    hi := lo + step - 1;
    UPDATE /* wiki_addcol_backfill */ t_add SET id_new = id
      WHERE id BETWEEN lo AND hi AND id_new IS DISTINCT FROM id;
    lo := hi + 1;
  END LOOP;
END $$;
SELECT pg_current_wal_lsn() AS lsn_fill \gset
\! date +%s%N > $OUTDIR/addcol.t_fill
\! du -sb $PGDATA > $OUTDIR/addcol.datadir_peak

-- step 3: the new column needs its own unique index; CONCURRENTLY keeps writers in
CREATE /* wiki_addcol_index */ UNIQUE INDEX CONCURRENTLY t_add_id_new_uq ON t_add (id_new);
SELECT pg_current_wal_lsn() AS lsn_idx \gset
\! date +%s%N > $OUTDIR/addcol.t_idx

-- step 4: swap the columns and promote the new index to the primary key
BEGIN;
ALTER /* wiki_addcol_swap */ TABLE t_add DROP COLUMN id;
ALTER /* wiki_addcol_swap */ TABLE t_add RENAME COLUMN id_new TO id;
ALTER /* wiki_addcol_swap */ TABLE t_add
  ADD CONSTRAINT t_add_pkey2 PRIMARY KEY USING INDEX t_add_id_new_uq;
COMMIT;
SELECT pg_current_wal_lsn() AS lsn_swap \gset
\! date +%s%N > $OUTDIR/addcol.t1
\! cat /proc/$BPID/io > $OUTDIR/addcol.io.after

SELECT pg_wal_lsn_diff(:'lsn_add', :'lsn0')     AS w_add,
       pg_wal_lsn_diff(:'lsn_fill', :'lsn_add') AS w_fill,
       pg_wal_lsn_diff(:'lsn_idx', :'lsn_fill') AS w_idx,
       pg_wal_lsn_diff(:'lsn_swap', :'lsn_idx') AS w_swap \gset
\setenv WADD :w_add
\setenv WFILL :w_fill
\setenv WIDX :w_idx
\setenv WSWAP :w_swap
\! echo $WADD > $OUTDIR/addcol.wal_add
\! echo $WFILL > $OUTDIR/addcol.wal_fill
\! echo $WIDX > $OUTDIR/addcol.wal_idx
\! echo $WSWAP > $OUTDIR/addcol.wal_swap
EOF
  [ $? -eq 0 ] || die "addcol failed, see $OUT/addcol.log"
  iodelta addcol_backfill "$OUT/addcol.io.before" "$OUT/addcol.io.after"
  record addcol_backfill wal_add_column "$(cat "$OUT/addcol.wal_add")"
  record addcol_backfill wal_backfill "$(cat "$OUT/addcol.wal_fill")"
  record addcol_backfill wal_index_build "$(cat "$OUT/addcol.wal_idx")"
  record addcol_backfill wal_swap "$(cat "$OUT/addcol.wal_swap")"
  record addcol_backfill add_ms "$(( ( $(cat "$OUT/addcol.t_add") - $(cat "$OUT/addcol.t0") ) / 1000000 ))"
  record addcol_backfill backfill_ms "$(( ( $(cat "$OUT/addcol.t_fill") - $(cat "$OUT/addcol.t_add") ) / 1000000 ))"
  record addcol_backfill index_ms "$(( ( $(cat "$OUT/addcol.t_idx") - $(cat "$OUT/addcol.t_fill") ) / 1000000 ))"
  record addcol_backfill swap_ms "$(( ( $(cat "$OUT/addcol.t1") - $(cat "$OUT/addcol.t_idx") ) / 1000000 ))"
  record addcol_backfill datadir_peak "$(cut -f1 "$OUT/addcol.datadir_peak")"
  record addcol_backfill datadir_after "$(du -sb "$PGDATA" | cut -f1)"
  record addcol_backfill size_after "$(Q "SELECT pg_relation_size('t_add')")"
  record addcol_backfill table_size_after "$(Q "SELECT pg_table_size('t_add')")"
  record addcol_backfill indexes_size_after "$(Q "SELECT pg_indexes_size('t_add')")"
  record addcol_backfill filenode_after "$(Q "SELECT pg_relation_filenode('t_add')")"
  record addcol_backfill n_dead_tup "$(Q "SELECT n_dead_tup FROM pg_stat_all_tables WHERE relid = 't_add'::regclass")"
  record addcol_backfill n_tup_upd "$(Q "SELECT n_tup_upd FROM pg_stat_all_tables WHERE relid = 't_add'::regclass")"
  record addcol_backfill n_tup_hot_upd "$(Q "SELECT n_tup_hot_upd FROM pg_stat_all_tables WHERE relid = 't_add'::regclass")"
  record addcol_backfill dropped_col_still_there \
    "$(Q "SELECT count(*) FROM pg_attribute WHERE attrelid = 't_add'::regclass AND attisdropped")"
  # after a VACUUM FULL the add-column route would match the rewrite's size; record
  # the plain-VACUUM outcome instead, which is what an operator actually gets
  Q "VACUUM /* wiki_addcol_after */ (ANALYZE) t_add" >/dev/null
  record addcol_backfill size_after_vacuum "$(Q "SELECT pg_relation_size('t_add')")"
  record addcol_backfill indexes_size_after_vacuum "$(Q "SELECT pg_indexes_size('t_add')")"
}

stage_catalog() {
  say "catalog aftermath of the rewrite (run after 'alter')"
  record catalog_after pg_statistic_rows_altered_col \
    "$(Q "SELECT count(*) FROM pg_statistic WHERE starelid = 't_alter'::regclass
          AND staattnum = (SELECT attnum FROM pg_attribute
                           WHERE attrelid = 't_alter'::regclass AND attname = 'id')")"
  record catalog_after extstats_object_present \
    "$(Q "SELECT count(*) FROM pg_statistic_ext WHERE stxrelid = 't_alter'::regclass")"
  record catalog_after extstats_data_rows \
    "$(Q "SELECT count(*) FROM pg_statistic_ext_data d JOIN pg_statistic_ext s ON s.oid = d.stxoid
          WHERE s.stxrelid = 't_alter'::regclass")"
  record catalog_after extstats_ndistinct_null \
    "$(Q "SELECT coalesce(bool_and(d.stxdndistinct IS NULL), true)::text
          FROM pg_statistic_ext_data d JOIN pg_statistic_ext s ON s.oid = d.stxoid
          WHERE s.stxrelid = 't_alter'::regclass")"
  record catalog_after reltuples "$(Q "SELECT reltuples FROM pg_class WHERE oid = 't_alter'::regclass")"
  record catalog_after relpages "$(Q "SELECT relpages FROM pg_class WHERE oid = 't_alter'::regclass")"
  record catalog_after relallvisible "$(Q "SELECT relallvisible FROM pg_class WHERE oid = 't_alter'::regclass")"
  record catalog_after vm_pages_on_disk \
    "$(Q "SELECT pg_relation_size('t_alter', 'vm')")"
  record catalog_after atttypid_is_int8 \
    "$(Q "SELECT (atttypid = 'bigint'::regtype)::text FROM pg_attribute
          WHERE attrelid = 't_alter'::regclass AND attname = 'id'")"
  record catalog_after attlen \
    "$(Q "SELECT attlen FROM pg_attribute WHERE attrelid = 't_alter'::regclass AND attname = 'id'")"
  record catalog_after attalign \
    "$(Q "SELECT attalign FROM pg_attribute WHERE attrelid = 't_alter'::regclass AND attname = 'id'")"
  # planner estimate before and after ANALYZE
  Q "EXPLAIN /* wiki_iobig_est */ SELECT * FROM t_alter" >"$OUT/explain_before_analyze.txt"
  record catalog_after explain_before_analyze \
    "$(grep -o 'rows=[0-9]*' "$OUT/explain_before_analyze.txt" | head -1)"
  Q "ANALYZE /* wiki_iobig_est */ t_alter" >/dev/null
  Q "EXPLAIN /* wiki_iobig_est */ SELECT * FROM t_alter" >"$OUT/explain_after_analyze.txt"
  record catalog_after explain_after_analyze \
    "$(grep -o 'rows=[0-9]*' "$OUT/explain_after_analyze.txt" | head -1)"
  record catalog_after reltuples_after_analyze \
    "$(Q "SELECT reltuples FROM pg_class WHERE oid = 't_alter'::regclass")"
  record catalog_after relallvisible_after_analyze \
    "$(Q "SELECT relallvisible FROM pg_class WHERE oid = 't_alter'::regclass")"
  Q "VACUUM /* wiki_iobig_est */ t_alter" >/dev/null
  record catalog_after relallvisible_after_vacuum \
    "$(Q "SELECT relallvisible FROM pg_class WHERE oid = 't_alter'::regclass")"
  record catalog_after vm_pages_after_vacuum \
    "$(Q "SELECT pg_relation_size('t_alter', 'vm')")"
  # sequence attached to a serial column is NOT widened by ALTER COLUMN TYPE
  Q "DROP /* wiki_iobig_seq */ TABLE IF EXISTS t_serial" >/dev/null
  Q "CREATE /* wiki_iobig_seq */ TABLE t_serial (id serial PRIMARY KEY, v int)" >/dev/null
  record catalog_after serial_seqtypid_before \
    "$(Q "SELECT format_type(seqtypid,null) FROM pg_sequence WHERE seqrelid = 't_serial_id_seq'::regclass")"
  Q "ALTER /* wiki_iobig_seq */ TABLE t_serial ALTER COLUMN id TYPE bigint" >/dev/null
  record catalog_after serial_seqtypid_after \
    "$(Q "SELECT format_type(seqtypid,null) FROM pg_sequence WHERE seqrelid = 't_serial_id_seq'::regclass")"
  record catalog_after serial_seqmax_after \
    "$(Q "SELECT seqmax FROM pg_sequence WHERE seqrelid = 't_serial_id_seq'::regclass")"
  Q "ALTER /* wiki_iobig_seq */ SEQUENCE t_serial_id_seq AS bigint" >/dev/null
  record catalog_after serial_seqmax_after_alter_sequence \
    "$(Q "SELECT seqmax FROM pg_sequence WHERE seqrelid = 't_serial_id_seq'::regclass")"
  # a view on the column blocks the ALTER outright
  Q "DROP /* wiki_iobig_view */ TABLE IF EXISTS t_view CASCADE" >/dev/null
  Q "CREATE /* wiki_iobig_view */ TABLE t_view (id int)" >/dev/null
  Q "CREATE /* wiki_iobig_view */ VIEW v_view AS SELECT id FROM t_view" >/dev/null
  PSQL -d "$DB" -c "ALTER /* wiki_iobig_view */ TABLE t_view ALTER COLUMN id TYPE bigint" \
    >"$OUT/view_block.log" 2>&1
  record catalog_after view_block_exit "$?"
  record catalog_after view_block_msg "$(grep -c 'used by a view or rule' "$OUT/view_block.log")"
}

stage_toast() {
  say "a 400 kB heap with a 100 MB TOAST table"
  record toast_widen toast_size_before \
    "$(Q "SELECT pg_relation_size(reltoastrelid) FROM pg_class WHERE oid = 't_toast'::regclass")"
  record toast_widen toast_filenode_before \
    "$(Q "SELECT pg_relation_filenode(reltoastrelid) FROM pg_class WHERE oid = 't_toast'::regclass")"
  record toast_widen total_size_before "$(Q "SELECT pg_total_relation_size('t_toast')")"
  measure_ddl toast_widen t_toast \
    "ALTER /* wiki_alter_toast_widen */ TABLE t_toast ALTER COLUMN id TYPE bigint;"
  record toast_widen toast_size_after \
    "$(Q "SELECT pg_relation_size(reltoastrelid) FROM pg_class WHERE oid = 't_toast'::regclass")"
  record toast_widen toast_filenode_after \
    "$(Q "SELECT pg_relation_filenode(reltoastrelid) FROM pg_class WHERE oid = 't_toast'::regclass")"
  record toast_widen toast_blks_read \
    "$(Q "SELECT coalesce(toast_blks_read,0) FROM pg_statio_all_tables WHERE relid = 't_toast'::regclass")"
  record toast_widen toast_blks_hit \
    "$(Q "SELECT coalesce(toast_blks_hit,0) FROM pg_statio_all_tables WHERE relid = 't_toast'::regclass")"
  record toast_widen tidx_blks_read \
    "$(Q "SELECT coalesce(tidx_blks_read,0) FROM pg_statio_all_tables WHERE relid = 't_toast'::regclass")"
  record toast_widen total_size_after "$(Q "SELECT pg_total_relation_size('t_toast')")"
}

stage_iocl() {
  say "read shape: 12.2 has no read stream and no io_combine_limit"
  measure_ddl iocl_default t_iocl_a \
    "ALTER /* wiki_alter_iocl_default */ TABLE t_iocl_a ALTER COLUMN id TYPE bigint;"
  measure_ddl iocl_8kb t_iocl_b \
    "ALTER /* wiki_alter_iocl_8kb */ TABLE t_iocl_b ALTER COLUMN id TYPE bigint;"
  record iocl_default io_combine_limit_present \
    "$(Q "SELECT count(*) FROM pg_settings WHERE name = 'io_combine_limit'")"
}

stage_minimal() {
  say "wal_level = minimal: 12.2 always skips WAL for the new heap, with no threshold GUC"
  # wal_level and max_wal_senders are PGC_POSTMASTER, so this needs a restart
  cp "$PGDATA/postgresql.conf" "$PGDATA/postgresql.conf.logical" || die cp
  cat >>"$PGDATA/postgresql.conf" <<EOF
wal_level = minimal
max_wal_senders = 0
EOF
  "$INSTALL/bin/pg_ctl" -D "$PGDATA" -l "$OUT/server.log" -w restart || die "restart failed"
  record minimal wal_level "$(Q "SHOW wal_level")"
  measure_ddl minimal_default t_min_a \
    "ALTER /* wiki_alter_minimal_default */ TABLE t_min_a ALTER COLUMN id TYPE bigint;"
  # there is no wal_skip_threshold in 12.2; run the same statement unchanged so the
  # pair is comparable with the 17 leg's second run
  record minimal wal_skip_threshold_present \
    "$(Q "SELECT count(*) FROM pg_settings WHERE name = 'wal_skip_threshold'")"
  measure_ddl minimal_thresh_high t_min_b \
    "ALTER /* wiki_alter_minimal_thresh */ TABLE t_min_b ALTER COLUMN id TYPE bigint;"
  cp "$PGDATA/postgresql.conf.logical" "$PGDATA/postgresql.conf" || die cp
  "$INSTALL/bin/pg_ctl" -D "$PGDATA" -l "$OUT/server.log" -w restart || die "restart failed"
  record minimal wal_level_restored "$(Q "SHOW wal_level")"
}

stage_logrep() {
  say "logical replication from an int publisher to a bigint subscriber"
  PSQL -d postgres >"$OUT/logrep_setup.log" 2>&1 <<EOF
$(sql_header)
DROP /* wiki_logrep */ DATABASE IF EXISTS lr_pub;
DROP /* wiki_logrep */ DATABASE IF EXISTS lr_sub;
CREATE /* wiki_logrep */ DATABASE lr_pub;
CREATE /* wiki_logrep */ DATABASE lr_sub;
EOF
  [ $? -eq 0 ] || die "logrep databases failed"
  PSQL -d lr_pub >>"$OUT/logrep_setup.log" 2>&1 <<EOF
$(sql_header)
CREATE /* wiki_logrep */ TABLE widen (id int PRIMARY KEY, v text NOT NULL);
INSERT /* wiki_logrep */ INTO widen
  SELECT g, 'row' || g FROM generate_series(1, 100000) g;
CREATE /* wiki_logrep */ PUBLICATION widen_pub FOR TABLE widen;
-- publisher and subscriber are the same cluster here, so the slot must be created
-- outside the CREATE SUBSCRIPTION transaction: that transaction has an xid of its
-- own, and the slot's snapshot build would wait for it forever
SELECT /* wiki_logrep */ slot_name
  FROM pg_create_logical_replication_slot('widen_slot', 'pgoutput');
EOF
  [ $? -eq 0 ] || die "publisher failed"
  PSQL -d lr_sub >>"$OUT/logrep_setup.log" 2>&1 <<EOF
$(sql_header)
CREATE /* wiki_logrep */ TABLE widen (id bigint PRIMARY KEY, v text NOT NULL);
CREATE /* wiki_logrep */ SUBSCRIPTION widen_sub
  CONNECTION 'host=$SOCK port=$PORT dbname=lr_pub'
  PUBLICATION widen_pub
  WITH (create_slot = false, slot_name = 'widen_slot');
EOF
  [ $? -eq 0 ] || die "subscription failed"
  local i rows=0
  for i in $(seq 1 60); do
    rows=$(PSQL -d lr_sub -A -t -c "SELECT count(*) FROM widen")
    [ "$rows" = "100000" ] && break
    sleep 1
  done
  record logrep initial_copy_rows "$rows"
  record logrep publisher_type "$(PSQL -d lr_pub -A -t -c \
    "SELECT format_type(atttypid,atttypmod) FROM pg_attribute
     WHERE attrelid='widen'::regclass AND attname='id'")"
  record logrep subscriber_type "$(PSQL -d lr_sub -A -t -c \
    "SELECT format_type(atttypid,atttypmod) FROM pg_attribute
     WHERE attrelid='widen'::regclass AND attname='id'")"
  # incremental change replicates too
  PSQL -d lr_pub -c "INSERT /* wiki_logrep */ INTO widen VALUES (2000000001, 'big')" >/dev/null
  for i in $(seq 1 30); do
    rows=$(PSQL -d lr_sub -A -t -c "SELECT count(*) FROM widen WHERE id = 2000000001")
    [ "$rows" = "1" ] && break
    sleep 1
  done
  record logrep incremental_row_arrived "$rows"
  record logrep subscriber_max_id "$(PSQL -d lr_sub -A -t -c "SELECT max(id) FROM widen")"
  # 12.2 has no binary subscription option at all, which is why the trap the 17 leg
  # measures cannot be reached here
  PSQL -d lr_sub -c "ALTER /* wiki_logrep_binary */ SUBSCRIPTION widen_sub SET (binary = true)" \
    >"$OUT/logrep_binary.log" 2>&1
  record logrep binary_option_accepted "$?"
  record logrep binary_option_unrecognized \
    "$(grep -c 'unrecognized subscription parameter' "$OUT/logrep_binary.log")"
  PSQL -d lr_pub -c "INSERT /* wiki_logrep_binary */ INTO widen VALUES (2000000002, 'bin')" >/dev/null
  sleep 8
  record logrep binary_row_arrived "$(PSQL -d lr_sub -A -t -c \
    "SELECT count(*) FROM widen WHERE id = 2000000002")"
  PSQL -d lr_sub -c "ALTER /* wiki_logrep */ SUBSCRIPTION widen_sub DISABLE" >/dev/null 2>&1
  PSQL -d lr_sub -c "ALTER /* wiki_logrep */ SUBSCRIPTION widen_sub SET (slot_name = NONE)" >/dev/null 2>&1
  PSQL -d lr_sub -c "DROP /* wiki_logrep */ SUBSCRIPTION widen_sub" >/dev/null 2>&1
  PSQL -d lr_pub -c "SELECT /* wiki_logrep */ pg_drop_replication_slot('widen_slot')" >/dev/null 2>&1
  record logrep slots_left "$(PSQL -d postgres -A -t -c "SELECT count(*) FROM pg_replication_slots")"
  PSQL -d postgres -c "DROP /* wiki_logrep */ DATABASE lr_sub" >/dev/null 2>&1
  PSQL -d postgres -c "DROP /* wiki_logrep */ DATABASE lr_pub" >/dev/null 2>&1
}

stage_report() {
  say "report"
  {
    echo "# PostgreSQL 12 leg: int -> bigint I/O measurements"
    echo "# $(cat "$OUT/serverversion.txt" 2>/dev/null)"
    echo "# rows=$ROWS childrows=$CHILDROWS batches=$BATCHES port=$PORT"
    echo
    printf '%-26s %-26s %s\n' CASE METRIC VALUE
    sort -k1,1 -s "$RES" | while IFS=$'\t' read -r a b c; do
      printf '%-26s %-26s %s\n' "$a" "$b" "$c"
    done
  } >"$OUT/report.txt"
  cat "$OUT/report.txt"
}

stage_clean() {
  say "clean: stop server and delete sandbox pieces"
  if [ -f "$PGDATA/postmaster.pid" ]; then
    "$INSTALL/bin/pg_ctl" -D "$PGDATA" -m fast -w stop
  fi
  sleep 1
  if [ -f "$PGDATA/postmaster.pid" ]; then echo "WARNING: postmaster.pid survives"; fi
  pgrep -a postgres
  echo "pgrep exit: $?"
}

# one run at a time: a second concurrent run would re-initdb the data directory
# under the first one's postmaster
LOCK="$SANDBOX/.lock12"
mkdir "$LOCK" 2>/dev/null || die "another leg12 run holds $LOCK"
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

stages=("$@")
[ ${#stages[@]} -eq 0 ] && stages=(build check init fixture alter catalog control align toast
                                   iocl fk addcol minimal logrep report)
for s in "${stages[@]}"; do
  case "$s" in
    build) stage_build ;;
    check) stage_check ;;
    init) stage_init ;;
    fixture) stage_fixture ;;
    alter) stage_alter ;;
    catalog) stage_catalog ;;
    control) stage_control ;;
    align) stage_align ;;
    toast) stage_toast ;;
    iocl) stage_iocl ;;
    fk) stage_fk ;;
    addcol) stage_addcol ;;
    minimal) stage_minimal ;;
    logrep) stage_logrep ;;
    report) stage_report ;;
    clean) stage_clean ;;
    *) die "unknown stage: $s" ;;
  esac
done
date +%FT%T%z >"$OUT/STAGES_DONE"
say "all stages done: ${stages[*]}"
```

## Context Reviewed

- `ALTER TABLE` entry and dispatch in the pinned 17 tree: `AlterTableGetLockLevel`,
  `ATPrepCmd`/`ATExecCmd` for `AT_AlterColumnType`, `ATPrepAlterColumnType`,
  `ATColumnChangeRequiresRewrite`, `ATExecAlterColumnType`,
  `RememberAllDependentForRebuilding`, `RememberIndexForRebuilding`,
  `RememberConstraintForRebuilding`, `RememberStatisticsForRebuilding`,
  `ATPostAlterTypeCleanup`, `ATPostAlterTypeParse`, `TryReuseIndex`,
  `TryReuseForeignKey`, `ATRewriteTables`, `ATRewriteTable`, `ATGetQueueEntry`,
  `ATExecAddColumn`'s missing-value path, and `MergeAttributesIntoExisting`.
- The rewrite machinery it shares with `CLUSTER` and `VACUUM FULL`: `make_new_heap`,
  `swap_relation_files`, `finish_heap_swap`, and the one
  `pgstat_progress_start_command` call site in `cluster.c`.
- Heap access paths: `heap_insert`, `heap_prepare_insert`, `heap_toast_insert_or_update`
  via `toast_tuple_init`, `GetBulkInsertState`/`FreeBulkInsertState`,
  `RelationGetBufferForTuple` and `RelationAddBlocks` in `hio.c`, `initscan`'s strategy
  choice, and the read-stream setup in `heap_beginscan`.
- Buffer strategy and I/O accounting: `GetAccessStrategy`, `GetAccessStrategyWithSize`,
  `IOContextForStrategy`.
- WAL and storage: `RelationNeedsWAL`, `smgrDoPendingSyncs`, `log_newpage_range`, and
  the `wal_skip_threshold` definition in both `storage.c` and `guc_tables.c`.
- Catalog and planner aftermath: `heap_create_with_catalog`'s zeroed statistics,
  `index_update_stats`, `RemoveStatistics`, `estimate_rel_size`'s density branches.
- Type and tuple layout: `pg_type.dat` for `int4`/`int8`, `pg_cast.dat` for the
  `int4` -> `int8` entry, `pg_operator.dat` for `=(int8,int4)`,
  `heap_compute_data_size`, `heap_form_tuple`, `heap_deform_tuple`,
  `att_align_nominal`.
- Foreign keys: `ATAddForeignKeyConstraint`'s `old_check_ok` logic,
  `addFkRecurseReferenced`/`addFkRecurseReferencing`, `validateForeignKeyConstraint`,
  `RI_Initial_Check`.
- Logical replication: `logicalrep_rel_open`, `logicalrep_rel_att_by_name`,
  `slot_store_data`'s text and binary branches.
- Documentation: `ref/alter_table.sgml` Notes on rewrites, double disk space, combining
  subcommands, `DROP COLUMN`, and MVCC safety.
- Tests: `src/test/regress/sql/alter_table.sql` (`check_ddl_rewrite`,
  `skip_wal_skip_rewrite_index`, the `alter a type bigint` foreign-key case, the
  partitioned no-rewrite case) and `src/test/regress/sql/fast_default.sql`.
- Source history in the 17 checkout, with presence tests at `REL_12_0` through
  `REL_17_0` for `wal_skip_threshold`, `RelationAddBlocks`,
  `read_stream_begin_relation`, `reltuples = -1`, `RememberStatisticsForRebuilding`,
  `TABLE_INSERT_SKIP_WAL`, `StatisticExtRelationId` in `tablecmds.c`, `pg_stat_io`,
  `io_combine_limit`, the subscription `binary` option, and the two v17 dependency
  errors; plus `REL_12_0`'s `ATRewriteTable` comment and
  `UpdateStatisticsForTypeChange` read through `git show`.
- Measurement run of 2026-09-17 on both legs, from the two scripts filed above, on the
  pins named in `## Measurement Script`. `make check` All 225 (17.11) and All 192
  (12.2), 0 `ERROR`/`FATAL` lines in either measurement cluster's log except the two
  deliberate ones (the view blocker and the `binary = true` apply failure). The
  intermediate runs of the same day are superseded: an earlier 17 run reported
  `/proc/<pid>/io` deltas copied from a previous run because `cp` could not overwrite
  the mode-0400 snapshot files, which is why the filed scripts use `cat > file`.

## Evidence Map

| Claim | Evidence |
|---|---|
| `int` -> `bigint` is a function cast, so a rewrite is mandatory | [pg_cast.dat#L41-L42](../../../../raw/postgres-17/src/include/catalog/pg_cast.dat#L41-L42), [tablecmds.c#ATColumnChangeRequiresRewrite](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13099-L13153), measured `rewriting table` DEBUG1 line and a changed relfilenode on every `bigint` case, 0 on the `varchar` -> `text` control |
| The statement holds `AccessExclusiveLock` to commit | [tablecmds.c#AlterTableGetLockLevel](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L4494-L4506) |
| Other tables' constraints force `AccessExclusiveLock` on those tables | [tablecmds.c:13939-13951](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13939-L13951) |
| The rewrite is a new heap plus a swap plus a full reindex | [tablecmds.c:5758-5881](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L5758-L5881), [cluster.c#finish_heap_swap](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1476-L1508) |
| Reads = old heap once + new heap once per index | [tablecmds.c:6181-6194](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L6181-L6194), [cluster.c:1490-1508](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1490-L1508); measured 25,469 + 2 x 25,536 = 76,541 = 72,413 read + 4,128 hit on 17.11, and 76,425 on 12.2 |
| One WAL record per copied row | [heapam.c#heap_insert](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2196-L2279); measured 427,512,848 bytes of WAL for a 209,190,912-byte new heap plus 118,243,328 bytes of indexes |
| Writes go through a 16 MB bulk-write ring | [heapam.c#GetBulkInsertState](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2037-L2052), [freelist.c#BAS_BULKWRITE](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L551-L573); measured 23,488 `bulkwrite` blocks in `pg_stat_io` |
| Disk peaks at old plus new until commit | [cluster.c:1476-1490](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1476-L1490); measured +327,442,432 bytes at peak against 327,434,240 predicted, back to +466,944 after commit |
| The v17 read stream combines the scan's reads | [heapam.c:1237-1259](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1237-L1259); measured 341 read calls for 5,406 blocks, 5,407 at `io_combine_limit = '8kB'`, 5,406 on 12.2 |
| `wal_level = minimal` removes the copy's WAL; `wal_skip_threshold` decides fsync against WAL at commit | [rel.h#RelationNeedsWAL](../../../../raw/postgres-17/src/include/utils/rel.h#L620-L631), [storage.c#smgrDoPendingSyncs](../../../../raw/postgres-17/src/backend/catalog/storage.c#L769-L847); measured 161,016 bytes at the 2 MB default against 26,315,416 bytes at `'4GB'` |
| TOAST is read, re-toasted and WAL-logged | [heapam.c#heap_prepare_insert](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2348-L2362), [toast_helper.c:129-147](../../../../raw/postgres-17/src/backend/access/table/toast_helper.c#L129-L147); measured 110,927,872 bytes read and 111,148,848 bytes of WAL for a 417,792-byte main fork |
| A referenced-side widening rescans the referencing table | [tablecmds.c:9922-9934](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L9922-L9934), [ri_triggers.c#RI_Initial_Check](../../../../raw/postgres-17/src/backend/utils/adt/ri_triggers.c#L1441-L1476); measured `conpfeqop = {416}`, one `seq_scan`, all 8,850 child pages touched, child relfilenode unchanged |
| Row width grows by 0 or 8 bytes, not 4 | [pg_type.dat#int8](../../../../raw/postgres-17/src/include/catalog/pg_type.dat#L55-L59), [heaptuple.c#heap_compute_data_size](../../../../raw/postgres-17/src/backend/access/common/heaptuple.c#L211-L256); measured 0% on `(int,float8)` and `(int,int,text)`, +18% on `(int,text)`, +23% on `(int,int)` |
| No per-column statistics survive; extended statistics data does not either | [tablecmds.c:13415-13418](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13415-L13418), [tablecmds.c:13975-14004](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13975-L14004); measured 0 `pg_statistic` rows on both, and 0 `pg_statistic_ext_data` rows on 17.11 against 1 with non-null `stxdndistinct` on 12.2 |
| The visibility map is empty afterwards | [tablecmds.c:6026-6042](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L6026-L6042), [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2788-L2857); measured `relallvisible` 0 and a 0-byte `vm` fork, then 25,478 and 8,192 bytes after `VACUUM` |
| A `serial` sequence is not widened | [tablecmds.c:13527-13534](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13527-L13534); measured `seqtypid` `integer` and `seqmax` 2147483647 after the column became `bigint` |
| No progress view covers the rewrite | [cluster.c:323](../../../../raw/postgres-17/src/backend/commands/cluster.c#L323) as the only `pgstat_progress_start_command` call in the two files |
| A view on the column blocks the statement | [tablecmds.c:13570-13583](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13570-L13583); measured exit status 1 and one `used by a view or rule` line on both versions |
| Logical replication can widen the type, but not in binary mode | [relation.c:407-438](../../../../raw/postgres-17/src/backend/replication/logical/relation.c#L407-L438), [worker.c:807-862](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L807-L862); measured 100,000 rows copied `integer` -> `bigint`, then 0 rows applied under `binary = true` with 6 `insufficient data left in message` errors |
| `ADD COLUMN` is metadata-only unless the default is volatile | [tablecmds.c:7326-7370](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L7326-L7370); measured 23,904 bytes of WAL and 1 ms |
| The add-column route costs 3.8x the WAL and 2.15x the size | measured 1,634,508,136 bytes of WAL against 427,512,848, and 449,495,040 bytes of heap against 208,642,048, with `n_tup_hot_upd` 0 of 4,000,000 |

## Open Questions

1. **The 34 extra blocks on 17.11 are unattributed.** Every rewritten file came out 34
   blocks larger than on 12.2, including one fixture whose tuple length did not change.
   Bulk relation extension
   [hio.c:405-431](../../../../raw/postgres-17/src/backend/access/heap/hio.c#L405-L431)
   is the obvious candidate, because it can hand the bulk-insert state more blocks than
   the copy ends up using, but this page did not read the file's trailing pages to
   confirm they are empty, and did not test whether the 34 is a function of the number
   of pages or of the last extension's size.
2. **The scaling claim is arithmetic, not measured.** The "about 2.3 hours for 680 GB"
   figure extrapolates one 3,951 ms run at `fsync = off` on one local SSD with no
   concurrent load. Real hardware, `fsync = on`, replication and a live workload all
   change it, and the rewrite's rate is not proven to be linear over three orders of
   magnitude.
3. **`pg_statio_all_tables` read back zeros on 12.2 for the TOAST case.** The
   statement lasted 295 ms and the 12 statistics collector had not flushed when the
   view was queried, so that leg's `toast_blks_*` counters are 0 while `rchar` shows
   the full 110,927,872 bytes. The v15 shared-memory statistics rework removes the
   window, but this page did not re-measure the 12 leg with a sleep to prove that is
   the whole explanation.
4. **The `reltuples = -1` sentinel had no visible planner effect here.** 17.11 leaves
   -1 and 12.2 leaves 0, but both also leave `relpages = 0`, and
   `estimate_rel_size` takes its width-based density branch in either case
   [plancat.c#estimate_rel_size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1064-L1160).
   A state where the sentinel actually changes the estimate was not constructed.
5. **The two v17-only dependency errors were not exercised.** The function/procedure
   and publication-`WHERE` blockers are read from source and attributed to
   `42b041243c0` and `91e7115b177`; only the view blocker was run.
6. **Parallel index rebuilds were disabled.** The clusters ran
   `max_parallel_maintenance_workers = 0` so the index-rebuild numbers are serial. How
   much of the 3,951 ms a parallel B-tree build would remove is not measured here.
7. **One machine, one block size, one filesystem.** All figures are 8 kB blocks,
   `MAXALIGN` 8, x86_64, WSL2 on a single SSD-backed filesystem, with `fsync = off` so
   that write latency does not dominate. The block and syscall counts reproduced
   byte-for-byte across two runs of each leg; the millisecond figures did not and
   should be read as one sample.
8. **`wal_compression` was left off.** Its effect on a rewrite is stated from source
   (full-page images only) and was not measured.
9. **The add-column route was measured with one batch size.** Eight batches over
   4,000,000 rows, no `VACUUM` between batches, and the default `fillfactor`. A lower
   `fillfactor` or interleaved `VACUUM`s would change both the bloat and the WAL, and
   the crossover where that route becomes cheaper than a rewrite is not established.

## Source References

- Commands: [tablecmds.c](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L4494-L4506) lock level, [tablecmds.c#ATRewriteTables](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L5707-L5989) phase 3 and the foreign-key pass, [tablecmds.c#ATRewriteTable](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L5991-L6367) the copy loop, [tablecmds.c#ATExecAddColumn](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L7326-L7370) fast defaults, [tablecmds.c#ATAddForeignKeyConstraint](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L9808-L9993) the `old_check_ok` decision, [tablecmds.c#addFkRecurseReferencing](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L10476-L10500) queueing the check, [tablecmds.c#validateForeignKeyConstraint](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L12253-L12300), [tablecmds.c#ATPrepAlterColumnType](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L12822-L13097), [tablecmds.c#ATColumnChangeRequiresRewrite](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13099-L13153), [tablecmds.c#ATExecAlterColumnType](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13155-L13470), [tablecmds.c#RememberAllDependentForRebuilding](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13472-L13733), [tablecmds.c#ATPostAlterTypeCleanup](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L13869-L14060), [tablecmds.c#TryReuseIndex](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14320-L14345), [tablecmds.c#TryReuseForeignKey](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L14347-L14387), [tablecmds.c#MergeAttributesIntoExisting](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L15931-L15968).
- Rewrite machinery: [cluster.c#make_new_heap](../../../../raw/postgres-17/src/backend/commands/cluster.c#L687-L800), [cluster.c#swap_relation_files](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1061-L1239), [cluster.c#finish_heap_swap](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1437-L1560), [cluster.c:323](../../../../raw/postgres-17/src/backend/commands/cluster.c#L323).
- Heap: [heapam.c#initscan](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L403-L465), [heapam.c#heap_beginscan](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L1237-L1263), [heapam.c#GetBulkInsertState](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2037-L2064), [heapam.c#heap_insert](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2104-L2320), [heapam.c#heap_prepare_insert](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2323-L2363), [hio.c#RelationAddBlocks](../../../../raw/postgres-17/src/backend/access/heap/hio.c#L225-L433), [toast_helper.c#toast_tuple_init](../../../../raw/postgres-17/src/backend/access/table/toast_helper.c#L41-L162).
- Buffers and I/O: [freelist.c#GetAccessStrategy](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L540-L600), [freelist.c#IOContextForStrategy](../../../../raw/postgres-17/src/backend/storage/buffer/freelist.c#L757-L784), [read_stream.c#read_stream_begin_relation](../../../../raw/postgres-17/src/backend/storage/aio/read_stream.c#L389-L400).
- WAL and storage: [rel.h#RelationNeedsWAL](../../../../raw/postgres-17/src/include/utils/rel.h#L620-L631), [storage.c#wal_skip_threshold](../../../../raw/postgres-17/src/backend/catalog/storage.c#L39), [storage.c#smgrDoPendingSyncs](../../../../raw/postgres-17/src/backend/catalog/storage.c#L722-L860).
- Catalog and planner: [heap.c#heap_create_with_catalog](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1004-L1029), [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2788-L2860), [index.c:3126-3139](../../../../raw/postgres-17/src/backend/catalog/index.c#L3126-L3139), [plancat.c#estimate_rel_size](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1064-L1160).
- Types and tuples: [pg_type.dat#int8](../../../../raw/postgres-17/src/include/catalog/pg_type.dat#L55-L59), [pg_type.dat#int4](../../../../raw/postgres-17/src/include/catalog/pg_type.dat#L72-L76), [pg_cast.dat#int4-int8](../../../../raw/postgres-17/src/include/catalog/pg_cast.dat#L41-L42), [pg_operator.dat#int84eq](../../../../raw/postgres-17/src/include/catalog/pg_operator.dat#L281-L285), [heaptuple.c#heap_compute_data_size](../../../../raw/postgres-17/src/backend/access/common/heaptuple.c#L211-L256), [heaptuple.c#heap_deform_tuple](../../../../raw/postgres-17/src/backend/access/common/heaptuple.c#L1343-L1420), [tupmacs.h#att_align_nominal](../../../../raw/postgres-17/src/include/access/tupmacs.h#L114-L138).
- Foreign keys: [ri_triggers.c#RI_Initial_Check](../../../../raw/postgres-17/src/backend/utils/adt/ri_triggers.c#L1359-L1600).
- Logical replication: [relation.c#logicalrep_rel_open](../../../../raw/postgres-17/src/backend/replication/logical/relation.c#L380-L467), [worker.c#slot_store_data](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L799-L880).
- Index build memory: [nbtsort.c:365-431](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L365-L431).
- Settings: [guc_tables.c#maintenance_work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2465-L2474), [guc_tables.c#statement_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620), [guc_tables.c#lock_timeout](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2631), [guc_tables.c#max_wal_size](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2842-L2851), [guc_tables.c#wal_skip_threshold](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2924-L2933), [guc_tables.c#io_combine_limit](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3138-L3150), [guc_tables.c#max_parallel_maintenance_workers](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3409-L3417), [guc_tables.c#wal_compression](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4976-L4984), [guc_tables.c#wal_level](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4986-L4994).
- Documentation: [ref/alter_table.sgml#Notes](../../../../raw/postgres-17/doc/src/sgml/ref/alter_table.sgml#L1396-L1505).
- Tests: [alter_table.sql:791-796](../../../../raw/postgres-17/src/test/regress/sql/alter_table.sql#L791-L796), [alter_table.sql:1421-1426](../../../../raw/postgres-17/src/test/regress/sql/alter_table.sql#L1421-L1426), [alter_table.sql:1461-1470](../../../../raw/postgres-17/src/test/regress/sql/alter_table.sql#L1461-L1470), [alter_table.sql:1662-1720](../../../../raw/postgres-17/src/test/regress/sql/alter_table.sql#L1662-L1720), [fast_default.sql:1-10](../../../../raw/postgres-17/src/test/regress/sql/fast_default.sql#L1-L10).

## Navigation

- [v17/index](../../index.md)
- [wiki index](../../../index.md)
- [versions](../../../versions.md)
