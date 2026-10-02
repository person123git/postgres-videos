---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# Table Partitioning Optimizations and Configuration During Query Planning and Execution in PostgreSQL 17 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Configuration at a glance](#configuration-at-a-glance)
- [Inheritance-based (legacy) partitioning](#inheritance-based-legacy-partitioning)
  - [Constraint exclusion](#constraint-exclusion)
  - [Tuple routing is manual (triggers/rules)](#tuple-routing-is-manual-triggersrules)
  - [What inheritance partitioning does not get](#what-inheritance-partitioning-does-not-get)
- [Declarative partitioning](#declarative-partitioning)
  - [Partition pruning during planning and execution](#partition-pruning-during-planning-and-execution)
  - [How partition pruning differs by strategy](#how-partition-pruning-differs-by-strategy)
  - [Constraint exclusion on declarative tables](#constraint-exclusion-on-declarative-tables)
  - [Partitionwise join](#partitionwise-join)
  - [Partitionwise aggregate and grouping](#partitionwise-aggregate-and-grouping)
  - [Executor tuple routing, row movement, and COPY batching](#executor-tuple-routing-row-movement-and-copy-batching)
  - [What declarative partitioning does not optimize](#what-declarative-partitioning-does-not-optimize)
  - [Per-strategy summary](#per-strategy-summary)
- [Optimizations since PostgreSQL 12](#optimizations-since-postgresql-12)
  - [v13: advanced partitionwise join](#v13-advanced-partitionwise-join)
  - [v14: run-time pruning for UPDATE/DELETE, and DETACH PARTITION CONCURRENTLY](#v14-run-time-pruning-for-updatedelete-and-detach-partition-concurrently)
  - [v15: non-pruned-partition bitmap, run-time-prune refactor, and MERGE](#v15-non-pruned-partition-bitmap-run-time-prune-refactor-and-merge)
  - [v16: cached tuple-routing lookups](#v16-cached-tuple-routing-lookups)
  - [v17: boolean IS [NOT] UNKNOWN pruning and concurrent-detach robustness](#v17-boolean-is-not-unknown-pruning-and-concurrent-detach-robustness)
  - [Since-v12 summary table](#since-v12-summary-table)
- [Locking reduction and random-I/O sensitivity per optimization](#locking-reduction-and-random-io-sensitivity-per-optimization)
  - [Only plan-time pruning removes read locks](#only-plan-time-pruning-removes-read-locks)
  - [Why scan-eliminating optimizations gain most under slow random I/O](#why-scan-eliminating-optimizations-gain-most-under-slow-random-io)
  - [Partitionwise join and aggregate under slow random I/O](#partitionwise-join-and-aggregate-under-slow-random-io)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

During query planning or execution, what are the current optimizations and configurations per type of table partitioning currently implemented? Add a section with optimizations since version 12.

Follow-up: Add an extra analysis on how each optimization will reduce locking, and how each will have big gains if random I/O has higher latency.

> Prompt note: filed as an approved grammar-corrected restatement of the original
> question ("during query planning or execution what are the current
> optimizations and configuration per type of table parititioning currently
> implemented? add a section with optimization since version 12"), per the
> repository's prompt-hygiene rule. The follow-up above was supplied already
> grammatically clean and is recorded verbatim.

## Answer

PostgreSQL 17 has **two kinds of table partitioning**, and the optimizations available differ sharply between them:

- **Inheritance-based (legacy) partitioning** — plain table inheritance (`INHERITS`) plus `CHECK` constraints, wired up by hand. Its one planner optimization is **constraint exclusion**; routing rows to the right child table is your job (a trigger or rule).
- **Declarative partitioning** (`PARTITION BY` with the RANGE / LIST / HASH strategies) — the engine knows the partition bounds, so it adds **partition pruning** (plan-time and run-time), **partitionwise join**, **partitionwise aggregate**, and automatic **tuple routing** with per-partition COPY batching and cross-partition UPDATE row movement.

The documentation states this split directly: partition pruning "is a query optimization technique that improves performance for declaratively partitioned tables" ([ddl.sgml#Partition-Pruning](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L4901-L4918)), while constraint exclusion "is primarily used for partitioning implemented using the legacy inheritance method" and uses `CHECK` constraints rather than "the table's partition bounds, which exist only in the case of declarative partitioning" ([ddl.sgml#Constraint-Exclusion](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L5035-L5050)). The three declarative strategies are RANGE, LIST, and HASH ([ddl.sgml#Partitioning-Overview](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L3924-L3969)).

The two sections below answer per partitioning type. Internally, only a declaratively partitioned table carries a `PartitionScheme` ([pathnodes.h#PartitionSchemeData](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L582-L598)) plus per-relation bounds, key expressions, and child arrays on its `RelOptInfo` — `part_scheme`, `boundinfo`, `partbounds_merged`, `part_rels`, `live_parts`, and `partexprs` ([pathnodes.h#RelOptInfo-partition-fields](../../../../raw/postgres-17/src/include/nodes/pathnodes.h#L1008-L1046)); those fields are what every declarative-only optimization reads, and their absence is why inheritance tables get none of them. (See [Optimizations since PostgreSQL 12](#optimizations-since-postgresql-12) for what changed across v13–v17.)

### Configuration at a glance

Four GUCs govern these optimizations. All four are defined with context `PGC_USERSET`, so each has **session/transaction apply scope**: change it with `SET` for the current session or `SET LOCAL` for the current transaction, with no restart or reload for that session ([guc_tables.c#partitioning-GUCs](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L923-L974), [guc_tables.c#constraint_exclusion](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4797-L4807)). A server-wide default set in `postgresql.conf` is picked up by the normal configuration reload (SIGHUP / `pg_ctl reload` / `pg_reload_conf()`); none of these four requires a restart. Tuple routing and COPY batching have no GUC — the executor always performs them for a declaratively partitioned target.

| GUC | Partitioning type | Default | Phase | Definition |
|---|---|---|---|---|
| `constraint_exclusion` | legacy inheritance (also declarative `CHECK`s) | `partition` | planning | [guc_tables.c:4797-4807](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4797-L4807) |
| `enable_partition_pruning` | declarative | `on` | planning + execution | [guc_tables.c:963-974](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L963-L974) |
| `enable_partitionwise_join` | declarative | `off` | planning | [guc_tables.c:923-932](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L923-L932) |
| `enable_partitionwise_aggregate` | declarative | `off` | planning | [guc_tables.c:933-942](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L933-L942) |

The boolean variables and their compiled-in defaults live in `costsize.c`: `enable_partitionwise_join = false` and `enable_partitionwise_aggregate = false` ([costsize.c:148-149](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L148-L149)), `enable_partition_pruning = true` ([costsize.c:152](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L152)). The same defaults appear in `postgresql.conf.sample` ([postgresql.conf.sample#L413-L457](../../../../raw/postgres-17/src/backend/utils/misc/postgresql.conf.sample#L413-L457)).

## Inheritance-based (legacy) partitioning

Legacy partitioning is built from ordinary table inheritance: a "parent" table with no data, "child" tables created with `INHERITS (parent)`, non-overlapping `CHECK` constraints on the children, and a trigger/rule to route inserts. The engine has no partition metadata for such a tree, so its only automatic query optimization is constraint exclusion. The documentation caps the practical size of a legacy tree: it "will work well with up to perhaps a hundred child tables; don't try to use many thousands of children" ([ddl.sgml#L5107-L5115](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L5107-L5115)).

### Constraint exclusion

Constraint exclusion is the plan-time technique that proves a child table cannot match a query by comparing the query's restrictions against that table's constraints, and drops it from the plan. The GUC is an enum with three modes ([guc_tables.c#constraint_exclusion_options](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L327-L331)):

- `off` — never use it.
- `on` — apply to all relations.
- `partition` (the default) — apply only to appendrel children / inheritance members and `UNION ALL` subqueries.

The core logic is in `relation_excluded_by_constraints`. Regardless of the setting, it first detects constant-`FALSE`-or-`NULL` restriction clauses and excludes the relation ([plancat.c#L1602-L1621](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1602-L1621)). In the default `partition` mode it then processes only `RELOPT_OTHER_MEMBER_REL` (appendrel-member) rels — the inheritance-child case — and returns false for plain base relations ([plancat.c#L1632-L1642](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1632-L1642)). It fetches the child's `CHECK` and `NOT NULL` constraints via `get_relation_constraints` ([plancat.c#get_relation_constraints](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1272-L1290)) and asks `predicate_refuted_by` whether they contradict the query quals ([plancat.c#L1675-L1680](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1675-L1680)).

Configuration and caveats (from the docs):

- The default and recommended setting is `partition` ([config.sgml#guc-constraint-exclusion](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L6299-L6322)).
- It is **plan-time only** — "there is no attempt to remove partitions at execution time" ([ddl.sgml#L5042-L5050](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L5042-L5050)) — and it examines every child, so it does not scale past ~100 children ([ddl.sgml#L5107-L5115](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L5107-L5115)). This child-count ceiling is the main scalability limit of legacy partitioning.

`constraint_exclusion` is `PGC_USERSET` (session/transaction scope; `SET`/`SET LOCAL`, no restart or reload) ([guc_tables.c#L4797-L4807](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4797-L4807)).

### Tuple routing is manual (triggers/rules)

There is no automatic tuple routing for inheritance. To send a row inserted into the parent to the correct child, you attach a trigger (or rule). The documentation warns that such triggers "may be complicated to write, and will be much slower than the tuple routing performed internally by declarative partitioning" ([ddl.sgml#L4880-L4888](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L4880-L4888)).

### What inheritance partitioning does not get

Because an inheritance tree has no `PartitionScheme` or partition bounds, none of the declarative-only optimizations apply to it:

- **No partition pruning** (plan-time or run-time): pruning is driven by partition bounds that "exist only in the case of declarative partitioning" ([ddl.sgml#L5042-L5050](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L5042-L5050)).
- **No partitionwise join or aggregate**: both first require partitioned inputs carrying a `part_scheme`, which inheritance parents lack, so `build_joinrel_partition_info` bails immediately ([relnode.c#L2042-L2051](../../../../raw/postgres-17/src/backend/optimizer/util/relnode.c#L2042-L2051)) and partitionwise aggregation requires `IS_PARTITIONED_REL(input_rel)` ([planner.c#L4089-L4090](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L4089-L4090)).
- **No internal tuple routing / row movement / COPY batching per partition**: those executor paths operate on the partition descriptor of a declarative table (see the declarative section).

Constraint exclusion is therefore the whole story for planning against legacy partitions, and it is applied only at plan time.

## Declarative partitioning

Declarative partitioning (`PARTITION BY RANGE | LIST | HASH`) gives the engine the partition strategy and bounds, which unlocks the optimizations below.

### Partition pruning during planning and execution

Partition pruning compares query clauses against partition bounds to decide which partitions can be skipped. The module turns matching clauses into "pruning steps": a *base* step tests partition-key columns or expressions; a *combine* step joins earlier results with a Boolean AND/OR ([partprune.c#module-header](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L1-L35)). Steps are generated for one of three targets ([partprune.c#PartClauseTarget](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L91-L96)):

- `PARTTARGET_PLANNER` — clauses usable at plan time (constants).
- `PARTTARGET_INITIAL` — usable at executor startup.
- `PARTTARGET_EXEC` — usable per scan (including `PARAM_EXEC` Params).

**Plan-time pruning.** During expansion of a partitioned RTE, the planner prunes *before* it builds child relations: `expand_partitioned_rtentry` calls `prune_append_rel_partitions` and records the survivors in `live_parts`, then loops over `live_parts` only ([inherit.c#expand_partitioned_rtentry](../../../../raw/postgres-17/src/backend/optimizer/util/inherit.c#L352-L438)). Each surviving partition is opened — and thereby locked — with `try_table_open(childOID, lockmode)` inside that loop ([inherit.c#L389-L398](../../../../raw/postgres-17/src/backend/optimizer/util/inherit.c#L389-L398)). So pruned partitions are never locked, path-costed, or planned — a key scalability advantage over legacy partitioning. `prune_append_rel_partitions` short-circuits to "all partitions" when `enable_partition_pruning` is off or there are no clauses, then generates `PARTTARGET_PLANNER` steps and runs them in `get_matching_partitions` ([partprune.c#prune_append_rel_partitions](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L749-L804)).

**Run-time pruning.** When a clause compares the partition key to a non-constant but non-volatile expression (a `PREPARE` parameter, a subquery value, or a nested-loop inner parameter), the planner attaches a `PartitionPruneInfo` to the `Append`/`MergeAppend` plan via `make_partition_pruneinfo`, gated again by `enable_partition_pruning` ([createplan.c#Append](../../../../raw/postgres-17/src/backend/optimizer/plan/createplan.c#L1382-L1406) and [createplan.c#MergeAppend](../../../../raw/postgres-17/src/backend/optimizer/plan/createplan.c#L1546-L1560)). The executor then prunes in two phases:

1. **Initial pruning** at executor startup. `ExecInitAppend` calls `ExecInitPartitionPruning` when `part_prune_info` is set ([nodeAppend.c#ExecInitAppend](../../../../raw/postgres-17/src/backend/executor/nodeAppend.c#L137-L164)); that function runs `ExecFindMatchingSubPlans(prunestate, true)` and returns the initially valid subplans, so unneeded subplans are never initialized ([execPartition.c#ExecInitPartitionPruning](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1806-L1852)).
2. **Per-scan pruning** for execution parameters that change during the run (for example, the inner side of a parameterized nested loop). The Append/MergeAppend execution paths call `ExecFindMatchingSubPlans(prunestate, false)` whenever the valid-subplan set is invalidated ([nodeAppend.c#L569](../../../../raw/postgres-17/src/backend/executor/nodeAppend.c#L569), [execPartition.c#ExecFindMatchingSubPlans](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L2308-L2371)).

The documentation confirms both phases and how to observe them: initial pruning shows as "Subplans Removed" in `EXPLAIN`; per-scan pruning shows up only as `loops`/`(never executed)` in `EXPLAIN ANALYZE` ([ddl.sgml#execution-time-pruning](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L4973-L4998)). `enable_partition_pruning` controls both the planner's partition elimination and the executor's run-time removal ([config.sgml#guc-enable-partition-pruning](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5664-L5680)).

### How partition pruning differs by strategy

Both plan-time and run-time pruning funnel through `perform_pruning_base_step`, which switches on the partition strategy to a per-strategy bound-matching routine ([partprune.c#strategy-switch](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L3516-L3543)). The three routines behave differently:

- **HASH** — Pruning is possible only with equality clauses or `IS NULL`, and only when the query constrains **every** partition-key position (`nvalues + nullkeys == partnatts`); otherwise all partitions are kept. It computes the row hash and picks the one partition at `rowHash % greatest_modulus`. Hash partitioning has neither a null-accepting partition nor a `DEFAULT` partition ([partprune.c#get_matching_hash_bounds](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L2663-L2717)).
- **LIST** — Single key position. Supports B-tree comparison strategies (equality and inequalities) and a special `<>` (not-equal) path that keeps every bound except the matched one ([partprune.c#L2799-L2824](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L2799-L2824)). A NULL key routes to the null-accepting partition if one exists, else the `DEFAULT` partition ([partprune.c#get_matching_list_bounds](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L2739-L2770)).
- **RANGE** — Supports multi-column key prefixes and B-tree comparisons/ranges. There is no null-accepting range partition, so an `IS NULL` clause (or no usable datums) can only match the `DEFAULT` partition; a partial-prefix query also has to keep the `DEFAULT` partition ([partprune.c#get_matching_range_bounds](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L2951-L3005)). In the "no values to compare" case — the shape an `IS NOT NULL` step produces — `get_matching_range_bounds` since 17.11 returns **all** bound offsets, including key space no partition covers, and asserts only `partindices[minoff] >= -1 && partindices[maxoff] >= -1` ([partprune.c#no-values-to-compare](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L2984-L2998)). Before 17.11 it advanced `minoff` and retreated `maxoff` past that uncovered space and asserted `>= 0`, so the step signalled "scan the DEFAULT partition" only through `scan_default`; combined under an intersect combine step with another step that signalled it through `bound_offsets`, the intersection kept neither representation, pruned the `DEFAULT` partition, and lost rows (commit `31f2acde53d`, "Fix issue with RANGE's DEFAULT partition pruning", back-patched through v14).

The hash value used for HASH pruning and routing ignores NULL key values and combines each key's type-specific hash with a fixed seed ([partbounds.c#compute_partition_hash_value](../../../../raw/postgres-17/src/backend/partitioning/partbounds.c#L4722-L4752)).

### Constraint exclusion on declarative tables

Constraint exclusion (see the inheritance section for the mechanism) can *also* apply to declarative tables, because you may add ordinary `CHECK` constraints to them on top of their internal partition bounds. Two nuances in `relation_excluded_by_constraints` matter here:

- In the default `partition` mode, a declarative partition's own internal partition constraint is deliberately **not** re-checked, because "Partition pruning has already been applied" ([plancat.c#L1632-L1642](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1632-L1642)).
- In `on` mode, a directly named partition base relation additionally has its internal partition constraint pulled into the constraint set (`include_partition`) ([plancat.c#L1644-L1655](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1644-L1655)).

So on a declarative table, partition pruning is the primary tool; constraint exclusion is a plan-time supplement that only helps if you defined extra `CHECK` constraints or run in `on` mode. The docs point declarative users at `enable_partition_pruning` rather than `constraint_exclusion` ([config.sgml#L6299-L6322](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L6299-L6322)).

### Partitionwise join

When enabled, partitionwise join turns a join between two partitioned tables into a set of smaller joins between matching partitions. It is **off by default** because it increases planning CPU and memory and can raise the number of `work_mem`-limited nodes linearly with the partition count ([guc_tables.c#L923-L932](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L923-L932), [config.sgml#guc-enable-partitionwise-join](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5682-L5704)).

The applicability test lives in `build_joinrel_partition_info`, which returns immediately if the GUC is off and otherwise requires that both inputs are partitioned with `consider_partitionwise_join`, share the **same** `PartitionScheme`, and have an equi-join on the partition keys (`have_partkey_equi_join`) ([relnode.c#build_joinrel_partition_info](../../../../raw/postgres-17/src/backend/optimizer/util/relnode.c#L2017-L2080)). The equi-join check requires a usable equality clause for **every** partition key, matching operator families, and matching collation ([relnode.c#have_partkey_equi_join](../../../../raw/postgres-17/src/backend/optimizer/util/relnode.c#L2090-L2222)). Unlike PostgreSQL 12, the partition bounds no longer have to be identical at this point; `try_partitionwise_join` computes the join's partition bounds in `compute_partition_bounds`, using the inputs' bounds directly when they match exactly and otherwise **merging** them with `partition_bounds_merge` ([joinrels.c#try_partitionwise_join](../../../../raw/postgres-17/src/backend/optimizer/path/joinrels.c#L1479-L1560), [joinrels.c#compute_partition_bounds](../../../../raw/postgres-17/src/backend/optimizer/path/joinrels.c#L1790-L1849)). See [v13: advanced partitionwise join](#v13-advanced-partitionwise-join). The documented requirement matches: partitionwise join "applies only when the join conditions include all the partition keys, which must be of the same data type and have one-to-one matching sets of child partitions" ([config.sgml#L5682-L5704](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5682-L5704)).

### Partitionwise aggregate and grouping

Partitionwise aggregation performs grouping/aggregation per partition, then appends the results. It is **off by default** for the same planning-cost reason ([guc_tables.c#L933-L942](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L933-L942), [config.sgml#guc-enable-partitionwise-aggregate](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5706-L5729)).

`create_grouping_paths` marks the query as a candidate for **full** partitionwise aggregation only when `enable_partitionwise_aggregate` is set and there are no grouping sets ([planner.c#L3904-L3917](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L3904-L3917)). `create_ordinary_grouping_paths` then picks the concrete strategy on a partitioned input ([planner.c#L4081-L4147](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L4081-L4147)):

- **FULL** partitionwise aggregation if the `GROUP BY` clause contains all partition-key columns or expressions with matching collation, verified by `group_by_has_partkey` ([planner.c#group_by_has_partkey](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L8113-L8186)). Each partition is aggregated independently and the results appended.
- **PARTIAL** partitionwise aggregation otherwise (when partial aggregation is possible at all): each partition is partially aggregated, then a finalize step combines them. This matches the documented behavior that "if the `GROUP BY` clause does not include the partition keys, only partial aggregation can be performed on a per-partition basis, and finalization must be performed later" ([config.sgml#L5706-L5729](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5706-L5729)).

The per-partition paths are built by `create_partitionwise_grouping_paths` ([planner.c#L7975-L8105](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L7975-L8105)).

### Executor tuple routing, row movement, and COPY batching

Writing into a declaratively partitioned table needs no GUC; the executor always routes each row to the correct leaf partition. `ExecSetupPartitionTupleRouting` builds the routing state lazily ([execPartition.c#ExecSetupPartitionTupleRouting](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L202-L215)), and `ExecFindPartition` descends the partition hierarchy from the root, checking the root partition constraint first, to find the leaf for a tuple ([execPartition.c#ExecFindPartition](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L262-L316)). The per-strategy leaf lookup is `get_partition_for_tuple` ([execPartition.c#get_partition_for_tuple](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1396-L1600)):

- **HASH** — `boundinfo->indexes[rowHash % nindexes]`, after computing a hash value that ignores NULL key values; no `DEFAULT` and no caching ([execPartition.c#L1419-L1434](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1419-L1434)).
- **LIST** — a null key routes to `null_index` (if the table accepts nulls); otherwise a binary search on the list bounds, with a last-found-partition cache tried first ([execPartition.c#L1436-L1484](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1436-L1484)).
- **RANGE** — any null key position routes to the `DEFAULT` partition (ranges never accept null); otherwise a cached-then-binary-search on the range bounds ([execPartition.c#L1486-L1563](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1486-L1563)).

Any tuple that matches no partition falls to `default_index`, and a still-unmatched row raises an error ([execPartition.c#L1575-L1583](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1575-L1583)). The LIST/RANGE last-found cache (`PARTITION_CACHED_FIND_THRESHOLD`) speeds up bulk loads where consecutive rows land in the same partition; see [v16: cached tuple-routing lookups](#v16-cached-tuple-routing-lookups).

Two further executor behaviors are relevant:

- **Cross-partition UPDATE (row movement).** If an `UPDATE` changes the partition key so the row no longer satisfies its partition's constraint, `ExecCrossPartitionUpdate` moves it by performing a `DELETE` on the old partition and re-routing an `INSERT` back through the root table into the new partition ([nodeModifyTable.c#row-movement](../../../../raw/postgres-17/src/backend/executor/nodeModifyTable.c#L2049-L2114), [nodeModifyTable.c#ExecCrossPartitionUpdate](../../../../raw/postgres-17/src/backend/executor/nodeModifyTable.c#L1744-L1801)). The write path opens each touched leaf partition lazily with `RowExclusiveLock` the first time a row routes to it, via `ExecInitPartitionInfo` ([execPartition.c#L515-L517](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L515-L517)).
- **Per-partition COPY batching.** `COPY FROM` into a partitioned table uses the `CIM_MULTI_CONDITIONAL` insert method so it can multi-insert into each leaf partition, deciding per partition whether to batch (disabled for a partition that is a non-batching foreign table or has BEFORE/INSTEAD-OF row triggers) ([copyfrom.c#L896-L918](../../../../raw/postgres-17/src/backend/commands/copyfrom.c#L896-L918)).

### What declarative partitioning does not optimize

- **Partitionwise join/aggregate still need matching partition schemes and an all-partition-key equi-join / grouping.** Tables with different `PartitionScheme`s do not qualify ([relnode.c#L2042-L2051](../../../../raw/postgres-17/src/backend/optimizer/util/relnode.c#L2042-L2051)); a join missing an equi-join on any partition key is rejected ([relnode.c#L2214-L2219](../../../../raw/postgres-17/src/backend/optimizer/util/relnode.c#L2214-L2219)); full partitionwise aggregation needs all partition keys in `GROUP BY` ([planner.c#L4105-L4112](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L4105-L4112)).
- **Hash pruning needs all key positions** and only equality/`IS NULL`; a range or partial-key predicate cannot prune a hash-partitioned table ([partprune.c#L2680-L2708](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L2680-L2708)).
- **Both partitionwise settings default to off** and inflate planning CPU/memory when enabled, growing `work_mem`-limited nodes with the partition count ([config.sgml#L5682-L5729](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5682-L5729)).

### Per-strategy summary

| Aspect | RANGE | LIST | HASH |
|---|---|---|---|
| Pruning clauses used | equality + range/inequality (prefix of keys) | equality + inequality + `<>` | equality / `IS NULL` only, **all** keys required |
| NULL handling in pruning/routing | `DEFAULT` only (no null partition) | null partition, else `DEFAULT` | NULL keys ignored by the hash computation; no null/`DEFAULT` partition |
| `DEFAULT` partition | yes | yes | no |
| Plan-time + run-time pruning | yes | yes | yes |
| Constraint exclusion applies | via extra `CHECK` (or `constraint_exclusion=on`) | same | same |
| Partitionwise join/aggregate | if schemes match + all-key equi-join / grouping | same | same |
| Tuple routing | cached range bsearch | cached list bsearch / null_index | `hash % nindexes` |

Per-strategy pruning: [partprune.c#L3516-L3543](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L3516-L3543). Per-strategy routing: [execPartition.c#L1396-L1600](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1396-L1600).

## Optimizations since PostgreSQL 12

This section lists the partitioning planning/execution optimizations added after PostgreSQL 12. Each behavioral claim is cited to the current v17 source that implements it; the introducing major version is attributed from the v17 checkout's own commit history, bracketed by the "Stamp HEAD as NNdevel" boundary commits (`615cebc94b5` = 13devel, `d10b19e224c` = 14devel, `596b5af1d36` = 15devel, `d31d30973a1` = 16devel, `5bcc7e6dc8c` = 17devel).

### v13: advanced partitionwise join

PostgreSQL 12 could do partitionwise join only when both tables had **identical** partition bounds. v13 lifted that: `compute_partition_bounds` uses the inputs' bounds directly when they match exactly and otherwise **merges** them with `partition_bounds_merge`, setting `joinrel->partbounds_merged` ([joinrels.c#compute_partition_bounds](../../../../raw/postgres-17/src/backend/optimizer/path/joinrels.c#L1790-L1849), [partbounds.c#partition_bounds_merge](../../../../raw/postgres-17/src/backend/partitioning/partbounds.c#L1118)). So range/list tables whose partitions only partly overlap can still join partition-by-partition. Introduced by commit `c8434d64ce0` ("Allow partitionwise joins in more cases", first released in v13); a companion fix `981643dcdb7` ("Allow partitionwise join to handle nested FULL JOIN USING cases") is also in the v13 cycle.

### v14: run-time pruning for UPDATE/DELETE, and DETACH PARTITION CONCURRENTLY

- **Execution-time pruning now applies to `UPDATE`/`DELETE`.** In v12, execution-time pruning worked only for `Append`/`MergeAppend` in `SELECT`, not for the `ModifyTable` node. Commit `86dc90056df` ("Rework planning and execution of UPDATE and DELETE", v14) changed `UPDATE`/`DELETE` to plan the target as a single `Append`-fed `ModifyTable`, so run-time pruning applies to them too. The v12 documentation caveat about `ModifyTable` was removed by `1692d0c3a3f` ("Doc: Remove outdated note about run-time partition pruning", v14); no such caveat remains in the v17 pruning docs ([ddl.sgml#L4973-L4998](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L4973-L4998)). The regression suite demonstrates run-time pruning inside an `UPDATE` plan, with pruned partitions shown `(never executed)` ([partition_prune.out#L2952-L2978](../../../../raw/postgres-17/src/test/regress/expected/partition_prune.out#L2952-L2978)).
- **`ALTER TABLE ... DETACH PARTITION ... CONCURRENTLY`.** Added by `71f4c8c6f74` (v14). Its planner-visible mechanism is detach-pending partition filtering in partition descriptors, not the current `try_table_open` open-failure path. `RelationBuildPartitionDesc` asks `find_inheritance_children_extended` to omit detached partitions when building a descriptor for a user query ([partdesc.c#RelationBuildPartitionDesc](../../../../raw/postgres-17/src/backend/partitioning/partdesc.c#L156-L167)), and that helper omits an `inhdetachpending` partition once the marking transaction is visible to the active snapshot ([pg_inherits.c#find_inheritance_children_extended](../../../../raw/postgres-17/src/backend/catalog/pg_inherits.c#L70-L79), [pg_inherits.c#L123-L176](../../../../raw/postgres-17/src/backend/catalog/pg_inherits.c#L123-L176)). The relcache stores a separate descriptor that omits detached partitions, plus the `pg_inherits` xmin used to decide whether it can be reused with a later active snapshot ([partdesc.c#RelationGetPartitionDesc](../../../../raw/postgres-17/src/backend/partitioning/partdesc.c#L53-L109), [partdesc.c#L359-L405](../../../../raw/postgres-17/src/backend/partitioning/partdesc.c#L359-L405)). The `try_table_open` "dropped detached partition" handling is the v17 hardening below.

### v15: non-pruned-partition bitmap, run-time-prune refactor, and MERGE

- **`live_parts` bitmap.** The planner now tracks the set of non-pruned partitions as a `Bitmapset` on the `RelOptInfo`, filled by `prune_append_rel_partitions` and consumed by expansion, so pruned partitions are skipped cheaply ([inherit.c#L352-L358](../../../../raw/postgres-17/src/backend/optimizer/util/inherit.c#L352-L358), [partprune.c#L749-L804](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L749-L804)). Introduced by `475dbd0b718` ("Track a Bitmapset of non-pruned partitions in RelOptInfo", v15).
- **Run-time-prune code refactor.** Initial and per-scan pruning were unified behind `ExecInitPartitionPruning` and a single `ExecFindMatchingSubPlans(prunestate, initial_prune)` ([execPartition.c#L1806-L1852](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1806-L1852), [execPartition.c#L2308](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L2308)), replacing v12's two separate functions. From `297daa9d435` ("Refactor and cleanup runtime partition prune code a little", v15).
- **`MERGE`.** The `MERGE` command arrived in v15 (`7103ebb7aae`) and works on partitioned tables through the same tuple-routing path, including cross-partition row movement (`ExecCrossPartitionUpdate` has an explicit `CMD_MERGE` branch) ([nodeModifyTable.c#L2102-L2114](../../../../raw/postgres-17/src/backend/executor/nodeModifyTable.c#L2102-L2114)).

### v16: cached tuple-routing lookups

`ExecFindPartition`/`get_partition_for_tuple` gained a last-found-partition cache for LIST and RANGE routing: after `PARTITION_CACHED_FIND_THRESHOLD` consecutive hits on the same partition it checks that partition first, skipping the binary search ([execPartition.c#L1456-L1483](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1456-L1483), [execPartition.c#L1509-L1547](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1509-L1547), cache update at [execPartition.c#L1588-L1600](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1588-L1600)). This speeds up bulk `INSERT`/`COPY` where consecutive rows cluster into the same partition. From `3592e0ff98b` ("Have ExecFindPartition cache the last found partition", v16). v16 also moved `PartitionPruneInfo` out of individual plan nodes into `PlannedStmt` (`ec386948948`), centralizing run-time-pruning metadata.

### v17: boolean IS [NOT] UNKNOWN pruning and concurrent-detach robustness

- **Pruning on `boolcol IS [NOT] UNKNOWN`.** v17 extended partition pruning of boolean partition keys to handle the `IS UNKNOWN` / `IS NOT UNKNOWN` clause forms (mapped to a nullness match) in addition to `IS [NOT] TRUE/FALSE`, in the boolean-clause matcher ([partprune.c#match_boolean_partition_clause](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L3682-L3713)). From `07c36c1333e` ("Support partition pruning on boolcol IS [NOT] UNKNOWN", v17), alongside boolean-pruning correctness fixes (`4c2369ac5`).
- **Concurrent-detach robustness for pruning/expansion.** v17 finished making plan-time expansion tolerate a partition dropped after a concurrent detach: `try_table_open` returning NULL is handled by treating the partition as pruned ([inherit.c#L389-L398](../../../../raw/postgres-17/src/backend/optimizer/util/inherit.c#L389-L398)), from `11f1218ce81` ("Avoid failure to open dropped detached partition", v17). Run-time pruning setup during `DETACH ... CONCURRENTLY` was also fixed (`27162a64b38`). v17 further broadened `MERGE` on partitioned tables with `WHEN NOT MATCHED BY SOURCE` (`0294df2f1f8`) and `RETURNING` (`c649fa24a42`).
- **17.11 correctness fix: RANGE pruning could drop the `DEFAULT` partition.** `31f2acde53d` ("Fix issue with RANGE's DEFAULT partition pruning", back-patched through v14) made the "no values to compare" result mark `bound_offsets` over the whole bound range instead of skipping uncovered edge key space, so an `IS NOT NULL` step and a step that marks the `DEFAULT` partition through `bound_offsets` survive an intersect combine step together ([partprune.c#no-values-to-compare](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L2984-L2998)). This is a wrong-results fix, not a speedup: before it, such a query could prune the `DEFAULT` partition and lose rows. New regression coverage adds a range-partitioned `rangepart` with a `DEFAULT` partition and four `IN`-clause plans ([partition_prune.sql#L102-L120](../../../../raw/postgres-17/src/test/regress/sql/partition_prune.sql#L102-L120)), including `where a is not null and a in(-1,5,15,20)`, whose expected plan scans `rangepart1`, `rangepart2` **and** `rangepart_def` ([partition_prune.out#L674-L719](../../../../raw/postgres-17/src/test/regress/expected/partition_prune.out#L674-L719)).

### Since-v12 summary table

| Version | Optimization | Kind | Attribution |
|---|---|---|---|
| v13 | Partitionwise join with non-identical (merged) bounds | planner | `c8434d64ce0`, `981643dcdb7` |
| v14 | Run-time pruning for `UPDATE`/`DELETE` (`ModifyTable`) | planner + executor | `86dc90056df`, doc `1692d0c3a3f` |
| v14 | `DETACH PARTITION CONCURRENTLY` (detach-pending partitions can be omitted from query partition descriptors) | DDL / planner descriptor | `71f4c8c6f74` |
| v15 | `live_parts` non-pruned-partition bitmap | planner | `475dbd0b718` |
| v15 | Unified initial/per-scan run-time pruning | executor | `297daa9d435` |
| v15 | `MERGE` on partitioned tables (routing + row movement) | executor | `7103ebb7aae` |
| v16 | Cached last-found partition in tuple routing | executor | `3592e0ff98b` |
| v16 | `PartitionPruneInfo` moved into `PlannedStmt` | planner/executor plumbing | `ec386948948` |
| v17 | Pruning on `boolcol IS [NOT] UNKNOWN` | planner | `07c36c1333e` |
| v17 | Concurrent-detach open-failure robustness in expansion | planner | `11f1218ce81`, `27162a64b38` |
| v17.11 | RANGE `DEFAULT`-partition pruning correctness (no-values-to-compare result marks all bound offsets) | planner (wrong-results fix) | `31f2acde53d` |

## Locking reduction and random-I/O sensitivity per optimization

Short answer: **only plan-time partition pruning actually reduces the locks a read query takes**, and on the write path lazy tuple routing locks only the partitions that receive rows. Constraint exclusion, run-time pruning, and partitionwise join/aggregate keep the same lock set — they cut I/O and CPU, not locks. Separately, the *scan-eliminating* optimizations (plan-time and run-time pruning, plus constraint exclusion) gain the most when random I/O is slow, because the whole-partition heap and index reads they avoid are priced at `random_page_cost`, which v17 sets to 4× `seq_page_cost` and the docs say to raise on slower-than-assumed random storage. Partitionwise join gains from cutting CPU, memory, and sequential-spill I/O; **partitionwise aggregate additionally has a random-I/O tie-in in v17**, because v17 hash aggregation can spill to disk and its spill *writes* are priced at `random_page_cost` — the main way this analysis differs from PostgreSQL 12, where hash aggregation was in-memory only.

| Optimization | Reduces locks? | Gain when random I/O latency is high |
|---|---|---|
| Plan-time partition pruning | **Yes** — pruned partitions are never opened or locked | **Large** — avoids each pruned partition's random index/heap fetches |
| Run-time partition pruning | No — every plan-time survivor is locked before execution | **Large** — skips scanning partitions at execution |
| Constraint exclusion | No — children are already locked before it runs | Moderate — drops an excluded partition's scan, but only with a constant qual + `CHECK` |
| Partitionwise join | No — both sides' partitions stay locked | Indirect — smaller per-join footprint; batch spills modeled as sequential |
| Partitionwise aggregate | No | **Yes if it avoids a spill** — v17 prices hash-agg spill writes at `random_page_cost`; otherwise a CPU/memory/locality win |
| Tuple routing (write path) | Routed `INSERT`/`COPY` opens leaf partitions lazily; `UPDATE`/`DELETE` scan locks are separate | n/a (write path) |

### Only plan-time pruning removes read locks

The planner expands a partitioned or inherited parent into child relations in `add_other_rels_to_query`, which runs *before* `make_one_rel` costs anything; the expansion is deliberately delayed to the end of `query_planner` so restriction clauses are available to "prune away partitions that don't satisfy a restriction clause" ([planmain.c#query_planner](../../../../raw/postgres-17/src/backend/optimizer/plan/planmain.c#L260-L280)). Locking happens during that expansion, and the two partitioning kinds differ:

- **Declarative, plan-time pruning.** `expand_partitioned_rtentry` calls `prune_append_rel_partitions` first and records the survivors in `live_parts` ([inherit.c#L352-L358](../../../../raw/postgres-17/src/backend/optimizer/util/inherit.c#L352-L358)). It then iterates `live_parts` only, and `try_table_open(childOID, lockmode)` — the point at which a partition's lock is taken — is inside that loop ([inherit.c#L379-L398](../../../../raw/postgres-17/src/backend/optimizer/util/inherit.c#L379-L398)). A pruned partition is therefore never opened and never locked. Fewer locks means less lock-manager traffic and fewer objects with which later DDL (which needs a conflicting lock) can collide. The `live_parts` bitmap is itself a v15 addition (see [v15: non-pruned-partition bitmap, run-time-prune refactor, and MERGE](#v15-non-pruned-partition-bitmap-run-time-prune-refactor-and-merge)).
- **Inheritance + constraint exclusion.** `expand_inherited_rtentry` locks *every* member up front via `find_all_inheritors(parentOID, lockmode, NULL)` ([inherit.c#L166-L170](../../../../raw/postgres-17/src/backend/optimizer/util/inherit.c#L166-L170)), because for each child "we must obtain an appropriate lock, because this will be the first use of those relations in the parse/rewrite/plan pipeline" ([inherit.c#L113-L119](../../../../raw/postgres-17/src/backend/optimizer/util/inherit.c#L113-L119)). Constraint exclusion runs only afterward, in `set_append_rel_size`, on child rels already built during expansion, and merely marks an excluded child as a dummy (no scan) with `set_dummy_rel_pathlist` ([allpaths.c#L1027-L1035](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L1027-L1035)). The lock was already taken, so constraint exclusion removes work, not locks.

**Run-time pruning does not reduce locks either.** Every partition that survived *plan-time* pruning stays in the finished plan's range table, and for a cached/prepared plan `AcquireExecutorLocks` locks each `RTE_RELATION` in `plannedstmt->rtable` before the plan runs ([plancache.c#AcquireExecutorLocks](../../../../raw/postgres-17/src/backend/utils/cache/plancache.c#L1805-L1823)); run-time pruning only skips subplan initialization and scanning afterward. So a prepared statement or a parameterized nested loop that prunes 99 of 100 partitions at run time still holds locks on all 100. This holds even though v17 (unlike v12) also applies run-time pruning to `UPDATE`/`DELETE` `ModifyTable` plans (see [v14: run-time pruning for UPDATE/DELETE, and DETACH PARTITION CONCURRENTLY](#v14-run-time-pruning-for-updatedelete-and-detach-partition-concurrently)).

**Partitionwise join and aggregate do not change the lock set.** They are chosen during path generation on child rels that `add_other_rels_to_query` already expanded and locked; both joined tables' partitions are locked regardless of whether the join runs partition-by-partition.

**Write path: tuple routing locks lazily.** `ExecInitPartitionInfo` opens each leaf partition with `RowExclusiveLock` only the first time a row routes to it ([execPartition.c#ExecInitPartitionInfo](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L515-L517)), and the routing state itself is built lazily — "the actual ResultRelInfo for a partition is only allocated when the partition is found for the first time" ([execPartition.c#ExecSetupPartitionTupleRouting](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L201-L215)). For routed `INSERT`/`COPY`, a statement that touches only a few partitions therefore opens and locks only those leaf partitions. `UPDATE`/`DELETE` scan locks are determined by the scan plan; when an `UPDATE` moves a row across partitions, v17 implements the movement as a `DELETE` on the old partition plus a routed `INSERT` back through the root into the new one, so the moved row writes both partitions ([nodeModifyTable.c#ExecCrossPartitionUpdate](../../../../raw/postgres-17/src/backend/executor/nodeModifyTable.c#L1744-L1801)).

### Why scan-eliminating optimizations gain most under slow random I/O

v17's cost model prices a random page read at 4× a sequential one — `DEFAULT_RANDOM_PAGE_COST 4.0` versus `DEFAULT_SEQ_PAGE_COST 1.0` ([cost.h#L22-L25](../../../../raw/postgres-17/src/include/optimizer/cost.h#L22-L25)) — loaded into the `random_page_cost` / `seq_page_cost` variables the cost functions read ([costsize.c#L119-L120](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L119-L120)). The docs give 4.0 as the default and explain it is used "because the majority of random accesses to storage, such as indexed reads, are assumed to be in cache"; they add that if caching is less frequent than that "you can increase random_page_cost to better reflect the true cost of random storage reads", and that storage with "a higher random read cost relative to sequential, like magnetic disks, might also be better modeled with a higher value for random_page_cost" ([config.sgml#guc-random-page-cost](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5859-L5893)). The slower your real random I/O (cold cache, mechanical or high-latency storage), the higher the effective per-page penalty.

Those per-page penalties are exactly what a whole-partition scan pays and what pruning/exclusion avoids:

- An index scan charges `random_page_cost` for each heap page it fetches in the uncorrelated case ([costsize.c#cost_index](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L643-L660), applied as `max_IO_cost = pages_fetched * spc_random_page_cost` at [costsize.c#L730-L731](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L730-L731)).
- A sequential scan charges `seq_page_cost` per page: `disk_run_cost = spc_seq_page_cost * baserel->pages` ([costsize.c#cost_seqscan](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L312-L315)).

Because each partition is its own physical relation with its own heap and indexes, dropping a partition removes that whole relation's page fetches. When those fetches are random and slow, the eliminated cost per pruned partition is proportionally larger, so plan-time pruning, run-time pruning, and constraint exclusion deliver their biggest wall-clock wins precisely on high-latency random storage. Plan-time pruning has the added edge that it also removes the partition's planning and locking work; run-time pruning still plans and locks the partition even though it skips the scan.

### Partitionwise join and aggregate under slow random I/O

Partitionwise join and aggregate shrink each per-partition operation. Whether that turns into avoided *random* I/O depends on how v17 costs the spill each one can incur, and the two differ:

- **Partitionwise join — sequential spill.** A hash join whose inner side overflows `work_mem` "batches" the join, "writing and reading most of the tuples to disk an extra time," and v17 charges that spill at `seq_page_cost` "since the I/O should be nice and sequential" ([costsize.c#initial_cost_hashjoin](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L4139-L4155)). Splitting into per-partition joins that each fit in memory avoids the spill, but the avoided cost is modeled as sequential, not random. So partitionwise join's tie-in to slow random I/O is indirect: smaller working sets, better cache/buffer locality, and less sequential spill — not fewer random reads.
- **Partitionwise aggregate — random-priced spill (v17 change).** Unlike v12, v17 hash aggregation can spill to disk: when the hash table exceeds its memory limit it enters "spill mode" and writes overflow tuples to logical tapes ([nodeAgg.c#spill-mode](../../../../raw/postgres-17/src/backend/executor/nodeAgg.c#L199-L201), [nodeAgg.c#hash_agg_check_limits](../../../../raw/postgres-17/src/backend/executor/nodeAgg.c#L1856-L1873)). That limit is `work_mem × hash_mem_multiplier` ([nodeAgg.c#hash_agg_set_limits](../../../../raw/postgres-17/src/backend/executor/nodeAgg.c#L1802-L1804), [nodeHash.c#get_hash_memory_limit](../../../../raw/postgres-17/src/backend/executor/nodeHash.c#L3592-L3607)). Crucially, `cost_agg` prices the spill's **writes at `random_page_cost`** (and reads at `seq_page_cost`, plus a 2× "HashAgg has ... worse IO behavior than Sort" penalty) ([costsize.c#cost_agg](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L2791-L2807)). A full partitionwise aggregate builds one smaller hash table per partition instead of a single large one, so it can keep each partition's table within `work_mem × hash_mem_multiplier` and avoid the spill entirely — and the write cost it thereby avoids is priced as *random* I/O. On high-latency random storage that avoided spill is a direct win, on top of the usual CPU/memory/cache-locality gains.

Both `work_mem` and `hash_mem_multiplier` are `PGC_USERSET`, so they take effect with session/transaction scope (`SET` / `SET LOCAL`, no restart or reload) ([guc_tables.c#work_mem](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2448), [guc_tables.c#hash_mem_multiplier](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3833-L3841)). Raising them lets a larger hash aggregate stay in memory whether or not the plan is partitionwise; partitionwise aggregate is the structural way to shrink each hash table's input.

## Context Reviewed

- Pinned checkout `raw/postgres-17/` at commit `786db8dcf168bd9df8f55047337525ac19118b1c` (`REL_17_STABLE`, 17.11, `REL_17_11-7-g786db8dcf16`), verified via `git rev-parse HEAD`; repinned from `54eeefaedbee0385529f3edf321bb99e49232aaa` (17.10) on 2026-08-17.
- 2026-08-17 repin review: `31f2acde53d` ("Fix issue with RANGE's DEFAULT partition pruning", back-patched through v14) is the one commit in the `54eeefaed..786db8dcf16` range that changed a claim on this page; it is recorded in the RANGE strategy bullet, the v17 since-v12 subsection, and the summary table, together with its new `partition_prune` regression cases. No pruning-entry-point, partitionwise, routing, locking, or costing claim changed in the range.
- GUCs: `src/backend/utils/misc/guc_tables.c` (the three `enable_*` blocks and `constraint_exclusion` + its enum options; all `PGC_USERSET`), `src/backend/optimizer/path/costsize.c` (compiled defaults), `src/backend/utils/misc/postgresql.conf.sample`, and `doc/src/sgml/config.sgml` GUC blocks.
- Inheritance/constraint exclusion: `src/backend/optimizer/util/plancat.c` (`relation_excluded_by_constraints`, `get_relation_constraints`), and the `doc/src/sgml/ddl.sgml` "Partition Pruning", "Partitioning and Constraint Exclusion", inheritance-caveats, and partitioning-overview sections.
- Partition pruning core: `src/backend/partitioning/partprune.c` — module header, `PartClauseTarget`, `prune_append_rel_partitions`, `get_matching_partitions`, `perform_pruning_base_step` (strategy switch), and the per-strategy `get_matching_hash_bounds` / `get_matching_list_bounds` / `get_matching_range_bounds`; `src/backend/partitioning/partbounds.c` for `compute_partition_hash_value` and `partition_bounds_merge`.
- Plan-time integration: `src/backend/optimizer/util/inherit.c` `expand_partitioned_rtentry` (prune-before-expand, `live_parts`, `try_table_open`); run-time prune-info attach in `src/backend/optimizer/plan/createplan.c` (`Append`/`MergeAppend`).
- Run-time pruning executor path: `src/backend/executor/execPartition.c` (`ExecInitPartitionPruning`, `CreatePartitionPruneState`, `ExecFindMatchingSubPlans`) and `src/backend/executor/nodeAppend.c` (`ExecInitAppend` and the per-scan `ExecFindMatchingSubPlans(..., false)` call sites).
- Partitionwise join: `src/backend/optimizer/util/relnode.c` (`build_joinrel_partition_info`, `have_partkey_equi_join`), `src/backend/optimizer/path/joinrels.c` (`try_partitionwise_join`, `compute_partition_bounds`).
- Partitionwise aggregate: `src/backend/optimizer/plan/planner.c` (`create_grouping_paths`, `create_ordinary_grouping_paths`, `group_by_has_partkey`, `create_partitionwise_grouping_paths`).
- Executor routing/DML: `src/backend/executor/execPartition.c` (`ExecSetupPartitionTupleRouting`, `ExecFindPartition`, `get_partition_for_tuple`, `ExecInitPartitionInfo`), `src/backend/executor/nodeModifyTable.c` (`ExecCrossPartitionUpdate`, row movement), `src/backend/commands/copyfrom.c` (`CIM_MULTI_CONDITIONAL`).
- Since-v12 history: `git log`/`git merge-base --is-ancestor` against the `Stamp HEAD as NNdevel` boundary commits for `c8434d64ce0`, `981643dcdb7`, `86dc90056df`, `1692d0c3a3f`, `71f4c8c6f74`, `475dbd0b718`, `297daa9d435`, `7103ebb7aae`, `3592e0ff98b`, `ec386948948`, `07c36c1333e`, `11f1218ce81`, `27162a64b38`; v14 detach-pending descriptor evidence in `src/backend/partitioning/partdesc.c` and `src/backend/catalog/pg_inherits.c`; regression evidence in `src/test/regress/expected/partition_prune.out`.
- Follow-up (locking): expansion/locking-before-costing order in `src/backend/optimizer/plan/planmain.c` (`query_planner`: `add_other_rels_to_query` before `make_one_rel`); `expand_partitioned_rtentry` prune-then-lock-live-only versus `expand_inherited_rtentry` `find_all_inheritors` lock-all in `src/backend/optimizer/util/inherit.c`; constraint-exclusion timing and the `set_dummy_rel_pathlist` dummy path in `src/backend/optimizer/path/allpaths.c` (`set_append_rel_size`); executor plan locking in `src/backend/utils/cache/plancache.c` (`AcquireExecutorLocks` over `plannedstmt->rtable`); lazy write-path `RowExclusiveLock` in `src/backend/executor/execPartition.c` (`ExecInitPartitionInfo`, `ExecSetupPartitionTupleRouting`) and cross-partition row movement in `src/backend/executor/nodeModifyTable.c` (`ExecCrossPartitionUpdate`).
- Follow-up (random I/O): page-cost defaults in `src/include/optimizer/cost.h` and the `random_page_cost`/`seq_page_cost` variables in `src/backend/optimizer/path/costsize.c`; the `cost_seqscan`, `cost_index`, `initial_cost_hashjoin`, and `cost_agg` cost functions in the same file; `random_page_cost` documentation in `doc/src/sgml/config.sgml`; v17 disk-based hash-aggregation spill in `src/backend/executor/nodeAgg.c` (`hash_agg_check_limits`, spill mode, logical-tape spill) with the `work_mem × hash_mem_multiplier` limit from `get_hash_memory_limit` in `src/backend/executor/nodeHash.c` and the `work_mem`/`hash_mem_multiplier` `PGC_USERSET` GUC definitions in `src/backend/utils/misc/guc_tables.c`.

## Evidence Map

| Claim | Evidence |
|---|---|
| Two partitioning kinds; pruning is declarative-only, constraint exclusion is legacy-inheritance-primary | [ddl.sgml#L4901-L4918](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L4901-L4918), [ddl.sgml#L5035-L5050](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L5035-L5050) |
| Four GUCs, all `PGC_USERSET` (session/transaction scope); defaults | [guc_tables.c#L923-L974](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L923-L974), [guc_tables.c#L4797-L4807](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4797-L4807), [costsize.c#L148-L152](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L148-L152) |
| Constraint exclusion modes, const-FALSE, partition/on handling; plan-time only | [plancat.c#L1602-L1655](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c#L1602-L1655), [ddl.sgml#L5042-L5050](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L5042-L5050) |
| Plan-time pruning prunes before locking; only live parts locked via `try_table_open` | [inherit.c#L352-L438](../../../../raw/postgres-17/src/backend/optimizer/util/inherit.c#L352-L438), [partprune.c#L749-L804](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L749-L804) |
| Run-time pruning attached to Append/MergeAppend; two executor phases | [createplan.c#L1382-L1406](../../../../raw/postgres-17/src/backend/optimizer/plan/createplan.c#L1382-L1406), [nodeAppend.c#L137-L164](../../../../raw/postgres-17/src/backend/executor/nodeAppend.c#L137-L164), [execPartition.c#L1806-L1852](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1806-L1852) |
| Per-strategy pruning (HASH all-keys/equality; LIST incl. `<>`; RANGE prefix + DEFAULT) | [partprune.c#L3516-L3543](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L3516-L3543), [partprune.c#L2663-L2717](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L2663-L2717), [partprune.c#L2739-L2835](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L2739-L2835), [partprune.c#L2951-L3005](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L2951-L3005) |
| Partitionwise join gate; all-key equi-join; merged bounds | [relnode.c#L2017-L2080](../../../../raw/postgres-17/src/backend/optimizer/util/relnode.c#L2017-L2080), [relnode.c#L2090-L2222](../../../../raw/postgres-17/src/backend/optimizer/util/relnode.c#L2090-L2222), [joinrels.c#L1790-L1849](../../../../raw/postgres-17/src/backend/optimizer/path/joinrels.c#L1790-L1849) |
| Partitionwise aggregate FULL/PARTIAL/NONE; needs partitioned input + all keys in GROUP BY | [planner.c#L3904-L3917](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L3904-L3917), [planner.c#L4081-L4147](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L4081-L4147), [planner.c#L8113-L8186](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L8113-L8186) |
| Tuple routing, per-strategy leaf lookup, DEFAULT fallback, lazy `RowExclusiveLock` | [execPartition.c#L262-L316](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L262-L316), [execPartition.c#L1396-L1600](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1396-L1600), [execPartition.c#L515-L517](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L515-L517) |
| Cross-partition UPDATE = DELETE + re-route INSERT; COPY `CIM_MULTI_CONDITIONAL` | [nodeModifyTable.c#L2049-L2114](../../../../raw/postgres-17/src/backend/executor/nodeModifyTable.c#L2049-L2114), [copyfrom.c#L896-L918](../../../../raw/postgres-17/src/backend/commands/copyfrom.c#L896-L918) |
| v13 advanced PWJ (`partition_bounds_merge`) | [joinrels.c#L1790-L1849](../../../../raw/postgres-17/src/backend/optimizer/path/joinrels.c#L1790-L1849), [partbounds.c#L1118](../../../../raw/postgres-17/src/backend/partitioning/partbounds.c#L1118); commit `c8434d64ce0` |
| v14 run-time pruning for UPDATE/DELETE; doc caveat removed | [ddl.sgml#L4973-L4998](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml#L4973-L4998), [partition_prune.out#L2952-L2978](../../../../raw/postgres-17/src/test/regress/expected/partition_prune.out#L2952-L2978); commits `86dc90056df`, `1692d0c3a3f` |
| v14 `DETACH PARTITION CONCURRENTLY` uses detach-pending partition-descriptor filtering, not `try_table_open` | [partdesc.c#L53-L109](../../../../raw/postgres-17/src/backend/partitioning/partdesc.c#L53-L109), [partdesc.c#L156-L167](../../../../raw/postgres-17/src/backend/partitioning/partdesc.c#L156-L167), [pg_inherits.c#L70-L79](../../../../raw/postgres-17/src/backend/catalog/pg_inherits.c#L70-L79), [pg_inherits.c#L123-L176](../../../../raw/postgres-17/src/backend/catalog/pg_inherits.c#L123-L176); commit `71f4c8c6f74` |
| v15 `live_parts`; v16 routing cache; v17 boolcol IS [NOT] UNKNOWN | [inherit.c#L352-L358](../../../../raw/postgres-17/src/backend/optimizer/util/inherit.c#L352-L358), [execPartition.c#L1456-L1547](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L1456-L1547), [partprune.c#L3682-L3713](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L3682-L3713); commits `475dbd0b718`, `3592e0ff98b`, `07c36c1333e` |
| 17.11: RANGE "no values to compare" marks all bound offsets and asserts `>= -1`, so an `IS NOT NULL` step under an intersect combine step no longer prunes the `DEFAULT` partition | [partprune.c#L2984-L2998](../../../../raw/postgres-17/src/backend/partitioning/partprune.c#L2984-L2998), [partition_prune.sql#L102-L120](../../../../raw/postgres-17/src/test/regress/sql/partition_prune.sql#L102-L120), [partition_prune.out#L674-L719](../../../../raw/postgres-17/src/test/regress/expected/partition_prune.out#L674-L719); commit `31f2acde53d` |
| Follow-up: expansion/locking runs before costing (`add_other_rels_to_query` before `make_one_rel`) | [planmain.c#L260-L280](../../../../raw/postgres-17/src/backend/optimizer/plan/planmain.c#L260-L280) |
| Follow-up: plan-time pruning locks only survivors; inheritance `find_all_inheritors` locks all; CE marks dummy afterward | [inherit.c#L352-L398](../../../../raw/postgres-17/src/backend/optimizer/util/inherit.c#L352-L398), [inherit.c#L113-L170](../../../../raw/postgres-17/src/backend/optimizer/util/inherit.c#L113-L170), [allpaths.c#L1027-L1035](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c#L1027-L1035) |
| Follow-up: run-time pruning keeps locks (`AcquireExecutorLocks` locks each `RTE_RELATION`) | [plancache.c#L1805-L1823](../../../../raw/postgres-17/src/backend/utils/cache/plancache.c#L1805-L1823) |
| Follow-up: write path locks leaf partitions lazily; cross-partition UPDATE = DELETE + re-route | [execPartition.c#L201-L215](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L201-L215), [execPartition.c#L515-L517](../../../../raw/postgres-17/src/backend/executor/execPartition.c#L515-L517), [nodeModifyTable.c#L1744-L1801](../../../../raw/postgres-17/src/backend/executor/nodeModifyTable.c#L1744-L1801) |
| Follow-up: `random_page_cost` 4.0 vs `seq_page_cost` 1.0; docs advise raising for slow random storage | [cost.h#L22-L25](../../../../raw/postgres-17/src/include/optimizer/cost.h#L22-L25), [costsize.c#L119-L120](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L119-L120), [config.sgml#L5859-L5893](../../../../raw/postgres-17/doc/src/sgml/config.sgml#L5859-L5893) |
| Follow-up: index-scan heap fetches charged at `random_page_cost`; seq scan at `seq_page_cost` | [costsize.c#L643-L660](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L643-L660), [costsize.c#L730-L731](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L730-L731), [costsize.c#L312-L315](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L312-L315) |
| Follow-up: hash-join batch spill costed at `seq_page_cost` | [costsize.c#L4139-L4155](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L4139-L4155) |
| Follow-up: v17 hash aggregation spills to disk; limit `work_mem × hash_mem_multiplier`; spill writes at `random_page_cost` | [nodeAgg.c#L199-L201](../../../../raw/postgres-17/src/backend/executor/nodeAgg.c#L199-L201), [nodeAgg.c#L1856-L1873](../../../../raw/postgres-17/src/backend/executor/nodeAgg.c#L1856-L1873), [nodeHash.c#L3592-L3607](../../../../raw/postgres-17/src/backend/executor/nodeHash.c#L3592-L3607), [costsize.c#L2791-L2807](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c#L2791-L2807) |
| Follow-up: `work_mem` and `hash_mem_multiplier` are `PGC_USERSET` (session/transaction scope) | [guc_tables.c#L2448](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2448), [guc_tables.c#L3833-L3841](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L3833-L3841) |

## Open Questions

- Since-v12 attribution uses the "Stamp HEAD as NNdevel" boundary commits to identify the introducing **major** version. The exact **minor** release (e.g. which 17.x first shipped `11f1218ce81` / `27162a64b38`) was not traced, and this checkout carries no release tags for a `git tag --contains` cross-check.
- The LIST/RANGE `<>` (not-equal) pruning path exists in v17 (`InvalidStrategy` handling), but its first-introduction version relative to v12 was not pinned down; a v14 step-generation fix (`13838740f61`) touched the `op_is_ne` path, which is a fix, not necessarily the origin.
- The since-v12 survey targeted the core partitioning/pruning/partitionwise files (`partprune.c`, `partbounds.c`, `inherit.c`, `relnode.c`, `joinrels.c`, `planner.c`, `execPartition.c`, `nodeAppend.c`, `createplan.c`); minor per-cycle optimizations outside those files may not be captured.
- Follow-up (locking scope): the "run-time pruning keeps every plan-time-surviving partition locked" claim is anchored to the cached-plan `AcquireExecutorLocks` path; a one-shot simple query instead takes those locks during parse/rewrite/expansion, but the plan-time survivors are still locked before execution either way. Whether any release after v17 defers per-partition locking until after initial run-time pruning was not investigated here (cross-version work is out of scope for this v17 page).
- Follow-up (magnitude): the random-I/O argument is qualitative and cost-model-based (per-page `random_page_cost` vs `seq_page_cost`, and the hash-agg spill write pricing). Actual wall-clock gains depend on cache-hit rates, correlation, `effective_cache_size`, and per-partition sizes that were not benchmarked against this checkout.
- `verified_by_agent: not yet`: this is a fresh draft built from a claim-to-source map, not a second claim-by-claim re-verification pass.

## Source References

- [guc_tables.c](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c) — the four partitioning GUCs and `constraint_exclusion` enum, plus `work_mem` / `hash_mem_multiplier` (all `PGC_USERSET`).
- [costsize.c](../../../../raw/postgres-17/src/backend/optimizer/path/costsize.c) — compiled-in GUC defaults, the `random_page_cost` / `seq_page_cost` variables, and the `cost_seqscan` / `cost_index` / `initial_cost_hashjoin` / `cost_agg` cost functions.
- [cost.h](../../../../raw/postgres-17/src/include/optimizer/cost.h) — `DEFAULT_SEQ_PAGE_COST` / `DEFAULT_RANDOM_PAGE_COST` (1.0 / 4.0).
- [postgresql.conf.sample](../../../../raw/postgres-17/src/backend/utils/misc/postgresql.conf.sample) — sample defaults.
- [planmain.c](../../../../raw/postgres-17/src/backend/optimizer/plan/planmain.c) — `query_planner`: `add_other_rels_to_query` (expansion/locking) before `make_one_rel` (costing).
- [plancat.c](../../../../raw/postgres-17/src/backend/optimizer/util/plancat.c) — `relation_excluded_by_constraints`, `get_relation_constraints`.
- [allpaths.c](../../../../raw/postgres-17/src/backend/optimizer/path/allpaths.c) — `set_append_rel_size` constraint-exclusion timing and the `set_dummy_rel_pathlist` dummy path.
- [plancache.c](../../../../raw/postgres-17/src/backend/utils/cache/plancache.c) — `AcquireExecutorLocks` locking every `RTE_RELATION` in `plannedstmt->rtable`.
- [partprune.c](../../../../raw/postgres-17/src/backend/partitioning/partprune.c) — pruning module, `prune_append_rel_partitions`, `perform_pruning_base_step`, per-strategy bound matching.
- [partbounds.c](../../../../raw/postgres-17/src/backend/partitioning/partbounds.c) — `compute_partition_hash_value`, `partition_bounds_merge`.
- [partdesc.c](../../../../raw/postgres-17/src/backend/partitioning/partdesc.c) — partition descriptor construction and cached descriptors that omit concurrently detached partitions.
- [pg_inherits.c](../../../../raw/postgres-17/src/backend/catalog/pg_inherits.c) — `find_inheritance_children_extended` and `inhdetachpending` omission.
- [inherit.c](../../../../raw/postgres-17/src/backend/optimizer/util/inherit.c) — `expand_partitioned_rtentry` plan-time pruning, `live_parts`, `try_table_open`; `expand_inherited_rtentry` + `find_all_inheritors` lock-all-members.
- [createplan.c](../../../../raw/postgres-17/src/backend/optimizer/plan/createplan.c) — run-time prune-info attach for `Append`/`MergeAppend`.
- [nodeAppend.c](../../../../raw/postgres-17/src/backend/executor/nodeAppend.c) — `ExecInitAppend`, per-scan pruning.
- [execPartition.c](../../../../raw/postgres-17/src/backend/executor/execPartition.c) — run-time pruning, tuple routing, `get_partition_for_tuple`, `ExecInitPartitionInfo`.
- [relnode.c](../../../../raw/postgres-17/src/backend/optimizer/util/relnode.c) — `build_joinrel_partition_info`, `have_partkey_equi_join`.
- [joinrels.c](../../../../raw/postgres-17/src/backend/optimizer/path/joinrels.c) — `try_partitionwise_join`, `compute_partition_bounds`.
- [planner.c](../../../../raw/postgres-17/src/backend/optimizer/plan/planner.c) — partitionwise aggregate paths.
- [nodeModifyTable.c](../../../../raw/postgres-17/src/backend/executor/nodeModifyTable.c) — `ExecCrossPartitionUpdate` cross-partition UPDATE row movement.
- [nodeAgg.c](../../../../raw/postgres-17/src/backend/executor/nodeAgg.c) — disk-based hash-aggregation spill (`hash_agg_check_limits`, spill mode, `hash_agg_set_limits`).
- [nodeHash.c](../../../../raw/postgres-17/src/backend/executor/nodeHash.c) — `get_hash_memory_limit` (`work_mem × hash_mem_multiplier`).
- [copyfrom.c](../../../../raw/postgres-17/src/backend/commands/copyfrom.c) — per-partition COPY multi-insert.
- [ddl.sgml](../../../../raw/postgres-17/doc/src/sgml/ddl.sgml) — partitioning, pruning, constraint exclusion, inheritance caveats.
- [config.sgml](../../../../raw/postgres-17/doc/src/sgml/config.sgml) — the four GUC documentation blocks and `random_page_cost`.
- [partition_prune.out](../../../../raw/postgres-17/src/test/regress/expected/partition_prune.out) — run-time pruning inside an `UPDATE` plan; the 17.11 RANGE `DEFAULT`-partition cases.
- [partition_prune.sql](../../../../raw/postgres-17/src/test/regress/sql/partition_prune.sql) — the 17.11 range-`IN`-clause pruning tests added by `31f2acde53d`.

## Navigation

- [PostgreSQL 17 index](../../index.md)
- [PostgreSQL 17 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- Sibling: [Table Partitioning Optimizations and Configuration During Query Planning and Execution in PostgreSQL 12 (unverified)](../../../v12/questions/query-planning/partitioning-planning-execution-optimizations.md)
- [Wiki index](../../../index.md)
- [Versions](../../../versions.md)
