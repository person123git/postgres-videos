---
type: question
version: 18
pinned_commit: baa7b142aace6821ce085906f314a75bcc4d95c8
verified: false
verified_by_agent: not yet
---

# How Bi-Directional Logical Replication Works in PostgreSQL 18, and New Logical Replication Features Since PostgreSQL 17 (unverified)

## Question

Explain how bi-directional logical replication works in PostgreSQL 18, and add
a section with all new logical replication features since version 17.

> Prompt note: the user approved correcting the original prompt wording
> ("explain how the bi-directional logical replication works, add section with
> all new features on logical replication since version 17") to the form
> above.

## Answer

PostgreSQL 18 supports bi-directional logical replication by combining
ordinary publish/subscribe logical replication with the subscription parameter
`origin = none`. Each of two nodes publishes a table and subscribes to the
same table on the other node with `origin = none`. Every transaction an apply
worker replays is tagged in WAL with a *replication origin*; a subscription
created with `origin = none` asks the publisher to send only changes that
carry **no** origin. Locally entered data therefore replicates exactly one
hop, and replayed data is filtered out on the way back — that is what prevents
infinite loops
([create_subscription.sgml#origin](../../../../raw/postgres-18/doc/src/sgml/ref/create_subscription.sgml#L407-L425),
[replication-origins.sgml:22-24](../../../../raw/postgres-18/doc/src/sgml/replication-origins.sgml#L22-L24),
[030_origin.pl:76-98](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl#L76-L98)).

There is still no dedicated "bidirectional mode" in v18: the building blocks
are the origin filter, the initial-sync warning, and the reserved origin
names. What v18 adds on top of v17 is *conflict detection with logging and
statistics* — write-write collisions between the two nodes are now named,
logged with the other node's origin, and counted in
`pg_stat_subscription_stats` (see
[the new-features section](#new-logical-replication-features-since-postgresql-17)).
Conflict *resolution* is still manual, and DDL and sequence data still do not
replicate (see
[Limitations](#what-bi-directional-replication-does-not-include-in-v18)).

### The moving parts

| Piece | Where | Role |
|---|---|---|
| `origin` subscription parameter | [subscriptioncmds.c#parse_subscription_options](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L310-L332) | Accepts only `none` or `any`; default `any` |
| `pg_subscription.suborigin` | [pg_subscription.h#suborigin](../../../../raw/postgres-18/src/include/catalog/pg_subscription.h#L95) | Stores the choice per subscription |
| Replication origin per subscription | [worker.c#run_apply_worker](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L4584-L4594) | Tags all WAL the apply worker writes |
| `XLOG_INCLUDE_ORIGIN` | [xloginsert.c#XLogRecordAssemble](../../../../raw/postgres-18/src/backend/access/transam/xloginsert.c#L841-L847) | Attaches the origin ID to WAL records |
| `origin` option of `pgoutput` | [pgoutput.c#parse_output_parameters](../../../../raw/postgres-18/src/backend/replication/pgoutput/pgoutput.c#L397-L414) | Publisher-side switch `publish_no_origin` |
| `pgoutput_origin_filter` | [pgoutput.c#pgoutput_origin_filter](../../../../raw/postgres-18/src/backend/replication/pgoutput/pgoutput.c#L1763-L1776) | Skips changes whose WAL carries an origin |
| `check_publications_origin` | [subscriptioncmds.c#check_publications_origin](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L2130-L2232) | WARNING for the initial-copy blind spot |
| `ReportApplyConflict` | [conflict.c#ReportApplyConflict](../../../../raw/postgres-18/src/backend/replication/logical/conflict.c#L102-L106) | New in 18: names and logs apply conflicts |

### The `origin` subscription parameter

`CREATE SUBSCRIPTION ... WITH (origin = ...)` accepts exactly two values,
validated case-insensitively against the macros `LOGICALREP_ORIGIN_NONE`
(`"none"`) and `LOGICALREP_ORIGIN_ANY` (`"any"`); anything else raises
`unrecognized origin value`
([subscriptioncmds.c#SUBOPT_ORIGIN](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L310-L332),
[pg_subscription.h#LOGICALREP_ORIGIN_NONE](../../../../raw/postgres-18/src/include/catalog/pg_subscription.h#L156-L162)).
The default is `any`
([subscriptioncmds.c:165-166](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L165-L166)).
The parameter is deliberately a string, not a boolean, so future versions can
filter by specific origin names
([subscriptioncmds.c:319-324](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L319-L324)).

- `CREATE SUBSCRIPTION` accepts it
  ([subscriptioncmds.c:586-592](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L586-L592))
  and stores it in `pg_subscription.suborigin`
  ([subscriptioncmds.c:710-711](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L710-L711),
  [catalogs.sgml#suborigin](../../../../raw/postgres-18/doc/src/sgml/catalogs.sgml#L8128)).
- `ALTER SUBSCRIPTION ... SET (origin = ...)` updates the same column
  ([subscriptioncmds.c:1354-1359](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L1354-L1359);
  `SUBOPT_ORIGIN` is in the `ALTER_SUBSCRIPTION_OPTIONS` list at
  [subscriptioncmds.c:1188-1195](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L1188-L1195)).
  A running apply worker notices the change and exits so the launcher restarts
  it with the new setting — `origin` is in `maybe_reread_subscription`'s
  restart list
  ([worker.c#maybe_reread_subscription](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L4038-L4047)).
- `psql`'s `\dRs+` shows it as the `Origin` column
  ([describe.c:6809-6815](../../../../raw/postgres-18/src/bin/psql/describe.c#L6809-L6815)).

### How applied changes get an origin tag

Each subscription owns a replication origin named `pg_<subscription-oid>`
(tablesync workers use `pg_<subscription-oid>_<relation-oid>`)
([worker.c#ReplicationOriginNameForLogicalRep](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L421-L434)).
The apply worker creates the origin if needed and configures the whole session
with it: `replorigin_session_setup(originid, 0)` plus
`replorigin_session_origin = originid`
([worker.c#run_apply_worker](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L4584-L4594)).
Tablesync workers do the same with their per-table origin before copying
([tablesync.c#LogicalRepSyncTableStart](../../../../raw/postgres-18/src/backend/replication/logical/tablesync.c#L1389-L1423),
[tablesync.c:1509-1510](../../../../raw/postgres-18/src/backend/replication/logical/tablesync.c#L1509-L1510)),
so even rows written by the initial COPY are origin-tagged on the subscriber.

From then on, WAL records produced by that session carry the origin ID:

- Row-level records request it explicitly with
  `XLogSetRecordFlags(XLOG_INCLUDE_ORIGIN)`:
  [heapam.c#heap_insert](../../../../raw/postgres-18/src/backend/access/heap/heapam.c#L2243),
  [heapam.c#heap_multi_insert](../../../../raw/postgres-18/src/backend/access/heap/heapam.c#L2673),
  [heapam.c#heap_delete](../../../../raw/postgres-18/src/backend/access/heap/heapam.c#L3199),
  [heapam.c#log_heap_update](../../../../raw/postgres-18/src/backend/access/heap/heapam.c#L9327),
  [heapam.c#heap_finish_speculative](../../../../raw/postgres-18/src/backend/access/heap/heapam.c#L6397),
  [tablecmds.c#ExecuteTruncateGuts](../../../../raw/postgres-18/src/backend/commands/tablecmds.c#L2335),
  [message.c#LogLogicalMessage](../../../../raw/postgres-18/src/backend/replication/logical/message.c#L70).
- Transaction records do the same:
  [xact.c#XactLogCommitRecord](../../../../raw/postgres-18/src/backend/access/transam/xact.c#L5974),
  [xact.c#XactLogAbortRecord](../../../../raw/postgres-18/src/backend/access/transam/xact.c#L6120),
  [twophase.c#EndPrepare](../../../../raw/postgres-18/src/backend/access/transam/twophase.c#L1201).
- `XLogRecordAssemble` appends an `XLR_BLOCK_ID_ORIGIN` chunk holding
  `replorigin_session_origin` when the flag is set and the session origin is
  valid
  ([xloginsert.c#XLogRecordAssemble](../../../../raw/postgres-18/src/backend/access/transam/xloginsert.c#L841-L847),
  [xlog.h#XLOG_INCLUDE_ORIGIN](../../../../raw/postgres-18/src/include/access/xlog.h#L156)).
- At commit, the origin's replay progress (remote LSN, commit timestamp) is
  advanced crash-safely together with the commit record
  ([xact.c#RecordTransactionCommit](../../../../raw/postgres-18/src/backend/access/transam/xact.c#L1452-L1468)).

Locally executed transactions have `replorigin_session_origin =
InvalidRepOriginId`, so their WAL carries no origin chunk — that absence is
what `origin = none` selects for.

### How the publisher filters by origin

1. The subscriber's apply worker copies `pg_subscription.suborigin` into the
   streaming options
   ([worker.c#set_stream_options](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L4452-L4495))
   and the walreceiver adds `origin '<value>'` to `START_REPLICATION ...
   (proto_version ..., origin 'none', publication_names ...)`, but only when
   the publisher is version 16 or newer
   ([libpqwalreceiver.c#libpqrcv_startstreaming](../../../../raw/postgres-18/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L630-L635)).
   The effect is unchanged but the mechanism is not: since `abb5825550a`
   ("Clean up quoting of variable strings within replication commands.") the
   option is emitted as `appendStringInfoString(&cmd, ", origin ")` followed by
   `appendQuotedLiteral()`, a replication-grammar quoting helper that doubles
   embedded single quotes, rather than by a `%s` format
   ([libpqwalreceiver.c#appendQuotedString](../../../../raw/postgres-18/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L545-L571)).
2. On the publisher, `pgoutput` parses the option into
   `PGOutputData.publish_no_origin`
   ([pgoutput.c#parse_output_parameters](../../../../raw/postgres-18/src/backend/replication/pgoutput/pgoutput.c#L397-L414))
   and registers `pgoutput_origin_filter` as the plugin's
   `filter_by_origin_cb`
   ([pgoutput.c#_PG_output_plugin_init](../../../../raw/postgres-18/src/backend/replication/pgoutput/pgoutput.c#L274)).
3. The filter returns `true` (= skip) exactly when `publish_no_origin` is set
   and the record's origin ID is not `InvalidRepOriginId`
   ([pgoutput.c#pgoutput_origin_filter](../../../../raw/postgres-18/src/backend/replication/pgoutput/pgoutput.c#L1763-L1776)).
4. Logical decoding consults the callback through `FilterByOrigin`
   ([decode.c#FilterByOrigin](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L573-L580),
   [logical.c#filter_by_origin_cb_wrapper](../../../../raw/postgres-18/src/backend/replication/logical/logical.c#L1269-L1297))
   at two levels:
   - **Per change**, before the change is even queued into the reorder buffer:
     [decode.c#DecodeInsert](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L919),
     [decode.c#DecodeUpdate](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L969),
     [decode.c#DecodeDelete](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L1035),
     [decode.c#DecodeTruncate](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L1087),
     [decode.c#DecodeMultiInsert](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L1137),
     [decode.c#DecodeSpecConfirm](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L1228),
     and logical messages
     ([decode.c#logicalmsg_decode](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L606-L609)).
   - **Per transaction**, via `DecodeTXNNeedSkip`, whose reason 3 is "the
     output plugin is not interested in the origin"; commit, prepare, and
     abort records pass the record's origin ID into it
     ([decode.c#DecodeTXNNeedSkip](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L1296-L1316),
     [decode.c#DecodeCommit](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L703),
     [decode.c#DecodePrepare](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L804),
     [decode.c#DecodeAbort](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L859)).

The replication-origins chapter describes this design: filtering via
`filter_by_origin_cb` "is considerably more efficient than doing it in the
output plugin"
([replication-origins.sgml](../../../../raw/postgres-18/doc/src/sgml/replication-origins.sgml#L85-L95)).

### Why a two-node loop stops after one hop

With node A and node B each publishing `t` and subscribing to the other with
`origin = none`:

1. `INSERT` on A runs in a normal backend. No session origin, so its WAL has
   no origin chunk
   ([xloginsert.c#XLogRecordAssemble](../../../../raw/postgres-18/src/backend/access/transam/xloginsert.c#L841-L847)).
2. A's walsender for B's subscription decodes the insert; the filter sees
   `InvalidRepOriginId` and publishes it
   ([pgoutput.c#pgoutput_origin_filter](../../../../raw/postgres-18/src/backend/replication/pgoutput/pgoutput.c#L1763-L1776)).
3. B's apply worker replays it with `replorigin_session_origin =
   pg_<suboid>`, so the replayed row's WAL on B **is** origin-tagged
   ([worker.c#run_apply_worker](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L4584-L4594)).
4. B's walsender for A's subscription decodes that WAL, sees a non-invalid
   origin ID, and skips it — the row never travels back to A
   ([decode.c#DecodeInsert](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L919)).

The TAP test asserts exactly this: after inserts on both nodes, each node
holds both rows and the insert completes "without leading to infinite
recursion in bidirectional replication setup"
([030_origin.pl:76-98](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl#L76-L98)).
The same mechanism also stops *transitive* data: with a third node C feeding
B, B's data that originated on C is filtered out of B's `origin = none` stream
to A
([030_origin.pl:105-149](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl#L105-L149)).
Note the flip side: `origin = none` keeps an n-node mesh loop-free, but it
also means a node only ever forwards its *own* data, so every node must
subscribe to every other node it wants data from.

### Conflicts between the two nodes are now named and logged (new in 18)

When both nodes write the same rows, the apply worker can collide with local
state. v18 detects these cases, logs them with a conflict name, and counts
them per subscription (this whole layer is new since v17; details and commits
in [the new-features section](#new-logical-replication-features-since-postgresql-17)):

- `update_origin_differs` / `delete_origin_differs` fire when the incoming
  change touches a row last modified by a *different* origin — exactly the
  bidirectional collision case. Detection requires `track_commit_timestamp =
  on` on the subscriber (a `postmaster`-context GUC: changing it needs a
  server restart;
  [guc_tables.c#track_commit_timestamp](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L1100-L1103),
  [conflict.c#GetTupleTransactionInfo](../../../../raw/postgres-18/src/backend/replication/logical/conflict.c#L62-L77)).
  The update/delete is still applied or skipped as before; the conflict is
  reported at `LOG` level
  ([worker.c:2723](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L2723),
  [worker.c:2897](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L2897),
  [logical-replication.sgml#update_origin_differs](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L1778-L1789)).
- `insert_exists`, `update_exists`, and `multiple_unique_conflicts` are
  unique-constraint collisions; they raise an `ERROR` and stop the apply
  worker until resolved
  ([execReplication.c:550](../../../../raw/postgres-18/src/backend/executor/execReplication.c#L550),
  [logical-replication.sgml#insert_exists](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L1765-L1777)).

The bidirectional TAP test drives both origin-differs conflicts in the A↔B
setup and checks the logged
`conflict detected on relation ... conflict=update_origin_differs` /
`delete_origin_differs` messages, with `track_commit_timestamp` enabled on
node B
([030_origin.pl:38-40](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl#L38-L40),
[030_origin.pl:150-191](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl#L150-L191)).

### Reserved origin names

Because `none` and `any` are option keywords, `pg_replication_origin_create()`
rejects them (and `pg_`-prefixed names) as reserved
([origin.c#pg_replication_origin_create](../../../../raw/postgres-18/src/backend/replication/logical/origin.c#L1292-L1311),
[origin.c#IsReservedOriginName](../../../../raw/postgres-18/src/backend/replication/logical/origin.c#L208-L213)),
with regression coverage in
[replorigin.sql:34-37](../../../../raw/postgres-18/contrib/test_decoding/sql/replorigin.sql#L34-L37).

### The initial-copy blind spot and its WARNING

Origin filtering works on WAL, but the initial table synchronization runs a
COPY of the publisher's current table contents, where row provenance is
unknowable. If the publisher itself subscribes to other nodes, the copy may
include foreign-origin rows
([create_subscription.sgml#Notes](../../../../raw/postgres-18/doc/src/sgml/ref/create_subscription.sgml#L519-L529)).
`CREATE SUBSCRIPTION` and `ALTER SUBSCRIPTION ... REFRESH PUBLICATION` with
`copy_data = true` and `origin = none` therefore run
`check_publications_origin`: it asks the publisher which of the subscribed
tables (including partition ancestors and children, via
`pg_get_publication_tables`) are themselves written by subscriptions there,
and raises a WARNING — "might copy data that had a different origin" — naming
the publications involved
([subscriptioncmds.c#check_publications_origin](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L2130-L2232),
call sites
[subscriptioncmds.c:750](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L750)
and
[subscriptioncmds.c:909](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L909)).
It is only a warning; verifying the copied data is the user's responsibility
([create_subscription.sgml#Notes](../../../../raw/postgres-18/doc/src/sgml/ref/create_subscription.sgml#L519-L529)).
That is why the in-tree bidirectional setup creates both subscriptions before
any data exists, with `copy_data = off` on the second one
([030_origin.pl:24-75](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl#L24-L75)).

That publisher-side query is now built with quoted literals. `cb35d730689`
("Fix SQL injection in logical replication origin checks.", Noah Misch,
2026-05-11, CVE-2026-6638, back-patched through 16) wraps both the schema name
and the relation name in `quote_literal_cstr()` before appending the
`AND NOT (N.nspname = %s AND C.relname = %s)` predicate, so a table name
containing a quote can no longer terminate the literal
([subscriptioncmds.c#check_publications_origin-quoting](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L2166-L2177),
[subscriptioncmds.c:2172-2173](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L2172-L2173)).
The v17 sibling page records the same fix released in 17.10; on this pin the
v18 line carries it, so the earlier open question about unquoted interpolation
is resolved.

The docs ship a publisher-side query to list tables that might contain
non-local rows
([create_subscription.sgml:531-546](../../../../raw/postgres-18/doc/src/sgml/ref/create_subscription.sgml#L531-L546)).
Session-scoped timeouts are sensible when running it on a busy publisher
(`SET statement_timeout = '30s'; SET lock_timeout = '5s';` — both are
user-settable session GUCs:
[guc_tables.c:2740](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2740),
[guc_tables.c:2751](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2751)):

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

This is the shape used by the v18 test suite, with the table name simplified
([030_origin.pl:24-75](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl#L24-L75)).
The test itself no longer uses a plain identifier: it declares
`my $tab_unquoted = q{tab'le}; my $tab = qq{"$tab_unquoted"};` and substitutes
`$tab` into every DDL and DML statement, so the replicated relation is the
quoted name `"tab'le"`
([030_origin.pl:12-13](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl#L12-L13)).
Table DDL must already exist on both nodes since DDL does not replicate
([logical-replication.sgml#Restrictions](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L2058-L2070)):

```sql
-- on node A
CREATE PUBLICATION tap_pub_A FOR TABLE tab;
-- on node B
CREATE PUBLICATION tap_pub_B FOR TABLE tab;

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

To get origin-differs conflict detection, also set `track_commit_timestamp =
on` on each node and restart it (`postmaster` context), as the test does for
node B
([030_origin.pl:38-40](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl#L38-L40),
[guc_tables.c#track_commit_timestamp](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L1100-L1103)).

**New mandatory precondition in 18.6: `pgoutput` must be listed in
`output_plugin_libraries` on both nodes.** `2a29b607dbb` (CVE-2026-6471) added
that GUC; before loading a slot's output plugin,
`StartupDecodingContext()` — the shared helper behind
`CreateInitDecodingContext()` and `CreateDecodingContext()` — splits the list
and raises `ERROR: library "%s" may not be used as an output plugin` when the
plugin name is not an exact match, so a subscription's apply worker cannot
start its slot
([guc_tables.c#output_plugin_libraries](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L4986-L4996),
[logical.c#plugin_allowed](../../../../raw/postgres-18/src/backend/replication/logical/logical.c#L188-L251),
[logical-replication.sgml#output-plugin-libraries](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L2274-L2281),
[config.sgml#output_plugin_libraries](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L4615-L4670)).
The boot value is `'pgoutput, test_decoding'`, so a default installation keeps
working; a DBA who narrowed the list — for example to allow only one custom
plugin — breaks logical replication, bidirectional pairs included. Apply scope:
the GUC is `PGC_SUSET` with `GUC_SUPERUSER_ONLY`, so a `postgresql.conf` change
needs a reload (no restart), a superuser can change it for a session with `SET`,
and a superuser can also override it for a single replication connection with
`options=-coutput_plugin_libraries=...` in the connection string
([guc_tables.c#output_plugin_libraries](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L4986-L4996),
[logical-replication.sgml#output-plugin-libraries](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L2274-L2281)).
New coverage: a `REPLICATION` user cannot load an unblessed plugin
([100_bugs.pl#output_plugin_libraries](../../../../raw/postgres-18/src/test/subscription/t/100_bugs.pl#L498-L518)),
and `test_decoding` has its own permission case
([permissions.sql#output_plugin_libraries](../../../../raw/postgres-18/contrib/test_decoding/sql/permissions.sql#L18-L24),
[permissions.out#output_plugin_libraries](../../../../raw/postgres-18/contrib/test_decoding/expected/permissions.out#L33-L41)).

### What bi-directional replication does *not* include in v18

- **No conflict resolution.** v18 detects and logs conflicts (see above), but
  resolution is manual: fix the data, or skip the transaction with
  `ALTER SUBSCRIPTION ... SKIP` or `pg_replication_origin_advance()`, possibly
  after `disable_on_error` stopped the subscription
  ([logical-replication.sgml:2006-2017](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L2006-L2017)).
  In a bidirectional pair, concurrent writes to the same key on both nodes are
  exactly such conflicts.
- **No DDL replication** — schema changes must be applied on each node
  ([logical-replication.sgml#Restrictions](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L2058-L2070)).
- **No sequence replication** — serial/identity columns need disjoint ranges
  or another scheme
  ([logical-replication.sgml:2075](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L2075)).
- **No step-by-step bidirectional how-to in the v18 docs.** The only doc
  mention of bi-directional setups is the loop-prevention bullet in the
  replication-origins chapter
  ([replication-origins.sgml:22-24](../../../../raw/postgres-18/doc/src/sgml/replication-origins.sgml#L22-L24));
  the `origin` parameter and its `copy_data` interaction are documented on
  `CREATE SUBSCRIPTION`
  ([create_subscription.sgml#origin](../../../../raw/postgres-18/doc/src/sgml/ref/create_subscription.sgml#L407-L425)).

### Test coverage

- [030_origin.pl](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl) —
  the dedicated TAP test, now 380 lines: bidirectional A↔B setup (L24-L75), no
  infinite recursion (L76-L98), three-node origin isolation (L105-L149),
  origin-differs conflict detection in the bidirectional pair (L150-L191, new
  relative to the v17 sibling page), the `copy_data`/`origin = none` WARNING
  incl. `ALTER ... REFRESH` (L192-L270), and partitioned-table WARNING cases
  (L271 onward). Because the test's table is now the quoted name `"tab'le"`,
  its conflict-log regexes match `conflict detected on relation
  "public.tab'le"`.
- [subscription.sql:69-75](../../../../raw/postgres-18/src/test/regress/sql/subscription.sql#L69-L75) —
  option validation: bad value fails, `origin = none` works, `ALTER ... SET
  (origin = any)` works.
- [replorigin.sql:34-37](../../../../raw/postgres-18/contrib/test_decoding/sql/replorigin.sql#L34-L37) —
  reserved origin names.

## New Logical Replication Features Since PostgreSQL 17

Scope: feature commits in the pinned `REL_18_STABLE` history (`git log` of
`raw/postgres-18/` at `baa7b142aac`) that fall in the v18 development cycle —
after `Stamp HEAD as 18devel` (`e26810d01d`, 2024-07-01) and reachable from
`Stamp 18.0` (`3d6a828938`, 2025-09-22), verified with `git merge-base
--is-ancestor`. `release-18.sgml` at this pin also carries the 18.4 and 18.6
minor-release sections ahead of the major-release notes, which shifted the
v18 feature sections' line numbers without changing their content. The
checkout's own release notes enumerate them in the
"Logical Replication"
([release-18.sgml](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L10378-L10482)),
"Streaming Replication and Recovery"
([release-18.sgml](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L10335-L10375)),
and "Logical Replication Applications"
([release-18.sgml](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L12070-L12153))
sections; every claim below is additionally verified against v18 source.

### 1. Conflict detection, logging, and per-subscription statistics

The apply path now classifies conflicts into seven named types —
`insert_exists`, `update_origin_differs`, `update_exists`, `update_missing`,
`delete_origin_differs`, `delete_missing`, `multiple_unique_conflicts`
([conflict.h#ConflictType](../../../../raw/postgres-18/src/include/replication/conflict.h#L31-L61)) —
and reports each through the new
[conflict.c#ReportApplyConflict](../../../../raw/postgres-18/src/backend/replication/logical/conflict.c#L102-L106),
which logs the conflicting local row, its origin, transaction, and commit
timestamp. Call sites cover update/delete origin-differs and missing-row cases
in the apply worker
([worker.c:2723](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L2723),
[worker.c:2753](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L2753),
[worker.c:2897](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L2897),
[worker.c:2914](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L2914))
and unique-violation cases during replicated DML execution
([execReplication.c:550](../../../../raw/postgres-18/src/backend/executor/execReplication.c#L550)).
Origin and commit-timestamp details of the conflicting row are available only
with `track_commit_timestamp = on` (subscriber-side; `postmaster` context =
restart required;
[conflict.c#GetTupleTransactionInfo](../../../../raw/postgres-18/src/backend/replication/logical/conflict.c#L62-L77),
[guc_tables.c#track_commit_timestamp](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L1100-L1103)).
Conflict counts surface in seven new `confl_*` columns of
`pg_stat_subscription_stats`
([system_views.sql#pg_stat_subscription_stats](../../../../raw/postgres-18/src/backend/catalog/system_views.sql#L1384-L1399),
[monitoring.sgml](../../../../raw/postgres-18/doc/src/sgml/monitoring.sgml#L2192-L2262)),
and the conflict types are documented with their behavior (LOG vs ERROR)
in the Conflicts chapter
([logical-replication.sgml#Conflicts](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L1746-L1848)).
Commits: `9758174e2` (2024-08-20, conflict logging), `edcb71258` (docs),
`640178c92` (origin-differs renames), `6c2b5edec` (2024-09-04, statistics),
`73eba5004` (2025-03-24, `multiple_unique_conflicts`).

This is the feature most relevant to bi-directional setups: write-write
collisions between the two nodes were silent overwrites or opaque errors in
v17; in v18 they are named, logged with the other node's origin, counted, and
regression-tested in the bidirectional TAP test
([030_origin.pl:150-191](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl#L150-L191)).

### 2. Generated columns can be replicated

Stored generated columns can now be published, two ways: name them in a
publication column list, or set the new publication option
`publish_generated_columns = stored` (default `none`)
([create_publication.sgml#publish_generated_columns](../../../../raw/postgres-18/doc/src/sgml/ref/create_publication.sgml#L199-L230)).
The option parses in
[publicationcmds.c:165-170](../../../../raw/postgres-18/src/backend/commands/publicationcmds.c#L165-L170)
and stores per publication in the new catalog column `pubgencols`
([pg_publication.h:62](../../../../raw/postgres-18/src/include/catalog/pg_publication.h#L62),
[pg_publication.h#PublishGencolsType](../../../../raw/postgres-18/src/include/catalog/pg_publication.h#L115-L123)).
A new docs section explains publisher/subscriber generated-column
combinations
([logical-replication.sgml#Generated Column Replication](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L1568-L1600)).
In v17 generated columns were never replicated; the subscriber had to compute
them
([release-18.sgml](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L10394-L10417)).
Commits: `745217a05` (2024-10-30, column lists), `7054186c4` (2024-11-07,
`publish_generated_columns`), `87ce27de6` (2024-12-04, publish-when-required
check), `6252b1eaf` (docs).

### 3. Subscription `streaming` default changed to `parallel`

`CREATE SUBSCRIPTION` now defaults `streaming` to `parallel` — in-progress
transactions are applied directly by parallel apply workers when available
([subscriptioncmds.c:154](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L154),
[create_subscription.sgml:274-279](../../../../raw/postgres-18/doc/src/sgml/ref/create_subscription.sgml#L274-L279)).
In v17 the default was `off` (buffered until commit). Commit: `1bf1140be`
(2024-10-28).

### 4. `ALTER SUBSCRIPTION ... SET (two_phase)` is allowed

`two_phase` joined the alterable option set (`SUBOPT_TWOPHASE_COMMIT` in the
`ALTER_SUBSCRIPTION_OPTIONS` list,
[subscriptioncmds.c:1188-1195](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L1188-L1195)),
so a subscription's prepared-transaction decoding can be switched on or off
after creation; switching `two_phase = false` may require resolving prepared
transactions on the publisher first, and the subscription must be disabled to
alter it
([alter_subscription.sgml:73-82](../../../../raw/postgres-18/doc/src/sgml/ref/alter_subscription.sgml#L73-L82),
[alter_subscription.sgml:239-272](../../../../raw/postgres-18/doc/src/sgml/ref/alter_subscription.sgml#L239-L272)).
Commits: `1462aad2e` (2024-07-24), `4868c96bc` (2025-04-03, slot-sync fix for
`two_phase` slots).

### 5. New GUC `max_active_replication_origins`

Replication origins (one per subscription, plus one per running tablesync) no
longer share the `max_replication_slots` budget on the subscriber: the new
`max_active_replication_origins` GUC sizes the shared origin-state array
(default 10, `postmaster` context = restart required;
[guc_tables.c#max_active_replication_origins](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3389-L3399),
[origin.c:104](../../../../raw/postgres-18/src/backend/replication/logical/origin.c#L104),
[origin.c:538-544](../../../../raw/postgres-18/src/backend/replication/logical/origin.c#L538-L544)).
Directly relevant to bidirectional meshes, where every node carries one
subscription — and so one origin — per peer. Commit: `04ff636cb`
(2025-03-21).

### 6. New GUC `idle_replication_slot_timeout`

Replication slots idle longer than this timeout are invalidated with the new
`idle_timeout` invalidation cause (default 0 = disabled, unit seconds,
`sighup` context = config reload, no restart;
[guc_tables.c#idle_replication_slot_timeout](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3108-L3118),
[slot.c:117](../../../../raw/postgres-18/src/backend/replication/slot.c#L117),
[slot.c:1685-1693](../../../../raw/postgres-18/src/backend/replication/slot.c#L1685-L1693)).
Operationally relevant to bidirectional pairs: if one node's subscription
stays down past the timeout, its slot on the peer can be invalidated and the
subscription must be resynchronized. Commit: `ac0e33136` (2025-02-19).

### 7. `pg_createsubscriber` gains `--all`, `--clean`, `--enable-two-phase`

The physical-standby-to-logical-subscriber conversion tool (itself new in 17)
gains: `--all` to convert every database
([pg_createsubscriber.sgml:92](../../../../raw/postgres-18/doc/src/sgml/ref/pg_createsubscriber.sgml#L92),
[pg_createsubscriber.c:2064](../../../../raw/postgres-18/src/bin/pg_basebackup/pg_createsubscriber.c#L2064)),
`--clean=publications` to drop replicated publications on the new subscriber
([pg_createsubscriber.sgml:233](../../../../raw/postgres-18/doc/src/sgml/ref/pg_createsubscriber.sgml#L233),
[pg_createsubscriber.c:2081](../../../../raw/postgres-18/src/bin/pg_basebackup/pg_createsubscriber.c#L2081)),
and `--enable-two-phase` to create the subscriptions with `two_phase = on`
([pg_createsubscriber.sgml:196](../../../../raw/postgres-18/doc/src/sgml/ref/pg_createsubscriber.sgml#L196),
[pg_createsubscriber.c:2072](../../../../raw/postgres-18/src/bin/pg_basebackup/pg_createsubscriber.c#L2072)).
Commits: `fb2ea12f4` (2025-03-28), `e5aeed4b8` (2025-03-20) renamed by
`60dda7bbc` (2025-06-25), `e117cfb2f` (2025-02-26).

### 8. `pg_recvlogical` improvements

`--enable-failover` creates the slot with failover enabled (synchronized to
standbys;
[pg_recvlogical.c:44-45](../../../../raw/postgres-18/src/bin/pg_basebackup/pg_recvlogical.c#L44-L45),
[pg_recvlogical.sgml:179](../../../../raw/postgres-18/doc/src/sgml/ref/pg_recvlogical.sgml#L179)),
`--enable-two-phase` replaces `--two-phase` (kept as a deprecated synonym;
[pg_recvlogical.c:108-109](../../../../raw/postgres-18/src/bin/pg_basebackup/pg_recvlogical.c#L108-L109),
[pg_recvlogical.sgml:313-314](../../../../raw/postgres-18/doc/src/sgml/ref/pg_recvlogical.sgml#L313-L314)),
and `--drop-slot` no longer requires `--dbname`
([pg_recvlogical.sgml:302](../../../../raw/postgres-18/doc/src/sgml/ref/pg_recvlogical.sgml#L302)).
Commits: `cf2655a90` (2025-04-04), `c68100aa4` (2025-03-25).

### 9. New contrib module `pg_logicalinspect`

Inspects logical decoding snapshot files from `pg_logical/snapshots/` via
`pg_get_logical_snapshot_meta()` and `pg_get_logical_snapshot_info()`
([pglogicalinspect.sgml](../../../../raw/postgres-18/doc/src/sgml/pglogicalinspect.sgml#L30-L71),
[contrib/pg_logicalinspect](../../../../raw/postgres-18/contrib/pg_logicalinspect/Makefile)).
Commit: `7cdfeee32` (2024-10-14).

### Related but not a logical replication feature proper

`pg_upgrade` parallelized its per-database subscription checks as part of its
general parallelization work (commit `7baa36de5`, 2024-09-16;
[release-18.sgml](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L11984)).
It changes upgrade speed, not replication behavior.

## Source References

- [subscriptioncmds.c#parse_subscription_options](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L310-L332)
- [subscriptioncmds.c#check_publications_origin](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L2130-L2232)
- [pg_subscription.h#LOGICALREP_ORIGIN_NONE](../../../../raw/postgres-18/src/include/catalog/pg_subscription.h#L156-L162)
- [pg_subscription.h#suborigin](../../../../raw/postgres-18/src/include/catalog/pg_subscription.h#L95)
- [worker.c#run_apply_worker](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L4584-L4594)
- [worker.c#ReplicationOriginNameForLogicalRep](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L421-L434)
- [worker.c#set_stream_options](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L4452-L4495)
- [tablesync.c#LogicalRepSyncTableStart](../../../../raw/postgres-18/src/backend/replication/logical/tablesync.c#L1389-L1423)
- [libpqwalreceiver.c#libpqrcv_startstreaming](../../../../raw/postgres-18/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L630-L635)
- [pgoutput.c#parse_output_parameters](../../../../raw/postgres-18/src/backend/replication/pgoutput/pgoutput.c#L397-L414)
- [pgoutput.c#pgoutput_origin_filter](../../../../raw/postgres-18/src/backend/replication/pgoutput/pgoutput.c#L1763-L1776)
- [decode.c#FilterByOrigin](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L573-L580)
- [decode.c#DecodeTXNNeedSkip](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L1296-L1316)
- [logical.c#filter_by_origin_cb_wrapper](../../../../raw/postgres-18/src/backend/replication/logical/logical.c#L1269-L1297)
- [logical.c#StartupDecodingContext](../../../../raw/postgres-18/src/backend/replication/logical/logical.c#L188-L251)
- [origin.c#pg_replication_origin_create](../../../../raw/postgres-18/src/backend/replication/logical/origin.c#L1292-L1311)
- [xloginsert.c#XLogRecordAssemble](../../../../raw/postgres-18/src/backend/access/transam/xloginsert.c#L841-L847)
- [xact.c#RecordTransactionCommit](../../../../raw/postgres-18/src/backend/access/transam/xact.c#L1452-L1468)
- [heapam.c#heap_insert](../../../../raw/postgres-18/src/backend/access/heap/heapam.c#L2243)
- [conflict.h#ConflictType](../../../../raw/postgres-18/src/include/replication/conflict.h#L31-L61)
- [conflict.c#ReportApplyConflict](../../../../raw/postgres-18/src/backend/replication/logical/conflict.c#L102-L106)
- [system_views.sql#pg_stat_subscription_stats](../../../../raw/postgres-18/src/backend/catalog/system_views.sql#L1384-L1399)
- [pg_publication.h#PublishGencolsType](../../../../raw/postgres-18/src/include/catalog/pg_publication.h#L115-L123)
- [guc_tables.c#max_active_replication_origins](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3389-L3399)
- [guc_tables.c#idle_replication_slot_timeout](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3108-L3118)
- [guc_tables.c#output_plugin_libraries](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L4986-L4996)
- [config.sgml#output_plugin_libraries](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L4615-L4670)
- [ref/create_subscription.sgml#origin](../../../../raw/postgres-18/doc/src/sgml/ref/create_subscription.sgml#L407-L425)
- [ref/create_subscription.sgml#Notes](../../../../raw/postgres-18/doc/src/sgml/ref/create_subscription.sgml#L519-L546)
- [ref/create_publication.sgml#publish_generated_columns](../../../../raw/postgres-18/doc/src/sgml/ref/create_publication.sgml#L199-L230)
- [replication-origins.sgml](../../../../raw/postgres-18/doc/src/sgml/replication-origins.sgml#L12-L95)
- [logical-replication.sgml#Conflicts](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L1746-L1848)
- [release-18.sgml#Logical Replication](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L10378-L10482)
- [030_origin.pl](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl)
- [100_bugs.pl#output_plugin_libraries](../../../../raw/postgres-18/src/test/subscription/t/100_bugs.pl#L498-L518)
- [subscription.sql:69-75](../../../../raw/postgres-18/src/test/regress/sql/subscription.sql#L69-L75)
- [replorigin.sql:34-37](../../../../raw/postgres-18/contrib/test_decoding/sql/replorigin.sql#L34-L37)
- [permissions.sql#output_plugin_libraries](../../../../raw/postgres-18/contrib/test_decoding/sql/permissions.sql#L18-L24)
- [permissions.out#output_plugin_libraries](../../../../raw/postgres-18/contrib/test_decoding/expected/permissions.out#L33-L41)

## Context Reviewed

- Subscriber option path: `parse_subscription_options`, `CreateSubscription`,
  `AlterSubscription` in
  [subscriptioncmds.c](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L310-L332),
  catalog
  [pg_subscription.h](../../../../raw/postgres-18/src/include/catalog/pg_subscription.h#L95-L162).
- Apply-side tagging: `run_apply_worker`, `set_stream_options`,
  `maybe_reread_subscription`, `ReplicationOriginNameForLogicalRep` in
  [worker.c](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L4561-L4594);
  tablesync origins in
  [tablesync.c](../../../../raw/postgres-18/src/backend/replication/logical/tablesync.c#L1389-L1423).
- WAL plumbing: `XLogSetRecordFlags(XLOG_INCLUDE_ORIGIN)` call sites in
  [heapam.c](../../../../raw/postgres-18/src/backend/access/heap/heapam.c#L2243),
  [xact.c](../../../../raw/postgres-18/src/backend/access/transam/xact.c#L5974),
  [twophase.c](../../../../raw/postgres-18/src/backend/access/transam/twophase.c#L1201),
  [tablecmds.c](../../../../raw/postgres-18/src/backend/commands/tablecmds.c#L2335),
  [message.c](../../../../raw/postgres-18/src/backend/replication/logical/message.c#L70);
  record assembly in
  [xloginsert.c](../../../../raw/postgres-18/src/backend/access/transam/xloginsert.c#L841-L847).
- Publisher filtering: `START_REPLICATION` option in
  [libpqwalreceiver.c](../../../../raw/postgres-18/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L630-L635),
  `pgoutput`
  ([pgoutput.c](../../../../raw/postgres-18/src/backend/replication/pgoutput/pgoutput.c#L1763-L1776)),
  decode-time filters in
  [decode.c](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L573-L580),
  callback wrapper in
  [logical.c](../../../../raw/postgres-18/src/backend/replication/logical/logical.c#L1269-L1297).
- Conflict layer: types and reporting in
  [conflict.h](../../../../raw/postgres-18/src/include/replication/conflict.h#L31-L61)
  /
  [conflict.c](../../../../raw/postgres-18/src/backend/replication/logical/conflict.c#L62-L106),
  apply-worker call sites in
  [worker.c](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L2723-L2914),
  executor site in
  [execReplication.c](../../../../raw/postgres-18/src/backend/executor/execReplication.c#L550),
  stats view in
  [system_views.sql](../../../../raw/postgres-18/src/backend/catalog/system_views.sql#L1384-L1399).
- New-feature evidence: gencols catalog/options
  ([pg_publication.h](../../../../raw/postgres-18/src/include/catalog/pg_publication.h#L62-L133),
  [publicationcmds.c](../../../../raw/postgres-18/src/backend/commands/publicationcmds.c#L165-L170)),
  GUCs in
  [guc_tables.c](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3108-L3118)
  and slot invalidation in
  [slot.c](../../../../raw/postgres-18/src/backend/replication/slot.c#L1685-L1693),
  origin array sizing in
  [origin.c](../../../../raw/postgres-18/src/backend/replication/logical/origin.c#L538-L544),
  client tools in
  [pg_createsubscriber.c](../../../../raw/postgres-18/src/bin/pg_basebackup/pg_createsubscriber.c#L2064-L2081)
  and
  [pg_recvlogical.c](../../../../raw/postgres-18/src/bin/pg_basebackup/pg_recvlogical.c#L44-L45).
- Docs:
  [create_subscription.sgml](../../../../raw/postgres-18/doc/src/sgml/ref/create_subscription.sgml#L407-L546),
  [create_publication.sgml](../../../../raw/postgres-18/doc/src/sgml/ref/create_publication.sgml#L199-L230),
  [alter_subscription.sgml](../../../../raw/postgres-18/doc/src/sgml/ref/alter_subscription.sgml#L239-L272),
  [replication-origins.sgml](../../../../raw/postgres-18/doc/src/sgml/replication-origins.sgml#L12-L95),
  [logical-replication.sgml](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L1568-L2106),
  [monitoring.sgml](../../../../raw/postgres-18/doc/src/sgml/monitoring.sgml#L2192-L2262),
  [release-18.sgml](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L10335-L10482),
  [pglogicalinspect.sgml](../../../../raw/postgres-18/doc/src/sgml/pglogicalinspect.sgml#L30-L71).
- Tests:
  [030_origin.pl](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl),
  [subscription.sql](../../../../raw/postgres-18/src/test/regress/sql/subscription.sql#L69-L75),
  [replorigin.sql](../../../../raw/postgres-18/contrib/test_decoding/sql/replorigin.sql#L34-L37).
- Source history: ancestry checks of all listed feature commits against
  `e26810d01d` (Stamp HEAD as 18devel) and `3d6a828938` (Stamp 18.0) with
  `git merge-base --is-ancestor`; all 20 fall inside the v18 cycle.

## Evidence Map

| Claim | Evidence |
|---|---|
| `origin` accepts only `none`/`any`, default `any`, stored in `suborigin` | [subscriptioncmds.c#parse_subscription_options](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L310-L332), [subscriptioncmds.c:165-166](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L165-L166), [subscriptioncmds.c:710-711](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L710-L711), [pg_subscription.h#suborigin](../../../../raw/postgres-18/src/include/catalog/pg_subscription.h#L95) |
| Apply worker sets session origin `pg_<suboid>`; tablesync uses `pg_<suboid>_<relid>` | [worker.c#run_apply_worker](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L4584-L4594), [worker.c#ReplicationOriginNameForLogicalRep](../../../../raw/postgres-18/src/backend/replication/logical/worker.c#L421-L434), [tablesync.c#LogicalRepSyncTableStart](../../../../raw/postgres-18/src/backend/replication/logical/tablesync.c#L1389-L1423) |
| WAL records of applied transactions carry the origin ID | [xloginsert.c#XLogRecordAssemble](../../../../raw/postgres-18/src/backend/access/transam/xloginsert.c#L841-L847), [heapam.c#heap_insert](../../../../raw/postgres-18/src/backend/access/heap/heapam.c#L2243), [xact.c#XactLogCommitRecord](../../../../raw/postgres-18/src/backend/access/transam/xact.c#L5974) |
| Subscriber sends `origin` to publisher only for servers >= 16 | [libpqwalreceiver.c#libpqrcv_startstreaming](../../../../raw/postgres-18/src/backend/replication/libpqwalreceiver/libpqwalreceiver.c#L630-L635) |
| `pgoutput` skips origin-tagged changes when `origin = none` | [pgoutput.c#pgoutput_origin_filter](../../../../raw/postgres-18/src/backend/replication/pgoutput/pgoutput.c#L1763-L1776), [decode.c#DecodeInsert](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L919), [decode.c#DecodeTXNNeedSkip](../../../../raw/postgres-18/src/backend/replication/logical/decode.c#L1296-L1316) |
| Loop prevention works; transitive origins filtered | [030_origin.pl:76-98](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl#L76-L98), [030_origin.pl:105-149](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl#L105-L149) |
| Initial COPY cannot see origins; WARNING raised; user must verify | [subscriptioncmds.c#check_publications_origin](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L2130-L2232), [create_subscription.sgml#Notes](../../../../raw/postgres-18/doc/src/sgml/ref/create_subscription.sgml#L519-L546) |
| `none`/`any`/`pg_*` origin names reserved | [origin.c#pg_replication_origin_create](../../../../raw/postgres-18/src/backend/replication/logical/origin.c#L1292-L1311) |
| Seven conflict types logged/counted; origin-differs needs `track_commit_timestamp` | [conflict.h#ConflictType](../../../../raw/postgres-18/src/include/replication/conflict.h#L31-L61), [conflict.c#GetTupleTransactionInfo](../../../../raw/postgres-18/src/backend/replication/logical/conflict.c#L62-L77), [system_views.sql](../../../../raw/postgres-18/src/backend/catalog/system_views.sql#L1384-L1399), [logical-replication.sgml#Conflicts](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L1746-L1848), [030_origin.pl:150-191](../../../../raw/postgres-18/src/test/subscription/t/030_origin.pl#L150-L191) |
| Conflict resolution still manual (SKIP / origin advance / disable_on_error) | [logical-replication.sgml:2006-2017](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L2006-L2017) |
| DDL and sequences not replicated | [logical-replication.sgml#Restrictions](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L2058-L2070), [logical-replication.sgml:2075](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L2075) |
| Gencols replication via column list or `publish_generated_columns` | [pg_publication.h#PublishGencolsType](../../../../raw/postgres-18/src/include/catalog/pg_publication.h#L115-L123), [create_publication.sgml](../../../../raw/postgres-18/doc/src/sgml/ref/create_publication.sgml#L199-L230), [logical-replication.sgml:1568-1600](../../../../raw/postgres-18/doc/src/sgml/logical-replication.sgml#L1568-L1600) |
| `streaming` default now `parallel` | [subscriptioncmds.c:154](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L154), [create_subscription.sgml:274-279](../../../../raw/postgres-18/doc/src/sgml/ref/create_subscription.sgml#L274-L279) |
| `two_phase` alterable | [subscriptioncmds.c:1188-1195](../../../../raw/postgres-18/src/backend/commands/subscriptioncmds.c#L1188-L1195), [alter_subscription.sgml:239-272](../../../../raw/postgres-18/doc/src/sgml/ref/alter_subscription.sgml#L239-L272) |
| `max_active_replication_origins`: default 10, restart-scoped, sizes origin array | [guc_tables.c:3389-3399](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3389-L3399), [origin.c:538-544](../../../../raw/postgres-18/src/backend/replication/logical/origin.c#L538-L544) |
| `idle_replication_slot_timeout`: default 0, reload-scoped, invalidates idle slots | [guc_tables.c:3108-3118](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3108-L3118), [slot.c:1685-1693](../../../../raw/postgres-18/src/backend/replication/slot.c#L1685-L1693) |
| Client tool options (`pg_createsubscriber`, `pg_recvlogical`) | [pg_createsubscriber.c:2064-2081](../../../../raw/postgres-18/src/bin/pg_basebackup/pg_createsubscriber.c#L2064-L2081), [pg_recvlogical.c:44-45](../../../../raw/postgres-18/src/bin/pg_basebackup/pg_recvlogical.c#L44-L45), docs cited inline |
| Commit attribution to the v18 cycle | checkout git history: `git merge-base --is-ancestor` against `e26810d01d` (18devel) and `3d6a828938` (Stamp 18.0); release-note commit annotations in [release-18.sgml](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L10378-L10482) |

## Open Questions

- The new-features list is scoped to the release notes' logical-replication
  sections plus the two replication GUC items, the client tools, and the
  contrib module, each verified in source. A v18 behavior change relevant to
  logical replication but filed under another release-note section (for
  example performance work) and absent from these sweeps would be missed.
- The release notes mention `--clean` taking only `publications` as object
  type; the broader `--clean` design (other object types) is not verified
  beyond [pg_createsubscriber.sgml:233](../../../../raw/postgres-18/doc/src/sgml/ref/pg_createsubscriber.sgml#L233).
