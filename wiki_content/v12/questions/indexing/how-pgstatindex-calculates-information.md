---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# How pgstatindex Calculates B-Tree Index Statistics in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [What `pgstatindex` does](#what-pgstatindex-does)
  - [Values and observation times](#values-and-observation-times)
  - [Logic map](#logic-map)
  - [SQL and C call path](#sql-and-c-call-path)
  - [Accepted relations, permissions, and index state](#accepted-relations-permissions-and-index-state)
  - [Data structures and generated-header boundary](#data-structures-and-generated-header-boundary)
  - [Metapage read](#metapage-read)
  - [Physical page scan](#physical-page-scan)
  - [Page classification](#page-classification)
  - [Lifecycle changes that alter a later call](#lifecycle-changes-that-alter-a-later-call)
  - [How `index_size` is calculated](#how-index_size-is-calculated)
  - [How `avg_leaf_density` is calculated](#how-avg_leaf_density-is-calculated)
  - [How `leaf_fragmentation` is calculated](#how-leaf_fragmentation-is-calculated)
  - [Result construction and edge paths](#result-construction-and-edge-paths)
  - [Concurrency and integrity limits](#concurrency-and-integrity-limits)
  - [Regression coverage](#regression-coverage)
  - [Worked measurements and calculations](#worked-measurements-and-calculations)
  - [Causal summary](#causal-summary)
- [Measurement Script](#measurement-script)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 12, provide a comprehensive explanation of how `pgstatindex` calculates its information.

## Answer

### What `pgstatindex` does

[pgstatindex](../../../glossary.md#pgstatindex) calculates statistics from
physical [B-tree](../../../glossary.md#b-tree) pages. It scans the index's
[main fork](../../../glossary.md#fork) in physical block order, so the result
describes stored page occupancy rather than the number of visible rows.
The worker reads [block](../../../glossary.md#block) 0,
captures the main-fork length once, then reads each block from `1` through that
captured length minus one and interprets PostgreSQL's private B-tree page
layout directly
([pgstatindex.c#includes-and-AM-tests](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L28-L73),
[pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L215-L365)).

The surprising field is `empty_pages`: it counts the
[half-dead page state](../../../glossary.md#b-tree-page-deletion), rather than
pages with zero items. Only live [leaf pages](../../../glossary.md#leaf-page)
contribute to density and fragmentation. Deleted pages still contribute to
`index_size` because their blocks remain in the scanned main fork
([pgstatindex.c#classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310),
[pgstatindex.c#result-formulas](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L333-L356),
[nbtree.h#page-state-macros](../../../../raw/postgres-12/src/include/access/nbtree.h#L183-L196)).

The function belongs to the [pgstattuple](../../../glossary.md#pgstattuple)
[contrib extension](../../../glossary.md#contrib). It does not sample pages,
read the catalog's `pg_class.relpages` estimate, traverse from the root, or
call an index [access-method](../../../glossary.md#access-method) callback
([pgstatindex.c#includes-and-worker](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L28-L73),
[pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L215-L365)).

### Values and observation times

A [metapage](../../../glossary.md#metapage) stores whole-tree metadata.
Each ordinary page stores its own header and B-tree flags. The worker reads
these stored values during this call; it does not retrieve a previously
computed statistics record. The observations occur at different times,
because the metapage read precedes the page-by-page scan
([pgstatindex.c#metadata-and-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L315)).

| Value | Meaning and origin | Observation time | Later use |
|---|---|---|---|
| `btm_version`, `btm_root`, `btm_level` | Stored format version and true-root identity/level from block 0 | Copied before the scan, without a content lock | Reported as `version`, `root_block_no`, and `tree_level` ([pgstatindex.c#metapage-read](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L253)). |
| `nblocks` | Main-fork length from the storage manager | Captured once after the metapage read | Bounds the scan; later extension is outside this call ([pgstatindex.c#scan-bound](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L271), [bufmgr.c#RelationGetNumberOfBlocksInFork](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2790-L2810)). |
| `btpo_flags` | Stored deleted, half-dead, leaf, and other page flags | Read during each ordinary-page inspection; shared buffers are content-locked | Selects exactly one page-class counter ([pgstatindex.c#classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L278-L310)). |
| `pd_special`, `pd_lower`, `pd_upper` | [Page](../../../glossary.md#page)-header offsets delimiting special space and the free gap; `pd_lower` follows the [line-pointer](../../../glossary.md#line-pointer) array | Read for each live leaf | Supplies leaf capacity and allocatable free space ([pgstatindex.c#leaf-space](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L299), [bufpage.h#PageHeaderData](../../../../raw/postgres-12/src/include/storage/bufpage.h#L151-L164), [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L597)). |
| `btpo_next` | Stored [right sibling link](../../../glossary.md#sibling-link) | Read for each live leaf | A lower nonzero block number adds one fragment ([pgstatindex.c#fragment-test](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L300-L307)). |
| `BTIndexStat` counters and sums | Values accumulated by this call, initially zero | Updated as each page is inspected | Supplies byte size and the two final ratios ([pgstatindex.c#accumulators-and-results](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L255-L359)). |

Here, “live leaf” means a leaf without deleted or half-dead flags. It does
not mean that every tuple on it is visible to an SQL query. The leaf branch
uses page free space without checking tuple visibility
([pgstatindex.c#leaf-branch](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L307)).

An SQL `regclass` value identifies a relation by its
[OID](../../../glossary.md#oid). Converting a name to that value can require
schema lookup before the C wrapper runs. Both overloads eventually open a
[`Relation`](../../../glossary.md#relation) with
[`AccessShareLock`](../../../glossary.md#lock-mode)
([regproc.c#regclassin](../../../../raw/postgres-12/src/backend/utils/adt/regproc.c#L903-L938),
[pgstatindex.c#v1.5-wrappers](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L162-L213)).

### Logic map

This map shows the v1.5 path. The keyed citations below it support its
decisions and calculations.

```text
[A] Input and SQL access
    text name ---------------------> resolve relation name / schema access
    named regclass input ----------> resolve name before the C wrapper
    already-resolved / numeric OID -> use relation identity directly
    lookup or function privilege failure -> ERROR
    STRICT null input -> NULL without entering C
                 |
[B] Open relation with AccessShareLock
    physical built-in B-tree? no -> ERROR
    another session's temporary relation? yes -> ERROR
                 |
[C] Read block 0 -> copy version, true root, true-root level
    Initialize counters and sums -> capture main-fork nblocks once
                 |
[D] For physical blocks 1 .. nblocks-1, read one page
    Shared buffer -> shared content lock; local buffer -> no content lock
    deleted? -------- yes -> deleted_pages++
       | no
    ignored? -------- yes -> empty_pages++ (half-dead)
       | no
    leaf? ----------- yes -> leaf_pages++
       |                    capacity += pd_special - fixed_header_size
       |                    free += PageGetFreeSpace(page)
       |                    nonzero right-link < this block? fragments++
       | no
    internal_pages++
    Unlock/release this page -> repeat
                 |
[E] Close relation and release its lock
    index_size = (1 + all four page counters) * BLCKSZ
    density denominator zero? -> NaN; else 100 - free/capacity*100
    leaf count zero? -> NaN; else fragments/leaf_pages*100
    Format non-NaN percentages with %.2f -> construct result record
```

- **A:** SQL bindings, grants, strictness, and name/OID resolution:
  [pgstattuple--1.4--1.5.sql#pgstatindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L22-L92),
  [xfunc.sgml#STRICT](../../../../raw/postgres-12/doc/src/sgml/xfunc.sgml#L2397-L2404),
  [regproc.c#regclassin](../../../../raw/postgres-12/src/backend/utils/adt/regproc.c#L903-L938),
  [namespace.c#LookupExplicitNamespace](../../../../raw/postgres-12/src/backend/catalog/namespace.c#L2884-L2915).
- **B:** Wrappers and object checks:
  [pgstatindex.c#v1.5-wrappers-and-checks](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L162-L238).
- **C–D:** Metadata, scan bound, content lock, classification, and sums:
  [pgstatindex.c#metadata-and-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L315),
  [bufmgr.c#LockBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3585-L3607).
- **E:** Lock release, zero denominators, formatting, and result construction:
  [pgstatindex.c#result-construction](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L317-L365).

### SQL and C call path

The extension control file selects version 1.5. There is no standalone
`pgstattuple--1.5.sql` install script in the Makefile. A fresh default install
therefore starts from the installable 1.4 script and follows the 1.4-to-1.5
update path, which is the extension manager's defined fallback when the target
version has no direct install script
([pgstattuple.control#default-version](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.control#L1-L5),
[Makefile#extension-scripts](../../../../raw/postgres-12/contrib/pgstattuple/Makefile#L3-L13),
[extension.c#install-path-selection](../../../../raw/postgres-12/src/backend/commands/extension.c#L1297-L1400),
[extension.c#install-then-update](../../../../raw/postgres-12/src/backend/commands/extension.c#L1536-L1550)).

The 1.4 base definitions point the two SQL overloads at the legacy C symbols.
The 1.5 update replaces them as follows
([pgstattuple--1.4.sql#legacy-pgstatindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L19-L31),
[pgstattuple--1.4.sql#legacy-pgstatindexbyid](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L62-L74),
[pgstattuple--1.4--1.5.sql#v1.5-pgstatindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L22-L37),
[pgstattuple--1.4--1.5.sql#v1.5-pgstatindexbyid](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92)):

```text
pgstatindex(text)
  -> pgstatindex_v1_5
  -> makeRangeVarFromNameList(textToQualifiedNameList(...))
  -> relation_openrv(..., AccessShareLock)
  -> pgstatindex_impl

pgstatindex(regclass)
  -> pgstatindexbyid_v1_5
  -> relation_open(oid, AccessShareLock)
  -> pgstatindex_impl
```

The text overload resolves a possibly schema-qualified name in the C wrapper.
The `regclass` overload receives an already-resolved OID. Both wrappers acquire
`AccessShareLock` on the index and transfer the open `Relation` to the same
worker
([pgstatindex.c#text-wrappers](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L134-L180),
[pgstatindex.c#regclass-wrappers](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L182-L213),
[relation.c#relation_openrv](../../../../raw/postgres-12/src/backend/access/common/relation.c#L131-L161)).

Both 1.5 overloads are `STRICT` and `PARALLEL SAFE`. The update script revokes
`PUBLIC` execution and grants execution to `pg_stat_scan_tables`; superusers
bypass that SQL privilege check. `STRICT` means PostgreSQL returns null for a
null input without entering the C function
([pgstattuple--1.4--1.5.sql#v1.5-pgstatindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L22-L37),
[pgstattuple--1.4--1.5.sql#v1.5-pgstatindexbyid](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L77-L92),
[pgstattuple.sgml#access](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L10-L24),
[xfunc.sgml#STRICT](../../../../raw/postgres-12/doc/src/sgml/xfunc.sgml#L2397-L2404)).

The shared library retains the legacy C entry points. They still call
`superuser()` because a library can be upgraded while the installed extension
SQL remains older than 1.5 and still grants the old SQL functions to `PUBLIC`.
The 1.5 C wrappers omit that internal check because SQL function privileges now
control access
([pgstatindex.c#legacy-text-wrapper](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L134-L160),
[pgstatindex.c#legacy-regclass-wrapper](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L182-L201),
[pgstatindex.c#v1.5-wrappers](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L162-L213)).

### Accepted relations, permissions, and index state

`pgstatindex_impl` accepts only `RELKIND_INDEX` relations whose `relam` equals
the built-in `BTREE_AM_OID`. It therefore rejects tables, views, foreign tables,
partitioned indexes, and every non-B-tree index. A physical B-tree index on a
table partition is accepted
([pgstatindex.c#object-check](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L224-L238),
[pg_class.h#relation-kinds](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L154-L163),
[pg_am.dat#BTREE_AM_OID](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L15-L23),
[pgstattuple.sql#relation-kind-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L55-L113)).

The worker rejects another session's temporary relation because the backend
cannot see that session's local buffers. It can inspect a temporary B-tree
owned by the current session
([pgstatindex.c#other-session-temp-check](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L230-L238),
[rel.h#RELATION_IS_OTHER_TEMP](../../../../raw/postgres-12/src/include/utils/rel.h#L541-L549)).

Function execution, name lookup, and relation access are separate boundaries.
Neither wrapper nor the worker checks relation ownership or a relation-level
`SELECT` privilege. `relation_open` gets the requested relation lock and
[relcache](../../../glossary.md#relcache) entry; the caller is responsible for
checking whether it can handle that relation kind
([pgstatindex.c#wrappers-and-worker](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L134-L238),
[relation.c#relation_open](../../../../raw/postgres-12/src/backend/access/common/relation.c#L35-L79)).

Name resolution still checks schema access. The text wrapper reaches
`RangeVarGetRelid`; a named `regclass` input reaches it through `regclassin`
before entering the wrapper. For an explicitly named schema,
`LookupExplicitNamespace` requires `USAGE`. An already-resolved OID, including
numeric `regclass` input, does not repeat that name lookup
([relation.c#relation_openrv](../../../../raw/postgres-12/src/backend/access/common/relation.c#L131-L161),
[namespace.c#RangeVarGetRelidExtended](../../../../raw/postgres-12/src/backend/catalog/namespace.c#L312-L327),
[namespace.c#LookupExplicitNamespace](../../../../raw/postgres-12/src/backend/catalog/namespace.c#L2884-L2915),
[regproc.c#regclassin](../../../../raw/postgres-12/src/backend/utils/adt/regproc.c#L903-L938),
[pgstatindex.c#OID-wrapper](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L203-L213)).

| Input / permission state | Behavior | Consequence |
|---|---|---|
| No SQL function `EXECUTE` privilege | SQL access is denied | No scan is authorized ([pgstattuple--1.4--1.5.sql#grants](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L22-L92), [pgstattuple.sgml#access](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L10-L24)). |
| Explicitly qualified text name or named `regclass`, without schema `USAGE` | Name lookup raises a schema permission error | Granting function execution alone does not make that name resolvable ([namespace.c#LookupExplicitNamespace](../../../../raw/postgres-12/src/backend/catalog/namespace.c#L2884-L2915), [regproc.c#named-regclass](../../../../raw/postgres-12/src/backend/utils/adt/regproc.c#L927-L938)). |
| Already-resolved OID and SQL function execution allowed | Wrapper opens the relation directly by OID | No schema-name lookup or relation-level `SELECT` check is added by this path ([pgstatindex.c#OID-wrapper-and-worker](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L203-L238), [relation.c#relation_open](../../../../raw/postgres-12/src/backend/access/common/relation.c#L35-L79)). |

The worker also does not read `pg_index.indisvalid`, `indisready`, or
`indislive`. An invalid or not-ready physical B-tree can therefore be scanned
if its storage is readable. An [invalid index](../../../glossary.md#invalid-index)'s
output describes pages, not whether the planner
or executor may use the index
([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L215-L365),
[pg_index.h#index-state-flags](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L32-L44)).

### Data structures and generated-header boundary

`BTIndexStat` is the local whole-index accumulator. It stores three metapage
values, four page-class counters, the summed leaf capacity and free space, and
the backward-link count
([pgstatindex.c#BTIndexStat](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L75-L95)).

The worker reads two core B-tree structures directly:

- `BTMetaPageData` supplies `btm_version`, `btm_root`, and `btm_level`
  ([nbtree.h#BTMetaPageData](../../../../raw/postgres-12/src/include/access/nbtree.h#L90-L110)).
- `BTPageOpaqueData`, stored in each B-tree page's special space, contains the
  sibling links, level-or-deletion-[XID](../../../glossary.md#transaction-id) union,
  flags, and [VACUUM](../../../glossary.md#vacuum) cycle ID. The
  worker uses its flags and `btpo_next` right-link
  ([nbtree.h#BTPageOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L29-L78),
  [pgstatindex.c#opaque-fields-used](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L283-L307)).

This is a core-layout dependency, not an index-AM callback boundary. The source
includes private `access/nbtree.h` and compares `relam` with `BTREE_AM_OID`
directly
([pgstatindex.c#includes-and-AM-tests](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L28-L73)).

`BTREE_AM_OID` also exposes a build-time generated-header dependency.
`pgstatindex.c` includes `catalog/pg_am.h`; that header includes generated
`catalog/pg_am_d.h`. The catalog Makefile generates every `*_d.h` from catalog
headers and `.dat` seed files through `genbki.pl`, and `pg_am.dat` supplies the
`BTREE_AM_OID` symbol and value
([pg_am.h#generated-header-include](../../../../raw/postgres-12/src/include/catalog/pg_am.h#L18-L29),
[pg_am.dat#BTREE_AM_OID](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L15-L23),
[catalog/Makefile#generated-catalog-headers](../../../../raw/postgres-12/src/backend/catalog/Makefile#L28-L100),
[genbki.pl#OID-symbol-emission](../../../../raw/postgres-12/src/backend/catalog/genbki.pl#L595-L603)).

The contrib Makefile links `pgstatindex.o` with `pgstattuple.o` and
`pgstatapprox.o` into one `pgstattuple` module. `PG_FUNCTION_INFO_V1` emits each
`pg_finfo_<symbol>` function that the function manager requires when loading an
SQL-callable C symbol
([Makefile#module](../../../../raw/postgres-12/contrib/pgstattuple/Makefile#L1-L13),
[pgstatindex.c#function-info](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L47-L67),
[fmgr.h#PG_FUNCTION_INFO_V1](../../../../raw/postgres-12/src/include/fmgr.h#L383-L413),
[fmgr.c#fetch_finfo_record](../../../../raw/postgres-12/src/backend/utils/fmgr/fmgr.c#L458-L511)).

### Metapage read

Block 0 is `BTREE_METAPAGE`. The worker reads it with `ReadBufferExtended(...,
MAIN_FORKNUM, 0, RBM_NORMAL, bstrategy)`, obtains `BTMetaPageData` with
`BTPageGetMeta`, copies three fields, and releases the buffer
([pgstatindex.c#metapage-read](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L253),
[nbtree.h#metapage-layout](../../../../raw/postgres-12/src/include/access/nbtree.h#L90-L135)).

| Output | Metapage source | Exact meaning |
|---|---|---|
| `version` | `btm_version` | On-disk B-tree format version. Version 4 is current at this pin; versions 2 and 3 remain readable. |
| `tree_level` | `btm_level` | Level of the true root, counting upward from leaf level 0. |
| `root_block_no` | `btm_root` | True-root block number; `P_NONE`, represented by zero, means no root exists yet. |

Those meanings come from the structure and version definitions
([nbtree.h#metapage-layout](../../../../raw/postgres-12/src/include/access/nbtree.h#L90-L135),
[nbtree.h#page-levels](../../../../raw/postgres-12/src/include/access/nbtree.h#L29-L39)).
The worker does not report `btm_fastroot` or `btm_fastlevel`, the
[fast-root](../../../glossary.md#fast-root) fields. Normal B-tree
searches may start from that effective root, while `pgstatindex` reports the
true-root fields
([nbtpage.c#fast-root-selection](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L426-L465),
[nbtpage.c#root-height](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L574-L625)).

A metapage-only empty index therefore reports format version 4, level 0, root
block 0, zero classified non-metapages, one block of `index_size`, and `NaN` for
both ratios in the checked-in regression result
([pgstattuple.out#empty-index](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L44-L82)).

Two limits matter:

1. The worker [pins](../../../glossary.md#buffer-pin) the metapage but does not
   acquire a buffer content lock before reading it. A root
   [page split](../../../glossary.md#page-split) updates `btm_root` and `btm_level` while
   holding the metapage's B-tree write lock, so the three copied fields are not
   protected as one metapage observation
   ([pgstatindex.c#unlocked-metapage-read](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L253),
   [nbtinsert.c#new-root-metapage-update](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L2060-L2110)).
2. The worker does not call `_bt_getmeta` and does not verify `BTP_META`,
   `BTREE_MAGIC`, or the supported version range. The normal B-tree metadata
   accessor performs all three checks
   ([pgstatindex.c#unvalidated-metapage-read](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L253),
   [nbtpage.c#_bt_getmeta](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L111-L148)).

### Physical page scan

After the metapage read, the worker zeros its counters and calls
`RelationGetNumberOfBlocks(rel)` once. That macro asks for the main fork;
`RelationGetNumberOfBlocksInFork` opens storage-manager state if necessary and
calls `smgrnblocks`
([pgstatindex.c#counter-init-and-length](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L255-L271),
[bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-12/src/include/storage/bufmgr.h#L188-L199),
[bufmgr.c#RelationGetNumberOfBlocksInFork](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2790-L2810)).

The loop visits every captured block number from 1 through `nblocks - 1`. For
each block it:

1. checks for interrupts;
2. reads the main-fork block with the `BAS_BULKREAD` strategy;
3. requests `BUFFER_LOCK_SHARE` on the page contents;
4. reads its B-tree opaque flags and, for a live leaf, page-header free space;
5. releases the content lock and buffer pin.

The implementation is at
[pgstatindex.c#scan-loop](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315).
`BAS_BULKREAD` is the [buffer manager](../../../glossary.md#buffer-manager)'s
[ring-buffer](../../../glossary.md#ring-buffer) strategy for a large read-only scan, and
`BUFFER_LOCK_SHARE` maps to a shared buffer content lock for shared buffers.
`LockBuffer` returns immediately for local buffers, so a current-session
temporary index does not acquire that shared content lock
([bufmgr.h#BufferAccessStrategyType](../../../../raw/postgres-12/src/include/storage/bufmgr.h#L26-L47),
[bufmgr.h#buffer-lock-modes](../../../../raw/postgres-12/src/include/storage/bufmgr.h#L83-L89),
[bufmgr.c#LockBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3585-L3607)).

The worker never follows a downlink or sibling link to choose the next page.
Physical block order drives the scan; `btpo_next` is read only to calculate
fragmentation
([pgstatindex.c#scan-and-fragment-test](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315)).

### Page classification

Each scanned block enters exactly one branch:

| Test order | Counter | What the code counts |
|---|---:|---|
| `P_ISDELETED(opaque)` | `deleted_pages` | Every page carrying `BTP_DELETED`, without checking whether its deletion XID is old enough for page reuse ([pgstatindex.c#classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310), [nbtpage.c#_bt_page_recyclable](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L931-L963)). |
| Remaining `P_IGNORE(opaque)` | `empty_pages` | A page carrying `BTP_HALF_DEAD`; deleted pages have already taken the first branch ([nbtree.h#page-state-macros](../../../../raw/postgres-12/src/include/access/nbtree.h#L183-L196)). |
| `P_ISLEAF(opaque)` | `leaf_pages` | A live, non-half-dead leaf; this branch also accumulates capacity, free space, and backward right-links ([pgstatindex.c#leaf-branch](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L307)). |
| Fallback | `internal_pages` | For a well-formed B-tree, any remaining non-leaf page, including an internal root; `P_ISROOT` has no separate counter ([pgstatindex.c#classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310), [nbtree.h#page-flags](../../../../raw/postgres-12/src/include/access/nbtree.h#L70-L78)). |

`empty_pages` is therefore a state count, not an item-count test. PostgreSQL
marks an empty deletable leaf half-dead during the first page-deletion stage,
removes its old high key, and installs one dummy high-key tuple. A live leaf
with no data items remains in `leaf_pages`; the root cannot be deleted merely
because it is empty
([nbtpage.c#page-deletion-preconditions](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1356-L1389),
[nbtpage.c#mark-half-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1642-L1665)).

The classification ignores orthogonal flags such as `BTP_HAS_GARBAGE`,
`BTP_SPLIT_END`, and `BTP_INCOMPLETE_SPLIT`. Such a live page is still counted
only as leaf or internal
([nbtree.h#page-flags](../../../../raw/postgres-12/src/include/access/nbtree.h#L70-L78),
[pgstatindex.c#classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310)).

### Lifecycle changes that alter a later call

`pgstatindex` calculates a new result on every call. It has no statistics
refresh operation: a later call observes whatever page state it reads then
([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L215-L365)).

| Event | State before | State after | Effect on a later calculation |
|---|---|---|---|
| An index scan marks a tuple `LP_DEAD` | Tuple storage and a normal line pointer | Dead line-pointer flag with storage retained | Marking alone does not free bytes, so it does not lower density ([itemid.h#ItemIdMarkDead](../../../../raw/postgres-12/src/include/storage/itemid.h#L160-L182), [nbtutils.c#_bt_killitems](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1687-L1813), [pgstatindex.c#leaf-space](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L299)). |
| VACUUM removes tuples from a leaf | Stored tuples consume page area | `PageIndexMultiDelete` removes selected tuples | Changed free space affects density if the page remains a live leaf ([nbtpage.c#_bt_delitems_vacuum](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L986-L1015), [pgstatindex.c#leaf-space](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L299)). |
| First deletion stage for an empty deletable leaf | Live leaf with no data items | Half-dead page with a dummy high key | Page moves from `leaf_pages` to `empty_pages`; its capacity/free space leave both leaf sums ([nbtpage.c#mark-half-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1642-L1665), [pgstatindex.c#classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L307)). |
| Page unlink completes | Half-dead leaf or an internal page being unlinked | Sibling links bypass it; `BTP_DELETED` replaces `BTP_HALF_DEAD` | It counts as `deleted_pages` even while it is too young to recycle; changing this classification alone does not change the size sum ([nbtpage.c#unlink-and-delete](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1966-L2006), [nbtpage.c#_bt_page_recyclable](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L931-L963), [pgstatindex.c#index-size](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L333-L346)). |
| A split reuses a recyclable block or extends the main fork | Available deleted/new block, or no reusable block | Initialized B-tree page | Reuse can change counters without increasing length; extension increases the bound captured by a later call ([nbtinsert.c#split-allocation](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L1407-L1430), [nbtpage.c#_bt_getbuf](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L790-L879), [pgstatindex.c#scan-bound](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L271)). |
| Root split | Previous true root and metapage fields | New root, updated true/fast root identity and level | A later metapage read can report the new true-root fields ([nbtinsert.c#new-root-metapage-update](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L2060-L2110), [pgstatindex.c#metapage-read](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L253)). |

Page deletion changes which blocks contribute to density, while `index_size`
counts all scanned classes. Therefore a lower live-leaf count need not produce
a lower byte size. The worked measurements below demonstrate this distinction
([pgstatindex.c#classification-and-sums](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310),
[pgstatindex.c#size-and-density](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L333-L351)).

### How `index_size` is calculated

The worker does not call a byte-size function at result time. It adds the four
page-class counters, adds one metapage, and multiplies by the compile-time
`BLCKSZ`
([pgstatindex.c#index-size](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L333-L346)).
Because every scanned block takes exactly one classification branch, a
completed call has this exact arithmetic invariant:

```text
1 + internal_pages + leaf_pages + empty_pages + deleted_pages
    = nblocks captured before the loop

index_size = (1 + internal_pages + leaf_pages
               + empty_pages + deleted_pages) * BLCKSZ
           = nblocks * BLCKSZ
```

Consequently, `index_size` equals the captured main-fork block count times
`BLCKSZ`, the compiled block size in bytes. It includes deleted and half-dead
pages, but excludes the [free space map](../../../glossary.md#free-space-map)
and any init fork because the worker uses `MAIN_FORKNUM` only
([pgstatindex.c#length-and-scan](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315),
[relpath.h#fork-numbers](../../../../raw/postgres-12/src/include/common/relpath.h#L32-L53)).
The documentation describes the same metapage relationship
([pgstattuple.sgml#index-size-note](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L268-L273)).

Pages appended after the one-time `nblocks` read are outside this call's scan
and size. B-tree VACUUM, by contrast, takes the relation-extension lock,
rechecks the relation length, and explains why extension synchronization is
needed around an in-progress all-zero page
([pgstatindex.c#one-time-length](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L271),
[nbtree.c#btvacuumscan-extension-loop](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L991-L1041)).

### How `avg_leaf_density` is calculated

For each live leaf page, `pd_special` is the start of special space, and
`SizeOfPageHeaderData` is the fixed header size without the
line-pointer array. The worker subtracts
these offsets to get the page area available to line pointers and index tuples
([bufpage.h#PageHeaderData](../../../../raw/postgres-12/src/include/storage/bufpage.h#L151-L164),
[bufpage.h#SizeOfPageHeaderData](../../../../raw/postgres-12/src/include/storage/bufpage.h#L207-L217),
[pgstatindex.c#leaf-capacity](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L299)):

```text
max_avail = BLCKSZ - (BLCKSZ - pd_special + SizeOfPageHeaderData)
          = pd_special - SizeOfPageHeaderData
```

The free-space term is `PageGetFreeSpace(page)`, not the raw gap. It calculates
`pd_upper - pd_lower`, returns zero if less than one line pointer remains, and
otherwise subtracts one `ItemIdData` slot for a future tuple
([bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L597)).
`PageGetExactFreeSpace` would return the raw nonnegative gap without that
reservation, but `pgstatindex` does not call it
([bufpage.c#PageGetExactFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L626-L647),
[pgstatindex.c#leaf-free-space](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L296-L299)).

The final percentage is a ratio of sums across live leaf pages, not a scan of
live index tuples:

```text
100 - sum(PageGetFreeSpace(page))
      / sum(pd_special - SizeOfPageHeaderData) * 100
```

This measures physical occupancy. High keys, line pointers, and the stored
bytes of `LP_DEAD` index tuples all reduce free space. Marking an item
`LP_DEAD` preserves its storage, and `pgstatindex` does not inspect item states
or `BTP_HAS_GARBAGE`
([nbtree.h#high-key-layout](../../../../raw/postgres-12/src/include/access/nbtree.h#L198-L219),
[itemid.h#ItemIdMarkDead](../../../../raw/postgres-12/src/include/storage/itemid.h#L160-L182),
[nbtutils.c#LP_DEAD-and-BTP_HAS_GARBAGE](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1687-L1813),
[pgstatindex.c#leaf-branch](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L307)).

The result is formatted to two decimal places. If no live leaf contributes
capacity, the worker emits `NaN`
([pgstatindex.c#density-result](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L351)).

### How `leaf_fragmentation` is calculated

For each live leaf page at physical block `blkno`, the worker increments
`fragments` when its right-link is not `P_NONE` and is strictly lower than
`blkno`:

```text
btpo_next != P_NONE && btpo_next < blkno
```

`btpo_next` is the B-tree link to the page's right sibling, and `P_NONE` is
zero. Deleted and half-dead pages are excluded because their branches run
before the live-leaf branch
([pgstatindex.c#fragment-count](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L307),
[nbtree.h#BTPageOpaqueData](../../../../raw/postgres-12/src/include/access/nbtree.h#L29-L68),
[nbtree.h#P_NONE](../../../../raw/postgres-12/src/include/access/nbtree.h#L173-L194)).

The output is:

```text
fragments / leaf_pages * 100
```

The denominator includes every live leaf, including the rightmost leaf whose
right-link is `P_NONE`. The result is formatted to two decimal places, or is
`NaN` when `leaf_pages` is zero
([pgstatindex.c#fragmentation-result](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L300-L307),
[pgstatindex.c#fragmentation-result-format](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L352-L356)).

This is a backward-right-link percentage. It is not a count of fragmented
runs, bytes, filesystem extents, or reciprocal-link errors. The worker tests
one link independently on each physically scanned live leaf and does not
validate the sibling chain
([pgstatindex.c#scan-and-fragment-test](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315)).

### Result construction and edge paths

After the scan, the worker closes the relation and releases `AccessShareLock`.
It then requires the caller's declared result type to be composite, formats ten
C strings, feeds them through the tuple descriptor's input functions, and
returns the resulting record
([pgstatindex.c#close-and-build-result](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L317-L365),
[relation.c#relation_close](../../../../raw/postgres-12/src/backend/access/common/relation.c#L196-L217)).

| Output column | Source or calculation |
|---|---|
| `version` | `BTMetaPageData.btm_version` ([pgstatindex.c#metapage-read](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L253)). |
| `tree_level` | `BTMetaPageData.btm_level`, the true root's level ([nbtree.h#BTMetaPageData](../../../../raw/postgres-12/src/include/access/nbtree.h#L97-L110)). |
| `index_size` | Captured classified blocks, including the metapage, times `BLCKSZ` ([pgstatindex.c#index-size](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L333-L346)). |
| `root_block_no` | `BTMetaPageData.btm_root` ([pgstatindex.c#metapage-read](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L253)). |
| `internal_pages` | Classification fallback after deleted, half-dead, and leaf tests ([pgstatindex.c#classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310)). |
| `leaf_pages` | Live leaf branch count ([pgstatindex.c#leaf-branch](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L307)). |
| `empty_pages` | Half-dead branch count ([pgstatindex.c#classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310)). |
| `deleted_pages` | `BTP_DELETED` branch count ([pgstatindex.c#classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310)). |
| `avg_leaf_density` | Summed physical leaf occupancy, formatted to two decimals, or `NaN` ([pgstatindex.c#density-result](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L351)). |
| `leaf_fragmentation` | Backward-right-link count divided by live leaves, formatted to two decimals, or `NaN` ([pgstatindex.c#fragmentation-result-format](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L352-L356)). |

The explicit errors and exits are:

- SQL `STRICT` handles a null argument without entering C
  ([pgstattuple--1.4--1.5.sql#pgstatindex-definitions](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L22-L92),
  [xfunc.sgml#STRICT](../../../../raw/postgres-12/doc/src/sgml/xfunc.sgml#L2397-L2404)).
- Name/OID resolution can fail while opening the relation; the legacy wrappers
  can first reject a non-superuser
  ([pgstatindex.c#wrappers](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L134-L213),
  [relation.c#relation_open](../../../../raw/postgres-12/src/backend/access/common/relation.c#L35-L79)).
- The worker raises `wrong_object_type` for a non-physical-B-tree object and
  `feature_not_supported` for another session's temporary relation
  ([pgstatindex.c#object-errors](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L224-L238)).
- `CHECK_FOR_INTERRUPTS()` makes a long page scan cancellable
  ([pgstatindex.c#scan-loop](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315)).
- A non-composite call context fails with `return type must be a row type` after
  the relation has been closed
  ([pgstatindex.c#result-type-check](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L317-L332)).

### Concurrency and integrity limits

`pgstatindex` derives its counters from the page images it reads, but those
images do not form one whole-index [snapshot](../../../glossary.md#snapshot).
The documentation explicitly says
that results accumulate page by page and should not be expected to represent
an instantaneous index snapshot
([pgstattuple.sgml#page-by-page-caveat](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L268-L279)).

| Boundary | PostgreSQL 12 behavior |
|---|---|
| Relation lock | Both wrappers hold `AccessShareLock` during the scan. That mode conflicts only with `AccessExclusiveLock`; ordinary index maintenance opens indexes with `RowExclusiveLock`, as does lazy VACUUM, so inserts, deletes, page splits, and VACUUM can overlap the scan ([lock.c#LockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L61-L105), [execIndexing.c#ExecOpenIndices](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L141-L213), [vacuumlazy.c#index-lock](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L279-L288)). |
| Metapage | It is pinned but not content-locked, and its three reported fields are loaded before the page scan ([pgstatindex.c#unlocked-metapage-read](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L253)). |
| Non-metapage blocks | Each shared-buffer page gets a shared content lock while inspected, but that lock is released before the next page. `LockBuffer` is a no-op for local temporary buffers. The call can therefore combine shared-page states observed at different times ([pgstatindex.c#scan-loop](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L315), [bufmgr.c#LockBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3585-L3607)). |
| Relation growth | `nblocks` is read once without the relation-extension lock. Later blocks are omitted; an extension already in progress also lacks the synchronization used by B-tree VACUUM around newly extended all-zero pages ([pgstatindex.c#one-time-length](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L266-L271), [nbtree.c#btvacuumscan-extension-loop](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L991-L1041)). |
| Generic buffer validation | `RBM_NORMAL` validates a page header and, when enabled, its checksum when reading from storage, but accepts an all-zero page as generically valid ([bufmgr.c#ReadBufferExtended](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L600-L638), [bufpage.c#PageIsVerified](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L64-L142)). |
| B-tree validation | The worker omits `_bt_getmeta` and `_bt_checkpage`, so it lacks their explicit checks of metapage magic/version, `PageIsNew`, and exact B-tree special-space size. This does not bypass assertions in the page macros ([pgstatindex.c#raw-page-access](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L315), [nbtpage.c#_bt_getmeta](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L111-L148), [nbtpage.c#_bt_checkpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L688-L720), [bufpage.h#PageGetSpecialPointer](../../../../raw/postgres-12/src/include/storage/bufpage.h#L303-L330)). |
| Assertion build | `PageGetSpecialPointer` asserts that `pd_special` lies between the fixed header size and `BLCKSZ`. An all-zero ordinary page has `pd_special=0`, so an assertion-enabled build aborts there. Without assertions, that validation compiles out; the worker has no explicit zero-page rejection ([bufpage.h#PageValidateSpecialPointer](../../../../raw/postgres-12/src/include/storage/bufpage.h#L303-L330), [c.h#AssertMacro](../../../../raw/postgres-12/src/include/c.h#L719-L793), [assert.c#ExceptionalCondition](../../../../raw/postgres-12/src/backend/utils/error/assert.c#L26-L54), [pgstatindex.c#classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L283-L310)). |

Therefore, use `pgstatindex` as a physical diagnostic, not as proof that a
B-tree is structurally valid and not as a transactionally consistent size or
occupancy snapshot. It does not validate parent/downlink structure, sibling
reciprocity, key order, tuple-to-heap correspondence, or index-state flags
([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L215-L365),
[pg_index.h#index-state-flags](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L32-L44)).

### Regression coverage

The contrib Makefile defines one regression target, `pgstattuple`. Its test
creates an empty primary-key B-tree and calls `pgstatindex` through an untyped
literal, explicit `text`, `name`, and `regclass`. The expected output checks a
one-metapage index, root block 0, zero page counters, and `NaN` ratios
([Makefile#regression-target](../../../../raw/postgres-12/contrib/pgstattuple/Makefile#L1-L13),
[pgstattuple.sql#empty-B-tree](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L1-L37),
[pgstattuple.out#empty-B-tree](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L44-L82)).

The same test verifies wrong-AM errors, unsupported relation kinds, and success
for a physical B-tree index on a table partition
([pgstattuple.sql#object-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L47-L113),
[pgstattuple.out#object-test-results](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L126-L236)).

The checked-in test does not create a populated B-tree. It therefore does not
assert a non-`NaN` density, internal-page counting, backward-link
fragmentation, half-dead pages, deleted pages, percentage rounding, concurrent
extension, malformed-page handling, another-session temporary-index errors,
index-state flags, or non-superuser privileges. The module has no declared
isolation or TAP test target
([Makefile#regression-target](../../../../raw/postgres-12/contrib/pgstattuple/Makefile#L1-L13),
[pgstattuple.sql#complete-test](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L1-L119)).

### Worked measurements and calculations

The [published script](#measurement-script) ran on the pinned PostgreSQL 12.2
build on 2026-09-26. It independently counted page classes with `pageinspect`,
read page-header offsets, and compared the resulting sums and ratios with
`pgstatindex`. Every comparison passed. These fixtures were quiescent while
captured; they do not establish behavior under concurrent page changes.
`bt_page_stats` supplies page type, free space, and sibling links, while
`page_header(get_raw_page(...))` supplies the header offsets
([btreefuncs.c#GetBTPageStatistics](../../../../raw/postgres-12/contrib/pageinspect/btreefuncs.c#L90-L153),
[btreefuncs.c#bt_page_stats](../../../../raw/postgres-12/contrib/pageinspect/btreefuncs.c#L161-L237),
[rawpage.c#page_header](../../../../raw/postgres-12/contrib/pageinspect/rawpage.c#L219-L285)).

Reported results from that script:

| Capture | Blocks | Internal / live leaf / half-dead / deleted | Retained `LP_DEAD` items | `index_size` bytes | Density % | Fragmentation % |
|---|---:|---|---:|---:|---:|---:|
| Empty primary-key index | 1 | 0 / 0 / 0 / 0 | 0 | 8,192 | `NaN` | `NaN` |
| Sorted build, 100,000 keys | 276 | 1 / 274 / 0 / 0 | 0 | 2,260,992 | 89.83 | 0 |
| Deterministic permuted inserts, 100,000 keys | 295 | 1 / 293 / 0 / 0 | 0 | 2,416,640 | 84.03 | 49.83 |
| Delete 80,000 keys; no VACUUM | 276 | 1 / 274 / 0 / 0 | 0 | 2,260,992 | 89.83 | 0 |
| Scan the deleted key range | 276 | 1 / 274 / 0 / 0 | 80,000 | 2,260,992 | 89.83 | 0 |
| VACUUM the same index | 276 | 1 / 56 / 0 / 218 | 0 | 2,260,992 | 87.91 | 0 |

The script's `results.txt` reports these outputs; `killed-scan.txt` confirms
that the deleted-range query used an ordinary index scan and returned zero.
The equality of the two pre-VACUUM densities demonstrates the distinction
between dead-item flags and reclaimed storage. VACUUM changed the denominator
by moving empty leaves into the deleted class, so its result is occupancy of
the remaining live leaves, rather than occupancy of every physical block
([itemid.h#ItemIdMarkDead](../../../../raw/postgres-12/src/include/storage/itemid.h#L160-L182),
[pgstatindex.c#classification-and-leaf-space](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310)).

For the permuted-insert fixture, the census supplied 293 live leaves,
2,388,536 bytes of total leaf capacity, 381,524 bytes of allocatable free
space, and 146 backward right-links. The measured block size was 8,192 bytes.
Using the worker's formulas gives:

1. **Size:** `(1 metapage + 1 internal + 293 leaves) * 8192 = 2,416,640` bytes.
2. **Density:** format `100 - 381524 / 2388536 * 100` with `%.2f` to get
   `84.03` percent.
3. **Fragmentation:** format `146 / 293 * 100` with `%.2f` to get `49.83`
   percent. All 293 live leaves are in the denominator, including the
   rightmost leaf.

The sums come from the [script](#measurement-script); the arithmetic and
formatting come from
[pgstatindex.c#result-formulas](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L333-L359).
The census also checked that every live leaf's `free_size` equaled
`max(pd_upper - pd_lower - 4, 0)`. The four-byte reservation is one
`ItemIdData` slot on this build, matching `PageGetFreeSpace`
([itemid.h#ItemIdData](../../../../raw/postgres-12/src/include/storage/itemid.h#L23-L39),
[bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L597)).

The permission stage produced these results under a role with neither schema
`USAGE` nor relation `SELECT` for the private fixture:

| Call / role state | Observed result |
|---|---|
| No function execution grant | `permission denied for function pgstatindex` |
| Granted `pg_stat_scan_tables`; explicit text name in private schema | `permission denied for schema wiki_stat12_private` |
| Same role; named `regclass` input in private schema | Same schema permission error |
| Same role; OID resolved earlier by the fixture owner | Scan succeeded and reported format version 4 |

These observations are reproduced by the script's `permissions` stage and
support the boundary described above: name lookup enforces schema access,
while the OID wrapper opens the relation without a relation `SELECT` check
([namespace.c#LookupExplicitNamespace](../../../../raw/postgres-12/src/backend/catalog/namespace.c#L2884-L2915),
[regproc.c#regclassin](../../../../raw/postgres-12/src/backend/utils/adt/regproc.c#L903-L938),
[pgstatindex.c#OID-wrapper](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L203-L213),
[relation.c#relation_open](../../../../raw/postgres-12/src/backend/access/common/relation.c#L35-L79)).

### Causal summary

An authorized call opens a physical B-tree, copies its stored true-root
metadata, and captures the main-fork length once. Physical block order then
supplies one page at a time. Flags determine its class; only live leaves
supply capacity, free space, and backward right-links. The counter sum
produces byte size, while the leaf sums produce two ratios rounded through
`%.2f`, or `NaN` for zero denominators. Page maintenance changes the inputs
that a later call reads; there is no separate statistics refresh. Concurrent
maintenance can make one call combine observations from different times
([pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L215-L365),
[pgstattuple.sgml#page-by-page-caveat](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L268-L279)).

## Measurement Script

This is the page's single measurement script. It measures the byte-size,
density, fragmentation, dead-item, and page-class examples above, and tests
the schema/function privilege boundary. The separate page census uses
`bt_page_stats` for page classes and `PageGetFreeSpace` results, then checks
those free-space results against raw header offsets. It is a cross-check of
quiescent page images, not an independent corruption validator
([btreefuncs.c#GetBTPageStatistics](../../../../raw/postgres-12/contrib/pageinspect/btreefuncs.c#L90-L153),
[rawpage.c#page_header](../../../../raw/postgres-12/contrib/pageinspect/rawpage.c#L219-L285)).

Save the full fenced script as `.wiki-runtime/tmp/stat12-work/measure.sh`
(create its parent directory first). From the repository root, invoke
`bash .wiki-runtime/tmp/stat12-work/measure.sh`. Its default order is
`build start test fixtures measure vacuum permissions report clean`.
To re-run measurements while the build remains present, invoke
`bash .wiki-runtime/tmp/stat12-work/measure.sh fixtures measure vacuum permissions report`,
then `bash .wiki-runtime/tmp/stat12-work/measure.sh clean` after reading the
outputs. After cleanup, a new run rebuilds. The saved script is separate from
the cluster sandbox; remove its working directory when finished.

| Stage | Purpose / prerequisite |
|---|---|
| `build` | Check the exact pin and absence of tracked source edits; configure/build/install out of tree. Reuses an existing owned build. |
| `start` | Initialize a `C`-locale UTF-8 trust-authenticated disposable cluster if absent; start it on socket `.wiki-runtime/tmp/stat12/s`, port 55462. An already-running owned cluster is accepted. |
| `test` | Run the pinned `pgstattuple` and `pageinspect` installcheck suites against this cluster. Requires `build start`. |
| `fixtures` | Recreate the empty, sorted, and permuted-insert fixtures and the result table. Requires a running cluster. |
| `measure` | Replace the three baseline captures with a page census and formula comparisons. Requires `fixtures`. |
| `vacuum` | Recreate the churn fixture; capture after DELETE, after an index scan sets dead-item hints, and after VACUUM. Requires `fixtures`. |
| `permissions` | Recreate the private-schema fixture and test role; check exact denial messages and the already-resolved OID path. Requires the extensions from `fixtures`. |
| `report` | Print platform facts and the result table; check that fragmentation, retained dead items, and deleted pages were exercised. Requires `measure vacuum`. |
| `stop` | Fast-stop the owned cluster and check PID, process, socket, and TCP-port teardown. Idempotent while the owned sandbox exists. |
| `clean` | Run `stop` and delete `.wiki-runtime/tmp/stat12/`, including its build and outputs. Idempotent if already absent. |

The only optional input variable is `PGSTAT12_JOBS`, a positive integer
(default `4`) controlling build parallelism. The repository root is the
current physical working directory. The pin, sandbox, socket, port, and
cluster owner are fixed in the script. It sets `LC_ALL=C`, redirects `TMPDIR`
and `PG_REGRESS_SOCK_DIR` into the sandbox, sets connection variables for
installcheck, clears service/credential/connection overrides, and supplies
host, port, user, and database explicitly to each fixture `psql` call.

Prerequisites are Bash, Git with `--no-lazy-fetch` support, the local C/build
toolchain required by this checkout, and POSIX utilities. `pgrep` and `lsof`
are also required for the repository's mandated teardown checks. Those checks
follow **MANDATORY Environment Isolation**, which takes precedence over the
measurement tool allowlist. The build uses `--without-readline --without-zlib
--disable-nls --enable-cassert`, with `CC=cc` and
`CFLAGS='-O2 -Wno-deprecated-non-prototype'`. It installs `pgstattuple` and
`pageinspect`; no system PostgreSQL installation or network fetch is used.
Every table, index, role, and schema created here is a disposable fixture.
Do not run the fixture SQL against a database that matters.

Output lands under `.wiki-runtime/tmp/stat12/out/`. Read `results.txt` first,
then `permissions.txt`, `killed-scan.txt`, and the two `*-test.log` files.
The default `report` stage prints the results before `clean` deletes the
files. Allow several minutes for a cold build; the fixture and measurement
stages take a few seconds on the recorded machine while the build is retained.

All GUC settings have these scopes:

| Setting | Context and apply scope | Script use |
|---|---|---|
| `statement_timeout`, `lock_timeout` | `user`; session `SET`, no reload/restart | 120 seconds / 5 seconds in each fixture/capture connection ([guc.c#timeouts](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2378-L2398)). |
| `enable_seqscan`, `enable_bitmapscan`, `enable_indexonlyscan` | `user`; session `SET`, no reload/restart | Disabled only in the disposable deleted-range scan connection ([guc.c#scan-method-settings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L884-L922)). |
| `role` | `user`; session scope, subject to role authorization | `SET ROLE`/`RESET ROLE` exercise the disposable role ([guc.c#role](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3826-L3836)). |
| `autovacuum` | `sighup`; reload for an existing server | Supplied as `off` at this isolated server's startup to keep fixtures stable ([guc.c#autovacuum](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1426-L1434)). |
| `port`, `unix_socket_directories`, `listen_addresses` | `postmaster`; restart required | Supplied at startup; listen addresses are empty, so connections use the private Unix socket ([guc.c#port](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2177-L2185), [guc.c#socket-and-listen](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3936-L3958)). |
| `debug_assertions` | `internal`; cannot be changed with a GUC | Read for the platform record; `--enable-cassert` selected the build ([guc.c#debug_assertions](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1254-L1267)). |

**Last run:** 2026-09-26, PostgreSQL 12.2 at
`45b88269a353ad93744772791feb6d01bc7e1e42`, Darwin arm64 (server build target `arm-apple-darwin27.0.0`), Apple clang
21.0.0, 64-bit, `block_size=8192`, `max_data_alignment=8`, assertions enabled,
locale `C`, UTF-8, data checksums disabled. `pg_control_init()` supplied the
alignment field. Both extension regression suites passed (pgstattuple: 1;
pageinspect: 5). The six captures and all formula checks passed, as did the
permission cases. These observations supplement the pinned-source evidence;
concurrent, half-dead, invalid-index, and malformed-page cases were not measured
([pg_controldata.c#pg_control_init](../../../../raw/postgres-12/src/backend/utils/misc/pg_controldata.c#L264-L292),
[pgstattuple/Makefile#REGRESS](../../../../raw/postgres-12/contrib/pgstattuple/Makefile#L1-L13),
[pageinspect/Makefile#REGRESS](../../../../raw/postgres-12/contrib/pageinspect/Makefile#L1-L16)).

```bash
#!/usr/bin/env bash
set -uo pipefail
# Disposable fixtures only. Run from the repository root.
REPO=$(pwd -P)
PIN=45b88269a353ad93744772791feb6d01bc7e1e42
SRC=$REPO/raw/postgres-12
RUN=$REPO/.wiki-runtime/tmp/stat12
BUILD=$RUN/build
INSTALL=$RUN/install
DATA=$RUN/data
SOCKET=$RUN/s
OUT=$RUN/out
export TMPDIR=$RUN/t PG_REGRESS_SOCK_DIR=$RUN/r LC_ALL=C
PORT=55462
DBUSER=wiki_pgstat12
JOBS=${PGSTAT12_JOBS:-4}
case "$JOBS" in ''|*[!0-9]*|0) exit 2 ;; esac
unset PGSERVICE PGSERVICEFILE PGHOSTADDR PGOPTIONS PGDATABASE PGUSER
unset PGPASSWORD PGPASSFILE PGTARGETSESSIONATTRS
export PGHOST=$SOCKET PGPORT=$PORT PGUSER=$DBUSER PGDATABASE=postgres
OWNER="$REPO $PIN $PORT"
die() { printf '%s\n' "$*" >&2; exit 1; }
owned() {
  test -f "$RUN/owner" && test "$(cat "$RUN/owner")" = "$OWNER"
}
sql() {
  owned || die "No owned sandbox"
  "$INSTALL/bin/psql" -X -v ON_ERROR_STOP=1 \
    -h "$SOCKET" -p "$PORT" -U "$DBUSER" -d postgres "$@"
}
stop_server() {
  owned || die "Refusing to stop an unowned sandbox: $RUN"
  if test -f "$DATA/postmaster.pid"; then
    "$INSTALL/bin/pg_ctl" -D "$DATA" -m fast -w stop || return 1
  fi
  test ! -e "$DATA/postmaster.pid" || return 1
  # Required teardown checks take precedence over the measurement tool list.
  pgrep -f -- "$DATA" > "$RUN/process-check.txt"
  test "$?" -eq 1 || return 1
  test ! -e "$SOCKET/.s.PGSQL.$PORT" || return 1
  test ! -e "$SOCKET/.s.PGSQL.$PORT.lock" || return 1
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN > "$RUN/port-check.txt"; then
    return 1
  fi
}
on_exit() {
  status=$?
  if test "$status" -ne 0 && owned && test -f "$DATA/postmaster.pid"; then
    stop_server || printf '%s\n' "Cleanup failed; inspect $RUN" >&2
  fi
}
trap on_exit EXIT

build() {
  test -f "$REPO/wiki/versions.md" || die "Run from the repository root"
  test "$(git --no-lazy-fetch -C "$SRC" rev-parse HEAD)" = "$PIN" || die "Wrong pin"
  git --no-lazy-fetch -C "$SRC" diff --quiet || die "Tracked source changes"
  git --no-lazy-fetch -C "$SRC" diff --cached --quiet || die "Staged source changes"
  if test -e "$RUN"; then owned || die "Existing unowned sandbox: $RUN"; fi
  mkdir -p "$BUILD" "$OUT" "$SOCKET" "$TMPDIR" "$PG_REGRESS_SOCK_DIR" \
    || die "mkdir failed"
  printf '%s\n' "$OWNER" > "$RUN/owner"
  if test ! -f "$BUILD/Makefile"; then
    (cd "$BUILD" && CC=cc CFLAGS='-O2 -Wno-deprecated-non-prototype' \
      "$SRC/configure" --prefix="$INSTALL" --without-readline \
      --without-zlib --disable-nls --enable-cassert) \
      > "$OUT/configure.log" 2>&1 || die "See configure.log"
  fi
  make -C "$BUILD" -j "$JOBS" > "$OUT/build.log" 2>&1 || die "See build.log"
  make -C "$BUILD" install > "$OUT/install.log" 2>&1 || die "See install.log"
  for module in pgstattuple pageinspect; do
    make -C "$BUILD/contrib/$module" -j "$JOBS" all install \
      > "$OUT/$module-build.log" 2>&1 || die "See $module-build.log"
  done
}

start() {
  owned || die "Run build first"
  if test -f "$DATA/postmaster.pid"; then
    "$INSTALL/bin/pg_ctl" -D "$DATA" status || die "Stale pid file"
    return
  fi
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN > "$RUN/port-check.txt"; then
    die "Port is already in use"
  fi
  test ! -e "$SOCKET/.s.PGSQL.$PORT" || die "Socket is already in use"
  if test ! -f "$DATA/PG_VERSION"; then
    "$INSTALL/bin/initdb" -D "$DATA" -A trust -U "$DBUSER" \
      --locale=C --encoding=UTF8 > "$OUT/initdb.log" 2>&1 || die "initdb failed"
  fi
  "$INSTALL/bin/pg_ctl" -D "$DATA" -l "$OUT/server.log" -w start \
    -o "-p $PORT -k $SOCKET -c listen_addresses='' -c autovacuum=off" \
    || die "Server start failed"
}

test_extensions() {
  for module in pgstattuple pageinspect; do
    make -C "$BUILD/contrib/$module" installcheck \
      > "$OUT/$module-test.log" 2>&1 || die "See $module-test.log"
  done
}

fixtures() {
  sql > "$OUT/fixtures.txt" <<'SQL'
SET /* wiki_stat12_timeout */ statement_timeout = '120s';
SET /* wiki_stat12_lock_timeout */ lock_timeout = '5s';
CREATE /* wiki_stat12_extension */ EXTENSION IF NOT EXISTS pgstattuple;
CREATE /* wiki_stat12_extension */ EXTENSION IF NOT EXISTS pageinspect;
DROP /* wiki_stat12_disposable */ SCHEMA IF EXISTS wiki_stat12 CASCADE;
CREATE /* wiki_stat12_disposable */ SCHEMA wiki_stat12;
CREATE /* wiki_stat12_empty */ TABLE wiki_stat12.empty (id integer PRIMARY KEY);
CREATE /* wiki_stat12_sorted */ TABLE wiki_stat12.sorted (id integer);
INSERT /* wiki_stat12_sorted */ INTO wiki_stat12.sorted SELECT generate_series(1,100000);
CREATE /* wiki_stat12_sorted */ INDEX sorted_idx ON wiki_stat12.sorted(id) WITH (fillfactor=90);
CREATE /* wiki_stat12_random */ TABLE wiki_stat12.random (id integer);
CREATE /* wiki_stat12_random */ INDEX random_idx ON wiki_stat12.random(id);
INSERT /* wiki_stat12_random */ INTO wiki_stat12.random
SELECT g FROM generate_series(1,100000) g ORDER BY (g::bigint * 48271) % 100003;
CREATE /* wiki_stat12_results */ TABLE wiki_stat12.results (
  label text PRIMARY KEY, index_name text, nblocks bigint,
  version integer, tree_level integer, index_size bigint, root_block_no bigint,
  internal_pages bigint, leaf_pages bigint, empty_pages bigint, deleted_pages bigint,
  avg_leaf_density float8, leaf_fragmentation float8,
  capacity bigint, free_bytes bigint, fragments bigint, dead_items bigint,
  census_internal bigint, census_leaf bigint, census_empty bigint, census_deleted bigint,
  free_space_matches boolean, metadata_matches boolean
);
SQL
  test "$?" -eq 0 || die "Fixtures failed"
}

capture() {
  sql -v label="$1" -v idx="$2" > "$OUT/$1.txt" <<'SQL'
SET /* wiki_stat12_timeout */ statement_timeout = '120s';
SET /* wiki_stat12_lock_timeout */ lock_timeout = '5s';
SELECT /* wiki_stat12_blocks */ pg_relation_size(:'idx'::regclass, 'main') /
  current_setting('block_size')::integer AS nblocks \gset
CREATE /* wiki_stat12_census */ TEMP TABLE census AS
SELECT b AS block, p.type, p.free_size, p.btpo_next, p.dead_items,
       h.lower, h.upper, h.special
FROM generate_series(1, :nblocks - 1) b
CROSS JOIN LATERAL bt_page_stats(:'idx', b) p
CROSS JOIN LATERAL page_header(get_raw_page(:'idx', b)) h;
DELETE /* wiki_stat12_replace_capture */ FROM wiki_stat12.results WHERE label = :'label';
INSERT /* wiki_stat12_capture */ INTO wiki_stat12.results
SELECT :'label', :'idx', :nblocks, s.*,
  COALESCE(c.capacity,0), COALESCE(c.free_bytes,0), c.fragments, COALESCE(c.dead_items,0),
  c.internal, c.leaf, c.empty, c.deleted, COALESCE(c.free_matches,true),
  s.version=m.version AND s.tree_level=m.level AND s.root_block_no=m.root
FROM pgstatindex(:'idx'::regclass) s
CROSS JOIN bt_metap(:'idx') m
CROSS JOIN (
  SELECT sum(special-24) FILTER (WHERE type='l') AS capacity,
    sum(free_size) FILTER (WHERE type='l') AS free_bytes,
    count(*) FILTER (WHERE type='l' AND btpo_next<>0 AND btpo_next<block) AS fragments,
    sum(dead_items) FILTER (WHERE type='l') AS dead_items,
    count(*) FILTER (WHERE type NOT IN ('l','e','d')) AS internal,
    count(*) FILTER (WHERE type='l') AS leaf,
    count(*) FILTER (WHERE type='e') AS empty,
    count(*) FILTER (WHERE type='d') AS deleted,
    bool_and(free_size=GREATEST(upper-lower-4,0)) FILTER (WHERE type='l') AS free_matches
  FROM census
) c;
DO /* wiki_stat12_check */ $$
BEGIN
  IF EXISTS (SELECT 1 FROM wiki_stat12.results WHERE
      index_size<>nblocks*current_setting('block_size')::integer OR
      internal_pages<>census_internal OR leaf_pages<>census_leaf OR
      empty_pages<>census_empty OR deleted_pages<>census_deleted OR
      NOT free_space_matches OR NOT metadata_matches OR
      avg_leaf_density <> CASE WHEN capacity=0 THEN 'NaN'::float8
        ELSE round(100-free_bytes::numeric/capacity*100,2)::float8 END OR
      leaf_fragmentation <> CASE WHEN leaf_pages=0 THEN 'NaN'::float8
        ELSE round(fragments::numeric/leaf_pages*100,2)::float8 END) THEN
    RAISE EXCEPTION 'pgstatindex/census mismatch';
  END IF;
END $$;
SQL
  test "$?" -eq 0 || die "Capture failed: $1"
}

measure() {
  capture empty wiki_stat12.empty_pkey
  capture sorted wiki_stat12.sorted_idx
  capture random wiki_stat12.random_idx
}

vacuum_case() {
  sql > "$OUT/churn-fixture.txt" <<'SQL'
SET /* wiki_stat12_timeout */ statement_timeout = '120s';
SET /* wiki_stat12_lock_timeout */ lock_timeout = '5s';
DROP /* wiki_stat12_disposable */ TABLE IF EXISTS wiki_stat12.churn;
CREATE /* wiki_stat12_churn */ TABLE wiki_stat12.churn(id integer);
INSERT /* wiki_stat12_churn */ INTO wiki_stat12.churn SELECT generate_series(1,100000);
CREATE /* wiki_stat12_churn */ INDEX churn_idx ON wiki_stat12.churn(id) WITH (fillfactor=90);
DELETE /* wiki_stat12_churn */ FROM wiki_stat12.churn WHERE id<=80000;
SQL
  test "$?" -eq 0 || die "Churn fixture failed"
  capture after_delete wiki_stat12.churn_idx
  sql > "$OUT/killed-scan.txt" <<'SQL'
SET /* wiki_stat12_timeout */ statement_timeout = '120s';
SET /* wiki_stat12_lock_timeout */ lock_timeout = '5s';
SET /* wiki_stat12_index_scan */ enable_seqscan = off;
SET /* wiki_stat12_index_scan */ enable_bitmapscan = off;
SET /* wiki_stat12_index_scan */ enable_indexonlyscan = off;
EXPLAIN /* wiki_stat12_scan_plan */ (COSTS OFF)
SELECT /* wiki_stat12_dead_range */ count(*) FROM wiki_stat12.churn WHERE id<=80000;
SELECT /* wiki_stat12_dead_range */ count(*) FROM wiki_stat12.churn WHERE id<=80000;
SQL
  test "$?" -eq 0 || die "Killed-tuple scan failed"
  capture after_kill wiki_stat12.churn_idx
  sql > "$OUT/vacuum.txt" <<'SQL'
SET /* wiki_stat12_timeout */ statement_timeout = '120s';
SET /* wiki_stat12_lock_timeout */ lock_timeout = '5s';
VACUUM /* wiki_stat12_vacuum */ (VERBOSE, ANALYZE) wiki_stat12.churn;
SQL
  test "$?" -eq 0 || die "VACUUM failed"
  capture after_vacuum wiki_stat12.churn_idx
}

permissions() {
  sql > "$OUT/permissions.txt" 2>&1 <<'SQL'
SET /* wiki_stat12_timeout */ statement_timeout = '120s';
SET /* wiki_stat12_lock_timeout */ lock_timeout = '5s';
DROP /* wiki_stat12_disposable */ SCHEMA IF EXISTS wiki_stat12_private CASCADE;
DROP /* wiki_stat12_disposable */ ROLE IF EXISTS wiki_stat12_reader;
CREATE /* wiki_stat12_disposable */ ROLE wiki_stat12_reader;
CREATE /* wiki_stat12_private */ SCHEMA wiki_stat12_private;
CREATE /* wiki_stat12_private */ TABLE wiki_stat12_private.t(id integer PRIMARY KEY);
REVOKE /* wiki_stat12_private */ ALL ON SCHEMA wiki_stat12_private FROM PUBLIC;
SELECT /* wiki_stat12_resolve_oid */ 'wiki_stat12_private.t_pkey'::regclass::oid AS idxoid \gset
SET /* wiki_stat12_reader */ ROLE wiki_stat12_reader;
DO /* wiki_stat12_execute_denied */ $$
BEGIN
  BEGIN
    PERFORM /* wiki_stat12_execute_denied */ public.pgstatindex('wiki_stat12.empty_pkey'::text);
    RAISE EXCEPTION 'Expected function execution denial';
  EXCEPTION WHEN insufficient_privilege THEN
    IF SQLERRM <> 'permission denied for function pgstatindex' THEN RAISE; END IF;
    RAISE NOTICE 'PASS: function execution denied without grant';
  END;
END $$;
RESET /* wiki_stat12_reader */ ROLE;
GRANT /* wiki_stat12_reader */ pg_stat_scan_tables TO wiki_stat12_reader;
SET /* wiki_stat12_reader */ ROLE wiki_stat12_reader;
DO /* wiki_stat12_schema_denied */ $$
BEGIN
  BEGIN
    PERFORM /* wiki_stat12_text_schema */ public.pgstatindex('wiki_stat12_private.t_pkey'::text);
    RAISE EXCEPTION 'Expected schema lookup denial for text';
  EXCEPTION WHEN insufficient_privilege THEN
    IF SQLERRM <> 'permission denied for schema wiki_stat12_private' THEN RAISE; END IF;
    RAISE NOTICE 'PASS: schema lookup denied for text';
  END;
  BEGIN
    PERFORM /* wiki_stat12_regclass_schema */ public.pgstatindex('wiki_stat12_private.t_pkey'::regclass);
    RAISE EXCEPTION 'Expected schema lookup denial for named regclass';
  EXCEPTION WHEN insufficient_privilege THEN
    IF SQLERRM <> 'permission denied for schema wiki_stat12_private' THEN RAISE; END IF;
    RAISE NOTICE 'PASS: schema lookup denied for named regclass';
  END;
END $$;
SELECT /* wiki_stat12_oid_access */ current_user,
  has_schema_privilege(current_user,'wiki_stat12_private','USAGE') AS schema_usage,
  has_table_privilege(current_user,:idxoid::oid,'SELECT') AS relation_select,
  (public.pgstatindex(:idxoid::oid::regclass)).version AS oid_call_version;
RESET /* wiki_stat12_reader */ ROLE;
SQL
  test "$?" -eq 0 || die "Permissions test failed"
}

report() {
  { date -u '+%Y-%m-%dT%H:%M:%SZ'; uname -s; uname -m;
    printf 'pin=%s\n' "$PIN"; "$INSTALL/bin/pg_config" --configure;
    sql -A -F '|' <<'SQL'
SET /* wiki_stat12_timeout */ statement_timeout = '120s';
SET /* wiki_stat12_lock_timeout */ lock_timeout = '5s';
SELECT /* wiki_stat12_platform */ version(), current_setting('block_size'),
  max_data_alignment, current_setting('debug_assertions') FROM pg_control_init();
SELECT /* wiki_stat12_results */ label,nblocks,version,tree_level,root_block_no,
  internal_pages,leaf_pages,empty_pages,deleted_pages,index_size,
  capacity,free_bytes,fragments,dead_items,avg_leaf_density,leaf_fragmentation
FROM wiki_stat12.results ORDER BY label;
DO /* wiki_stat12_fixture_checks */ $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM wiki_stat12.results WHERE label='random' AND fragments>0)
    OR NOT EXISTS (SELECT 1 FROM wiki_stat12.results WHERE label='after_kill' AND dead_items>0)
    OR NOT EXISTS (SELECT 1 FROM wiki_stat12.results WHERE label='after_vacuum' AND deleted_pages>0)
  THEN RAISE EXCEPTION 'A fixture did not exercise its intended branch'; END IF;
END $$;
SQL
  } > "$OUT/results.txt"
  test "$?" -eq 0 || die "Report failed"
  cat "$OUT/results.txt"
}

clean() {
  if test ! -e "$RUN"; then return; fi
  stop_server || die "Teardown checks failed; leaving sandbox for inspection"
  rm -rf "$RUN" || die "Sandbox removal failed"
  test ! -e "$RUN" || die "Sandbox remains"
}

if test "$#" -eq 0; then
  set -- build start test fixtures measure vacuum permissions report clean
fi
for stage in "$@"; do
  printf 'stage=%s\n' "$stage"
  case "$stage" in
    build) build ;; start) start ;; test) test_extensions ;; fixtures) fixtures ;;
    measure) measure ;; vacuum) vacuum_case ;; permissions) permissions ;;
    report) report ;; stop) stop_server || die "Stop failed" ;; clean) clean ;;
    *) die "Unknown stage: $stage" ;;
  esac
done
```

## Context Reviewed

- Pinned checkout: `raw/postgres-12/` at
  `45b88269a353ad93744772791feb6d01bc7e1e42` (`REL_12_2`).
- SQL/module boundary: control file, Makefile, 1.4 base SQL, 1.4-to-1.5 update
  SQL, extension install-path code, fmgr V1 registration and loading.
- Core worker: every `pgstatindex` wrapper, `BTIndexStat`, and every statement
  in `pgstatindex_impl`.
- B-tree boundary: metapage and opaque structures, true/fast roots, root split,
  page deletion, half-dead/deleted/recyclable states, high keys, and ordinary
  B-tree page checks.
- Storage and concurrency: relation opening/closing, lock conflict table, DML
  and VACUUM index locks, `ReadBufferExtended`, generic page validation,
  per-buffer content locks, block-count path, forks, and extension-lock handling
  in B-tree VACUUM.
- Tests and docs: complete `pgstattuple.sql`/expected output, contrib Makefiles,
  `pageinspect` btree/raw-page functions and SQL signatures, and the PostgreSQL
  12 `pgstattuple` documentation.
- Permission and build boundaries: namespace lookup, `regclassin`, the
  special-pointer assertion macros and backend assertion abort, and GUC
  definitions for every setting the measurement script uses.
- Direct history inspected: `fd321a1dfd6` (v1.5 privilege split),
  `48e6c943e5f` (page classification, metapage inclusion in `index_size`, and
  root counting), and `af7d181298f` (explicit empty-index `NaN` handling); each
  is an ancestor of the pinned commit.
- Supplementary exact-pin check: the full [measurement script](#measurement-script)
  built PostgreSQL 12.2 with assertions, ran both extension installchecks,
  checked six quiescent page censuses and formulas, and exercised the function,
  schema, and OID permission boundaries. All passed; the pinned source remains
  the evidence base.

## Evidence Map

| Claim | Primary evidence |
|---|---|
| Fresh v1.5 installation follows the 1.4 base plus update path | [Makefile#extension-scripts](../../../../raw/postgres-12/contrib/pgstattuple/Makefile#L3-L13), [extension.c#install-path-selection](../../../../raw/postgres-12/src/backend/commands/extension.c#L1297-L1400) |
| Both SQL overloads reach `pgstatindex_impl` under `AccessShareLock` | [pgstatindex.c#wrappers](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L134-L216) |
| Only physical built-in B-tree indexes are accepted | [pgstatindex.c#object-check](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L224-L238), [pg_am.dat#BTREE_AM_OID](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L15-L23) |
| Reported metadata comes from true-root fields on block 0 | [pgstatindex.c#metapage-read](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L253), [nbtree.h#BTMetaPageData](../../../../raw/postgres-12/src/include/access/nbtree.h#L90-L110) |
| The metapage read is neither content-locked nor B-tree-validated | [pgstatindex.c#metapage-read](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L253), [nbtpage.c#_bt_getmeta](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L111-L148) |
| The worker captures main-fork length once and scans every captured non-metapage block | [pgstatindex.c#scan-loop](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L255-L315), [bufmgr.h#RelationGetNumberOfBlocks](../../../../raw/postgres-12/src/include/storage/bufmgr.h#L188-L199) |
| `empty_pages` means half-dead pages, while deleted-page recyclability is not distinguished | [pgstatindex.c#classification](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L286-L310), [nbtpage.c#_bt_page_recyclable](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L931-L963) |
| `index_size` is captured main-fork blocks times `BLCKSZ` | [pgstatindex.c#index-size](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L333-L346), [relpath.h#fork-numbers](../../../../raw/postgres-12/src/include/common/relpath.h#L32-L53) |
| Density is summed physical leaf occupancy using `PageGetFreeSpace` | [pgstatindex.c#leaf-and-result-formulas](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L356), [bufpage.c#PageGetFreeSpace](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L597) |
| `LP_DEAD` tuple storage still contributes to density | [itemid.h#ItemIdMarkDead](../../../../raw/postgres-12/src/include/storage/itemid.h#L160-L182), [pgstatindex.c#leaf-branch](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L292-L307) |
| Fragmentation is the percentage of live leaves with a backward physical right-link | [pgstatindex.c#fragmentation](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L300-L307), [pgstatindex.c#fragmentation-result](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L352-L356) |
| Both percentages are limited to two decimal places | [pgstatindex.c#result-formulas](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L347-L359) |
| Results are page-by-page, not a whole-index snapshot | [pgstattuple.sgml#page-by-page-caveat](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L268-L279), [lock.c#LockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L61-L105) |
| Schema lookup checks apply to names, while direct OID opening adds no relation SELECT check | [namespace.c#LookupExplicitNamespace](../../../../raw/postgres-12/src/backend/catalog/namespace.c#L2884-L2915), [regproc.c#regclassin](../../../../raw/postgres-12/src/backend/utils/adt/regproc.c#L903-L938), [relation.c#relation_open](../../../../raw/postgres-12/src/backend/access/common/relation.c#L35-L79) |
| Special-pointer assertions still apply in assertion builds | [bufpage.h#PageGetSpecialPointer](../../../../raw/postgres-12/src/include/storage/bufpage.h#L303-L330), [c.h#AssertMacro](../../../../raw/postgres-12/src/include/c.h#L719-L793), [assert.c#ExceptionalCondition](../../../../raw/postgres-12/src/backend/utils/error/assert.c#L26-L54) |
| The worker is not a B-tree integrity checker | [pgstatindex.c#raw-page-access](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L240-L315), [nbtpage.c#B-tree-page-checks](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L688-L720) |
| In-tree coverage is limited to empty output and object/error paths | [pgstattuple.sql#complete-test](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L1-L119), [pgstattuple.out#complete-output](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L1-L248) |

## Open Questions

- No unresolved source claim remains for the PostgreSQL 12.2 calculation path
  documented above.
- The in-tree verification gap remains substantial: there is no populated,
  concurrent, malformed-page, permissions, temporary-relation, or index-state
  regression/isolation/TAP case
  ([Makefile#regression-target](../../../../raw/postgres-12/contrib/pgstattuple/Makefile#L1-L13),
  [pgstattuple.sql#complete-test](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L1-L119)).
- Malformed-page outcomes can depend on whether the page is already cached,
  checksums are enabled, or assertions are compiled in. This page therefore
  records the source-verifiable absence of B-tree-specific checks but does not
  promise one particular error or misclassification for every corruption shape
  ([bufmgr.c#ReadBufferExtended](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L600-L638),
  [bufpage.c#PageIsVerified](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L64-L142),
  [nbtpage.c#_bt_checkpage](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L688-L720),
  [bufpage.h#PageValidateSpecialPointer](../../../../raw/postgres-12/src/include/storage/bufpage.h#L303-L330),
  [c.h#AssertMacro](../../../../raw/postgres-12/src/include/c.h#L719-L793)).

## Source References

- [namespace.c#RangeVarGetRelidExtended](../../../../raw/postgres-12/src/backend/catalog/namespace.c#L205-L355) and [namespace.c#LookupExplicitNamespace](../../../../raw/postgres-12/src/backend/catalog/namespace.c#L2884-L2915) - relation-name lookup and schema USAGE.
- [regproc.c#regclassin](../../../../raw/postgres-12/src/backend/utils/adt/regproc.c#L903-L938) - named versus numeric OID inputs.
- [bufpage.h#PageGetSpecialPointer](../../../../raw/postgres-12/src/include/storage/bufpage.h#L303-L330), [c.h#assertions](../../../../raw/postgres-12/src/include/c.h#L719-L793), and [assert.c#ExceptionalCondition](../../../../raw/postgres-12/src/backend/utils/error/assert.c#L26-L54) - assertion-build qualification.
- [nbtpage.c#tuple-removal](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L986-L1015) and [nbtpage.c#unlink-and-delete](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1966-L2017) - lifecycle inputs to a later scan.
- [btreefuncs.c#page-statistics](../../../../raw/postgres-12/contrib/pageinspect/btreefuncs.c#L90-L237) and [rawpage.c#page_header](../../../../raw/postgres-12/contrib/pageinspect/rawpage.c#L219-L285) - measurement census inputs.
- [guc.c#scan-settings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L884-L922), [guc.c#timeouts](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2378-L2398), [guc.c#autovacuum](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1426-L1434), and [guc.c#startup-connection-settings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3936-L3958) - measurement GUC apply scopes.

- [pgstatindex.c#entry-points-and-structures](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L47-L132) - fmgr registrations, AM tests, accumulators, and worker declaration.
- [pgstatindex.c#wrappers](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L134-L216) - legacy and v1.5 text/regclass wrappers.
- [pgstatindex.c#pgstatindex_impl](../../../../raw/postgres-12/contrib/pgstattuple/pgstatindex.c#L215-L365) - checks, scan, formulas, and result construction.
- [pgstattuple.control](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple.control#L1-L5) - default extension version and module path.
- [Makefile#pgstattuple](../../../../raw/postgres-12/contrib/pgstattuple/Makefile#L1-L24) - shared module, SQL scripts, and regression target.
- [pgstattuple--1.4.sql#pgstatindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4.sql#L19-L79) - legacy SQL-to-C bindings.
- [pgstattuple--1.4--1.5.sql#pgstatindex](../../../../raw/postgres-12/contrib/pgstattuple/pgstattuple--1.4--1.5.sql#L22-L100) - v1.5 bindings, attributes, revoke, and grants.
- [extension.c#CreateExtensionInternal](../../../../raw/postgres-12/src/backend/commands/extension.c#L1261-L1400) - default version and install/update-path selection.
- [extension.c#install-then-update](../../../../raw/postgres-12/src/backend/commands/extension.c#L1536-L1550) - base script followed by update scripts.
- [pgstattuple.sgml#pgstatindex](../../../../raw/postgres-12/doc/src/sgml/pgstattuple.sgml#L161-L295) - documented columns and page-by-page caveat.
- [pgstattuple.sql#pgstatindex-tests](../../../../raw/postgres-12/contrib/pgstattuple/sql/pgstattuple.sql#L1-L119) - complete module regression input.
- [pgstattuple.out#pgstatindex-results](../../../../raw/postgres-12/contrib/pgstattuple/expected/pgstattuple.out#L44-L236) - empty output and object/error results.
- [nbtree.h#page-structures](../../../../raw/postgres-12/src/include/access/nbtree.h#L29-L135) - opaque and metapage layouts, flags, and format versions.
- [nbtree.h#page-navigation-macros](../../../../raw/postgres-12/src/include/access/nbtree.h#L173-L219) - `P_NONE`, state macros, and high-key layout.
- [nbtpage.c#metapage-access](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L46-L148) - initialization, upgrade, and standard validation.
- [nbtpage.c#root-access](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L228-L625) - true/fast root selection and root height.
- [nbtpage.c#page-checks-and-reuse](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L688-L963) - ordinary-page checks, extension, zero pages, and recyclability.
- [nbtpage.c#page-deletion](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1320-L1517) - deletion preconditions and two-stage flow.
- [nbtpage.c#mark-half-dead](../../../../raw/postgres-12/src/backend/access/nbtree/nbtpage.c#L1520-L1707) - half-dead transition and dummy high key.
- [nbtinsert.c#new-root](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L2050-L2110) - locked metapage update during a root split.
- [nbtree.c#btvacuumscan](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L944-L1041) - repeated length checks and extension synchronization.
- [bufpage.h#PageHeaderData](../../../../raw/postgres-12/src/include/storage/bufpage.h#L151-L229) - page header, header size, empty/new-page macros.
- [bufpage.c#PageIsVerified](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L64-L142) - generic page-header/checksum validation and all-zero acceptance.
- [bufpage.c#free-space-functions](../../../../raw/postgres-12/src/backend/storage/page/bufpage.c#L572-L647) - allocatable versus exact free space.
- [bufmgr.c#ReadBufferExtended](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L600-L669) - read mode, pin, generic validation, and other-session temp check.
- [bufmgr.c#RelationGetNumberOfBlocksInFork](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2790-L2810) - storage-manager block count.
- [bufmgr.c#LockBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L3585-L3607) - buffer content-lock modes.
- [lock.c#LockConflicts](../../../../raw/postgres-12/src/backend/storage/lmgr/lock.c#L61-L105) - table/index relation-lock conflict matrix.
- [relation.c#relation-open-close](../../../../raw/postgres-12/src/backend/access/common/relation.c#L35-L79) and [relation.c#relation_close](../../../../raw/postgres-12/src/backend/access/common/relation.c#L196-L217) - relation lock and relcache boundary.
- [execIndexing.c#ExecOpenIndices](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L141-L213) - DML's `RowExclusiveLock` on indexes.
- [vacuumlazy.c#index-lock](../../../../raw/postgres-12/src/backend/access/heap/vacuumlazy.c#L279-L288) - lazy VACUUM's index lock.
- [pg_am.h#generated-header-include](../../../../raw/postgres-12/src/include/catalog/pg_am.h#L18-L29), [pg_am.dat#BTREE_AM_OID](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L15-L23), and [catalog/Makefile#generated-catalog-headers](../../../../raw/postgres-12/src/backend/catalog/Makefile#L28-L100) - generated OID symbol path.
- [fmgr.h#PG_FUNCTION_INFO_V1](../../../../raw/postgres-12/src/include/fmgr.h#L383-L413) and [fmgr.c#fetch_finfo_record](../../../../raw/postgres-12/src/backend/utils/fmgr/fmgr.c#L458-L511) - SQL-callable C function metadata.
- [itemid.h#ItemIdMarkDead](../../../../raw/postgres-12/src/include/storage/itemid.h#L160-L182) and [nbtutils.c#_bt_killitems](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1687-L1813) - retained `LP_DEAD` storage and garbage hinting.
- [pg_index.h#index-state-flags](../../../../raw/postgres-12/src/include/catalog/pg_index.h#L32-L44) - validity/readiness/liveness fields that the worker does not inspect.

## Navigation

- [Shared glossary (unverified)](../../../glossary.md)
- [v12/index](../../index.md)
- [Planner Penalties for Bloated Indexes in PostgreSQL 12 (unverified)](../query-planning/bloated-indexes-query-planner.md)
- [Impact of B-Tree Leaf Density (60% vs 90%) on Index Scan Queries in PostgreSQL 12 (unverified)](leaf-density-60-vs-90-query-impact.md)
- [B-Tree Leaf Density vs Fragmentation Impact on Index Scan I/O in PostgreSQL 12 (unverified)](leaf-density-vs-fragmentation-index-scan-io.md)
- [versions](../../../versions.md)
