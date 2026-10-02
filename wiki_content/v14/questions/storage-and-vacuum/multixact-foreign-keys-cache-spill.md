---
type: question
version: 14
pinned_commit: a92fbdfb830046e907813e9067b2c9de9708d600
verified: false
verified_by_agent: not yet
---

# How MultiXact Works in PostgreSQL 14, and How Foreign Keys and Other Operations Degrade Performance When the Local Cache Spills to Secondary Storage (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Short answer](#short-answer)
  - [How MultiXact works](#how-multixact-works)
  - [What the backend-local cache actually does](#what-the-backend-local-cache-actually-does)
  - [How foreign keys create MultiXacts](#how-foreign-keys-create-multixacts)
  - [Other operations and caller boundaries](#other-operations-and-caller-boundaries)
  - [Where performance can degrade](#where-performance-can-degrade)
  - [Observability in v14](#observability-in-v14)
  - [Mitigations and settings](#mitigations-and-settings)
  - [Build, generated artifacts, tools, and extensions](#build-generated-artifacts-tools-and-extensions)
  - [Test coverage and limits](#test-coverage-and-limits)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Explain how MultiXact works, and how foreign keys and other operations could lead to database engine performance degradation when the MultiXact local cache fills up and spills to secondary storage.

> Prompt note: this is a lightly grammar-corrected restatement of the original request, applied with the asker's approval per the wiki's prompt-hygiene rule.

## Answer

### Short answer

The premise needs one correction: PostgreSQL 14 does **not** spill the backend-local MultiXact cache to storage. When the cache already contains 256 entries, `mXactCachePut` inserts the new entry, removes the least-recently-used tail entry, and frees it with `pfree`; eviction performs no file write [multixact.c#mXactCachePut](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1713-L1761). Every newly created MultiXact has already been recorded in WAL and in the shared offsets/members SLRUs before it enters that local cache [multixact.c#MultiXactIdCreateFromMembers](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L771-L861).

Eviction can still make later work slower. For an MXID that still needs resolution, a backend-local miss can make `GetMultiXactIdMembers` read the shared MultiXact offsets and members SLRUs. An SLRU hit stays in shared memory; an SLRU miss invokes `pg_pread` on a `pg_multixact/` segment [multixact.c#GetMultiXactIdMembers](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1389-L1588) [slru.c#SimpleLruReadPage](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L394-L476). That is a **filesystem read request**, not proof of physical device I/O: `pg_pread` ultimately calls the operating system, which may satisfy the request from its page cache [pread.c#pg_pread](../../../../raw/postgres-14/src/port/pread.c#L26-L57) [monitoring.sgml#SLRU-cache-boundary](../../../../raw/postgres-14/doc/src/sgml/monitoring.sgml#L4893-L4910).

A foreign key reaches MultiXact creation when the referenced tuple already has locker or updater state that the new row lock must preserve. The referencing-side trigger issues `SELECT ... FOR KEY SHARE` on the matching referenced row [ri_triggers.c#RI_FKey_check](../../../../raw/postgres-14/src/backend/utils/adt/ri_triggers.c#L343-L404). The first locker normally stores its own transaction ID in the tuple's single `xmax`; a MultiXact is needed when another compatible locker, a live updater, or a committed updater must be preserved in that same field [heapam.c#compute_new_xmax_infomask](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L5255-L5532). Many MXIDs created cluster-wide do not by themselves overflow one cache: a specific backend must create or resolve more than 256 distinct MXIDs in one transaction before that backend starts evicting entries [multixact.c#cache-definition](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L296-L324) [multixact.c#AtEOXact_MultiXact](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1811-L1837).

The source exposes three distinct performance mechanisms:

1. hot-row locking and MXID creation modify tuple headers, write WAL, reserve IDs under `MultiXactGenLock`, and copy complete member arrays into WAL and SLRU state [heapam.c#heap_lock_tuple-WAL](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L5091-L5184) [multixact.c#GetNewMultiXactId](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1078-L1332);
2. local-cache misses can serialize briefly on the two exclusive SLRU control locks, wait on per-buffer locks, and issue SLRU file reads or dirty-victim writes [multixact.c#GetMultiXactIdMembers-SLRU](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1475-L1575) [slru.c#I/O-locking](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L16-L34);
3. sustained MXID/member allocation can eventually force more aggressive vacuuming and reach either the MXID-counter stop or the separate member-space stop [multixact.c#MXID-stop-and-warn](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1113-L1209) [multixact.c#member-stop-and-warn](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1231-L1301).

### How MultiXact works

#### Tuple representation and member statuses

A heap tuple has one `xmax` field [htup_details.h#HeapTupleFields](../../../../raw/postgres-14/src/include/access/htup_details.h#L121-L131). PostgreSQL sets `HEAP_XMAX_IS_MULTI` when that field contains a `MultiXactId` instead of one transaction ID [htup_details.h#HEAP_XMAX_IS_MULTI](../../../../raw/postgres-14/src/include/access/htup_details.h#L188-L208). The MultiXact manager maps that 32-bit ID to an array of `MultiXactMember` values; each member contains a transaction ID and a `MultiXactStatus` [multixact.c#overview](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L6-L25) [multixact.h#MultiXactMember](../../../../raw/postgres-14/src/include/access/multixact.h#L60-L64).

The six statuses distinguish four row-lock requests — `ForKeyShare`, `ForShare`, `ForNoKeyUpdate`, and `ForUpdate` — from the two updater/delete statuses `NoKeyUpdate` and `Update` [multixact.h#MultiXactStatus](../../../../raw/postgres-14/src/include/access/multixact.h#L36-L57). A MultiXact may contain one member, despite its name [multixact.c#singleton](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L6-L12), but `MultiXactIdCreateFromMembers` rejects a set with more than one updating member [multixact.c#one-updater](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L806-L821).

#### Creation, immutability, conflict checks, and waits

`compute_new_xmax_infomask` implements the heap decision:

- with no usable old `xmax`, it stores the current transaction ID directly, so one locker does not need an MXID [heapam.c#single-xid](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L5286-L5332);
- with an existing live MultiXact, it discards no-longer-interesting members when appropriate and calls `MultiXactIdExpand`; expansion never mutates the old MXID, but returns the old ID for an identical member or creates a new ID for the new member set [heapam.c#expand-decision](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L5333-L5389) [multixact.c#MultiXactIdExpand](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L432-L549);
- with another in-progress single locker/updater, it calls `MultiXactIdCreate` for both members; it preserves a committed updater in the same way, whether or not the tuple already has the committed hint bit [heapam.c#create-cases](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L5391-L5521);
- if the former locker finishes in the race between reading the tuple and checking transaction state, it retries as though no locker remained [heapam.c#finished-race](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L5522-L5532).

`MultiXactIdCreate` and `MultiXactIdExpand` feed `MultiXactIdCreateFromMembers`. That function sorts the set, reuses an identical current-transaction cache entry when possible, reserves an ID and member range, emits `XLOG_MULTIXACT_CREATE_ID`, writes offsets and members, and then caches the result [multixact.c#MultiXactIdCreate](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L389-L430) [multixact.c#MultiXactIdCreateFromMembers](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L771-L861). Reusing a member set matters when the same transactions lock many rows: the source names reduced I/O and wraparound pressure as the reason for the set lookup [multixact.c#mXactCacheGetBySet](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1615-L1660).

Readers do more than decode members. Heap visibility calls `MultiXactIdIsRunning`, which resolves the members and checks whether any member transaction is still active [multixact.c#MultiXactIdIsRunning](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L552-L622) [heapam_visibility.c#MultiXactIdIsRunning-callers](../../../../raw/postgres-14/src/backend/access/heap/heapam_visibility.c#L520-L670). Heap locking calls `DoesMultiXactIdConflict` to compare each live member's lock mode with the requested mode [heapam.c#DoesMultiXactIdConflict](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L7429-L7507). Blocking waits then walk the immutable member array and wait only for conflicting members from other backends; `NOWAIT` and `SKIP LOCKED` use the conditional form [heapam.c#Do_MultiXactIdWait](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L7509-L7639) [heapam.c#heap_lock_tuple-wait-policy](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L4909-L4945).

#### SLRU storage, WAL, recovery, and reclamation

PostgreSQL stores variable-length member arrays in two simple least-recently-used logs. The offsets SLRU maps each MXID to a member offset; the members SLRU packs transaction IDs and status bits [multixact.c#two-SLRUs](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L19-L25) [multixact.c#member-layout](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L95-L174). `MultiXactShmemInit` gives them the shared names `MultiXactOffset` and `MultiXactMember`, backing directories `pg_multixact/offsets` and `pg_multixact/members`, and fixed pools of 8 and 16 pages respectively [multixact.h#SLRU-buffers](../../../../raw/postgres-14/src/include/access/multixact.h#L30-L34) [multixact.c#MultiXactShmemInit](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1953-L2018).

Shared `MultiXactStateData` holds the next ID and member offset, the oldest cluster MXID, and ID/member safety limits. Two arrays record each backend's oldest possible membership and visibility horizons, with extra slots reserved for prepared transactions [multixact.c#MultiXactStateData](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L193-L280). Normal transaction end clears both backend slots and the local cache; `PREPARE TRANSACTION` transfers only the membership horizon into a prepared-transaction slot because the prepared transaction will perform no further MXID lookups [multixact.c#transaction-end-and-2PC](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1811-L1903).

Creation WAL covers zeroed offset/member pages and complete MXID definitions. Heap row-lock/update WAL records follow the MultiXact creation record, and checkpoints flush both dirty SLRUs [multixact.c#WAL-design](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L27-L49) [multixact.c#CheckPointMultiXact](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L2291-L2308). The `RM_MULTIXACT_ID` redo routine recreates zeroed pages, definitions, counters, and truncations during recovery [rmgrlist.h#RM_MULTIXACT_ID](../../../../raw/postgres-14/src/include/access/rmgrlist.h#L27-L38) [multixact.c#multixact_redo](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L3396-L3524).

Reclamation is horizon-driven, not cache-driven. A full/aggressive vacuum can advance a relation's `pg_class.relminmxid`; the database minimum becomes `pg_database.datminmxid`, and the cluster minimum is checkpoint state [multixact.c#horizon-design](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L51-L60) [multixact.c#per-backend-horizons](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L245-L280). `vac_truncate_clog` computes the oldest database value and calls `TruncateMultiXact`; truncation WAL-logs the change and removes whole old members and offsets segments [vacuum.c#TruncateMultiXact-call](../../../../raw/postgres-14/src/backend/commands/vacuum.c#L1738-L1822) [multixact.c#TruncateMultiXact](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L3079-L3273).

### What the backend-local cache actually does

#### Lifetime, contents, and exact cap

Each backend has a private doubly-linked list of `mXactCacheEnt` objects. An entry stores one MXID, its member count, and a variable-length member array [multixact.c#cache-definition](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L296-L324). `mXactCacheGetById` decodes an MXID from that list; `mXactCacheGetBySet` finds an identical sorted member set so creation can reuse an ID. Both move a hit to the head, making the tail least recently used [multixact.c#cache-lookups](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1615-L1710).

`MXactContext` is a child of `TopTransactionContext`. Commit, abort, and successful prepare discard the whole cache [multixact.c#mXactCachePut-context](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1724-L1731) [multixact.c#cache-cleanup](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1811-L1903). The post-call cap is exactly 256 entries: the 256th entry remains; insertion while the pre-insertion count is already 256 removes one tail entry and returns the count to 256 [multixact.c#MAX_CACHE_ENTRIES](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L313-L324) [multixact.c#mXactCachePut](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1713-L1761).

#### Eviction is not a spill

The eviction code calls `dlist_delete`, decrements the count, and `pfree`s the entry. It does not copy the evicted entry to an SLRU or file [multixact.c#mXactCachePut-eviction](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1745-L1760). Authoritative MXID state already entered WAL and the shared SLRUs during creation [multixact.c#CreateFromMembers-recording](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L823-L861).

Therefore “cache spill” should be read as **loss of a backend-local shortcut**. A later reference to that evicted MXID may follow the normal shared-SLRU read path. The same applies when a new transaction or another backend first needs to resolve that MXID, because the cache has transaction and backend scope [multixact.c#cache-lifetime](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L296-L312) [multixact.c#GetMultiXactIdMembers-cache-first](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1383-L1399).

#### When a cache miss reaches a file read

A cache miss does **not** imply storage I/O. After the validity and obsolete-lock-only checks, `GetMultiXactIdMembers` reads the offsets page and then the necessary members pages through the shared SLRU pools when it must resolve the definition [multixact.c#GetMultiXactIdMembers-SLRU](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1398-L1588). `SimpleLruReadPage` records `blks_hit` and returns immediately when the page is already resident [slru.c#SLRU-hit](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L406-L431).

Only an SLRU miss selects a free/LRU slot. A dirty victim is written before reuse; if all usable slots are I/O-busy, the caller waits and retries [slru.c#SlruSelectLRUPage](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L1002-L1146). The new page is then read from the segment file under `SLRURead`; the operating system may serve that request from its page cache [slru.c#SlruPhysicalReadPage](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L673-L738) [pread.c#pg_pread](../../../../raw/postgres-14/src/port/pread.c#L26-L57).

### How foreign keys create MultiXacts

#### Referencing-side checks

Foreign-key enforcement uses referential-integrity triggers. On a referencing-table `INSERT` or relevant `UPDATE`, `RI_FKey_check` first skips deleted/superseded trigger rows. All-null keys pass; under `MATCH SIMPLE`, any-null keys pass without querying the referenced table [ri_triggers.c#RI_FKey_check-early-exits](../../../../raw/postgres-14/src/backend/utils/adt/ri_triggers.c#L230-L338).

For a key that must be checked, the trigger opens the referenced relation with `RowShareLock`, prepares `SELECT 1 FROM [ONLY] <referenced> ... FOR KEY SHARE OF x`, and executes it. A partitioned referenced relation omits `ONLY` [ri_triggers.c#RI_FKey_check-query](../../../../raw/postgres-14/src/backend/utils/adt/ri_triggers.c#L264-L404). On the referenced-table `DELETE`/`UPDATE` side, `NO ACTION` and `RESTRICT` checks similarly query matching referencing rows with `FOR KEY SHARE` [ri_triggers.c#ri_restrict](../../../../raw/postgres-14/src/backend/utils/adt/ri_triggers.c#L614-L730).

The executor's `LockRows` node maps `FOR KEY SHARE` to `LockTupleKeyShare` and dispatches through `table_tuple_lock` [nodeLockRows.c#ExecLockRows](../../../../raw/postgres-14/src/backend/executor/nodeLockRows.c#L160-L190). For the built-in heap table access method, the callback is `heapam_tuple_lock`, which calls `heap_lock_tuple` [tableam.h#table_tuple_lock](../../../../raw/postgres-14/src/include/access/tableam.h#L1530-L1558) [heapam_handler.c#heapam_tuple_lock](../../../../raw/postgres-14/src/backend/access/heap/heapam_handler.c#L347-L367).

#### Exactly when an FK lock becomes a MultiXact

One `FOR KEY SHARE` locker normally leaves its own transaction ID in `xmax`, not an MXID [heapam.c#single-xid](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L5286-L5332). PostgreSQL creates or expands a MultiXact when it must preserve the new lock together with another live compatible member or a committed updater in the tuple header [heapam.c#compute_new_xmax_infomask](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L5333-L5521).

That can occur when concurrent FK checks lock the same referenced row, because key-share locks are mutually compatible. `FOR KEY SHARE` also coexists with `FOR NO KEY UPDATE`, the lock used by an update that does not change a key column; key-changing updates and deletes conflict and wait [mvcc.sgml#row-lock-modes](../../../../raw/postgres-14/doc/src/sgml/mvcc.sgml#L1248-L1307) [mvcc.sgml#row-lock-conflicts](../../../../raw/postgres-14/doc/src/sgml/mvcc.sgml#L1321-L1373). The `fk-contention` isolation test uses exactly that compatible case: one transaction inserts a referencing row for `foo(42)` while another updates only non-key column `foo.b` [fk-contention.spec](../../../../raw/postgres-14/src/test/isolation/specs/fk-contention.spec#L1-L19).

Row locks normally remain until transaction end, so long transactions enlarge the concurrency window in which members must coexist [mvcc.sgml#row-lock-lifetime](../../../../raw/postgres-14/doc/src/sgml/mvcc.sgml#L1209-L1215). The source does not establish that foreign keys are the most frequent MXID producer; it establishes the mechanism and the concurrency condition.

#### System-wide MXID creation is not local-cache pressure

Creation and reading are separate dimensions:

- `MultiXactIdCreateFromMembers` advances the shared MXID/member counters and changes WAL/SLRU state unless its exact member set is reusable in the current cache [multixact.c#CreateFromMembers](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L789-L861) [multixact.c#counter-advance](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1303-L1329).
- `GetMultiXactIdMembers` reads an existing definition and may add it to only the calling backend's local cache; that read does not allocate another MXID [multixact.c#GetMembers](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1336-L1588).
- Adding a distinct compatible locker to a still-live member set can create successive immutable MXIDs, but a local eviction begins only after one backend has accumulated more than 256 distinct cached definitions during one transaction [multixact.c#MultiXactIdExpand](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L432-L549) [multixact.c#mXactCachePut](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1713-L1761).

A hot referenced row can therefore drive row contention and system-wide member allocation without necessarily thrashing every backend's local cache. Conversely, a backend that resolves many different existing MXIDs can churn its cache without allocating new MXIDs [multixact.c#CreateFromMembers](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L789-L861) [multixact.c#GetMembers](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1336-L1588).

### Other operations and caller boundaries

MultiXacts are heap row-lock infrastructure, not an FK-specific object:

- **Explicit row locks.** `SELECT ... FOR KEY SHARE`, `FOR SHARE`, `FOR NO KEY UPDATE`, and `FOR UPDATE` all use `LockRows` and `table_tuple_lock`; compatible modes can become co-members, while conflicting modes follow the wait policy [nodeLockRows.c#ExecLockRows](../../../../raw/postgres-14/src/backend/executor/nodeLockRows.c#L160-L196) [heapam.c#heap_lock_tuple-waits](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L4909-L4945).
- **`UPDATE` and `DELETE`.** Both call `compute_new_xmax_infomask` so they can preserve surviving row lockers along with the updater/delete member [heapam.c#heap_delete](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L2990-L3004) [heapam.c#heap_update](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L3688-L3816). Locking later versions in an update chain calls the same helper recursively [heapam.c#heap_lock_updated_tuple_rec](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L5840-L5935).
- **Executor and internal locking paths.** `ON CONFLICT DO UPDATE`, EvalPlanQual retries for `UPDATE`/`DELETE`, trigger tuple fetches, and logical-replication apply lookups call `table_tuple_lock`; they can reach the same heap callback when a heap row already has compatible lockers [nodeModifyTable.c#delete-retry-lock](../../../../raw/postgres-14/src/backend/executor/nodeModifyTable.c#L1320-L1365) [nodeModifyTable.c#update-retry-lock](../../../../raw/postgres-14/src/backend/executor/nodeModifyTable.c#L1980-L2028) [nodeModifyTable.c#ExecOnConflictUpdate](../../../../raw/postgres-14/src/backend/executor/nodeModifyTable.c#L2155-L2197) [trigger.c#GetTupleForTrigger](../../../../raw/postgres-14/src/backend/commands/trigger.c#L3106-L3140) [execReplication.c#table_tuple_lock](../../../../raw/postgres-14/src/backend/executor/execReplication.c#L140-L184).
- **Freezing and rewrites.** When old members must be removed, `FreezeMultiXactId` creates a replacement MXID if at least one surviving locker must remain, possibly with an updater; a sole surviving updater becomes a plain XID. Other branches keep the old MXID or invalidate `xmax` [heapam.c#FreezeMultiXactId](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L6687-L6974). Lazy VACUUM calls the freeze preparation path, while heap rewrites used by operations such as `CLUSTER` call the non-WAL-logging wrapper and provide their own WAL treatment [vacuumlazy.c#heap_prepare_freeze_tuple](../../../../raw/postgres-14/src/backend/access/heap/vacuumlazy.c#L1923-L1935) [heapam.c#heap_freeze_tuple](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L7252-L7279) [rewriteheap.c#heap_freeze_tuple](../../../../raw/postgres-14/src/backend/access/heap/rewriteheap.c#L385-L395).

The `table_tuple_lock` interface is an access-method callback. The built-in heap AM uses `heap_lock_tuple`; a foreign table is delegated to its FDW by `LockRows`, and another table AM can implement different storage semantics [tableam.h#tuple_lock-callback](../../../../raw/postgres-14/src/include/access/tableam.h#L518-L539) [heapam_handler.c#heap-callback](../../../../raw/postgres-14/src/backend/access/heap/heapam_handler.c#L2555-L2569) [nodeLockRows.c#foreign-table-boundary](../../../../raw/postgres-14/src/backend/executor/nodeLockRows.c#L125-L158).

### Where performance can degrade

#### Hot-row and creation-path work

The row itself can be the first bottleneck. Row locking changes the tuple header, dirties its heap page, and emits heap-lock WAL for WAL-logged relations [heapam.c#heap_lock_tuple-WAL](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L5091-L5184). Compatible lock-mode pairs can coexist but still need to be represented; incompatible lockers/updaters wait on member transactions [heapam.c#Do_MultiXactIdWait](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L7509-L7639).

Every non-reused MXID reservation takes `MultiXactGenLock` exclusively. Page-boundary extension can zero SLRU pages and emit WAL before the shared counters advance [multixact.c#GetNewMultiXactId](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1078-L1108) [multixact.c#ExtendMultiXact](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L2535-L2631). Creation WAL contains the full `nmembers` array, and `RecordNewMultiXact` loops over every member, so creation work and recorded member bytes grow with the member count [multixact.c#CreateFromMembers-WAL](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L837-L855) [multixact.c#RecordNewMultiXact](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L869-L1074).

`RecordNewMultiXact` no longer holds `MultiXactOffsetSLRULock` for its whole body. Commit `2bb60eb4fea` moved the acquisition later: the lock is now taken around the recovery-only next-page zeroing and released again, then reacquired immediately before the offsets `SimpleLruReadPage` [multixact.c#RecordNewMultiXact-offsets-lock](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L946-L981) [multixact.c:989](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L989). The reason is a self-deadlock: that recovery-only branch calls `SimpleLruWriteAll`, which acquires the same control lock, so replaying multixact WAL written by an older minor version deadlocked against the entry-time acquisition [multixact.c:941](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L941) [slru.c#SimpleLruWriteAll](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L1156-L1190). Normal creation therefore holds the offsets control lock over a shorter section than it did before that commit.

#### Cache misses, SLRU contention, and file reads

A local-cache hit avoids SLRU access. A resolving miss acquires `MultiXactOffsetSLRULock` and `MultiXactMemberSLRULock` in exclusive mode around SLRU lookup/state changes; unlike `SimpleLruReadPage_ReadOnly`, this path has no shared-lock resident-page fast path [multixact.c#GetMembers-exclusive-locks](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1475-L1575) [slru.c#SimpleLruReadPage_ReadOnly](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L480-L525). Concurrent SLRU lookups can therefore wait on the two control locks even when the requested pages are resident.

The SLRU code marks a miss read-busy, acquires that slot's per-buffer lock, releases the control lock during the file read, and reacquires it to publish the page. Dirty writes follow the same lock handoff [slru.c#SimpleLruReadPage-I/O](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L434-L476) [slru.c#SlruInternalWritePage](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L527-L607). This limits how long the global control lock covers I/O, but sessions needing the same busy slot wait on `MultiXactOffsetBuffer` or `MultiXactMemberBuffer`, and a small 8/16-page pool can replace pages as the working set moves across more pages [slru.c#SimpleLruWaitIO](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L333-L375) [slru.c#SlruSelectLRUPage](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L1002-L1146).

An SLRU miss increments `blks_read` after the filesystem read; a hit increments `blks_hit` [slru.c#SLRU-read-counters](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L406-L476). Neither counter reveals whether the earlier backend-local lookup hit, and `blks_read` does not distinguish an operating-system page-cache hit from device access [monitoring.sgml#pg_stat_slru-blocks](../../../../raw/postgres-14/doc/src/sgml/monitoring.sgml#L4893-L4919).

#### Member growth, aggressive vacuum, and hard stops

Each new definition reserves `nmembers` positions and advances the 32-bit `nextOffset` counter, skipping zero at wraparound [multixact.c#member-reservation](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1217-L1229) [multixact.c#counter-advance](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1303-L1329). Space is reclaimed only after relation/database/cluster horizons advance enough for whole old segments to be removed [multixact.c#TruncateMultiXact](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L3029-L3273).

When more than half the member address space is in use, `MultiXactMemberFreezeThreshold` progressively lowers the effective `autovacuum_multixact_freeze_max_age`, potentially to zero. That makes autovacuum selection and manual VACUUM freezing more aggressive [multixact.c#MultiXactMemberFreezeThreshold](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L2936-L3003) [autovacuum.c#effective-multixact-age](../../../../raw/postgres-14/src/backend/postmaster/autovacuum.c#L2022-L2028). An aggressive vacuum visits every page that might contain unfrozen XIDs/MXIDs, but it can still skip pages known all-frozen; it is not an unconditional read of every heap page [maintenance.sgml#aggressive-MXID-vacuum](../../../../raw/postgres-14/doc/src/sgml/maintenance.sgml#L750-L772).

The documentation gives approximate thresholds of 10 GB for more frequent aggressive scans and 20 GB at member wraparound [maintenance.sgml#member-storage](../../../../raw/postgres-14/doc/src/sgml/maintenance.sgml#L774-L783). There are two independent hard stops:

- the MXID counter refuses commands that need a new MXID within three million IDs of its wrap limit [multixact.c#MXID-stop-condition](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1141-L1168) [multixact.c#SetMultiXactIdLimit](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L2365-L2419);
- the member counter raises `multixact "members" limit exceeded` when the requested member range would cross `offsetStopLimit` [multixact.c#member-stop-condition](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1231-L1267).

Both stop only commands that need a new MXID, not every write [maintenance.sgml#MXID-exhaustion-boundary](../../../../raw/postgres-14/doc/src/sgml/maintenance.sgml#L793-L819).

### Observability in v14

`pg_stat_slru` has separate `MultiXactOffset` and `MultiXactMember` rows. `blks_hit` counts shared-SLRU hits; `blks_read` counts SLRU file reads; `blks_written` counts SLRU page writes; `stats_reset` marks the counter epoch [system_views.sql#pg_stat_slru](../../../../raw/postgres-14/src/backend/catalog/system_views.sql#L866-L877) [pgstat.c#SLRU-names](../../../../raw/postgres-14/src/backend/postmaster/pgstat.c#L141-L165) [monitoring.sgml#pg_stat_slru](../../../../raw/postgres-14/doc/src/sgml/monitoring.sgml#L4841-L4955). Compare deltas over a workload interval. These counters have no query, relation, foreign-key, or backend-local-cache attribution.

The exact v14 LWLock wait names are easy to get wrong. `lwlocknames.txt` calls the C symbols `MultiXactGenLock`, `MultiXactOffsetSLRULock`, `MultiXactMemberSLRULock`, and `MultiXactTruncationLock`, but the build generator removes the final `Lock` from user-visible names [lwlocknames.txt#MultiXact-locks](../../../../raw/postgres-14/src/backend/storage/lmgr/lwlocknames.txt#L19-L23) [lwlocknames.txt#truncation-lock](../../../../raw/postgres-14/src/backend/storage/lmgr/lwlocknames.txt#L47-L50) [generate-lwlocknames.pl#strip-Lock](../../../../raw/postgres-14/src/backend/storage/lmgr/generate-lwlocknames.pl#L28-L58). Therefore `pg_stat_activity.wait_event` reports `MultiXactGen`, `MultiXactOffsetSLRU`, `MultiXactMemberSLRU`, and `MultiXactTruncation`; the per-buffer names are `MultiXactOffsetBuffer` and `MultiXactMemberBuffer` [monitoring.sgml#MultiXact-waits](../../../../raw/postgres-14/doc/src/sgml/monitoring.sgml#L1960-L1983) [lwlock.c#buffer-tranches](../../../../raw/postgres-14/src/backend/storage/lmgr/lwlock.c#L130-L140).

`SLRURead` and `SLRUWrite` are generic I/O wait names used by all SLRUs, so a current `SLRURead` wait alone cannot identify MultiXact as the source [slru.c#SLRURead](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L673-L729) [slru.c#SLRUWrite](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L755-L876). `pg_stat_activity` exposes current wait type/name, not a history of completed waits [system_views.sql#pg_stat_activity](../../../../raw/postgres-14/src/backend/catalog/system_views.sql#L812-L838).

`mxid_age(pg_class.relminmxid)` finds relations with old MXID horizons, while `pg_get_multixact_members(xid)` resolves one known MXID [pg_proc.dat#mxid_age](../../../../raw/postgres-14/src/include/catalog/pg_proc.dat#L2371-L2378) [pg_proc.dat#pg_get_multixact_members](../../../../raw/postgres-14/src/include/catalog/pg_proc.dat#L6068-L6072). The latter itself calls `GetMultiXactIdMembers` and can raise an error for a truncated or future MXID, so use it for targeted diagnosis rather than an unbounded relation scan [multixact.c#GetMembers-range-errors](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1414-L1447) [multixact.c#pg_get_multixact_members](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L3527-L3590).

These read-only queries were checked against the pinned v14 checkout. The timeouts are session-scoped:

```sql
SET /* wiki_multixact_statement_timeout */ statement_timeout = '30s';
SET /* wiki_multixact_lock_timeout */ lock_timeout = '5s';

SELECT /* wiki_multixact_slru_io */
       name, blks_zeroed, blks_hit, blks_read, blks_written,
       flushes, truncates, stats_reset
FROM pg_stat_slru
WHERE name IN ('MultiXactOffset', 'MultiXactMember')
ORDER BY name;

SELECT /* wiki_multixact_current_waits */
       wait_event_type, wait_event, count(*) AS waiting_backends
FROM pg_stat_activity
WHERE wait_event IN ('MultiXactGen',
                     'MultiXactOffsetSLRU', 'MultiXactMemberSLRU',
                     'MultiXactOffsetBuffer', 'MultiXactMemberBuffer',
                     'MultiXactTruncation',
                     'SLRURead', 'SLRUWrite', 'SLRUSync', 'SLRUFlushSync')
GROUP BY wait_event_type, wait_event
ORDER BY waiting_backends DESC, wait_event_type, wait_event;

SELECT /* wiki_multixact_relation_age */
       n.nspname, c.relname, c.relminmxid,
       mxid_age(c.relminmxid) AS multixact_age
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'm', 't')
ORDER BY multixact_age DESC
LIMIT 50;
```

The first query measures shared-SLRU activity, not the 256-entry local cache. The second can attribute the six named LWLock waits to MultiXact, but the four generic SLRU I/O waits need correlation with `pg_stat_slru` deltas and workload timing. The third identifies old relation horizons, not current cache churn.

### Mitigations and settings

PostgreSQL 14 has no GUC for either cache size. `MAX_CACHE_ENTRIES` is a source constant, and the two SLRU page counts are compile-time constants [multixact.c#MAX_CACHE_ENTRIES](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L313-L324) [multixact.h#SLRU-buffers](../../../../raw/postgres-14/src/include/access/multixact.h#L30-L34).

Use levers that match the observed mechanism:

- For hot referenced rows, reduce concurrent transactions that hold locks on the same key and shorten those transactions. This reduces the interval during which compatible members must coexist; it also reduces conflicting row-lock waits [mvcc.sgml#row-lock-lifetime](../../../../raw/postgres-14/doc/src/sgml/mvcc.sgml#L1209-L1215) [mvcc.sgml#row-lock-conflicts](../../../../raw/postgres-14/doc/src/sgml/mvcc.sgml#L1321-L1373).
- Do not infer local-cache churn from total MXID creation alone. Confirm shared-SLRU reads/waits and relation ages over the same workload interval before changing vacuum policy [multixact.c#cache-vs-create](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L789-L861) [system_views.sql#pg_stat_slru](../../../../raw/postgres-14/src/backend/catalog/system_views.sql#L866-L877).
- Keep aggressive vacuum able to advance every old relation/database horizon. Evicting a cache entry advances no horizon, and vacuuming one hot table is insufficient while another relation or database still pins the cluster minimum [maintenance.sgml#horizon-advancement](../../../../raw/postgres-14/doc/src/sgml/maintenance.sgml#L750-L772) [vacuum.c#TruncateMultiXact-call](../../../../raw/postgres-14/src/backend/commands/vacuum.c#L1738-L1822).
- Do not drop stale replication slots as an MXID remedy. Unlike XID wraparound, replication slots do not directly hold back multixact cleanup, so dropping them is not normally relevant to resolving MXID wraparound; commit `802dc79df63` added that documentation statement and dropped the `or drop stale replication slots` clause from all six MXID wraparound `errhint()` texts [maintenance.sgml#replication-slots-and-MXID](../../../../raw/postgres-14/doc/src/sgml/maintenance.sgml#L803-L808) [multixact.c#GetNewMultiXactId-hints](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1160-L1201) [multixact.c#SetMultiXactIdLimit-hints](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L2478-L2489).

The direct MultiXact vacuum GUCs are:

| Setting | Context | Apply requirement | Default | Direct role |
|---|---|---|---|---|
| `vacuum_multixact_freeze_min_age` | `PGC_USERSET` | session/transaction; configuration-default changes take reload | 5,000,000 | Replacement cutoff while VACUUM scans [guc.c#vacuum_multixact_freeze_min_age](../../../../raw/postgres-14/src/backend/utils/misc/guc.c#L2637-L2645) |
| `vacuum_multixact_freeze_table_age` | `PGC_USERSET` | session/transaction; configuration-default changes take reload | 150,000,000 | Age that makes VACUUM aggressive [guc.c#vacuum_multixact_freeze_table_age](../../../../raw/postgres-14/src/backend/utils/misc/guc.c#L2647-L2655) |
| `autovacuum_multixact_freeze_max_age` | `PGC_POSTMASTER` | **server restart** | 400,000,000 | Forces anti-wraparound autovacuum and caps the two ages above [guc.c#autovacuum_multixact_freeze_max_age](../../../../raw/postgres-14/src/backend/utils/misc/guc.c#L3292-L3301) |
| `vacuum_multixact_failsafe_age` | `PGC_USERSET` | session/transaction; configuration-default changes take reload | 1,600,000,000 | During a VACUUM, disables cost delay and bypasses nonessential work after the failsafe threshold [guc.c#vacuum_multixact_failsafe_age](../../../../raw/postgres-14/src/backend/utils/misc/guc.c#L2675-L2682) [config.sgml#vacuum_multixact_failsafe_age](../../../../raw/postgres-14/doc/src/sgml/config.sgml#L8910-L8939) |

Lowering the two `PGC_USERSET` freeze ages in one session affects VACUUM run by that session; changing their configuration defaults for future/manual and autovacuum sessions requires a reload, not a restart. Lower values trade earlier horizon advancement for more freezing/aggressive scan work. VACUUM also caps the effective minimum age at half, and the table age at 95%, of the effective max age [vacuum.c#multixact-freeze-limits](../../../../raw/postgres-14/src/backend/commands/vacuum.c#L1059-L1156). `MultiXactMemberFreezeThreshold` can lower that effective max age further regardless of the configured value [multixact.c#MultiXactMemberFreezeThreshold](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L2967-L3003).

Per-table and `toast.` storage parameters exist for `autovacuum_multixact_freeze_min_age`, `autovacuum_multixact_freeze_max_age`, and `autovacuum_multixact_freeze_table_age` [create_table.sgml#MultiXact-reloptions](../../../../raw/postgres-14/doc/src/sgml/ref/create_table.sgml#L1704-L1752). They affect autovacuum, are stored in `pg_class.reloptions`, and use `ShareUpdateExclusiveLock` when changed; they need neither reload nor restart [reloptions.c#MultiXact-reloptions](../../../../raw/postgres-14/src/backend/access/common/reloptions.c#L263-L305) [alter_table.sgml#SET-storage-parameters](../../../../raw/postgres-14/doc/src/sgml/ref/alter_table.sgml#L737-L760). Autovacuum extracts them, and the per-table max can tighten but never loosen the effective cluster maximum [autovacuum.c#reloption-extraction](../../../../raw/postgres-14/src/backend/postmaster/autovacuum.c#L2784-L2813) [autovacuum.c#MultiXact-reloptions-use](../../../../raw/postgres-14/src/backend/postmaster/autovacuum.c#L2928-L2995) [autovacuum.c#per-table-max-cap](../../../../raw/postgres-14/src/backend/postmaster/autovacuum.c#L3181-L3205).

### Build, generated artifacts, tools, and extensions

- `multixact.c` is compiled into the backend's transaction-manager objects [access/transam/Makefile#multixact.o](../../../../raw/postgres-14/src/backend/access/transam/Makefile#L15-L35).
- `mxid_age` and `pg_get_multixact_members` are declared in `pg_proc.dat`. Catalog generation consumes that file for `postgres.bki` and generated catalog headers, while `Gen_fmgrtab.pl` consumes it for generated fmgr tables/prototypes [pg_proc.dat#MultiXact-functions](../../../../raw/postgres-14/src/include/catalog/pg_proc.dat#L2371-L2378) [pg_proc.dat#pg_get_multixact_members](../../../../raw/postgres-14/src/include/catalog/pg_proc.dat#L6068-L6072) [catalog/Makefile#generated-catalogs](../../../../raw/postgres-14/src/backend/catalog/Makefile#L50-L106) [utils/Makefile#fmgr-generation](../../../../raw/postgres-14/src/backend/utils/Makefile#L47-L52).
- `lwlocknames.h` and `lwlocknames.c` are generated from `lwlocknames.txt`; the generator's suffix removal is why SQL wait names omit `Lock` [storage/lmgr/Makefile#lwlocknames](../../../../raw/postgres-14/src/backend/storage/lmgr/Makefile#L37-L42) [generate-lwlocknames.pl#strip-Lock](../../../../raw/postgres-14/src/backend/storage/lmgr/generate-lwlocknames.pl#L28-L58).
- `rmgrlist.h` macro-expands the MultiXact WAL resource manager into both backend recovery and `pg_waldump`; `mxactdesc.c` renders zero-page, create, and truncate records [rmgr.c#RmgrTable](../../../../raw/postgres-14/src/backend/access/transam/rmgr.c#L8-L38) [rmgrlist.h#RM_MULTIXACT_ID](../../../../raw/postgres-14/src/include/access/rmgrlist.h#L27-L38) [pg_waldump/rmgrdesc.c#RmgrDescTable](../../../../raw/postgres-14/src/bin/pg_waldump/rmgrdesc.c#L8-L40) [mxactdesc.c#MultiXact-WAL-descriptions](../../../../raw/postgres-14/src/backend/access/rmgrdesc/mxactdesc.c#L49-L105).
- Contrib `pgrowlocks` calls `GetMultiXactIdMembers` and renders each stored member's mode plus a current PID lookup. A broad `pgrowlocks` scan can therefore perform the same member lookups discussed above [pgrowlocks.c#MultiXact-members](../../../../raw/postgres-14/contrib/pgrowlocks/pgrowlocks.c#L140-L247). Contrib `amcheck` does not decode member arrays in its range check; it validates a tuple's MXID against `relminmxid` and the cached cluster oldest/next range [verify_heapam.c#MXID-state](../../../../raw/postgres-14/contrib/amcheck/verify_heapam.c#L78-L109) [verify_heapam.c#check_mxid_valid_in_rel](../../../../raw/postgres-14/contrib/amcheck/verify_heapam.c#L1636-L1694).

### Test coverage and limits

PostgreSQL 14 has direct correctness coverage for the main row-lock semantics:

- `fk-contention` covers an FK key-share lock coexisting with a non-key update [fk-contention.spec](../../../../raw/postgres-14/src/test/isolation/specs/fk-contention.spec#L1-L19).
- `multixact-no-deadlock` covers reacquiring a held share lock while another transaction waits [multixact-no-deadlock.spec](../../../../raw/postgres-14/src/test/isolation/specs/multixact-no-deadlock.spec#L1-L35).
- `multixact-no-forget` covers preserving a key-share locker across updater commit/abort combinations [multixact-no-forget.spec](../../../../raw/postgres-14/src/test/isolation/specs/multixact-no-forget.spec#L1-L44).
- `tuplelock-conflict` exercises the complete row-lock conflict matrix with explicit MultiXact permutations [tuplelock-conflict.spec](../../../../raw/postgres-14/src/test/isolation/specs/tuplelock-conflict.spec#L1-L63).
- `nowait-2` and `skip-locked-2` cover conditional failure/skip behavior against MultiXact locks [nowait-2.spec](../../../../raw/postgres-14/src/test/isolation/specs/nowait-2.spec#L1-L37) [skip-locked-2.spec](../../../../raw/postgres-14/src/test/isolation/specs/skip-locked-2.spec#L1-L41).
- `freeze-the-dead` covers a MultiXact with an updater and key-share lockers across vacuum freezing/pruning [freeze-the-dead.spec](../../../../raw/postgres-14/src/test/isolation/specs/freeze-the-dead.spec#L1-L56).

Those seven MultiXact-relevant specs passed on an isolated build of the previous pin `5c00f4e2e3bcee6931ae93429d53f7c2a4f46156` (14.23). The suite was not re-run for the 2026-08-17 repin to 14.24, which added one spec, `ddl-dependency-locking`, so the schedule now has 107 entries [isolation_schedule:107](../../../../raw/postgres-14/src/test/isolation/isolation_schedule#L107).

The absence result still holds at the new pin. The schedule contains direct correctness tests, but no test references `MAX_CACHE_ENTRIES`, the local-cache functions, `MultiXactOffset`/`MultiXactMember` SLRU statistics, or `SLRURead`; the checkout therefore has no direct cache-eviction, SLRU-thrash, or performance benchmark [isolation_schedule](../../../../raw/postgres-14/src/test/isolation/isolation_schedule#L1-L107) [multixact.c#MAX_CACHE_ENTRIES](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L313-L324).

## Context Reviewed

- Repin review (2026-08-17): moved the v14 pin from `5c00f4e2e3bcee6931ae93429d53f7c2a4f46156` (14.23) to `a92fbdfb830046e907813e9067b2c9de9708d600` (14.24, `REL_14_24-6-ga92fbdfb830`) and reviewed all 133 commits in the range. Three touched this page's claims or citations: `802dc79df63` rewrote the six MXID wraparound `errhint()` texts and documented that replication slots do not hold back multixact cleanup, `2bb60eb4fea` moved the `MultiXactOffsetSLRULock` acquisition later in `RecordNewMultiXact()`, and `5100bdbd3ba` added the `ddl-dependency-locking` isolation spec, taking the schedule to 107 entries. A fourth doc commit, `e3a4e9edd5c`, changed only XID-section wording in `maintenance.sgml`, outside every range cited here. Nothing was re-measured on 14.24.
- `src/backend/access/transam/multixact.c` and `src/include/access/multixact.h` — representation, shared/per-backend state, creation, duplicate-set reuse, reads, cache, 2PC, SLRU setup, WAL, recovery, limits, freeze threshold, truncation, and SQL member decoding.
- `src/backend/access/transam/slru.c`, `src/include/access/slru.h`, and `src/port/pread.c` — shared SLRU hit/miss, LRU replacement, control/per-buffer locks, file reads/writes, counters, and operating-system call boundary.
- `src/backend/access/heap/heapam.c`, `heapam_handler.c`, `heapam_visibility.c`, `vacuumlazy.c`, and `rewriteheap.c` — tuple `xmax` decisions, waits, updates/deletes/update chains, visibility, freezing, and heap table-AM dispatch.
- `src/backend/utils/adt/ri_triggers.c`, `src/backend/executor/nodeLockRows.c`, `nodeModifyTable.c`, `execReplication.c`, and `src/backend/commands/trigger.c` — FK and adjacent tuple-lock callers.
- `src/include/access/htup_details.h`, `tableam.h`, `rmgrlist.h`, `src/backend/access/rmgrdesc/mxactdesc.c`, and `src/bin/pg_waldump/rmgrdesc.c` — tuple flags, AM boundary, and WAL resource-manager/tool boundary.
- `src/backend/commands/vacuum.c`, `src/backend/postmaster/autovacuum.c`, `src/backend/utils/misc/guc.c`, `src/backend/access/common/reloptions.c`, `doc/src/sgml/config.sgml`, `maintenance.sgml`, and `ref/create_table.sgml`/`ref/alter_table.sgml` — horizons, truncation, aggressive/failsafe behavior, GUCs, and reloptions.
- `src/backend/catalog/system_views.sql`, `src/backend/postmaster/pgstat.c`, `src/backend/utils/activity/wait_event.c`, `src/backend/storage/lmgr/lwlock.c`, `lwlocknames.txt`, and `generate-lwlocknames.pl` — SLRU statistics and exact wait names.
- `src/include/catalog/pg_proc.dat`, `src/backend/catalog/Makefile`, `src/backend/utils/Makefile`, `src/backend/storage/lmgr/Makefile`, and `src/backend/access/transam/Makefile` — SQL registration, generated artifacts, and build ownership.
- `contrib/pgrowlocks/pgrowlocks.c` and `contrib/amcheck/verify_heapam.c` — extension readout and integrity-check boundaries.
- Isolation specs and expected outputs for `fk-contention`, `multixact-no-deadlock`, `multixact-no-forget`, `tuplelock-conflict`, `nowait-2`, `skip-locked-2`, and `freeze-the-dead`; those seven MultiXact-relevant specs passed in `.wiki-runtime/` on the previous pin `5c00f4e2e3bcee6931ae93429d53f7c2a4f46156` (14.23), and the suite was not re-run for the 2026-08-17 repin to 14.24.
- The three filed diagnostic queries and both tagged timeout statements executed successfully against an isolated 14.23 PostgreSQL 14 server; the server was then stopped.
- Whole-checkout searches for local-cache instrumentation, `MAX_CACHE_ENTRIES` tests, MultiXact SLRU statistics/wait tests, and direct performance benchmarks; none were found.

## Evidence Map

| Claim | Primary evidence |
|---|---|
| MXID in tuple `xmax` represents a member array and status set | [multixact.c#overview](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L6-L25), [multixact.h#MultiXactStatus](../../../../raw/postgres-14/src/include/access/multixact.h#L36-L64), [htup_details.h#HEAP_XMAX_IS_MULTI](../../../../raw/postgres-14/src/include/access/htup_details.h#L188-L208) |
| One locker uses an XID; existing live lockers/updaters lead to create/expand | [heapam.c#compute_new_xmax_infomask](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L5255-L5532) |
| Expansion is immutable and filters dead members | [multixact.c#MultiXactIdExpand](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L432-L549) |
| Creation reuses an exact local set or reserves, WAL-logs, records, and caches a new MXID | [multixact.c#MultiXactIdCreateFromMembers](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L771-L861) |
| Conflict detection and waits walk member arrays and honor wait policy | [heapam.c#DoesMultiXactIdConflict](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L7429-L7507), [heapam.c#Do_MultiXactIdWait](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L7509-L7639) |
| Two shared SLRUs use 8 offset and 16 member pages under `pg_multixact/` | [multixact.h#SLRU-buffers](../../../../raw/postgres-14/src/include/access/multixact.h#L30-L34), [multixact.c#MultiXactShmemInit](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1953-L2018) |
| WAL/checkpoint/recovery rebuild and persist MultiXact state | [multixact.c#WAL-design](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L27-L49), [multixact.c#CheckPointMultiXact](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L2291-L2308), [multixact.c#multixact_redo](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L3396-L3524) |
| Horizon advancement and truncation reclaim SLRU segments | [multixact.c#horizon-design](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L51-L60), [vacuum.c#TruncateMultiXact-call](../../../../raw/postgres-14/src/backend/commands/vacuum.c#L1738-L1822), [multixact.c#TruncateMultiXact](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L3079-L3273) |
| Cache is backend-local, transaction-local, LRU, and capped at 256 entries | [multixact.c#cache-definition](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L296-L324), [multixact.c#cache-lookups](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1615-L1710), [multixact.c#mXactCachePut](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1713-L1761) |
| Eviction frees memory and does not write/spill the entry | [multixact.c#mXactCachePut-eviction](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1745-L1760) |
| Cache miss first reaches shared SLRU; only an SLRU miss requests a file read | [multixact.c#GetMultiXactIdMembers](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1389-L1588), [slru.c#SimpleLruReadPage](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L394-L476) |
| `pg_pread` does not prove physical device I/O | [slru.c#SlruPhysicalReadPage](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L673-L738), [pread.c#pg_pread](../../../../raw/postgres-14/src/port/pread.c#L26-L57) |
| Referencing-side FK checks issue `FOR KEY SHARE`, with null/partition edges | [ri_triggers.c#RI_FKey_check](../../../../raw/postgres-14/src/backend/utils/adt/ri_triggers.c#L230-L404) |
| FK key-share compatibility explains the hot-parent MultiXact path | [mvcc.sgml#row-lock-modes](../../../../raw/postgres-14/doc/src/sgml/mvcc.sgml#L1248-L1307), [fk-contention.spec](../../../../raw/postgres-14/src/test/isolation/specs/fk-contention.spec#L1-L19) |
| Creation traffic and one backend's cache pressure are distinct | [multixact.c#CreateFromMembers](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L789-L861), [multixact.c#GetMembers](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1336-L1588) |
| Explicit locks, UPDATE/DELETE, update chains, executor/trigger/apply paths reach heap locking | [nodeLockRows.c#ExecLockRows](../../../../raw/postgres-14/src/backend/executor/nodeLockRows.c#L160-L196), [heapam.c#heap_delete](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L2990-L3004), [heapam.c#heap_update](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L3688-L3816), [heapam.c#heap_lock_updated_tuple_rec](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L5840-L5935), [nodeModifyTable.c#ExecOnConflictUpdate](../../../../raw/postgres-14/src/backend/executor/nodeModifyTable.c#L2155-L2197), [execReplication.c#table_tuple_lock](../../../../raw/postgres-14/src/backend/executor/execReplication.c#L140-L184) |
| Freeze creates a replacement MXID only in one of several outcomes | [heapam.c#FreezeMultiXactId](../../../../raw/postgres-14/src/backend/access/heap/heapam.c#L6687-L6974) |
| MXID reservation uses `MultiXactGenLock`; full member arrays enter WAL/SLRU | [multixact.c#GetNewMultiXactId](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1078-L1332), [multixact.c#RecordNewMultiXact](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L869-L1074) |
| Member reads use exclusive SLRU control locks but release them for I/O | [multixact.c#GetMembers-exclusive-locks](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1475-L1575), [slru.c#SimpleLruReadPage-I/O](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L434-L476) |
| Member pressure lowers effective freeze age and makes VACUUM more aggressive | [multixact.c#MultiXactMemberFreezeThreshold](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L2936-L3003), [maintenance.sgml#aggressive-MXID-vacuum](../../../../raw/postgres-14/doc/src/sgml/maintenance.sgml#L750-L783) |
| MXID-counter and member-counter stops are separate | [multixact.c#MXID-stop-condition](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1141-L1168), [multixact.c#member-stop-condition](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1231-L1267) |
| SLRU counters do not expose local-cache hits or device-I/O certainty | [slru.c#SLRU-read-counters](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L406-L476), [monitoring.sgml#pg_stat_slru-blocks](../../../../raw/postgres-14/doc/src/sgml/monitoring.sgml#L4893-L4919) |
| User-visible MultiXact LWLock names omit `Lock` | [generate-lwlocknames.pl#strip-Lock](../../../../raw/postgres-14/src/backend/storage/lmgr/generate-lwlocknames.pl#L28-L58), [monitoring.sgml#MultiXact-waits](../../../../raw/postgres-14/doc/src/sgml/monitoring.sgml#L1960-L1983) |
| Four direct GUCs and three per-table reloptions have the stated scopes | [guc.c#MultiXact-vacuum-settings](../../../../raw/postgres-14/src/backend/utils/misc/guc.c#L2637-L2682), [guc.c#autovacuum_multixact_freeze_max_age](../../../../raw/postgres-14/src/backend/utils/misc/guc.c#L3292-L3301), [reloptions.c#MultiXact-reloptions](../../../../raw/postgres-14/src/backend/access/common/reloptions.c#L263-L305) |
| Build generation covers catalog/fmgr and user-visible LWLock names | [catalog/Makefile#generated-catalogs](../../../../raw/postgres-14/src/backend/catalog/Makefile#L50-L106), [utils/Makefile#fmgr-generation](../../../../raw/postgres-14/src/backend/utils/Makefile#L47-L52), [storage/lmgr/Makefile#lwlocknames](../../../../raw/postgres-14/src/backend/storage/lmgr/Makefile#L37-L42) |
| Core tests cover correctness, not cache eviction or SLRU performance | [isolation_schedule](../../../../raw/postgres-14/src/test/isolation/isolation_schedule#L1-L107), [multixact-no-forget.spec](../../../../raw/postgres-14/src/test/isolation/specs/multixact-no-forget.spec#L1-L44), [freeze-the-dead.spec](../../../../raw/postgres-14/src/test/isolation/specs/freeze-the-dead.spec#L1-L56) |
| Dropping stale replication slots does not resolve MXID wraparound | [maintenance.sgml#replication-slots-and-MXID](../../../../raw/postgres-14/doc/src/sgml/maintenance.sgml#L803-L808), [multixact.c#GetNewMultiXactId-hints](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L1160-L1201), [multixact.c#SetMultiXactIdLimit-hints](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L2478-L2489) |
| `RecordNewMultiXact` takes the offsets SLRU control lock late, not from entry | [multixact.c#RecordNewMultiXact-offsets-lock](../../../../raw/postgres-14/src/backend/access/transam/multixact.c#L946-L981), [slru.c#SimpleLruWriteAll](../../../../raw/postgres-14/src/backend/access/transam/slru.c#L1156-L1190) |

## Open Questions

- The pinned source establishes the mechanisms but contains no benchmark that quantifies latency or throughput as a function of FK concurrency, MXID member count, local-cache eviction rate, SLRU working-set size, operating-system cache state, or storage latency. Production magnitude is workload-specific and must be measured; this page makes no numeric performance claim.

## Source References

- [src/backend/access/transam/multixact.c](../../../../raw/postgres-14/src/backend/access/transam/multixact.c) — MultiXact manager, cache, SLRUs, WAL/recovery, horizons, limits, truncation, and SQL member decoder.
- [src/include/access/multixact.h](../../../../raw/postgres-14/src/include/access/multixact.h) — IDs, statuses, members, buffer constants, and WAL records.
- [src/backend/access/transam/slru.c](../../../../raw/postgres-14/src/backend/access/transam/slru.c) and [src/port/pread.c](../../../../raw/postgres-14/src/port/pread.c) — SLRU caching/locking/I/O and OS-read boundary.
- [src/backend/access/heap/heapam.c](../../../../raw/postgres-14/src/backend/access/heap/heapam.c), [heapam_handler.c](../../../../raw/postgres-14/src/backend/access/heap/heapam_handler.c), and [heapam_visibility.c](../../../../raw/postgres-14/src/backend/access/heap/heapam_visibility.c) — heap creation, waits, updates, freezing, AM dispatch, and visibility.
- [src/backend/utils/adt/ri_triggers.c](../../../../raw/postgres-14/src/backend/utils/adt/ri_triggers.c) — FK check/restrict SQL and early exits.
- [src/backend/executor/nodeLockRows.c](../../../../raw/postgres-14/src/backend/executor/nodeLockRows.c), [nodeModifyTable.c](../../../../raw/postgres-14/src/backend/executor/nodeModifyTable.c), [execReplication.c](../../../../raw/postgres-14/src/backend/executor/execReplication.c), and [src/backend/commands/trigger.c](../../../../raw/postgres-14/src/backend/commands/trigger.c) — tuple-lock callers.
- [src/backend/commands/vacuum.c](../../../../raw/postgres-14/src/backend/commands/vacuum.c), [src/backend/postmaster/autovacuum.c](../../../../raw/postgres-14/src/backend/postmaster/autovacuum.c), and [src/backend/access/heap/vacuumlazy.c](../../../../raw/postgres-14/src/backend/access/heap/vacuumlazy.c) — freeze limits, selection, failsafe, and truncation.
- [src/backend/utils/misc/guc.c](../../../../raw/postgres-14/src/backend/utils/misc/guc.c), [src/backend/access/common/reloptions.c](../../../../raw/postgres-14/src/backend/access/common/reloptions.c), and [doc/src/sgml/config.sgml](../../../../raw/postgres-14/doc/src/sgml/config.sgml) — settings, contexts, defaults, and effective bounds.
- [doc/src/sgml/maintenance.sgml](../../../../raw/postgres-14/doc/src/sgml/maintenance.sgml) and [doc/src/sgml/mvcc.sgml](../../../../raw/postgres-14/doc/src/sgml/mvcc.sgml) — wraparound/vacuum and row-lock semantics.
- [src/backend/catalog/system_views.sql](../../../../raw/postgres-14/src/backend/catalog/system_views.sql), [src/backend/postmaster/pgstat.c](../../../../raw/postgres-14/src/backend/postmaster/pgstat.c), [src/backend/storage/lmgr/lwlocknames.txt](../../../../raw/postgres-14/src/backend/storage/lmgr/lwlocknames.txt), [generate-lwlocknames.pl](../../../../raw/postgres-14/src/backend/storage/lmgr/generate-lwlocknames.pl), and [doc/src/sgml/monitoring.sgml](../../../../raw/postgres-14/doc/src/sgml/monitoring.sgml) — statistics and wait names.
- [src/include/catalog/pg_proc.dat](../../../../raw/postgres-14/src/include/catalog/pg_proc.dat), [src/backend/catalog/Makefile](../../../../raw/postgres-14/src/backend/catalog/Makefile), [src/backend/utils/Makefile](../../../../raw/postgres-14/src/backend/utils/Makefile), and [src/backend/storage/lmgr/Makefile](../../../../raw/postgres-14/src/backend/storage/lmgr/Makefile) — SQL registration and generated artifacts.
- [src/include/access/rmgrlist.h](../../../../raw/postgres-14/src/include/access/rmgrlist.h), [src/backend/access/rmgrdesc/mxactdesc.c](../../../../raw/postgres-14/src/backend/access/rmgrdesc/mxactdesc.c), and [src/bin/pg_waldump/rmgrdesc.c](../../../../raw/postgres-14/src/bin/pg_waldump/rmgrdesc.c) — WAL resource-manager and inspection-tool integration.
- [contrib/pgrowlocks/pgrowlocks.c](../../../../raw/postgres-14/contrib/pgrowlocks/pgrowlocks.c) and [contrib/amcheck/verify_heapam.c](../../../../raw/postgres-14/contrib/amcheck/verify_heapam.c) — extension boundaries.
- [src/test/isolation/isolation_schedule](../../../../raw/postgres-14/src/test/isolation/isolation_schedule), [fk-contention.spec](../../../../raw/postgres-14/src/test/isolation/specs/fk-contention.spec), [multixact-no-deadlock.spec](../../../../raw/postgres-14/src/test/isolation/specs/multixact-no-deadlock.spec), [multixact-no-forget.spec](../../../../raw/postgres-14/src/test/isolation/specs/multixact-no-forget.spec), [tuplelock-conflict.spec](../../../../raw/postgres-14/src/test/isolation/specs/tuplelock-conflict.spec), [nowait-2.spec](../../../../raw/postgres-14/src/test/isolation/specs/nowait-2.spec), [skip-locked-2.spec](../../../../raw/postgres-14/src/test/isolation/specs/skip-locked-2.spec), and [freeze-the-dead.spec](../../../../raw/postgres-14/src/test/isolation/specs/freeze-the-dead.spec) — direct correctness coverage.

## Navigation

- [v14/index](../../index.md)
- [PostgreSQL 14 Codebase Navigation Guide](../../codebase-navigation-guide.md)
- [Wiki Index](../../../index.md)
- [Versions](../../../versions.md)
