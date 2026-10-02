---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# How Bi-Directional Logical Replication Works in PostgreSQL 17, and All Related Commits by Minor Version (unverified)

## Question

Explain how bi-directional logical replication works in PostgreSQL 17, and add all commits related to it by minor version.

> Prompt note: the user approved correcting the original prompt wording ("explain how the bi-directional logical replication works, add all commits related to it by minor version") to the form above.

## Answer

PostgreSQL 17 supports bi-directional logical replication by combining ordinary
publish/subscribe logical replication with the subscription parameter
`origin = none`. Each of two nodes publishes a table and subscribes to the same
table on the other node with `origin = none`. Every transaction an apply worker
replays is tagged in WAL with a *replication origin*; a subscription created
with `origin = none` asks the publisher to send only changes that carry **no**
origin. Locally entered data therefore replicates exactly one hop, and replayed
data is filtered out on the way back — that is what prevents infinite loops
([create_subscription.sgml#origin](../../../../raw/postgres-17/doc/src/sgml/ref/create_subscription.sgml#L400-L418),
[replication-origins.sgml:22-24](../../../../raw/postgres-17/doc/src/sgml/replication-origins.sgml#L22-L24),
[030_origin.pl:71-74](../../../../raw/postgres-17/src/test/subscription/t/030_origin.pl#L71-L74)).

There is no dedicated "bidirectional mode": v17 ships the origin filter, the
initial-sync warning, and the reserved origin names. Conflict resolution,
DDL replication, and sequence replication are **not** part of it (see
[Limitations](#what-bi-directional-replication-does-not-include-in-v17)).

### The moving parts

| Piece | Where | Role |
|---|---|---|
| `origin` subscription parameter | [subscriptioncmds.c#parse_subscription_options](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L319-L341) | Accepts only `none` or `any`; default `any` |
| `pg_subscription.suborigin` | [pg_subscription.h#suborigin](../../../../raw/postgres-17/src/include/catalog/pg_subscription.h#L115) | Stores the choice per subscription |
| Replication origin per subscription | [worker.c#run_apply_worker](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L4516-L4526) | Tags all WAL the apply worker writes |
| `XLOG_INCLUDE_ORIGIN` | [xloginsert.c#XLogRecordAssemble](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L840-L847) | Attaches the origin ID to WAL records |
| `origin` option of `pgoutput` | [pgoutput.c#parse_output_parameters](../../../../raw/postgres-17/src/backend/replication/pgoutput/pgoutput.c#L391-L410) | Publisher-side switch `publish_no_origin` |
| `pgoutput_origin_filter` | [pgoutput.c#pgoutput_origin_filter](../../../../raw/postgres-17/src/backend/replication/pgoutput/pgoutput.c#L1722-L1736) | Skips changes whose WAL carries an origin |
| `check_publications_origin` | [subscriptioncmds.c#check_publications_origin](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L2044-L2161) | WARNING for the initial-copy blind spot |

### The `origin` subscription parameter

`CREATE SUBSCRIPTION ... WITH (origin = ...)` accepts exactly two values,
validated case-insensitively against the macros `LOGICALREP_ORIGIN_NONE`
(`"none"`) and `LOGICALREP_ORIGIN_ANY` (`"any"`); anything else raises
`unrecognized origin value`
([subscriptioncmds.c#SUBOPT_ORIGIN](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L319-L341),
[pg_subscription.h#LOGICALREP_ORIGIN_NONE](../../../../raw/postgres-17/src/include/catalog/pg_subscription.h#L34-L44)).
The default is `any`
([subscriptioncmds.c:162-163](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L162-L163)).
The parameter is deliberately a string, not a boolean, so future versions can
filter by specific origin names
([subscriptioncmds.c:328-333](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L328-L333)).

- `CREATE SUBSCRIPTION` accepts it
  ([subscriptioncmds.c:627-632](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L627-L632))
  and stores it in `pg_subscription.suborigin`
  ([subscriptioncmds.c:750-751](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L750-L751),
  [catalogs.sgml#suborigin](../../../../raw/postgres-17/doc/src/sgml/catalogs.sgml#L8075)).
- `ALTER SUBSCRIPTION ... SET (origin = ...)` updates the same column
  ([subscriptioncmds.c:1285-1290](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L1285-L1290)).
  A running apply worker notices the change and exits so the launcher restarts
  it with the new setting — `origin` is in `maybe_reread_subscription`'s
  restart list
  ([worker.c#maybe_reread_subscription](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L3945-L3972)).
- `psql`'s `\dRs+` shows it as the `Origin` column
  ([describe.c:6596](../../../../raw/postgres-17/src/bin/psql/describe.c#L6596)).

### How applied changes get an origin tag

Each subscription owns a replication origin named `pg_<subscription-oid>`
(tablesync workers use `pg_<subscription-oid>_<relation-oid>`)
([worker.c#ReplicationOriginNameForLogicalRep](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L429-L443)).
The apply worker creates the origin if needed and configures the whole session
with it: `replorigin_session_setup(originid, 0)` plus
`replorigin_session_origin = originid`
([worker.c#run_apply_worker](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L4516-L4526)).
Tablesync workers do the same with their per-table origin before copying
([tablesync.c#LogicalRepSyncTableStart](../../../../raw/postgres-17/src/backend/replication/logical/tablesync.c#L1405-L1414),
[tablesync.c:1442-1444](../../../../raw/postgres-17/src/backend/replication/logical/tablesync.c#L1442-L1444)),
so even rows written by the initial COPY are origin-tagged on the subscriber.

From then on, WAL records produced by that session carry the origin ID:

- Row-level records request it explicitly with
  `XLogSetRecordFlags(XLOG_INCLUDE_ORIGIN)` — the comment reads "filtering by
  origin on a row level is much more efficient":
  [heapam.c#heap_insert](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2189-L2190),
  [heapam.c#heap_multi_insert](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2697-L2698),
  [heapam.c#heap_delete](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L3094-L3095),
  [heapam.c#log_heap_update](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L9448-L9449),
  [heapam.c#heap_finish_speculative](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L6420-L6421),
  [tablecmds.c#ExecuteTruncateGuts](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L2264-L2265),
  [message.c#LogLogicalMessage](../../../../raw/postgres-17/src/backend/replication/logical/message.c#L70).
- Transaction records do the same:
  [xact.c#XactLogCommitRecord](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L5922),
  [xact.c#XactLogAbortRecord](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L6068),
  [twophase.c#EndPrepare](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L1201).
- `XLogRecordAssemble` appends an `XLR_BLOCK_ID_ORIGIN` chunk holding
  `replorigin_session_origin` when the flag is set and the session origin is
  valid
  ([xloginsert.c#XLogRecordAssemble](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L840-L847),
  [xlog.h#XLOG_INCLUDE_ORIGIN](../../../../raw/postgres-17/src/include/access/xlog.h#L154)).
- At commit, the origin's replay progress (remote LSN, commit timestamp) is
  advanced crash-safely together with the commit record
  ([xact.c#RecordTransactionCommit](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L1404-L1458)).

Locally executed transactions have `replorigin_session_origin =
InvalidRepOriginId`, so their WAL carries no origin chunk — that absence is
what `origin = none` selects for.

### How the publisher filters by origin

1. The subscriber's apply worker copies `pg_subscription.suborigin` into the
   streaming options
   ([worker.c#set_stream_options](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L4408-L4409))
   and the walreceiver adds `origin '<value>'` to `START_REPLICATION ...
   (proto_version ..., origin 'none', publication_names ...)`, but only when
   the publisher is version 16 or newer
   ([libpqwalreceiver.c#libpqrcv_startstreaming](../../../../raw/postgres-17/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L664-L669)).
2. On the publisher, `pgoutput` parses the option into
   `PGOutputData.publish_no_origin`
   ([pgoutput.c#parse_output_parameters](../../../../raw/postgres-17/src/backend/replication/pgoutput/pgoutput.c#L391-L410))
   and registers `pgoutput_origin_filter` as the plugin's
   `filter_by_origin_cb`
   ([pgoutput.c#_PG_output_plugin_init](../../../../raw/postgres-17/src/backend/replication/pgoutput/pgoutput.c#L268)).
3. The filter returns `true` (= skip) exactly when `publish_no_origin` is set
   and the record's origin ID is not `InvalidRepOriginId`
   ([pgoutput.c#pgoutput_origin_filter](../../../../raw/postgres-17/src/backend/replication/pgoutput/pgoutput.c#L1722-L1736)).
4. Logical decoding consults the callback through `FilterByOrigin`
   ([decode.c#FilterByOrigin](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L578-L585),
   [logical.c#filter_by_origin_cb_wrapper](../../../../raw/postgres-17/src/backend/replication/logical/logical.c#L1289-L1312))
   at two levels:
   - **Per change**, before the change is even queued into the reorder buffer:
     [decode.c#DecodeInsert](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L924),
     [decode.c#DecodeUpdate](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L974),
     [decode.c#DecodeDelete](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L1040),
     [decode.c#DecodeTruncate](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L1092),
     [decode.c#DecodeMultiInsert](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L1142),
     [decode.c#DecodeSpecConfirm](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L1235),
     and logical messages
     ([decode.c#logicalmsg_decode](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L612-L614)).
   - **Per transaction**, via `DecodeTXNNeedSkip`, whose reason 3 is "the
     output plugin is not interested in the origin"; commit, prepare, and
     abort records pass the record's origin ID into it
     ([decode.c#DecodeTXNNeedSkip](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L1304-L1325),
     [decode.c#DecodeCommit](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L708),
     [decode.c#DecodePrepare](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L809),
     [decode.c#DecodeAbort](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L864)).

The replication-origins chapter describes this design: every change carries the
origin of the generating session, and `filter_by_origin_cb` filtering "is
considerably more efficient than doing it in the output plugin"
([replication-origins.sgml](../../../../raw/postgres-17/doc/src/sgml/replication-origins.sgml#L79-L95)).

### Why a two-node loop stops after one hop

With node A and node B each publishing `t` and subscribing to the other with
`origin = none`:

1. `INSERT` on A runs in a normal backend. No session origin, so its WAL has
   no origin chunk
   ([xloginsert.c#XLogRecordAssemble](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L840-L847)).
2. A's walsender for B's subscription decodes the insert; the filter sees
   `InvalidRepOriginId` and publishes it
   ([pgoutput.c#pgoutput_origin_filter](../../../../raw/postgres-17/src/backend/replication/pgoutput/pgoutput.c#L1722-L1736)).
3. B's apply worker replays it with `replorigin_session_origin =
   pg_<suboid>`, so the replayed row's WAL on B **is** origin-tagged
   ([worker.c#run_apply_worker](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L4516-L4526)).
4. B's walsender for A's subscription decodes that WAL, sees a non-invalid
   origin ID, and skips it — the row never travels back to A
   ([decode.c#DecodeInsert](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L924)).

The TAP test asserts exactly this: after inserts on both nodes, each node holds
both rows and "bidirectional logical replication setup does not cause infinite
recursive insertion"
([030_origin.pl:71-99](../../../../raw/postgres-17/src/test/subscription/t/030_origin.pl#L71-L99)).
The same mechanism also stops *transitive* data: with a third node C feeding B,
B's data that originated on C is filtered out of B's `origin = none` stream to
A ([030_origin.pl:100-144](../../../../raw/postgres-17/src/test/subscription/t/030_origin.pl#L100-L144)).
Note the flip side: `origin = none` keeps an n-node mesh loop-free, but it also
means a node only ever forwards its *own* data, so every node must subscribe to
every other node it wants data from.

### Reserved origin names

Because `none` and `any` are option keywords, `pg_replication_origin_create()`
rejects them (and `pg_`-prefixed names) as reserved
([origin.c#pg_replication_origin_create](../../../../raw/postgres-17/src/backend/replication/logical/origin.c#L1279-L1289),
[origin.c#IsReservedOriginName](../../../../raw/postgres-17/src/backend/replication/logical/origin.c#L204-L208)),
with regression coverage in
[replorigin.sql:34-37](../../../../raw/postgres-17/contrib/test_decoding/sql/replorigin.sql#L34-L37).

### The initial-copy blind spot and its WARNING

Origin filtering works on WAL, but the initial table synchronization runs a
COPY of the publisher's current table contents, where row provenance is
unknowable. If the publisher itself subscribes to other nodes, the copy may
include foreign-origin rows
([create_subscription.sgml#Notes](../../../../raw/postgres-17/doc/src/sgml/ref/create_subscription.sgml#L511-L521)).
`CREATE SUBSCRIPTION` and `ALTER SUBSCRIPTION ... REFRESH PUBLICATION` with
`copy_data = true` and `origin = none` therefore run
`check_publications_origin`: it queries the publisher's
`pg_subscription_rel` for the subscribed tables (including partition ancestors
and children) and raises a WARNING — "might copy data that had a different
origin" — naming the publications involved
([subscriptioncmds.c#check_publications_origin](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L2044-L2161),
call sites
[subscriptioncmds.c:789](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L789)
and
[subscriptioncmds.c:947](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L947)).
It is only a warning; verifying the copied data is the user's responsibility
([create_subscription.sgml#Notes](../../../../raw/postgres-17/doc/src/sgml/ref/create_subscription.sgml#L511-L521)).
That is why the in-tree bidirectional setup creates both subscriptions before
any data exists, with `copy_data = false` on the second one
([030_origin.pl:44-69](../../../../raw/postgres-17/src/test/subscription/t/030_origin.pl#L44-L69)).

The docs ship a publisher-side query to list tables that might contain
non-local rows
([create_subscription.sgml:523-538](../../../../raw/postgres-17/doc/src/sgml/ref/create_subscription.sgml#L523-L538)).
Session-scoped timeouts are sensible when running it on a busy publisher
(`SET statement_timeout = '30s'; SET lock_timeout = '5s';` — both are
user-settable session GUCs):

```sql
-- substitute <pub-names> with your publication name(s)
SELECT /* wiki_find_nonlocal_origin_tables */ DISTINCT PT.schemaname, PT.tablename
FROM pg_publication_tables PT
     JOIN pg_class C ON (C.relname = PT.tablename)
     JOIN pg_namespace N ON (N.nspname = PT.schemaname),
     pg_subscription_rel PS
WHERE C.relnamespace = N.oid AND
      (PS.srrelid = C.oid OR
      C.oid IN (SELECT relid FROM pg_partition_ancestors(PS.srrelid) UNION
                SELECT relid FROM pg_partition_tree(PS.srrelid))) AND
      PT.pubname IN (<pub-names>);
```

### Setting up two nodes (the in-tree pattern)

This is the verbatim shape used by the v17 test suite
([030_origin.pl:44-69](../../../../raw/postgres-17/src/test/subscription/t/030_origin.pl#L44-L69));
table DDL must already exist on both nodes since DDL does not replicate
([logical-replication.sgml:1694](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1694)):

```sql
-- on node A
CREATE PUBLICATION tap_pub_A FOR TABLE t;
-- on node B
CREATE PUBLICATION tap_pub_B FOR TABLE t;

-- on node B (first direction; table still empty)
CREATE SUBSCRIPTION tap_sub_B_A
  CONNECTION '<node A connstr>'
  PUBLICATION tap_pub_A
  WITH (origin = none);

-- on node A (second direction; skip the copy, B has no local data yet)
CREATE SUBSCRIPTION tap_sub_A_B
  CONNECTION '<node B connstr>'
  PUBLICATION tap_pub_B
  WITH (origin = none, copy_data = off);
```

### What bi-directional replication does *not* include in v17

- **No conflict resolution.** A constraint-violating incoming row raises an
  error and stops the apply worker; resolution is manual, by fixing the data or
  skipping the transaction (`ALTER SUBSCRIPTION ... SKIP`,
  `pg_replication_origin_advance()`)
  ([logical-replication.sgml#Conflicts](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1602-L1682)).
  In a bidirectional pair, concurrent writes to the same key on both nodes are
  exactly such conflicts.
- **No DDL replication** — schema changes must be applied on each node
  ([logical-replication.sgml:1692-1706](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1692-L1706)).
- **No sequence replication** — serial/identity columns need disjoint ranges
  or another scheme; sequence state stays at the start value on the subscriber
  ([logical-replication.sgml:1707-1720](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1707-L1720)).
- **A custom output plugin must be blessed from 17.11 on.** A pair built on a
  non-core output plugin also needs that library listed in the publisher's
  `output_plugin_libraries`, whose default is `'pgoutput, test_decoding'`;
  otherwise `StartupDecodingContext` raises
  `library "..." may not be used as an output plugin`, both when the slot is
  created and when decoding starts on it. An ordinary `pgoutput` subscription is
  unaffected
  ([logical.c#StartupDecodingContext-plugin-check](../../../../raw/postgres-17/src/backend/replication/logical/logical.c#L197-L247),
  [guc_tables.c#output_plugin_libraries](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4735-L4745),
  [logical-replication.sgml#plugin-must-be-listed](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1906-L1913)).
  It is `PGC_SUSET`, so add it in `postgresql.conf` and **reload**, or `SET` it
  as a superuser for one session.
- **No step-by-step bidirectional how-to in the v17 docs.** The only doc
  mention of bi-directional setups is the loop-prevention bullet in the
  replication-origins chapter
  ([replication-origins.sgml:22-24](../../../../raw/postgres-17/doc/src/sgml/replication-origins.sgml#L22-L24));
  the `origin` parameter and its `copy_data` interaction are documented on
  `CREATE SUBSCRIPTION`
  ([create_subscription.sgml#origin](../../../../raw/postgres-17/doc/src/sgml/ref/create_subscription.sgml#L400-L418)).

### Test coverage

- [030_origin.pl](../../../../raw/postgres-17/src/test/subscription/t/030_origin.pl) —
  the dedicated TAP test: bidirectional A↔B setup (L24-L69), no infinite
  recursion (L71-L99), three-node origin isolation (L100-L144), the
  `copy_data`/`origin = none` WARNING incl. `ALTER ... REFRESH` (L145-L223),
  and the partitioned-table WARNING cases (L224 onward). Since 17.10 it uses a
  quoted table name (`tab'le`) to exercise the SQL-injection fix (see commit
  `f0f59b658e` below).
- [subscription.sql:69-75](../../../../raw/postgres-17/src/test/regress/sql/subscription.sql#L69-L75) —
  option validation: bad value fails, `origin = none` works, `ALTER ... SET
  (origin = any)` works.
- [replorigin.sql:34-37](../../../../raw/postgres-17/contrib/test_decoding/sql/replorigin.sql#L34-L37) —
  reserved origin names.

## Commits Related to Bi-Directional Logical Replication, by Version

Scope: commits in the pinned `REL_17_STABLE` history (`git log` of
`raw/postgres-17/` at `786db8dcf16`) that introduce or change the
origin-filtering feature that enables bi-directional logical replication
(subscription `origin` parameter, publisher-side filter, initial-sync
warning), plus the pre-existing foundations they build on. Release attribution
is bracketed by the checkout's own `Stamp HEAD as NNdevel` commits
(`d31d30973a` 16devel 2022-06-30, `5bcc7e6dc8` 17devel 2023-06-29) and the
`Stamp 17.N` commits (`d7ec59a63d` 17.0 ... `25c49f3a4a` 17.10,
`083ac033419` 17.11), verified with `git merge-base --is-ancestor`.

### Foundations (predate the feature; major-version attribution)

| Commit | Date | First in | Subject / relevance |
|---|---|---|---|
| `5aa2350426` | 2015-04-29 | 9.5 | "Introduce replication progress tracking infrastructure." — replication origins, session origin tagging, `filter_by_origin_cb` |
| `be65eddd80` | 2016-04-13 | 9.6 | "Add required database and origin filtering for logical messages." — the `logicalmsg_decode` origin filter |
| `665d1fad99` | 2017-01-20 | 10 | "Logical replication" — pub/sub framework, `pgoutput`, apply workers with per-subscription origins |

### In every v17 release (committed in the PostgreSQL 16 cycle; first shipped in 16.0)

| Commit | Date | Subject |
|---|---|---|
| `366283961a` | 2022-07-21 | "Allow users to skip logical replication of data having origin." — the core feature: `origin = none/any` subscription parameter, `pg_subscription.suborigin`, `START_REPLICATION` `origin` option, `pgoutput` `publish_no_origin` + origin filter, reserved origin names, `pg_dump`/`psql` support, `030_origin.pl`; commit message names loop avoidance "among replication nodes" as the purpose |
| `8756930190` | 2022-09-08 | "Raise a warning if there is a possibility of data from multiple origins." — `check_publications_origin` for `copy_data = true` + `origin = none`, plus the docs' detection query |
| `0324651573` | 2022-09-08 | "Fix the test case introduced by commit 8756930190." — waits for tablesync `ready` state before dropping |

### 17.0 (committed in the 17 development cycle)

| Commit | Date | Subject |
|---|---|---|
| `54ccfd6586` | 2023-09-27 | "Fix the misuse of origin filter across multiple pg_logical_slot_get_changes() calls." — moved `publish_no_origin` from a global into `PGOutputData` so retries cannot reuse a stale filter setting; back-patched through 16 |

### 17.1 - 17.4

No related commits (verified by ancestry: nothing from the scope list falls
between `91f20bc2f7` Stamp 17.1 and `f8554dee41` Stamp 17.4).

### 17.5

| Commit | Date | Subject |
|---|---|---|
| `0ae1245e04` | 2025-02-21 | "Fix a WARNING for data origin discrepancies." — `check_publications_origin` (and the docs query) now also detect partition ancestors/children of subscribed tables on the publisher; back-patched through 16 |

### 17.6 - 17.9

No related commits in scope. (The 17.8 origin-infrastructure fixes
`e063ccc722` and `0ed8f1afb1` are general logical-replication maintenance; see
the adjacent list below.)

### 17.10

| Commit | Date | Subject |
|---|---|---|
| `f0f59b658e` | 2026-05-11 | "Fix SQL injection in logical replication origin checks." — CVE-2026-6638: `check_publications_origin` interpolated schema/relation names unquoted during `ALTER SUBSCRIPTION ... REFRESH PUBLICATION`; now quoted with `quote_literal_cstr` ([subscriptioncmds.c:2093-2106](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L2093-L2106)); back-patched through 16 |

### 17.11

| Commit | Date | Subject |
|---|---|---|
| `14810cc0d96` | 2026-06-15 | "Clean up quoting of variable strings within replication commands." — the subscriber now builds `START_REPLICATION ... origin '<value>'`, `streaming`, `publication_names`, and `SLOT "<name>"` with local `appendQuotedString()` / `appendQuotedIdentifier()` / `appendQuotedLiteral()` helpers instead of `PQescapeLiteral`/`PQescapeIdentifier`, so quoting matches the replication-command scanner; the two out-of-memory error paths around those libpq calls are gone ([libpqwalreceiver.c#appendQuotedString](../../../../raw/postgres-17/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L579-L604), [libpqwalreceiver.c#origin-option](../../../../raw/postgres-17/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L664-L669), [libpqwalreceiver.c#stringlist_to_identifierstr](../../../../raw/postgres-17/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L1380-L1400)); back-patched through 14 |
| `01992176e08` | 2026-08-10 | "Add an output_plugin_libraries GUC to bless trusted output plugins" (CVE-2026-6471) — the publisher refuses a slot whose output plugin is not named in the new `output_plugin_libraries` list ([logical.c#StartupDecodingContext-plugin-check](../../../../raw/postgres-17/src/backend/replication/logical/logical.c#L197-L247), [guc_tables.c#output_plugin_libraries](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4735-L4745), [config.sgml#output_plugin_libraries](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L4538-L4593), [logical-replication.sgml#plugin-must-be-listed](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1906-L1913)); back-patched through 14 |

Both are subscriber/publisher plumbing rather than origin-filter changes, and
neither alters `origin = none` semantics:

- The quoting cleanup keeps the same `origin` option wire format; the subscriber
  still sends `, origin '<value>'` only to publishers >= 16, now with the value
  quoted by doubling single quotes
  ([libpqwalreceiver.c#origin-option](../../../../raw/postgres-17/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L664-L669)).
- `output_plugin_libraries` defaults to `'pgoutput, test_decoding'`, and a
  subscription's slot always uses `pgoutput`, so an ordinary bidirectional pair
  is unaffected
  ([guc_tables.c#output_plugin_libraries](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4735-L4745),
  [logical-replication.sgml#plugin-must-be-listed](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1906-L1913)).
  Apply scope: the GUC is `PGC_SUSET` with `GUC_SUPERUSER_ONLY`, so a
  `postgresql.conf` edit needs a **reload** (`SIGHUP`, no restart), and a
  superuser can change it for a **session** with `SET` — including per
  connection via `options=-coutput_plugin_libraries=...`
  ([guc_tables.c#output_plugin_libraries](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4735-L4745),
  [logical-replication.sgml#plugin-must-be-listed](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1906-L1913)).

Adjacent in the same range, listed without any claim on this page:
`1423a6efd01` (2026-07-16, `CREATE_REPLICATION_SLOT` response-shape check in
libpqwalreceiver), `a961b102cd9` (2026-08-03, "Do not log subscription
conninfo."), `15f4e3d0ce9` (2026-05-16, `ereport(ERROR)` instead of `Assert()`
for publisher tuples missing columns).

### Incidental commits touching the feature's test or docs (cosmetic/infrastructure)

| Commit | Date | Cycle | Subject |
|---|---|---|---|
| `0c20dd33db` | 2022-08-03 | 16 | "Add wait_for_subscription_sync for TAP tests." (refactors `030_origin.pl` waits) |
| `b2451385cb` | 2022-09-16 | 16 | "Message wording improvements" |
| `c8e1ba736b` | 2023-01-02 | 16 | "Update copyright for 2023" |
| `0245f8db36` | 2023-05-19 | 16 | "Pre-beta mechanical code beautification." |
| `f7c16a120c` | 2023-05-30 | 16 | "doc: PG 16 relnotes, adjust subscription origin mention" |
| `c538592959` | 2023-12-29 | 17.0 | "Make all Perl warnings fatal" |
| `29275b1d17` | 2024-01-03 | 17.0 | "Update copyright for 2024" |

### Adjacent replication-origin maintenance (not bidirectional-specific, listed for completeness)

These harden the origin infrastructure that any subscription (bidirectional or
not) relies on; they do not change the `origin = none` feature itself:
`f6c5edb8ab` (2022-08-30, 16), `88f488319b` (2022-09-12, 16), `776e1c8a5d`
(2022-10-11, 16, adds `ReplicationOriginNameForLogicalRep`), `3e577ff602`
(2023-02-03, 16), `ff68cc6f3b` (2023-11-22, 17.0), `aa817c7496` (2024-01-15,
17.0), `915aafe82a` (2024-08-21, 17.0, "Don't advance origin during apply
failure."), `e063ccc722` (2025-12-23, 17.8, orphaned origin after `DROP
SUBSCRIPTION`), `0ed8f1afb1` (2025-12-24, 17.8, second origin-advance fix).

## Source References

- [subscriptioncmds.c#parse_subscription_options](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L319-L341)
- [subscriptioncmds.c#check_publications_origin](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L2044-L2161)
- [pg_subscription.h#LOGICALREP_ORIGIN_NONE](../../../../raw/postgres-17/src/include/catalog/pg_subscription.h#L34-L44)
- [pg_subscription.h#suborigin](../../../../raw/postgres-17/src/include/catalog/pg_subscription.h#L115)
- [worker.c#run_apply_worker](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L4516-L4526)
- [worker.c#ReplicationOriginNameForLogicalRep](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L429-L443)
- [worker.c#set_stream_options](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L4408-L4409)
- [tablesync.c#LogicalRepSyncTableStart](../../../../raw/postgres-17/src/backend/replication/logical/tablesync.c#L1405-L1414)
- [libpqwalreceiver.c#libpqrcv_startstreaming](../../../../raw/postgres-17/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L664-L669)
- [pgoutput.c#parse_output_parameters](../../../../raw/postgres-17/src/backend/replication/pgoutput/pgoutput.c#L391-L410)
- [pgoutput.c#pgoutput_origin_filter](../../../../raw/postgres-17/src/backend/replication/pgoutput/pgoutput.c#L1722-L1736)
- [decode.c#FilterByOrigin](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L578-L585)
- [decode.c#DecodeTXNNeedSkip](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L1304-L1325)
- [logical.c#filter_by_origin_cb_wrapper](../../../../raw/postgres-17/src/backend/replication/logical/logical.c#L1289-L1312)
- [logical.c#StartupDecodingContext-plugin-check](../../../../raw/postgres-17/src/backend/replication/logical/logical.c#L197-L247)
- [guc_tables.c#output_plugin_libraries](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4735-L4745)
- [config.sgml#output_plugin_libraries](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L4538-L4593)
- [logical-replication.sgml#plugin-must-be-listed](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1906-L1913)
- [libpqwalreceiver.c#appendQuotedString](../../../../raw/postgres-17/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L579-L604)
- [libpqwalreceiver.c#stringlist_to_identifierstr](../../../../raw/postgres-17/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L1380-L1400)
- [origin.c#pg_replication_origin_create](../../../../raw/postgres-17/src/backend/replication/logical/origin.c#L1279-L1289)
- [xloginsert.c#XLogRecordAssemble](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L840-L847)
- [xact.c#RecordTransactionCommit](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L1404-L1458)
- [heapam.c#heap_insert](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2189-L2190)
- [ref/create_subscription.sgml#origin](../../../../raw/postgres-17/doc/src/sgml/ref/create_subscription.sgml#L400-L418)
- [ref/create_subscription.sgml#Notes](../../../../raw/postgres-17/doc/src/sgml/ref/create_subscription.sgml#L511-L538)
- [replication-origins.sgml](../../../../raw/postgres-17/doc/src/sgml/replication-origins.sgml#L12-L95)
- [logical-replication.sgml#Conflicts](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1602-L1682)
- [030_origin.pl](../../../../raw/postgres-17/src/test/subscription/t/030_origin.pl#L24-L99)
- [subscription.sql:69-75](../../../../raw/postgres-17/src/test/regress/sql/subscription.sql#L69-L75)
- [replorigin.sql:34-37](../../../../raw/postgres-17/contrib/test_decoding/sql/replorigin.sql#L34-L37)

## Context Reviewed

- Subscriber option path: `parse_subscription_options`, `CreateSubscription`,
  `AlterSubscription` in
  [subscriptioncmds.c](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L319-L341),
  catalog
  [pg_subscription.h](../../../../raw/postgres-17/src/include/catalog/pg_subscription.h#L34-L44).
- Apply-side tagging: `run_apply_worker`, `set_stream_options`,
  `maybe_reread_subscription`, `ReplicationOriginNameForLogicalRep` in
  [worker.c](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L4516-L4526);
  tablesync origins in
  [tablesync.c](../../../../raw/postgres-17/src/backend/replication/logical/tablesync.c#L1405-L1414).
- WAL plumbing: `XLogSetRecordFlags(XLOG_INCLUDE_ORIGIN)` call sites in
  [heapam.c](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2189-L2190),
  [xact.c](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L5922),
  [twophase.c](../../../../raw/postgres-17/src/backend/access/transam/twophase.c#L1201),
  [tablecmds.c](../../../../raw/postgres-17/src/backend/commands/tablecmds.c#L2264-L2265),
  [message.c](../../../../raw/postgres-17/src/backend/replication/logical/message.c#L70);
  record assembly in
  [xloginsert.c](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L840-L847).
- Publisher filtering: `START_REPLICATION` option in
  [libpqwalreceiver.c](../../../../raw/postgres-17/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L664-L669),
  `pgoutput`
  ([pgoutput.c](../../../../raw/postgres-17/src/backend/replication/pgoutput/pgoutput.c#L1722-L1736)),
  decode-time filters in
  [decode.c](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L578-L585),
  callback wrapper in
  [logical.c](../../../../raw/postgres-17/src/backend/replication/logical/logical.c#L1289-L1312).
- Origin name reservation in
  [origin.c](../../../../raw/postgres-17/src/backend/replication/logical/origin.c#L1279-L1289).
- Docs:
  [create_subscription.sgml](../../../../raw/postgres-17/doc/src/sgml/ref/create_subscription.sgml#L400-L418),
  [replication-origins.sgml](../../../../raw/postgres-17/doc/src/sgml/replication-origins.sgml#L12-L95),
  [logical-replication.sgml](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1602-L1682),
  [catalogs.sgml](../../../../raw/postgres-17/doc/src/sgml/catalogs.sgml#L8075).
- Tests:
  [030_origin.pl](../../../../raw/postgres-17/src/test/subscription/t/030_origin.pl),
  [subscription.sql](../../../../raw/postgres-17/src/test/regress/sql/subscription.sql#L69-L75),
  [replorigin.sql](../../../../raw/postgres-17/contrib/test_decoding/sql/replorigin.sql#L34-L37).
- Source history: `git log` sweeps over `030_origin.pl`, `-S
  LOGICALREP_ORIGIN_NONE`, `-S check_publications_origin`, `-S
  publish_no_origin`, subject search for "origin"; ancestry checks against the
  `Stamp` commits listed above.
- Pinned checkout `raw/postgres-17/` at commit
  `786db8dcf168bd9df8f55047337525ac19118b1c` (PostgreSQL 17.11,
  `REL_17_11-7-g786db8dcf16`); repinned from
  `54eeefaedbee0385529f3edf321bb99e49232aaa` (17.10) on 2026-08-17.
- 2026-08-17 repin review: the range `54eeefaed..786db8dcf16` contains the two
  17.11 commits now listed under `### 17.11` — `14810cc0d96` (replication-command
  quoting, which moved the `origin` option's construction) and `01992176e08`
  (`output_plugin_libraries`, CVE-2026-6471) — plus three adjacent replication
  commits carried without claims. Neither 17.11 commit changes `origin = none`
  semantics, the apply-side origin tagging, the `pgoutput` filter, or the
  initial-sync WARNING. The GUC's definition, sample entry, and documentation
  were read for its apply scope
  (`src/backend/utils/misc/guc_tables.c`, `postgresql.conf.sample`,
  `doc/src/sgml/config.sgml`, `doc/src/sgml/logical-replication.sgml`).

## Evidence Map

| Claim | Evidence |
|---|---|
| `origin` accepts only `none`/`any`, default `any`, stored in `suborigin` | [subscriptioncmds.c#parse_subscription_options](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L319-L341), [subscriptioncmds.c:162-163](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L162-L163), [subscriptioncmds.c:750-751](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L750-L751), [pg_subscription.h#suborigin](../../../../raw/postgres-17/src/include/catalog/pg_subscription.h#L115) |
| Apply worker sets session origin `pg_<suboid>`; tablesync uses `pg_<suboid>_<relid>` | [worker.c#run_apply_worker](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L4516-L4526), [worker.c#ReplicationOriginNameForLogicalRep](../../../../raw/postgres-17/src/backend/replication/logical/worker.c#L429-L443), [tablesync.c#LogicalRepSyncTableStart](../../../../raw/postgres-17/src/backend/replication/logical/tablesync.c#L1405-L1414) |
| WAL records of applied transactions carry the origin ID | [xloginsert.c#XLogRecordAssemble](../../../../raw/postgres-17/src/backend/access/transam/xloginsert.c#L840-L847), [heapam.c#heap_insert](../../../../raw/postgres-17/src/backend/access/heap/heapam.c#L2189-L2190), [xact.c#XactLogCommitRecord](../../../../raw/postgres-17/src/backend/access/transam/xact.c#L5922) |
| Subscriber sends `origin` to publisher only for servers >= 16 | [libpqwalreceiver.c#libpqrcv_startstreaming](../../../../raw/postgres-17/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L664-L669) |
| `pgoutput` skips origin-tagged changes when `origin = none` | [pgoutput.c#pgoutput_origin_filter](../../../../raw/postgres-17/src/backend/replication/pgoutput/pgoutput.c#L1722-L1736), [decode.c#DecodeInsert](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L924), [decode.c#DecodeTXNNeedSkip](../../../../raw/postgres-17/src/backend/replication/logical/decode.c#L1304-L1325) |
| Loop prevention works; transitive origins filtered | [030_origin.pl:71-99](../../../../raw/postgres-17/src/test/subscription/t/030_origin.pl#L71-L99), [030_origin.pl:100-144](../../../../raw/postgres-17/src/test/subscription/t/030_origin.pl#L100-L144) |
| Initial COPY cannot see origins; WARNING raised; user must verify | [subscriptioncmds.c#check_publications_origin](../../../../raw/postgres-17/src/backend/commands/subscriptioncmds.c#L2044-L2161), [create_subscription.sgml#Notes](../../../../raw/postgres-17/doc/src/sgml/ref/create_subscription.sgml#L511-L538) |
| `none`/`any`/`pg_*` origin names reserved | [origin.c#pg_replication_origin_create](../../../../raw/postgres-17/src/backend/replication/logical/origin.c#L1279-L1289) |
| Conflicts stop replication; manual resolution | [logical-replication.sgml#Conflicts](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1602-L1682) |
| DDL and sequences not replicated | [logical-replication.sgml:1692-1720](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1692-L1720) |
| Commit attribution to 16-cycle / 17.0 / 17.5 / 17.10 / 17.11 | checkout git history: `git merge-base --is-ancestor` against `d31d30973a`, `5bcc7e6dc8`, `e0b82fc8e8` (16beta1), `d7ec59a63d` (17.0), `f8554dee41` (17.4), `5e2f3df49d` (17.5), `6af885119b` (17.8), `25c49f3a4a` (17.10), `083ac033419` (17.11); commit messages of `54ccfd6586`, `0ae1245e04`, `f0f59b658e` state "Backpatch-through: 16", and of `14810cc0d96`, `01992176e08` state "Backpatch-through: 14" |
| 17.11: replication commands quote variable strings locally; the publisher refuses an output plugin missing from `output_plugin_libraries` (`PGC_SUSET`, default `'pgoutput, test_decoding'`) | [libpqwalreceiver.c#appendQuotedString](../../../../raw/postgres-17/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L579-L604), [libpqwalreceiver.c#stringlist_to_identifierstr](../../../../raw/postgres-17/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L1380-L1400), [logical.c#StartupDecodingContext-plugin-check](../../../../raw/postgres-17/src/backend/replication/logical/logical.c#L197-L247), [guc_tables.c#output_plugin_libraries](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4735-L4745), [config.sgml#output_plugin_libraries](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L4538-L4593), [logical-replication.sgml#plugin-must-be-listed](../../../../raw/postgres-17/doc/src/sgml/logical-replication.sgml#L1906-L1913); commits `14810cc0d96`, `01992176e08` |

## Open Questions

- Scope judgment: "all commits related to it" was interpreted as the
  origin-filtering feature family plus foundations, incidental, and adjacent
  origin-infrastructure commits. A broader reading (every replication-origin
  or logical-replication commit ever) would pull in dozens of commits that do
  not change bidirectional behavior; the adjacent list above marks that
  boundary explicitly.
- Conflict behavior in bidirectional pairs is asserted from the general
  Conflicts documentation and apply-worker error behavior; the v17 tree has no
  test that drives a write-write conflict in a bidirectional setup
  specifically.
- The claim that 17.1-17.4 and 17.6-17.9 contain no in-scope commits rests on
  the git sweeps listed in Context Reviewed; a commit that touched the feature
  without matching those file paths, symbols, or the word "origin" in its
  subject would have been missed.
