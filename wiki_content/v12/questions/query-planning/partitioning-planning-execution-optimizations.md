---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: gpt-5-codex 2026-07-09T12:48:19Z
---

# Table Partitioning Optimizations and Configuration During Query Planning and Execution in PostgreSQL 12 (unverified)

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
- [Locking reduction and random-I/O sensitivity per optimization](#locking-reduction-and-random-io-sensitivity-per-optimization)
  - [Only plan-time pruning removes read locks](#only-plan-time-pruning-removes-read-locks)
  - [Why scan-eliminating optimizations gain most under slow random I/O](#why-scan-eliminating-optimizations-gain-most-under-slow-random-io)
  - [Partitionwise join and aggregate: CPU, memory, and locality, not random I/O](#partitionwise-join-and-aggregate-cpu-memory-and-locality-not-random-io)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

During query planning or execution, what are the optimizations and configurations per type of table partitioning currently implemented?

Follow-up: Add an extra analysis on how each optimization will reduce locking, and how each will have big gains if random I/O has higher latency.

> Prompt note: filed as an approved grammar-corrected restatement of the original
> question ("during query planning or execution what are the current
> optimizations and configuration per type of table parititioning currently
> implemented?"), per the repository's prompt-hygiene rule. The follow-up above is
> likewise an approved grammar-corrected restatement (original: "add an extra
> analysis on how each optimization will reduce locking and it will have big gains
> if the random i/o has higher latency.").

## Answer

PostgreSQL 12 has **two kinds of table partitioning**, and the optimizations available differ sharply between them:

- **Inheritance-based (legacy) partitioning** — plain table inheritance (`INHERITS`) plus `CHECK` constraints, wired up by hand. Its one planner optimization is **constraint exclusion**; routing rows to the right child table is your job (a trigger or rule).
- **Declarative partitioning** (`PARTITION BY` with the RANGE / LIST / HASH strategies) — the engine knows the partition bounds, so it adds **partition pruning** (plan-time and run-time), **partitionwise join**, **partitionwise aggregate**, and automatic **tuple routing** with per-partition COPY batching and cross-partition UPDATE row movement.

The documentation states this split directly: partition pruning "improves performance for declaratively partitioned tables" ([ddl.sgml#L4479-L4497](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4479-L4497)), while constraint exclusion "is primarily used for partitioning implemented using the legacy inheritance method" and uses `CHECK` constraints rather than the "partition bounds, which exist only in the case of declarative partitioning" ([ddl.sgml#L4621-L4636](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4621-L4636)).

The two sections below answer per partitioning type. Internally, only a declaratively partitioned table carries a `PartitionScheme` (strategy, number of key positions, key type info — but not the specific bounds) plus per-relation bounds, key expressions, and child arrays on its `RelOptInfo` ([pathnodes.h#PartitionSchemeData](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L389-L405), [pathnodes.h#RelOptInfo-partition-fields](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L707-L722)); those fields are what every declarative-only optimization reads, and their absence is why inheritance tables get none of them.

### Configuration at a glance

Four GUCs govern these optimizations. All four are defined with context `PGC_USERSET`, so each has **session/transaction apply scope**: change it with `SET` for the current session or `SET LOCAL` for the current transaction, with no restart or reload for that session ([guc.c#partitioning-GUCs](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1003-L1054), [guc.c#constraint_exclusion](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4243-L4252), [ref/set.sgml#SET-scope](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L33-L58)). A server-wide default in `postgresql.conf` follows normal config-file processing: the file is reread on SIGHUP / `pg_ctl reload` / `pg_reload_conf()`, but these four do not require a server restart ([config.sgml#configuration-file-reload](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L169-L183)). Tuple routing and COPY batching have no GUC — the executor always performs them for a declaratively partitioned target.

| GUC | Partitioning type | Default | Phase | Definition |
|---|---|---|---|---|
| `constraint_exclusion` | legacy inheritance (also declarative `CHECK`s) | `partition` | planning | [guc.c:4243-4252](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4243-L4252) |
| `enable_partition_pruning` | declarative | `on` | planning + execution | [guc.c:1044-1054](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1044-L1054) |
| `enable_partitionwise_join` | declarative | `off` | planning | [guc.c:1003-1012](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1003-L1012) |
| `enable_partitionwise_aggregate` | declarative | `off` | planning | [guc.c:1013-1022](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1013-L1022) |

The boolean variables and their compiled-in defaults live in `costsize.c` ([costsize.c:137-140](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L137-L140)); the same defaults appear in `postgresql.conf.sample` ([postgresql.conf.sample#partitioning-defaults](../../../../raw/postgres-12/src/backend/utils/misc/postgresql.conf.sample#L361-L402)).

## Inheritance-based (legacy) partitioning

Legacy partitioning is built from ordinary table inheritance: a "master" table with no data, "child" tables created with `INHERITS (master)`, non-overlapping `CHECK` constraints on the children, and a trigger/rule to route inserts ([ddl.sgml#ddl-partitioning-implementation-inheritance](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4056-L4057), setup steps at [ddl.sgml#L4108-L4149](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4108-L4149)). The engine has no partition metadata for such a tree, so its only automatic query optimization is constraint exclusion.

### Constraint exclusion

Constraint exclusion is the plan-time technique that proves a child table cannot match a query by comparing the query's restrictions against that table's constraints, and drops it from the plan. The GUC is an enum with three modes ([cost.h#ConstraintExclusionType](../../../../raw/postgres-12/src/include/optimizer/cost.h#L34-L39)):

- `off` — never use it.
- `on` — apply to all relations.
- `partition` (the default) — apply only to appendrel children / inheritance members.

The core logic is in `relation_excluded_by_constraints`. In the default `partition` mode it processes only `RELOPT_OTHER_MEMBER_REL` (appendrel-member) rels or inherited target rels — exactly the inheritance-child case — and returns false for plain base relations ([plancat.c#L1435-L1474](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1435-L1474)). It then fetches the child's `CHECK` and `NOT NULL` constraints via `get_relation_constraints` and asks `predicate_refuted_by` whether they contradict the query quals ([plancat.c#get_relation_constraints](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1159-L1287)). The planner runs this for a base relation in `set_rel_size` and for each appendrel child in `set_append_rel_size`, replacing an excluded relation with a dummy (empty) path ([allpaths.c#set_rel_size](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L360-L384), [allpaths.c#set_append_rel_size](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L1031-L1039)).

Configuration and caveats (from the docs):

- The default and recommended setting is `partition`; `on` adds planning overhead on every query for little benefit, and `off` disables it ([config.sgml#guc-constraint-exclusion](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5158-L5217)).
- It is **plan-time only** — there is no execution-time equivalent — needs the `WHERE` clause to contain constants (or external parameters), and examines every child, so it "will work well with up to perhaps a hundred child tables" and no more ([ddl.sgml#L4638-L4703](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4638-L4703)). This child-count ceiling is the main scalability limit of legacy partitioning.

`constraint_exclusion` is `PGC_USERSET` (session/transaction scope; `SET`/`SET LOCAL`, no restart or reload) ([guc.c#L4243-L4252](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4243-L4252)).

### Tuple routing is manual (triggers/rules)

There is no automatic tuple routing for inheritance. To send a row inserted into the master to the correct child, you attach a trigger (or rule) that runs the `INSERT` against the right child table ([ddl.sgml#L4215-L4250](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4215-L4250)). The documentation warns that such "triggers may be complicated to write, and will be much slower than the tuple routing performed internally by declarative partitioning" ([ddl.sgml#L4462-L4464](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4462-L4464)).

### What inheritance partitioning does not get

Because an inheritance tree has no `PartitionScheme` or partition bounds, none of the declarative-only optimizations apply to it:

- **No partition pruning** (plan-time or run-time): pruning is driven by partition bounds that "exist only in the case of declarative partitioning" ([ddl.sgml#L4628-L4636](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4628-L4636)).
- **No partitionwise join or aggregate**: both first require `IS_PARTITIONED_REL` inputs carrying a `part_scheme`, which inheritance parents lack, so `build_joinrel_partition_info` bails immediately ([relnode.c#L1612-L1698](../../../../raw/postgres-12/src/backend/optimizer/util/relnode.c#L1612-L1698)).
- **No internal tuple routing / row movement / COPY batching per partition**: those executor paths operate on the partition descriptor of a declarative table (see the declarative section).

Constraint exclusion is therefore the whole story for planning against legacy partitions, and it is applied only at plan time.

## Declarative partitioning

Declarative partitioning (`PARTITION BY RANGE | LIST | HASH`) gives the engine the partition strategy and bounds ([ddl.sgml#L3560-L3597](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L3560-L3597)), which unlocks the optimizations below.

### Partition pruning during planning and execution

Partition pruning compares query clauses against partition bounds to decide which partitions can be skipped. The module turns matching clauses into "pruning steps": a *base* step tests partition-key columns or expressions; a *combine* step joins earlier results with a Boolean AND/OR ([partprune.c#L1-L35](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L1-L35)). Steps are generated for one of three targets ([partprune.c#PartClauseTarget](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L91-L96)):

- `PARTTARGET_PLANNER` — clauses usable at plan time (constants).
- `PARTTARGET_INITIAL` — usable at executor startup (any allowable clause except `PARAM_EXEC` Params).
- `PARTTARGET_EXEC` — usable per scan (including `PARAM_EXEC` Params).

**Plan-time pruning.** During expansion of a partitioned RTE, the planner prunes *before* it builds child relations: `expand_partitioned_rtentry` calls `prune_append_rel_partitions`, and only the surviving ("live") partitions get child RTEs and `RelOptInfo`s ([inherit.c#L320-L355](../../../../raw/postgres-12/src/backend/optimizer/util/inherit.c#L320-L355)). So pruned partitions are never locked, path-costed, or planned — a key scalability advantage over legacy partitioning. `prune_append_rel_partitions` short-circuits to "all partitions" when `enable_partition_pruning` is off or there are no clauses ([partprune.c#prune_append_rel_partitions](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L662-L716)), then runs the steps in `get_matching_partitions` ([partprune.c#get_matching_partitions](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L728-L769)).

**Run-time pruning.** When a clause compares the partition key to a non-constant but non-volatile expression (a `PREPARE` parameter, a subquery value, or a nested-loop inner parameter), the planner attaches a `PartitionPruneInfo` to the `Append`/`MergeAppend` plan, gated again by `enable_partition_pruning` ([createplan.c#L1216-L1241](../../../../raw/postgres-12/src/backend/optimizer/plan/createplan.c#L1216-L1241) for `Append`, [createplan.c#L1382-L1385](../../../../raw/postgres-12/src/backend/optimizer/plan/createplan.c#L1382-L1385) for `MergeAppend`). The executor then prunes in two phases ([execPartition.c#Run-Time-Pruning](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L1490-L1539)):

1. **Initial pruning** at executor startup for values known then; unneeded subplans are not even initialized. `ExecInitAppend` builds the prune state and calls `ExecFindInitialMatchingSubPlans` ([nodeAppend.c#L125-L194](../../../../raw/postgres-12/src/backend/executor/nodeAppend.c#L125-L194), [execPartition.c#ExecFindInitialMatchingSubPlans](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L1807-L1879)).
2. **Per-scan pruning** for execution parameters that change during the run (for example, the inner side of a parameterized nested loop). `ExecAppend` calls `ExecFindMatchingSubPlans` whenever the valid-subplan set is invalidated, and `ExecReScanAppend` clears that set when a relevant `PARAM_EXEC` changes ([nodeAppend.c#L479-L481](../../../../raw/postgres-12/src/backend/executor/nodeAppend.c#L479-L481), [nodeAppend.c#L348-L354](../../../../raw/postgres-12/src/backend/executor/nodeAppend.c#L348-L354), [execPartition.c#ExecFindMatchingSubPlans](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L1990-L2040)).

The documentation confirms both phases and how to observe them: initial pruning shows as "Subplans Removed" in `EXPLAIN`; per-scan pruning shows up only as `loops`/`(never executed)` in `EXPLAIN ANALYZE` ([ddl.sgml#L4551-L4596](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4551-L4596)). `enable_partition_pruning` controls both the planner's partition elimination and the executor's run-time removal ([config.sgml#guc-enable-partition-pruning](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4558-L4574)).

### How partition pruning differs by strategy

Both plan-time and run-time pruning funnel through `perform_pruning_base_step`, which switches on the partition strategy to a per-strategy bound-matching routine ([partprune.c#L3250-L3277](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L3250-L3277)). The three routines behave differently:

- **HASH** — Pruning is possible only with equality clauses or `IS NULL`, and only when the query constrains **every** partition-key position; otherwise all partitions are kept. It computes the row hash and picks the one partition at `rowHash % greatest_modulus`. `compute_partition_hash_value` ignores NULL key values while forming that hash, and hash partitioning has neither a null-accepting partition nor a `DEFAULT` partition ([partprune.c#get_matching_hash_bounds](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L2389-L2445), [partbounds.c#compute_partition_hash_value](../../../../raw/postgres-12/src/backend/partitioning/partbounds.c#L2738-L2759)).
- **LIST** — Single key position. Supports B-tree comparison strategies (equality and inequalities). `NULL` routes to the null-accepting partition if one exists, else the `DEFAULT` partition ([partprune.c#get_matching_list_bounds](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L2467-L2647), null handling at [L2486-L2498](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L2486-L2498)).
- **RANGE** — Supports multi-column key prefixes and B-tree comparisons/ranges. There is no null-accepting range partition, so an `IS NULL` clause (or no usable datums) can only match the `DEFAULT` partition; a partial-prefix query also has to keep the `DEFAULT` partition ([partprune.c#get_matching_range_bounds](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L2678-L2769)).

### Constraint exclusion on declarative tables

Constraint exclusion (see the inheritance section for the mechanism) can *also* apply to declarative tables, because you may add ordinary `CHECK` constraints to them on top of their internal partition bounds ([ddl.sgml#L4638-L4645](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4638-L4645)). Two nuances in `relation_excluded_by_constraints` matter here ([plancat.c#L1435-L1474](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1435-L1474)):

- In the default `partition` mode, a declarative partition's own internal partition constraint is deliberately **not** re-checked, because "partition pruning was already applied."
- In `on` mode, a directly named partition base relation additionally has its internal partition constraint pulled into the constraint set (`include_partition`).

So on a declarative table, partition pruning is the primary tool; constraint exclusion is a plan-time supplement that only helps if you defined extra `CHECK` constraints or run in `on` mode.

### Partitionwise join

When enabled, partitionwise join turns a join between two identically partitioned tables into a set of smaller joins between matching partitions. It is **off by default** because it increases planning CPU and memory ([guc.c#L1003-L1012](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1003-L1012), [config.sgml#guc-enable-partitionwise-join](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4576-L4594)).

The applicability test lives in `build_joinrel_partition_info`, which returns immediately if the GUC is off and otherwise requires that both inputs are partitioned with `consider_partitionwise_join`, share the **same** `PartitionScheme`, have an equi-join on the partition keys (`have_partkey_equi_join`), and have exactly matching bounds — same partition count and `partition_bounds_equal` ([relnode.c#build_joinrel_partition_info](../../../../raw/postgres-12/src/backend/optimizer/util/relnode.c#L1612-L1698)). The equi-join check requires a usable equality clause for every partition key ([joinrels.c#have_partkey_equi_join](../../../../raw/postgres-12/src/backend/optimizer/path/joinrels.c#L1563-L1674)). Only when the joinrel is thereby marked partitioned does `try_partitionwise_join` build and cost the child-partition joins pairwise ([joinrels.c#try_partitionwise_join](../../../../raw/postgres-12/src/backend/optimizer/path/joinrels.c#L1336-L1365)). The documented requirement matches the code: "the join conditions include all the partition keys, which must be of the same data type and have exactly matching sets of child partitions" ([config.sgml#L4576-L4594](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4576-L4594)).

### Partitionwise aggregate and grouping

Partitionwise aggregation performs grouping/aggregation per partition, then appends the results. It is **off by default** for the same planning-cost reason ([guc.c#L1013-L1022](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1013-L1022), [config.sgml#guc-enable-partitionwise-aggregate](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4596-L4614)).

`create_grouping_paths` marks the query as a candidate for **full** partitionwise aggregation only when `enable_partitionwise_aggregate` is set and there are no grouping sets ([planner.c#L3886-L3889](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L3886-L3889)). `create_ordinary_grouping_paths` then picks the concrete strategy on a partitioned input ([planner.c#L4066-L4086](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L4066-L4086)):

- **FULL** partitionwise aggregation if the `GROUP BY` clause contains all partition-key columns or expressions, verified by `group_by_has_partkey` ([planner.c#group_by_has_partkey](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L7361-L7405)). Each partition is aggregated independently and the results appended.
- **PARTIAL** partitionwise aggregation otherwise (when partial aggregation is possible at all): each partition is partially aggregated, then a finalize step combines them. This matches the documented behavior that "if the `GROUP BY` clause does not include the partition keys, only partial aggregation can be performed on a per-partition basis, and finalization must be performed later" ([config.sgml#L4596-L4614](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4596-L4614)).

The three states are the `PartitionwiseAggregateType` enum (`NONE`/`FULL`/`PARTIAL`) ([pathnodes.h#PartitionwiseAggregateType](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L2411-L2416)), and the per-partition paths are built by `create_partitionwise_grouping_paths` ([planner.c#create_partitionwise_grouping_paths](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L7205-L7353)).

### Executor tuple routing, row movement, and COPY batching

Writing into a declaratively partitioned table needs no GUC; the executor always routes each row to the correct leaf partition. `ExecSetupPartitionTupleRouting` builds the routing state lazily — each partition's `ResultRelInfo` is created only the first time a row lands there, which keeps single-row `INSERT` fast ([execPartition.c#ExecSetupPartitionTupleRouting](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L197-L235)). `ExecFindPartition` descends the partition hierarchy to find the leaf for a tuple ([execPartition.c#ExecFindPartition](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L251-L350)), calling the per-strategy `get_partition_for_tuple`:

- **HASH** — `boundinfo->indexes[rowHash % greatest_modulus]`, after computing a hash value that ignores NULL key values.
- **LIST** — a null key routes to `null_index` (if the table accepts nulls); otherwise a binary search on the list bounds.
- **RANGE** — any null key position routes to the `DEFAULT` partition (ranges never accept null); otherwise a binary search selects the containing range. If no partition matches, the row falls to `default_index`, and a still-unmatched row raises "no partition of relation ... found for row" ([execPartition.c#get_partition_for_tuple](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L1235-L1333)).

Two further executor behaviors are relevant:

- **Cross-partition UPDATE (row movement).** If an `UPDATE` changes the partition key so the row no longer satisfies its partition's constraint, v12 moves it by performing a `DELETE` on the old partition and an `INSERT` (through tuple routing) into the new one. `ON CONFLICT DO UPDATE` that would move partitions is rejected, and an `UPDATE` run directly on a leaf partition (no routing set up) raises the constraint-violation error ([nodeModifyTable.c#ExecUpdate-row-movement](../../../../raw/postgres-12/src/backend/executor/nodeModifyTable.c#L1139-L1208)).
- **Per-partition COPY batching.** `COPY FROM` into a partitioned table uses the `CIM_MULTI_CONDITIONAL` insert method so it can bulk/multi-insert into each leaf partition, disabling batching only for a partition that is a foreign table or has BEFORE/INSTEAD-OF row triggers ([copy.c#L2950-L2966](../../../../raw/postgres-12/src/backend/commands/copy.c#L2950-L2966), [copy.c#L3086-L3099](../../../../raw/postgres-12/src/backend/commands/copy.c#L3086-L3099)).

### What declarative partitioning does not optimize

- **Execution-time pruning is limited to `Append` and `MergeAppend`.** The documentation states it "is not yet implemented for the `ModifyTable` node type" in v12 ([ddl.sgml#L4603-L4611](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4603-L4611)). So an `UPDATE`/`DELETE` with run-time parameters does not benefit from execution-time pruning the way a `SELECT` does.
- **Partitionwise join/aggregate require exactly matching partition bounds.** Tables partitioned the same way but with different bounds do not qualify ([relnode.c#L1655-L1668](../../../../raw/postgres-12/src/backend/optimizer/util/relnode.c#L1655-L1668)).
- **Hash pruning needs all key positions** and only equality/`IS NULL`; a range or partial-key predicate cannot prune a hash-partitioned table ([partprune.c#L2406-L2436](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L2406-L2436)).

### Per-strategy summary

| Aspect | RANGE | LIST | HASH |
|---|---|---|---|
| Pruning clauses used | equality + range/inequality (prefix of keys) | equality + inequality | equality / `IS NULL` only, **all** keys required |
| NULL handling in pruning/routing | `DEFAULT` only (no null partition) | null partition, else `DEFAULT` | NULL keys ignored by the hash computation; no null/`DEFAULT` partition |
| `DEFAULT` partition | yes | yes | no |
| Plan-time + run-time pruning | yes | yes | yes |
| Constraint exclusion applies | via extra `CHECK` (or `constraint_exclusion=on`) | same | same |
| Partitionwise join/aggregate | if schemes + bounds match | same | same |
| Tuple routing | range bsearch | list bsearch / null_index | `hash % modulus` |

Per-strategy pruning: [partprune.c#L3250-L3277](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L3250-L3277). Per-strategy routing: [execPartition.c#L1235-L1333](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L1235-L1333).

## Locking reduction and random-I/O sensitivity per optimization

Short answer: **only plan-time partition pruning actually reduces the locks a read query takes**, and on the write path lazy tuple routing locks only the partitions that receive rows. Constraint exclusion, run-time pruning, and partitionwise join/aggregate keep the same lock set — they cut I/O and CPU, not locks. Separately, the *scan-eliminating* optimizations (plan-time and run-time pruning, plus constraint exclusion) gain the most when random I/O is slow, because the whole-partition heap and index reads they avoid are priced at `random_page_cost`, which v12 sets to 4× `seq_page_cost` and the docs say to raise further on high-latency storage. Partitionwise join and aggregate gain from cutting CPU, memory, and cache misses rather than from avoiding random reads directly.

| Optimization | Reduces locks? | Gain when random I/O latency is high |
|---|---|---|
| Plan-time partition pruning | **Yes** — pruned partitions are never opened or locked | **Large** — avoids each pruned partition's random index/heap fetches |
| Run-time partition pruning | No — all plan-time-surviving partitions are locked | **Large** — skips scanning partitions at execution |
| Constraint exclusion | No — children are already locked before it runs | Moderate — drops an excluded partition's scan, but only with a constant qual + `CHECK` |
| Partitionwise join | No — both sides' partitions stay locked | Indirect — smaller per-join footprint; spills are modeled as sequential |
| Partitionwise aggregate | No | Indirect — v12 hash aggregation is in-memory; benefit is CPU/memory/locality |
| Tuple routing (write path) | Routed `INSERT`/`COPY` opens leaf partitions lazily; `UPDATE`/`DELETE` scan locks are separate | n/a (write path) |

### Only plan-time pruning removes read locks

The planner expands a partitioned or inherited parent into child relations in `add_other_rels_to_query`, which runs *before* `make_one_rel` costs anything ([planmain.c#L258-L271](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L258-L271)). Locking happens during that expansion, and the two partitioning kinds differ:

- **Declarative, plan-time pruning.** `expand_partitioned_rtentry` calls `prune_append_rel_partitions` first and records the survivors in `live_parts` ([inherit.c#L324-L335](../../../../raw/postgres-12/src/backend/optimizer/util/inherit.c#L324-L335)). It then loops over `live_parts` only, and `table_open(childOID, lockmode)` — the point at which a partition's lock is taken — is inside that loop ([inherit.c#L351-L361](../../../../raw/postgres-12/src/backend/optimizer/util/inherit.c#L351-L361)). A pruned partition is therefore never opened and never locked. Fewer locks means less lock-manager traffic and fewer objects with which later DDL (which needs a conflicting lock) can collide.
- **Inheritance + constraint exclusion.** `expand_inherited_rtentry` locks *every* member up front via `find_all_inheritors(parentOID, lockmode, ...)` ([inherit.c#L156-L157](../../../../raw/postgres-12/src/backend/optimizer/util/inherit.c#L156-L157)), because each child "will be the first use of those relations in the parse/rewrite/plan pipeline" ([inherit.c#L106-L115](../../../../raw/postgres-12/src/backend/optimizer/util/inherit.c#L106-L115)). Constraint exclusion runs only afterward, in `set_append_rel_size`, on child rels that "were already created during `add_other_rels_to_query`," and merely marks an excluded child as a dummy (no scan) ([allpaths.c#L1013-L1039](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L1013-L1039)). The lock was already taken, so constraint exclusion removes work, not locks.

**Run-time pruning does not reduce locks either.** Every partition that survived *plan-time* pruning stays in the finished plan's range table, and `AcquireExecutorLocks` locks each `RTE_RELATION` in `plannedstmt->rtable` before the plan runs ([plancache.c#L1585-L1602](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1585-L1602)); run-time pruning only skips subplan initialization and scanning afterward. So a prepared statement or a parameterized nested loop that prunes 99 of 100 partitions at run time still holds locks on all 100.

**Partitionwise join and aggregate do not change the lock set.** They are chosen during path generation on child rels that `add_other_rels_to_query` already expanded and locked; both joined tables' partitions are locked regardless of whether the join runs partition-by-partition.

**Write path: tuple routing locks lazily.** `ExecInitPartitionInfo` opens each leaf partition with `RowExclusiveLock` only the first time a row routes to it ([execPartition.c#L517-L519](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L517-L519)), and the routing state itself is built lazily ([execPartition.c#L197-L235](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L197-L235)). For routed `INSERT`/`COPY`, a statement that touches only a few partitions therefore opens and locks only those leaf partitions through the routing path. `UPDATE`/`DELETE` scan locks are determined by the scan plan; when an `UPDATE` moves a row across partitions, v12 implements the movement as a `DELETE` on the old partition plus a routed `INSERT` into the new one, so the moved row writes both partitions ([nodeModifyTable.c#L1139-L1208](../../../../raw/postgres-12/src/backend/executor/nodeModifyTable.c#L1139-L1208)).

### Why scan-eliminating optimizations gain most under slow random I/O

v12's cost model prices a random page read at 4× a sequential one — `random_page_cost = 4.0` versus `seq_page_cost = 1.0` ([cost.h#L23-L26](../../../../raw/postgres-12/src/include/optimizer/cost.h#L23-L26); the variables are defined in [costsize.c#L110-L111](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L110-L111)). The docs state that 4.0 already assumes ~90% of random reads hit cache, and that "if you believe a 90% cache rate is an incorrect assumption for your workload, you can increase `random_page_cost` to better reflect the true cost of random storage reads" ([config.sgml#L4737-L4749](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4737-L4749)). The slower your real random I/O (cold cache, mechanical or network storage), the higher the effective per-page penalty.

Those per-page penalties are exactly what a whole-partition scan pays and what pruning/exclusion avoids:

- An index scan charges `random_page_cost` for each heap page it fetches in the uncorrelated case ([costsize.c#L570-L596](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L570-L596), applied at [costsize.c#L613-L670](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L613-L670)).
- A sequential scan charges `seq_page_cost` per page: `disk_run_cost = spc_seq_page_cost * baserel->pages` ([costsize.c#L236-L242](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L236-L242)).

Because each partition is its own physical relation with its own heap and indexes, dropping a partition removes that whole relation's page fetches. When those fetches are random and slow, the eliminated cost per pruned partition is proportionally larger, so plan-time pruning, run-time pruning, and constraint exclusion deliver their biggest wall-clock wins precisely on high-latency random storage. Plan-time pruning has the added edge that it also removes the partition's planning and locking work; run-time pruning still plans and locks the partition even though it skips the scan.

### Partitionwise join and aggregate: CPU, memory, and locality, not random I/O

Partitionwise join and aggregate help mainly by shrinking each per-partition operation, not by avoiding random reads, and the v12 cost model reflects that:

- A hash join that overflows `work_mem` spills batches to temporary `BufFile`s ([nodeHash.c#L566-L578](../../../../raw/postgres-12/src/backend/executor/nodeHash.c#L566-L578)), but v12 charges that spill at `seq_page_cost` "since the I/O should be nice and sequential" ([costsize.c#L3322-L3338](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L3322-L3338)). Splitting into per-partition joins that each fit in `work_mem` avoids the spill, but the avoided cost is modeled as sequential, not random.
- v12 hash aggregation is entirely in memory: `build_hash_table` builds a `TupleHashTable` whose per-group data lives in the hash memory context, with no batch/spill path ([nodeAgg.c#L1242-L1283](../../../../raw/postgres-12/src/backend/executor/nodeAgg.c#L1242-L1283)). A smaller per-partition hash-aggregate reduces memory pressure and cache misses, not disk I/O.

Their tie-in to slow random I/O is therefore indirect: both consume already-pruned partition inputs, and keeping each partition's working set small improves CPU-cache and buffer-cache locality, so the random reads that *do* happen are likelier to be cached. Neither reduces the number of random page fetches the way pruning does.

## Context Reviewed

- Pinned checkout `raw/postgres-12/` at commit `45b88269a353ad93744772791feb6d01bc7e1e42` (Stamp 12.2).
- Inheritance/constraint exclusion: `src/include/optimizer/cost.h` enum, `src/backend/optimizer/util/plancat.c` (`relation_excluded_by_constraints`, `get_relation_constraints`), the call sites in `src/backend/optimizer/path/allpaths.c`, and the `doc/src/sgml/ddl.sgml` "Implementation Using Inheritance" and "Partitioning and Constraint Exclusion" sections plus `config.sgml`.
- Partition pruning core: `src/backend/partitioning/partprune.c` — module header, `PartClauseTarget`, `prune_append_rel_partitions`, `get_matching_partitions`, `perform_pruning_base_step`, and the per-strategy `get_matching_hash_bounds` / `get_matching_list_bounds` / `get_matching_range_bounds`; `src/backend/partitioning/partbounds.c` for `compute_partition_hash_value`.
- Plan-time integration: `src/backend/optimizer/util/inherit.c` `expand_partitioned_rtentry` (prune-before-expand); run-time prune info in `src/backend/optimizer/plan/createplan.c` (`Append`/`MergeAppend`).
- Run-time pruning executor path: `src/backend/executor/execPartition.c` (`ExecCreatePartitionPruneState`, `ExecFindInitialMatchingSubPlans`, `ExecFindMatchingSubPlans`) and `src/backend/executor/nodeAppend.c`.
- Partitionwise join: `src/backend/optimizer/util/relnode.c` (`build_joinrel_partition_info`), `src/backend/optimizer/path/joinrels.c` (`try_partitionwise_join`, `have_partkey_equi_join`).
- Partitionwise aggregate: `src/backend/optimizer/plan/planner.c` (`create_grouping_paths`, `create_ordinary_grouping_paths`, `group_by_has_partkey`, `create_partitionwise_grouping_paths`).
- Executor routing/DML: `src/backend/executor/execPartition.c` (`ExecSetupPartitionTupleRouting`, `ExecFindPartition`, `get_partition_for_tuple`), `src/backend/executor/nodeModifyTable.c` (row movement), `src/backend/commands/copy.c` (multi-insert).
- Structs: `src/include/nodes/pathnodes.h` (`PartitionSchemeData`, `RelOptInfo` partition fields, `PartitionwiseAggregateType`).
- GUCs: `src/backend/utils/misc/guc.c`, `src/backend/optimizer/path/costsize.c`, `src/backend/utils/misc/postgresql.conf.sample`, `doc/src/sgml/ref/set.sgml`, and the configuration-file reload section in `doc/src/sgml/config.sgml`.
- Docs: `doc/src/sgml/ddl.sgml` (partitioning, inheritance, pruning, constraint exclusion) and `doc/src/sgml/config.sgml` (the four GUCs).
- Tests: `src/test/regress/sql/partition_prune.sql`, `partition_join.sql`, `partition_aggregate.sql`, `hash_part.sql`.
- Follow-up (locking): expansion/locking-before-costing order in `src/backend/optimizer/plan/planmain.c` (`query_planner`) and `src/backend/optimizer/plan/initsplan.c` (`add_other_rels_to_query`); `expand_partitioned_rtentry` prune-then-lock-live-only and `expand_inherited_rtentry` `find_all_inheritors` lock-all in `src/backend/optimizer/util/inherit.c`; `find_all_inheritors` in `src/backend/catalog/pg_inherits.c`; constraint-exclusion timing in `src/backend/optimizer/path/allpaths.c` (`set_append_rel_size`); executor plan locking in `src/backend/utils/cache/plancache.c` (`AcquireExecutorLocks`); lazy write-path `RowExclusiveLock` in `src/backend/executor/execPartition.c` (`ExecInitPartitionInfo`).
- Follow-up (random I/O): page-cost defaults in `src/include/optimizer/cost.h`; `seq_page_cost`/`random_page_cost` variables and the `cost_seqscan`, `cost_index`, and `initial_cost_hashjoin` cost functions in `src/backend/optimizer/path/costsize.c`; `random_page_cost` documentation in `doc/src/sgml/config.sgml`; hash-join batch `BufFile` spill in `src/backend/executor/nodeHash.c`; in-memory hash-aggregation `build_hash_table` in `src/backend/executor/nodeAgg.c`.

## Evidence Map

| Claim | Source |
|---|---|
| Two partitioning kinds; pruning = declarative, CE = legacy | [ddl.sgml:4479-4497](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4479-L4497), [ddl.sgml:4621-4636](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4621-L4636) |
| Three declarative strategies (RANGE/LIST/HASH) | [ddl.sgml:3560-3597](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L3560-L3597) |
| `PartitionScheme` holds strategy/key-count/types, not bounds | [pathnodes.h:389-405](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L389-L405) |
| `RelOptInfo` partition fields | [pathnodes.h:707-722](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L707-L722) |
| GUC variables and defaults | [costsize.c:137-140](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L137-L140) |
| `postgresql.conf.sample` lists the same partitioning defaults | [postgresql.conf.sample:361-402](../../../../raw/postgres-12/src/backend/utils/misc/postgresql.conf.sample#L361-L402) |
| `constraint_exclusion` default `partition`, `PGC_USERSET` | [guc.c:4243-4252](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4243-L4252) |
| `enable_partition_pruning` default on, `PGC_USERSET` | [guc.c:1044-1054](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1044-L1054) |
| `enable_partitionwise_join` default off, `PGC_USERSET` | [guc.c:1003-1012](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1003-L1012) |
| `enable_partitionwise_aggregate` default off, `PGC_USERSET` | [guc.c:1013-1022](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1013-L1022) |
| `SET`/`SET LOCAL` session and transaction scope; config-file reload | [ref/set.sgml:33-58](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L33-L58), [config.sgml:169-183](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L169-L183) |
| Inheritance setup (master/children/CHECK) | [ddl.sgml:4056-4057](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4056-L4057), [ddl.sgml:4108-4149](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4108-L4149) |
| `constraint_exclusion` enum modes | [cost.h:34-39](../../../../raw/postgres-12/src/include/optimizer/cost.h#L34-L39) |
| CE switch: partition mode targets inheritance children | [plancat.c:1435-1474](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1435-L1474) |
| CE constraint set: CHECK/NOT NULL/partition qual | [plancat.c:1159-1287](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1159-L1287) |
| CE call sites (baserel + appendrel child) | [allpaths.c:360-384](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L360-L384), [allpaths.c:1031-1039](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L1031-L1039) |
| CE plan-time only, scaling caveats (~100 children) | [ddl.sgml:4638-4703](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4638-L4703), [config.sgml:5158-5217](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5158-L5217) |
| Inheritance routing is manual (triggers) | [ddl.sgml:4215-4250](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4215-L4250) |
| Triggers slower than declarative internal routing | [ddl.sgml:4462-4464](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4462-L4464) |
| Partition bounds exist only for declarative | [ddl.sgml:4628-4636](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4628-L4636) |
| Partitionwise needs `part_scheme` (inheritance lacks it) | [relnode.c:1612-1698](../../../../raw/postgres-12/src/backend/optimizer/util/relnode.c#L1612-L1698) |
| Base/combine pruning steps; plan vs run-time | [partprune.c:1-35](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L1-L35) |
| `PartClauseTarget` three modes | [partprune.c:91-96](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L91-L96) |
| Plan-time prune before building children | [inherit.c:320-355](../../../../raw/postgres-12/src/backend/optimizer/util/inherit.c#L320-L355) |
| `enable_partition_pruning` gate at plan time | [partprune.c:662-716](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L662-L716) |
| Step execution / dispatch | [partprune.c:728-769](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L728-L769) |
| Run-time prune info attached to Append/MergeAppend | [createplan.c:1216-1241](../../../../raw/postgres-12/src/backend/optimizer/plan/createplan.c#L1216-L1241), [createplan.c:1382-1385](../../../../raw/postgres-12/src/backend/optimizer/plan/createplan.c#L1382-L1385) |
| Two executor pruning phases (overview) | [execPartition.c:1490-1539](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L1490-L1539) |
| Initial pruning in Append init | [nodeAppend.c:125-194](../../../../raw/postgres-12/src/backend/executor/nodeAppend.c#L125-L194), [execPartition.c:1807-1879](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L1807-L1879) |
| Per-scan pruning + rescan invalidation | [nodeAppend.c:479-481](../../../../raw/postgres-12/src/backend/executor/nodeAppend.c#L479-L481), [nodeAppend.c:348-354](../../../../raw/postgres-12/src/backend/executor/nodeAppend.c#L348-L354) |
| Run-time pruning observable in EXPLAIN | [ddl.sgml:4551-4596](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4551-L4596) |
| Per-strategy dispatch switch | [partprune.c:3250-3277](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L3250-L3277) |
| HASH pruning: equality/IS NULL, all keys, no null/default | [partprune.c:2389-2445](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L2389-L2445) |
| Hash partition hash computation ignores NULL keys | [partbounds.c:2738-2759](../../../../raw/postgres-12/src/backend/partitioning/partbounds.c#L2738-L2759) |
| LIST pruning: null/default handling | [partprune.c:2467-2647](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L2467-L2647) |
| RANGE pruning: null->default, prefixes | [partprune.c:2678-2769](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L2678-L2769) |
| CE also applies to declarative CHECKs; partition-mode skip | [ddl.sgml:4638-4645](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4638-L4645), [plancat.c:1435-1474](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1435-L1474) |
| Partitionwise join gate + requirements | [relnode.c:1612-1698](../../../../raw/postgres-12/src/backend/optimizer/util/relnode.c#L1612-L1698) |
| Equi-join on all partition keys | [joinrels.c:1563-1674](../../../../raw/postgres-12/src/backend/optimizer/path/joinrels.c#L1563-L1674) |
| Pairwise child joins only if joinrel partitioned | [joinrels.c:1336-1365](../../../../raw/postgres-12/src/backend/optimizer/path/joinrels.c#L1336-L1365) |
| Partitionwise join docs (all keys, same type, matching sets) | [config.sgml:4576-4594](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4576-L4594) |
| Partitionwise agg gate (FULL candidate) | [planner.c:3886-3889](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L3886-L3889) |
| FULL vs PARTIAL selection | [planner.c:4066-4086](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L4066-L4086) |
| `group_by_has_partkey` requirement for FULL | [planner.c:7361-7405](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L7361-L7405) |
| `PartitionwiseAggregateType` enum | [pathnodes.h:2411-2416](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L2411-L2416) |
| Lazy tuple-routing setup | [execPartition.c:197-235](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L197-L235) |
| `ExecFindPartition` leaf lookup | [execPartition.c:251-350](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L251-L350) |
| Per-strategy routing + no-match error | [execPartition.c:1235-1333](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L1235-L1333) |
| Cross-partition UPDATE = DELETE+INSERT | [nodeModifyTable.c:1139-1208](../../../../raw/postgres-12/src/backend/executor/nodeModifyTable.c#L1139-L1208) |
| COPY multi-insert per partition | [copy.c:2950-2966](../../../../raw/postgres-12/src/backend/commands/copy.c#L2950-L2966), [copy.c:3086-3099](../../../../raw/postgres-12/src/backend/commands/copy.c#L3086-L3099) |
| Execution-time pruning only Append/MergeAppend | [ddl.sgml:4603-4611](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4603-L4611) |
| Run-time pruning tests | [partition_prune.sql:330-561](../../../../raw/postgres-12/src/test/regress/sql/partition_prune.sql#L330-L561) |
| Partitionwise join/aggregate tests | [partition_join.sql:1-10](../../../../raw/postgres-12/src/test/regress/sql/partition_join.sql#L1-L10), [partition_aggregate.sql:1-10](../../../../raw/postgres-12/src/test/regress/sql/partition_aggregate.sql#L1-L10) |
| Expansion/locking runs before costing | [planmain.c:258-271](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L258-L271) |
| Plan-time pruning locks only live partitions | [inherit.c:324-335](../../../../raw/postgres-12/src/backend/optimizer/util/inherit.c#L324-L335), [inherit.c:351-361](../../../../raw/postgres-12/src/backend/optimizer/util/inherit.c#L351-L361) |
| Inheritance locks all members up front | [inherit.c:156-157](../../../../raw/postgres-12/src/backend/optimizer/util/inherit.c#L156-L157), [inherit.c:106-115](../../../../raw/postgres-12/src/backend/optimizer/util/inherit.c#L106-L115) |
| Constraint exclusion runs after children are locked | [allpaths.c:1013-1039](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L1013-L1039) |
| Executor locks all plan rtable rels (run-time pruning keeps locks) | [plancache.c:1585-1602](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1585-L1602) |
| Write-path lazy `RowExclusiveLock` per leaf partition | [execPartition.c:517-519](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L517-L519) |
| `random_page_cost` 4.0 vs `seq_page_cost` 1.0 defaults | [cost.h:23-26](../../../../raw/postgres-12/src/include/optimizer/cost.h#L23-L26), [costsize.c:110-111](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L110-L111) |
| Docs: 4.0 assumes ~90% cache; raise for slow random I/O | [config.sgml:4737-4749](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4737-L4749) |
| Index-scan heap fetches charged at `random_page_cost` | [costsize.c:570-596](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L570-L596), [costsize.c:613-670](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L613-L670) |
| Sequential scan charged at `seq_page_cost` per page | [costsize.c:236-242](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L236-L242) |
| Hash-join batch spill to `BufFile`s, charged as sequential | [nodeHash.c:566-578](../../../../raw/postgres-12/src/backend/executor/nodeHash.c#L566-L578), [costsize.c:3322-3338](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L3322-L3338) |
| v12 hash aggregation is in-memory (no disk spill) | [nodeAgg.c:1242-1283](../../../../raw/postgres-12/src/backend/executor/nodeAgg.c#L1242-L1283) |

## Open Questions

- Except for `compute_partition_hash_value`'s NULL-handling behavior, this page treats the lower-level bound-search and modulus helpers (`partition_list_bsearch`, `partition_range_datum_bsearch`, `get_hash_partition_greatest_modulus`) as building blocks called by the pruning and routing routines; their internal line ranges in `src/backend/partitioning/partbounds.c` are not separately cited here.
- Index access-method interactions (for example, per-partition B-tree/BRIN index scan costing) are out of scope; this page covers partition-level optimizations, not intra-partition index selection.
- The exact minor-release history of each optimization (what changed between 12.0 and the pinned 12.2, and versus v13+) is not traced here; the claims are stated only from the pinned 12.2 source and docs.
- FDW/postgres_fdw partition pushdown for partitionwise join across foreign partitions is not examined.
- The random-I/O analysis reasons from the v12 planner cost model (relative page costs) and the fact that each partition is a separate physical relation; it does not measure real wall-clock latency, which depends on cache-hit rates, storage type, and I/O concurrency not fully captured by `random_page_cost`.
- Prefetch/`effective_io_concurrency` (which can hide random-read latency on bitmap heap scans) is not analyzed here; it interacts with, but is separate from, how many partitions a query must scan.
- The claim that v12 hash aggregation cannot spill to disk is stated only from the pinned 12.2 source (`nodeAgg.c`); the later-version disk-based hash aggregation is out of scope and not cited here, per the single-version evidence rule.

## Source References

- [ddl.sgml#Implementation-Using-Inheritance](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4056-L4149)
- [ddl.sgml#inheritance-trigger-routing](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4215-L4250)
- [ddl.sgml#partition-pruning](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4472-L4612)
- [ddl.sgml#constraint-exclusion](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L4614-L4705)
- [cost.h#ConstraintExclusionType](../../../../raw/postgres-12/src/include/optimizer/cost.h#L34-L39)
- [plancat.c#relation_excluded_by_constraints](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1435-L1474)
- [plancat.c#get_relation_constraints](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1159-L1287)
- [allpaths.c#set_rel_size](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L360-L384)
- [partprune.c#module-header](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L1-L35)
- [partprune.c#prune_append_rel_partitions](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L662-L716)
- [partprune.c#get_matching_partitions](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L728-L769)
- [partprune.c#perform_pruning_base_step-switch](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L3250-L3277)
- [partprune.c#get_matching_hash_bounds](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L2389-L2445)
- [partprune.c#get_matching_list_bounds](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L2467-L2647)
- [partprune.c#get_matching_range_bounds](../../../../raw/postgres-12/src/backend/partitioning/partprune.c#L2678-L2769)
- [partbounds.c#compute_partition_hash_value](../../../../raw/postgres-12/src/backend/partitioning/partbounds.c#L2738-L2759)
- [inherit.c#expand_partitioned_rtentry](../../../../raw/postgres-12/src/backend/optimizer/util/inherit.c#L320-L355)
- [createplan.c#Append-prune-info](../../../../raw/postgres-12/src/backend/optimizer/plan/createplan.c#L1216-L1241)
- [execPartition.c#run-time-pruning](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L1490-L1539)
- [execPartition.c#ExecFindInitialMatchingSubPlans](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L1807-L1879)
- [execPartition.c#ExecFindMatchingSubPlans](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L1990-L2040)
- [execPartition.c#ExecFindPartition](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L251-L350)
- [execPartition.c#get_partition_for_tuple](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L1235-L1333)
- [execPartition.c#ExecSetupPartitionTupleRouting](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L197-L235)
- [nodeAppend.c#ExecInitAppend](../../../../raw/postgres-12/src/backend/executor/nodeAppend.c#L125-L194)
- [nodeModifyTable.c#ExecUpdate-row-movement](../../../../raw/postgres-12/src/backend/executor/nodeModifyTable.c#L1139-L1208)
- [copy.c#partition-multi-insert](../../../../raw/postgres-12/src/backend/commands/copy.c#L2950-L2966)
- [relnode.c#build_joinrel_partition_info](../../../../raw/postgres-12/src/backend/optimizer/util/relnode.c#L1612-L1698)
- [joinrels.c#try_partitionwise_join](../../../../raw/postgres-12/src/backend/optimizer/path/joinrels.c#L1336-L1365)
- [joinrels.c#have_partkey_equi_join](../../../../raw/postgres-12/src/backend/optimizer/path/joinrels.c#L1563-L1674)
- [planner.c#create_grouping_paths-patype](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L3886-L3889)
- [planner.c#create_ordinary_grouping_paths](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L4066-L4086)
- [planner.c#group_by_has_partkey](../../../../raw/postgres-12/src/backend/optimizer/plan/planner.c#L7361-L7405)
- [pathnodes.h#PartitionSchemeData](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L389-L405)
- [pathnodes.h#RelOptInfo-partition-fields](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L707-L722)
- [guc.c#partitioning-GUCs](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1003-L1054)
- [postgresql.conf.sample#partitioning-defaults](../../../../raw/postgres-12/src/backend/utils/misc/postgresql.conf.sample#L361-L402)
- [ref/set.sgml#SET-scope](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L33-L58)
- [config.sgml#configuration-file-reload](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L169-L183)
- [config.sgml#partitioning-GUCs](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4558-L4614)
- [config.sgml#constraint-exclusion](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5158-L5217)
- [partition_prune.sql](../../../../raw/postgres-12/src/test/regress/sql/partition_prune.sql#L1-L12)
- [planmain.c#query_planner-expand-then-cost](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L258-L271)
- [initsplan.c#add_other_rels_to_query](../../../../raw/postgres-12/src/backend/optimizer/plan/initsplan.c#L144-L164)
- [inherit.c#expand_inherited_rtentry-locking](../../../../raw/postgres-12/src/backend/optimizer/util/inherit.c#L106-L157)
- [inherit.c#expand_partitioned_rtentry-prune-then-lock](../../../../raw/postgres-12/src/backend/optimizer/util/inherit.c#L324-L388)
- [pg_inherits.c#find_all_inheritors](../../../../raw/postgres-12/src/backend/catalog/pg_inherits.c#L152-L165)
- [allpaths.c#set_append_rel_size-constraint-exclusion](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L1013-L1039)
- [plancache.c#AcquireExecutorLocks](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1585-L1602)
- [execPartition.c#ExecInitPartitionInfo](../../../../raw/postgres-12/src/backend/executor/execPartition.c#L501-L533)
- [cost.h#page-cost-defaults](../../../../raw/postgres-12/src/include/optimizer/cost.h#L23-L26)
- [costsize.c#page-cost-vars](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L110-L111)
- [costsize.c#cost_seqscan](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L236-L242)
- [costsize.c#cost_index-random-fetch](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L566-L670)
- [costsize.c#initial_cost_hashjoin-batch-io](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L3322-L3338)
- [config.sgml#random_page_cost](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L4713-L4770)
- [nodeHash.c#batch-files](../../../../raw/postgres-12/src/backend/executor/nodeHash.c#L566-L578)
- [nodeAgg.c#build_hash_table](../../../../raw/postgres-12/src/backend/executor/nodeAgg.c#L1242-L1283)

## Navigation

- [v12 index](../../index.md)
- [versions](../../../versions.md)
- [wiki index](../../../index.md)
- [v12: Can ALTER TABLE ... ATTACH PARTITION Drop Indexes?](../indexing/attach-partition-index-drops.md)
- [v12: Query Planner Statistics Sources](query-planner-statistics-sources.md)
