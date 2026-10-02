---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: GPT-5-6-Sol-Max-Thinking 2026-07-17T15:45:58Z
---

# Query Planner Statistics Sources in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Direct answer](#direct-answer)
  - [What `pg_stat_all_tables` contains](#what-pg_stat_all_tables-contains)
  - [Core planner call path and data structures](#core-planner-call-path-and-data-structures)
  - [Direct statistics catalogs](#direct-statistics-catalogs)
  - [Relation size path](#relation-size-path)
  - [Single-column, inheritance, and expression-index statistics](#single-column-inheritance-and-expression-index-statistics)
  - [Extended statistics path](#extended-statistics-path)
  - [Other catalog metadata that affects planning](#other-catalog-metadata-that-affects-planning)
  - [Missing, stale, inaccessible, and inconsistent statistics](#missing-stale-inaccessible-and-inconsistent-statistics)
  - [How planner statistics are written](#how-planner-statistics-are-written)
  - [The collector's indirect effect through auto-analyze](#the-collectors-indirect-effect-through-auto-analyze)
  - [Table AM, FDW, hooks, and extensions](#table-am-fdw-hooks-and-extensions)
  - [Build, generated-header, and cache boundaries](#build-generated-header-and-cache-boundaries)
  - [Regression coverage](#regression-coverage)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 12, does the query planner use stats from `pg_stat_all_tables`? Does it use stats from any other tables or catalogs?

## Answer

### Direct answer

No. PostgreSQL 12's core planner does not use the cumulative counters exposed by `pg_stat_all_tables` as estimates for an unrelated query. That view calls `pg_stat_get_*()` functions, and those functions read the statistics collector's `PgStat_StatTabEntry`; the core base-relation path instead loads relation, column, extended-statistics, index, and foreign-key information into planner structures ([system_views.sql#pg_stat_all_tables](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L552-L581), [pgstatfuncs.c#table-counter-functions](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L40-L360), [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L83-L149), [plancat.c#catalog-loads](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L164-L445)).

Yes, the planner uses statistics from other catalogs:

- `pg_class` supplies stored relation-level estimates: `relpages`, `reltuples`, and `relallvisible`. For ordinary heap tables, the table access method combines those values with the current physical block count ([pg_class.h#relation-statistics](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L59-L66), [heapam_handler.c#heapam_estimate_rel_size](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2072-L2171)).
- `pg_statistic` supplies per-column and expression-index statistics ([pg_statistic.h#FormData_pg_statistic](../../../../raw/postgres-12/src/include/catalog/pg_statistic.h#L29-L124), [selfuncs.c#column-lookup](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4709-L4737), [selfuncs.c#expression-index-lookup](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4524-L4695)).
- `pg_statistic_ext` identifies multicolumn statistics objects, and `pg_statistic_ext_data` stores built ndistinct, functional-dependency, and multivariate-MCV data ([pg_statistic_ext.h#FormData_pg_statistic_ext](../../../../raw/postgres-12/src/include/catalog/pg_statistic_ext.h#L33-L56), [pg_statistic_ext_data.h#FormData_pg_statistic_ext_data](../../../../raw/postgres-12/src/include/catalog/pg_statistic_ext_data.h#L31-L43), [plancat.c#get_relation_statistics](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1290-L1377)).

`pg_stats` and `pg_stats_ext` are inspection views, not separate planner inputs. Their SQL definitions join and decode the underlying catalogs with privilege and row-security filtering; planner code uses the underlying catalogs through relcache and syscache lookups ([system_views.sql#pg_stats](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L189-L252), [system_views.sql#pg_stats_ext](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L256-L294), [selfuncs.c#column-lookup](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4709-L4756), [plancat.c#get_relation_statistics](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1290-L1377)).

That is the answer for statistical data. If "use" includes all metadata that can change available paths, selectivity, cardinality, or cost, the planner also consults index, constraint, type, operator, function, access-method, and partition metadata. Those inputs are distinct from cumulative monitoring statistics and are summarized below ([plancat.c#get_relation_info-indexes](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L164-L423), [plancat.c#selectivity-and-function-cost](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1760-L2015)).

### What `pg_stat_all_tables` contains

`pg_stat_all_tables` joins `pg_class`, `pg_index`, and `pg_namespace`, then exposes scan counts, tuples read or changed, estimated live/dead tuples, modifications since analyze, timestamps, and maintenance counts by calling `pg_stat_get_*()` functions ([system_views.sql#pg_stat_all_tables](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L552-L581)).

Those functions fetch a `PgStat_StatTabEntry`. That collector entry stores scan and tuple counters, live/dead tuple estimates, `changes_since_analyze`, block counters, maintenance timestamps, and maintenance counts ([pgstatfuncs.c#table-counter-functions](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L40-L360), [pgstat.h#PgStat_StatTabEntry](../../../../raw/postgres-12/src/include/pgstat.h#L633-L662)). The monitoring documentation likewise defines the view as access and maintenance statistics for each table, rather than optimizer selectivity data ([monitoring.sgml#pg_stat_all_tables](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2704-L2845)).

The collector still matters indirectly: `changes_since_analyze` helps decide when auto-analyze should run. Auto-analyze then refreshes the catalogs that the planner does read. The view itself is not the input to that decision; the view and autovacuum read the same underlying collector entry ([autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2927-L3095)).

There is also a reverse-direction monitoring edge. While estimating an inequality, the planner can replace a stale histogram endpoint by scanning a matching non-partial B-tree for its current minimum or maximum. The B-tree first-scan path increments that index's cumulative scan counter, and `pg_stat_all_tables.idx_scan` sums the counters of the table's indexes. Planning can therefore increase a counter exposed by the view even though it never reads that counter as an estimate ([selfuncs.c#histogram-endpoint-refresh](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L885-L935), [selfuncs.c#get_actual_variable_range](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5250-L5417), [nbtsearch.c#planner-visible-index-scan-count](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L758-L770), [system_views.sql#pg_stat_all_tables-index-scans](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L552-L561), [monitoring.sgml#optimizer-index-access](../../../../raw/postgres-12/doc/src/sgml/monitoring.sgml#L2914-L2929)).

### Core planner call path and data structures

For an ordinary planned query, `query_planner()` creates base `RelOptInfo` nodes, matches usable foreign keys, and calls `make_one_rel()`; `build_simple_rel()` dispatches an `RTE_RELATION` to `get_relation_info()` ([planmain.c#query_planner](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L153-L271), [relnode.c#build_simple_rel](../../../../raw/postgres-12/src/backend/optimizer/util/relnode.c#L175-L293)). The normal path is:

```text
query_planner
  -> add_base_rels_to_query
     -> build_simple_rel
        -> get_relation_info
           -> estimate_rel_size
           -> load IndexOptInfo list
           -> load StatisticExtInfo list
           -> load relevant ForeignKeyOptInfo entries
  -> match_foreign_keys_to_quals
  -> make_one_rel
     -> set_baserel_size_estimates
        -> clauselist_selectivity
           -> extended statistics where applicable
           -> ordinary clause selectivity for the remainder
```

The source establishes those boundaries at the base-relation build, catalog load, foreign-key match, base-row estimate, and clause-selectivity calls ([planmain.c#base-relations-through-make_one_rel](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L153-L271), [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L83-L149), [plancat.c#index-stats-FK-loads](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L164-L445), [costsize.c#set_baserel_size_estimates](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4390-L4423), [clausesel.c#clauselist_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/clausesel.c#L53-L106)).

The key planner-side structures are:

| Structure | Statistics-related role |
|---|---|
| `RelOptInfo` | Holds `pages`, `tuples`, `allvisfrac`, cached attribute widths, `indexlist`, `statlist`, and FDW state ([pathnodes.h#RelOptInfo](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L632-L723)). |
| `VariableStatData` | Carries the matched variable or expression, relation, `pg_statistic` tuple, release callback, type data, uniqueness knowledge, and statistics-access result ([selfuncs.h#VariableStatData](../../../../raw/postgres-12/src/include/utils/selfuncs.h#L65-L84)). |
| `IndexOptInfo` | Holds index size, tuple count, B-tree height, keys, expressions, predicate, uniqueness, opfamilies, and AM costing capabilities ([pathnodes.h#IndexOptInfo](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L781-L835)). |
| `StatisticExtInfo` | Identifies one built extended-statistics kind and the columns it covers; one object can produce zero to three entries ([pathnodes.h#StatisticExtInfo](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L868-L882), [plancat.c#get_relation_statistics](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1332-L1367)). |
| `ForeignKeyOptInfo` | Holds FK columns/operators plus their matches to equivalence classes and join clauses ([pathnodes.h#ForeignKeyOptInfo](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L838-L865)). |

### Direct statistics catalogs

| Source | Direct use in PostgreSQL 12 |
|---|---|
| `pg_class` | Prior page/tuple density and all-visible-page count. The current physical block count is obtained separately, and the heap AM scales the stored density to it ([pg_class.h#relation-statistics](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L59-L66), [heapam_handler.c#heapam_estimate_rel_size](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2072-L2171)). |
| `pg_statistic` | Null fraction, average width, distinct estimate, and five extensible slots containing MCV, histogram, correlation, element, or range statistics ([pg_statistic.h#fields-and-slots](../../../../raw/postgres-12/src/include/catalog/pg_statistic.h#L29-L126), [pg_statistic.h#core-slot-kinds](../../../../raw/postgres-12/src/include/catalog/pg_statistic.h#L136-L271)). |
| `pg_statistic_ext` | Object OID, source relation, key columns, and requested kinds ([pg_statistic_ext.h#FormData_pg_statistic_ext](../../../../raw/postgres-12/src/include/catalog/pg_statistic_ext.h#L33-L69)). |
| `pg_statistic_ext_data` | Serialized multivariate ndistinct, functional dependencies, and multivariate MCV list ([pg_statistic_ext_data.h#FormData_pg_statistic_ext_data](../../../../raw/postgres-12/src/include/catalog/pg_statistic_ext_data.h#L31-L43)). |
| Current relation storage | Current main-fork block count for heap and index relations; it is not a catalog statistic ([heapam_handler.c#current-block-count](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2082-L2088), [plancat.c#index-block-count](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L407)). |

The PostgreSQL 12 planner-statistics documentation matches this split: relation row/page totals are in `pg_class`, per-column selectivity data is in `pg_statistic`, and `pg_stats` is the recommended human-readable view for inspection ([perform.sgml#single-column-statistics](../../../../raw/postgres-12/doc/src/sgml/perform.sgml#L920-L1059)).

### Relation size path

`get_relation_info()` calls `estimate_rel_size()` for a non-inheritance-parent base relation and stores the result in `RelOptInfo.pages`, `tuples`, and `allvisfrac` ([plancat.c#get_relation_info-size](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L105-L152)). For a heap table, the heap AM:

1. reads the current physical block count;
2. reads `pg_class.relpages`, `reltuples`, and `relallvisible` from the relation descriptor;
3. applies a ten-page floor to a small relation whose stored `relpages` is zero and which has no children;
4. scales the old tuple density to the current pages, or derives a fallback density from attribute widths when no prior page count exists; and
5. converts `relallvisible` to a fraction for index-only-scan costing ([heapam_handler.c#heapam_estimate_rel_size](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2072-L2171), [costsize.c#index-only-allvisfrac](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L607-L664)).

The prior page made the index path too broad. `get_relation_info()` handles an ordinary non-partial index by taking its current physical block count and assigning the parent table's tuple estimate. Only a partial index enters `estimate_rel_size()` to derive an index tuple estimate from its own stored density, after which the result is clamped to the table estimate ([plancat.c#get_relation_info-index-size](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L407)). On that partial-index path, the generic estimator discounts one presumed metapage when deriving density; its own comment says that heuristic is suitable for B-tree, hash, and GIN but suspect for GiST ([plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L946-L1040)).

An inheritance or partition parent does not use its own physical size as the append relation's size. `get_relation_info()` skips the parent estimate, and `set_append_rel_size()` computes child sizes, sums surviving child output rows, weights widths by child rows, and leaves the parent `pages` at zero to avoid double counting ([plancat.c#inheritance-parent-boundary](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L105-L149), [allpaths.c#set_append_rel_size](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L930-L1039), [allpaths.c#append-size-result](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L1130-L1208)).

The generic size dispatcher returns fixed `1 page / 1 tuple` values for a sequence, initial `pg_class` values for a foreign table, and zero for storage-less relation kinds. Foreign-table estimates are then handed to the FDW, as described below ([plancat.c#estimate_rel_size-relkinds](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1042-L1059), [allpaths.c#set_foreign_size](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L899-L914)). A temporary or unlogged relation is rejected during recovery before these estimates are used ([plancat.c#recovery-error](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L119-L130)).

### Single-column, inheritance, and expression-index statistics

For a plain table column, `examine_simple_variable()` uses the `STATRELATTINH` syscache key `(relation OID, attribute number, rte->inh)`. The `stainherit` key therefore selects table-only statistics for a non-inheritance scan and inheritance-tree statistics for an inherited scan ([selfuncs.c#examine_simple_variable](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4709-L4737), [pg_statistic.h#statistics-key](../../../../raw/postgres-12/src/include/catalog/pg_statistic.h#L29-L35), [syscache.c#STATRELATTINH](../../../../raw/postgres-12/src/backend/utils/cache/syscache.c#L764-L773)).

`pg_statistic` has five physical slots, but a reader searches by `stakind` rather than slot position. Core v12 kinds include MCV, histogram, physical-order correlation, most-common elements, distinct-element-count histogram, range-length histogram, and range-bounds histogram; custom type analysis and selectivity code can agree on additional kind numbers ([pg_statistic.h#slot-contract](../../../../raw/postgres-12/src/include/catalog/pg_statistic.h#L136-L178), [pg_statistic.h#core-slot-kinds](../../../../raw/postgres-12/src/include/catalog/pg_statistic.h#L178-L271), [lsyscache.c#get_attstatsslot](../../../../raw/postgres-12/src/backend/utils/cache/lsyscache.c#L2895-L2965)). For example, B-tree costing reads the first key's correlation slot from the table column or expression-index row and reduces its weight for a multicolumn index ([selfuncs.c#btcostestimate-correlation](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6118-L6213)).

Expression-index statistics are also `pg_statistic` rows, keyed by the index relation OID and index attribute number. During general expression selectivity, `examine_variable()` matches a single-relation expression to an index expression and reads that index's statistics tuple ([selfuncs.c#expression-index-match](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4524-L4604)). That path ignores a partial index's expression statistics because they do not describe the whole table; an installed `get_index_stats_hook` must decide for itself whether such statistics are valid ([selfuncs.c#partial-expression-index-boundary](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4574-L4604)). This is not a universal ban: B-tree costing directly looks up the first expression key's correlation row, and BRIN costing does the same for expression columns used by its index clauses. Both can therefore use correlation collected over a partial index's predicate-matching sample ([selfuncs.c#btcostestimate-correlation](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6118-L6213), [selfuncs.c#brincostestimate-correlation](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L7045-L7137), [analyze.c#compute_index_stats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L693-L867)).

`ANALYZE` only prepares separate index-relation statistics for expression columns. A simple index key continues to use the underlying table column's statistics; index setup calls `examine_attribute()` only where the index key number is zero, meaning an expression ([analyze.c#index-expression-setup](../../../../raw/postgres-12/src/backend/commands/analyze.c#L413-L467)). The expression values are evaluated over sampled heap rows that pass the index predicate, and completed rows are written with the index OID as `starelid` ([analyze.c#compute_index_stats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L693-L867), [analyze.c#write-index-statistics](../../../../raw/postgres-12/src/backend/commands/analyze.c#L560-L574)).

Average-width lookup first offers `get_attavgwidth_hook`, then reads `pg_statistic.stawidth`; if neither supplies a positive width, callers fall back to a datatype/typmod estimate from `pg_type` metadata ([lsyscache.c#get_attavgwidth](../../../../raw/postgres-12/src/backend/utils/cache/lsyscache.c#L2860-L2893), [plancat.c#get_rel_data_width](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1064-L1111), [lsyscache.c#get_typavgwidth](../../../../raw/postgres-12/src/backend/utils/cache/lsyscache.c#L2347-L2398)).

### Extended statistics path

`RelationGetStatExtList()` scans `pg_statistic_ext` by source relation and caches the object OIDs in the relcache. `get_relation_statistics()` then looks up both catalog tuples and creates one `StatisticExtInfo` for each non-NULL built kind. A newly created but not yet analyzed object contributes no planner entry ([relcache.c#RelationGetStatExtList](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4443-L4523), [plancat.c#get_relation_statistics](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1290-L1377)).

For restriction clauses on one relation, `clauselist_selectivity()` estimates compatible clauses with extended statistics first and sends the remaining clauses through ordinary selectivity. The extended path applies a multivariate MCV list before functional dependencies ([clausesel.c#clauselist_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/clausesel.c#L53-L106), [extended_stats.c#statext_clauselist_selectivity](../../../../raw/postgres-12/src/backend/statistics/extended_stats.c#L1169-L1202)). Group-count estimation separately searches for the multivariate ndistinct object matching the most grouping columns and loads its ndistinct data ([selfuncs.c#estimate_num_groups](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L3227-L3265), [selfuncs.c#estimate_multivariate_ndistinct](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L3562-L3643)).

PostgreSQL 12 extended statistics accept at least two simple user columns whose types have default B-tree ordering. Expressions, system columns, duplicate columns, unsupported types, and excessive dimensions are rejected before catalog insertion ([statscmds.c#extended-statistics-columns](../../../../raw/postgres-12/src/backend/commands/statscmds.c#L182-L273)). `ANALYZE` builds ndistinct, dependency, and MCV data from the same sampled rows as the per-column statistics and writes it to `pg_statistic_ext_data` ([extended_stats.c#BuildRelationExtStatistics](../../../../raw/postgres-12/src/backend/statistics/extended_stats.c#L75-L157), [extended_stats.c#statext_store](../../../../raw/postgres-12/src/backend/statistics/extended_stats.c#L315-L387)).

### Other catalog metadata that affects planning

The following are not cumulative monitoring statistics, but they can change planner estimates, path eligibility, or cost:

| Catalog or metadata | Planner effect |
|---|---|
| `pg_index` plus index relcache data | Determines live/valid indexes, key columns, expressions, predicates, uniqueness, ordering, opfamilies, physical pages, partial-index tuple estimates, and B-tree height ([relcache.c#RelationGetIndexList](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4318-L4399), [plancat.c#get_relation_info-indexes](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L164-L423)). A proven unique index can override stale or missing distinct-count statistics for equality estimates ([selfuncs.c#unique-override](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5070-L5079)). |
| `pg_constraint` and constraint relcache data | Foreign keys can replace ordinary join-clause selectivity after matching all required equality clauses; validated immutable CHECK constraints can prove a relation scan unnecessary ([plancat.c#get_relation_foreign_keys](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L465-L566), [costsize.c#get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4693-L4906), [plancat.c#get_relation_constraints](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1136-L1287), [plancat.c#relation_excluded_by_constraints](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1380-L1562)). |
| `pg_attribute` and partition relcache data | Attribute type, typmod, collation, dropped-column state, and `attnotnull` affect width and constraint reasoning. Partition constraints come from `RelationGetPartitionQual()`, not from `pg_constraint` ([plancat.c#get_rel_data_width](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1077-L1111), [plancat.c#NOT-NULL-and-partition-constraints](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1224-L1281)). |
| `pg_type` | `typlen` and typmod-aware rules provide fallback widths, while `typanalyze` selects type-specific statistics collection ([pg_type.h#type-width-fields](../../../../raw/postgres-12/src/include/catalog/pg_type.h#L50-L67), [pg_type.h#typanalyze](../../../../raw/postgres-12/src/include/catalog/pg_type.h#L123-L159), [analyze.c#type-specific-analysis](../../../../raw/postgres-12/src/backend/commands/analyze.c#L934-L973)). |
| `pg_operator` | `oprrest` and `oprjoin` select the restriction and join selectivity procedures; a missing procedure yields the generic `0.5` estimate ([pg_operator.h#selectivity-procedures](../../../../raw/postgres-12/src/include/catalog/pg_operator.h#L63-L76), [plancat.c#operator-selectivity](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1760-L1837)). |
| `pg_proc` | `prosupport` may supply selectivity, cost, or row estimates; otherwise `procost` prices function/operator execution and `prorows` estimates set-returning output. `provolatile` constrains constant treatment, `proparallel` constrains parallel paths, and `proleakproof` participates in statistics-value security checks ([pg_proc.h#planner-fields](../../../../raw/postgres-12/src/include/catalog/pg_proc.h#L44-L78), [plancat.c#function-selectivity-cost-rows](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1840-L2015), [costsize.c#function-cost-use](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L3909-L3962), [clauses.c#function-volatility](../../../../raw/postgres-12/src/backend/optimizer/util/clauses.c#L632-L654), [clauses.c#parallel-safety](../../../../raw/postgres-12/src/backend/optimizer/util/clauses.c#L895-L940), [selfuncs.c#statistic_proc_security_check](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4961-L4982)). |
| `pg_am`, opclass, opfamily, `pg_amop`, and `pg_amproc` data | Relcache resolves an access-method handler, opfamilies, opclass input types, and support functions. `get_relation_info()` copies search, ordering, parallel, bitmap, and `amcostestimate` capabilities into `IndexOptInfo` ([relcache.c#index-AM-and-opclass-load](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L1380-L1568), [amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L159-L233), [plancat.c#index-AM-capabilities](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L257-L357), [lsyscache.c#opfamily-lookups](../../../../raw/postgres-12/src/backend/utils/cache/lsyscache.c#L124-L217)). |

This table is deliberately scoped to metadata that directly affects estimates, costs, or path eligibility; it is not an exhaustive inventory of every catalog consulted during parsing, rewriting, and planning.

### Missing, stale, inaccessible, and inconsistent statistics

PostgreSQL 12 does not fall back from missing `pg_statistic` data to `pg_stat_all_tables`. It uses estimator defaults and structural facts instead. Representative defaults are `0.005` for equality, `1/3` for inequality, `0.005` for pattern matches and for `IS NULL`/unknown, the complementary `0.995` for the corresponding `NOT` tests, and `200` distinct values ([selfuncs.h#default-estimates](../../../../raw/postgres-12/src/include/utils/selfuncs.h#L30-L49)). Equality estimation with no usable statistics divides by the inferred/default distinct count, while null tests use their fixed defaults; unique-index knowledge and special system-column/type cases can still improve those guesses ([selfuncs.c#equality-without-stats](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L385-L425), [selfuncs.c#nulltestsel-fallback](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L1450-L1519), [selfuncs.c#get_variable_numdistinct](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4985-L5117)).

`pg_class` values are explicitly approximate and not updated for every row change. The heap path mitigates staleness by scaling old tuple density to the current physical page count; `pg_statistic` tuples have no age field or freshness test in the lookup path, so stale distributions remain inputs until statistics are refreshed ([pg_class.h#relation-statistics](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L59-L66), [heapam_handler.c#density-scaling](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2082-L2171), [selfuncs.c#column-lookup](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4709-L4737), [perform.sgml#stale-relation-statistics](../../../../raw/postgres-12/doc/src/sgml/perform.sgml#L960-L973)).

Statistics values also have a security boundary. The planner loads the tuple, but non-leakproof estimator functions may consume its value arrays only when the effective user can select the table/column and no security-barrier or row-security qual blocks access. Null fraction can still be used without exposing values ([selfuncs.c#statistics-access-check](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4739-L4838), [selfuncs.c#nullfrac-and-security-check](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L298-L330), [selfuncs.c#statistic_proc_security_check](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4961-L4982)). Expression-index statistics require whole-table SELECT permission because the core does not try to derive the expression's exact column set ([selfuncs.c#expression-statistics-access](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4606-L4678)). Extended-statistics MCV clauses likewise require table or referenced-column SELECT permission, and a security qual rejects a leaky comparison operator while allowing a leakproof one ([extended_stats.c#extended-statistics-security](../../../../raw/postgres-12/src/backend/statistics/extended_stats.c#L814-L867), [extended_stats.c#extended-statistics-ACL](../../../../raw/postgres-12/src/backend/statistics/extended_stats.c#L942-L998)).

An unbuilt extended-statistics value is normally skipped: `statext_is_kind_built()` tests for NULL before `StatisticExtInfo` creation. Missing catalog tuples are treated as internal consistency failures and raise `ERROR`; the individual loaders also error if asked to load a NULL kind ([plancat.c#get_relation_statistics-errors-and-built-checks](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1315-L1367), [extended_stats.c#statext_is_kind_built](../../../../raw/postgres-12/src/backend/statistics/extended_stats.c#L159-L187), [mvdistinct.c#statext_ndistinct_load](../../../../raw/postgres-12/src/backend/statistics/mvdistinct.c#L137-L165), [dependencies.c#statext_dependencies_load](../../../../raw/postgres-12/src/backend/statistics/dependencies.c#L629-L657), [mcv.c#statext_mcv_load](../../../../raw/postgres-12/src/backend/statistics/mcv.c#L554-L582)). The v12 MCV loader's NULL-data error mistakenly prints the dependency kind character rather than the MCV kind; this affects only that error text, not the normal built-kind guard or selected catalog column ([mcv.c#statext_mcv_load](../../../../raw/postgres-12/src/backend/statistics/mcv.c#L554-L582)).

Operator and function support code validates extension-provided estimates. A restriction or join estimator returning outside `[0,1]`, or a function support routine returning an invalid selectivity, raises `ERROR` rather than admitting that value into planning ([plancat.c#selectivity-validation](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1769-L1895)).

### How planner statistics are written

For an ordinary heap table, `ANALYZE` takes an approximate random sample. Its two-stage algorithm samples blocks and then applies Vitter reservoir sampling to rows; it extrapolates live/dead row totals from the sampled blocks ([analyze.c#acquire_sample_rows](../../../../raw/postgres-12/src/backend/commands/analyze.c#L976-L1127)). Type-specific analysis computes `VacAttrStats`, whose valid fields become a `pg_statistic` row through `CatalogTupleUpdate` or `CatalogTupleInsert` ([vacuum.h#VacAttrStats](../../../../raw/postgres-12/src/include/commands/vacuum.h#L44-L137), [analyze.c#update_attstats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L1394-L1547)).

The same sampled heap rows feed expression-index statistics and extended statistics. `ANALYZE` writes table-column rows, index-expression rows, and built extended data, then updates table and index `pg_class` statistics through `vac_update_relstats()` ([analyze.c#statistics-write-path](../../../../raw/postgres-12/src/backend/commands/analyze.c#L506-L629), [extended_stats.c#BuildRelationExtStatistics](../../../../raw/postgres-12/src/backend/statistics/extended_stats.c#L75-L157), [vacuum.c#vac_update_relstats](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1135-L1196)). It finally reports live/dead estimates and analyze completion back to the cumulative collector; that report resets `changes_since_analyze` only for a full-column analyze ([analyze.c#pgstat_report_analyze](../../../../raw/postgres-12/src/backend/commands/analyze.c#L631-L640)).

Creating an extended-statistics object inserts metadata into `pg_statistic_ext` and a `pg_statistic_ext_data` row whose three data fields are initially NULL. Only a later `ANALYZE` builds them ([statscmds.c#create-statistics-data-row](../../../../raw/postgres-12/src/backend/commands/statscmds.c#L340-L376), [extended_stats.c#BuildRelationExtStatistics](../../../../raw/postgres-12/src/backend/statistics/extended_stats.c#L75-L157)). If any requested column was omitted from a partial `ANALYZE` or could not produce per-column statistics, extended-statistics construction warns outside autovacuum and skips rebuilding that object. A new object therefore remains unbuilt; this branch does not clear data from an earlier successful build, so an existing object retains its previous values ([extended_stats.c#missing-column-statistics](../../../../raw/postgres-12/src/backend/statistics/extended_stats.c#L101-L127), [extended_stats.c#lookup_var_attr_stats](../../../../raw/postgres-12/src/backend/statistics/extended_stats.c#L259-L313), [extended_stats.c#statext_store](../../../../raw/postgres-12/src/backend/statistics/extended_stats.c#L315-L387)).

### The collector's indirect effect through auto-analyze

`relation_needs_vacanalyze()` computes the analyze threshold from a base threshold plus a scale factor times `pg_class.reltuples`, then compares it with `PgStat_StatTabEntry.changes_since_analyze`. If there is no collector entry, or automatic vacuuming is inactive, threshold-based auto-analyze does not run for that table ([autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2927-L3095)).

The causal chain is therefore:

```text
row changes
  -> collector changes_since_analyze
  -> auto-analyze threshold decision
  -> ANALYZE sample
  -> pg_class / pg_statistic / pg_statistic_ext_data refresh
  -> later plans consume refreshed catalog data
```

Each arrow is present in the collector threshold and `ANALYZE` write paths ([autovacuum.c#collector-threshold](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2932-L2955), [autovacuum.c#threshold-decision](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L3060-L3095), [analyze.c#statistics-write-path](../../../../raw/postgres-12/src/backend/commands/analyze.c#L506-L640)). This is an indirect influence of cumulative statistics, not planner consumption of `pg_stat_all_tables`.

Inheritance statistics have a separate freshness edge. `ANALYZE` can sample the parent plus children and write the result with `stainherit = true`, but auto-analyze considers changes on the parent itself when deciding whether to refresh the parent's inheritance statistics; the documentation therefore warns that manual `ANALYZE` can be needed when only children change ([analyze.c#write-inherited-statistics](../../../../raw/postgres-12/src/backend/commands/analyze.c#L496-L566), [analyze.c#acquire_inherited_sample_rows](../../../../raw/postgres-12/src/backend/commands/analyze.c#L1169-L1390), [analyze.sgml#inheritance-statistics](../../../../raw/postgres-12/doc/src/sgml/ref/analyze.sgml#L253-L263)).

### Table AM, FDW, hooks, and extensions

The heap formula is not mandatory for every table access method (table AM). `estimate_rel_size()` dispatches ordinary table-like relations to `table_relation_estimate_size()`, which calls the relation's `TableAmRoutine.relation_estimate_size` callback; the built-in heap routine is one implementation ([plancat.c#table-AM-dispatch](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L946-L953), [tableam.h#relation_estimate_size](../../../../raw/postgres-12/src/include/access/tableam.h#L586-L603), [tableam.h#table_relation_estimate_size](../../../../raw/postgres-12/src/include/access/tableam.h#L1621-L1637), [heapam_handler.c#heap-AM-registration](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2603-L2663)).

Foreign tables have another boundary. Core seeds a placeholder estimate, then calls the FDW's mandatory `GetForeignRelSize` callback and clamps the returned row count ([costsize.c#set_foreign_size_estimates](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L5174-L5200), [allpaths.c#set_foreign_size](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L899-L914), [fdwapi.h#GetForeignRelSize](../../../../raw/postgres-12/src/include/foreign/fdwapi.h#L23-L32)). Shipped `postgres_fdw` can use local catalog statistics or, with its table/server option enabled, execute remote `EXPLAIN` and replace local row/width estimates; shipped `file_fdw` derives size through its own callback ([postgres_fdw.c#postgresGetForeignRelSize](../../../../raw/postgres-12/contrib/postgres_fdw/postgres_fdw.c#L563-L720), [postgres-fdw.sgml#use_remote_estimate](../../../../raw/postgres-12/doc/src/sgml/postgres-fdw.sgml#L200-L267), [file_fdw.c#fileGetForeignRelSize](../../../../raw/postgres-12/contrib/file_fdw/file_fdw.c#L498-L523)).

Core exposes four statistics-adjacent hooks:

- `get_relation_info_hook` can change relation size or index metadata after core loading ([plancat.c#get_relation_info_hook](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L57-L62), [plancat.c#hook-call](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L456-L463));
- `get_relation_stats_hook` and `get_index_stats_hook` can supply an alternative statistics tuple ([selfuncs.h#statistics-hooks](../../../../raw/postgres-12/src/include/utils/selfuncs.h#L115-L125), [selfuncs.c#relation-hook-call](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4709-L4726), [selfuncs.c#index-hook-call](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4574-L4604)); and
- `get_attavgwidth_hook` can override average width ([lsyscache.h#get_attavgwidth_hook](../../../../raw/postgres-12/src/include/utils/lsyscache.h#L59-L64), [lsyscache.c#get_attavgwidth](../../../../raw/postgres-12/src/backend/utils/cache/lsyscache.c#L2860-L2893)).

Extensions need not use those hooks to affect estimates. They can define operator selectivity procedures or an index AM cost routine. Shipped `intarray` reads array MCE statistics in `_int_matchsel`, shipped `ltree` implements `ltreeparentsel`, and shipped Bloom installs `blcostestimate` as its index AM estimator ([intarray/_int_selfuncs.c#_int_matchsel](../../../../raw/postgres-12/contrib/intarray/_int_selfuncs.c#L119-L238), [ltree_op.c#ltreeparentsel](../../../../raw/postgres-12/contrib/ltree/ltree_op.c#L562-L614), [bloom/blutils.c#amcostestimate](../../../../raw/postgres-12/contrib/bloom/blutils.c#L118-L139), [bloom/blcost.c#blcostestimate](../../../../raw/postgres-12/contrib/bloom/blcost.c#L20-L45)). External extension behavior beyond the pinned checkout cannot be inferred from core hook declarations alone.

### Build, generated-header, and cache boundaries

The catalog declarations are build inputs. `pg_class.h`, `pg_statistic.h`, `pg_statistic_ext.h`, and `pg_statistic_ext_data.h` include generated `*_d.h` headers that provide relation IDs and attribute-number macros ([pg_class.h#catalog-includes](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L18-L29), [pg_statistic.h#catalog-includes](../../../../raw/postgres-12/src/include/catalog/pg_statistic.h#L20-L29), [pg_statistic_ext.h#catalog-includes](../../../../raw/postgres-12/src/include/catalog/pg_statistic_ext.h#L22-L33), [pg_statistic_ext_data.h#catalog-includes](../../../../raw/postgres-12/src/include/catalog/pg_statistic_ext_data.h#L20-L31)). The backend catalog Makefile lists these catalog headers, derives every `*_d.h` name, and runs `genbki.pl` before symlinking generated headers into the build include tree ([catalog/Makefile#catalog-and-generated-headers](../../../../raw/postgres-12/src/backend/catalog/Makefile#L27-L57), [catalog/Makefile#genbki-rule](../../../../raw/postgres-12/src/backend/catalog/Makefile#L71-L101)).

Statistics reads use named syscaches. `STATRELATTINH`, `STATEXTOID`, and `STATEXTDATASTXOID` are declared in the syscache enum; their cache definitions specify the backing relation, index, and key columns ([syscache.h#statistics-caches](../../../../raw/postgres-12/src/include/utils/syscache.h#L75-L93), [syscache.c#statistics-cache-definitions](../../../../raw/postgres-12/src/backend/utils/cache/syscache.c#L731-L773)). This is why the planner can request a column tuple by `(starelid, staattnum, stainherit)` and extended data by statistics-object OID rather than scanning those catalogs for each clause ([selfuncs.c#column-lookup](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4709-L4737), [plancat.c#extended-statistics-lookups](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1304-L1322)).

The list of extended-statistics objects is separately cached in each relation's relcache entry. Shared relcache invalidation clears `rd_statlist`/`rd_statvalid`; `CREATE STATISTICS` and `DROP STATISTICS` explicitly invalidate the associated relation so later planning rebuilds the list ([relcache.c#RelationGetStatExtList](../../../../raw/postgres-12/src/backend/utils/cache/relcache.c#L4443-L4523), [statscmds.c#create-statistics-invalidation](../../../../raw/postgres-12/src/backend/commands/statscmds.c#L340-L378), [statscmds.c#drop-statistics-invalidation](../../../../raw/postgres-12/src/backend/commands/statscmds.c#L417-L466)).

### Regression coverage

The checked-in tests cover the positive sources and the monitoring/source distinction from several angles:

- `stats_ext.sql` compares estimated and actual rows before and after building ndistinct, dependency, and MCV statistics; it also covers invalid definitions, unbuilt data, column drops, partial `ANALYZE`, and supported relation kinds ([stats_ext.sql#definition-and-error-paths](../../../../raw/postgres-12/src/test/regress/sql/stats_ext.sql#L7-L119), [stats_ext.sql#ndistinct](../../../../raw/postgres-12/src/test/regress/sql/stats_ext.sql#L122-L218), [stats_ext.sql#dependencies-and-MCV](../../../../raw/postgres-12/src/test/regress/sql/stats_ext.sql#L220-L491)).
- `join.sql` creates and analyzes a multicolumn FK case before checking its plan ([join.sql#FK-estimation](../../../../raw/postgres-12/src/test/regress/sql/join.sql#L1903-L1928)).
- `privileges.sql` and `inherit.sql` exercise expression-index statistics and the table/column privilege boundaries that decide whether estimators may use them ([privileges.sql#expression-statistics-security](../../../../raw/postgres-12/src/test/regress/sql/privileges.sql#L130-L202), [inherit.sql#inherited-statistics-security](../../../../raw/postgres-12/src/test/regress/sql/inherit.sql#L849-L885)).
- `join_hash.sql` deliberately changes `pg_class.reltuples` and `relpages` to create underestimated relations for hash-join tests, directly exercising planner dependence on those relation statistics ([join_hash.sql#forced-relation-estimates](../../../../raw/postgres-12/src/test/regress/sql/join_hash.sql#L55-L84)).
- `stats.sql` checks the asynchronously collected scan, tuple, live/dead, and block counters exposed by `pg_stat_user_tables` and related views; it does not present those counters as planner estimates ([stats.sql#collector-setup](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L1-L78), [stats.sql#collector-results](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L154-L175)).
- `postgres_fdw.sql` deliberately uses local statistics on one foreign table and remote-estimate mode on another, and separately analyzes foreign tables that do not use remote estimates ([postgres_fdw.sql#local-vs-remote-estimates](../../../../raw/postgres-12/contrib/postgres_fdw/sql/postgres_fdw.sql#L217-L224), [postgres_fdw.sql#local-foreign-statistics](../../../../raw/postgres-12/contrib/postgres_fdw/sql/postgres_fdw.sql#L376-L382)).

There is no dedicated regression assertion named for the negative statement "the core planner does not read `pg_stat_all_tables`." That boundary is established by the positive call paths above and by a source-wide search of `src/backend/optimizer/`, which contains no `PgStat_StatTabEntry`, `pgstat_fetch_stat_tabentry`, `pg_stat_get_*`, or `pg_stat_all_tables` reference. The cumulative-statistics regression test verifies the monitoring side, not planner non-use ([stats.sql#collector-setup](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L1-L78), [planmain.c#query_planner](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L65-L271), [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L83-L149)).

## Context Reviewed

- Pinned checkout: `raw/postgres-12/` at `45b88269a353ad93744772791feb6d01bc7e1e42` (`REL_12_2`).
- Monitoring side: complete `pg_stat_all_tables` definition, table-facing `pg_stat_get_*()` functions, `PgStat_StatTabEntry`, the planner's B-tree endpoint probe and resulting scan-counter increment, collector tests, and monitoring documentation.
- Normal planner path: `query_planner`, base-relation creation, `get_relation_info`, relation sizing, index/FK/constraint loading, base-row estimation, ordinary and extended selectivity, and relevant planner data structures.
- Statistics reads: plain and inherited columns, expression-index matching, slot extraction, width lookup, extended-statistics object/data loading, security checks, defaults, and consistency errors.
- Statistics writes: ordinary and inherited sampling, type-specific analysis, expression-index statistics, extended-statistics construction, `pg_class` updates, collector reporting, and object create/drop invalidation.
- Other metadata: index and access-method relcache data, FK and exclusion constraints, attributes/types, operator and function estimation procedures, opfamilies, and generated syscache definitions.
- Extension boundaries: table AM sizing, FDW sizing, all four core statistics-adjacent hooks, shipped `postgres_fdw`, `file_fdw`, `intarray`, `ltree`, and Bloom paths. A source-wide search found no assignment to the four statistics-adjacent hooks under the shipped `contrib/` tree.
- Tests and docs: `stats`, `stats_ext`, `join`, `join_hash`, `privileges`, `inherit`, `postgres_fdw`, planner-statistics documentation, `ANALYZE` documentation, monitoring documentation, and FDW documentation.
- Exact-pin verification: the core regression suite passed with exit status 0 in the isolated PostgreSQL 12 build under `.wiki-runtime/pg12-build/`; the pinned `raw/postgres-12/` checkout remained read-only evidence.

## Evidence Map

| Claim | Primary evidence |
|---|---|
| `pg_stat_all_tables` exposes cumulative collector counters, not planner statistics | [system_views.sql#pg_stat_all_tables](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L552-L581), [pgstat.h#PgStat_StatTabEntry](../../../../raw/postgres-12/src/include/pgstat.h#L633-L662) |
| A planner histogram-endpoint probe can increment an index counter without consuming it as input | [selfuncs.c#get_actual_variable_range](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5250-L5417), [nbtsearch.c#planner-visible-index-scan-count](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L758-L770) |
| Base-relation planning loads catalog/relcache data instead of collector entries | [relnode.c#build_simple_rel](../../../../raw/postgres-12/src/backend/optimizer/util/relnode.c#L175-L293), [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L83-L149) |
| Heap relation size combines current blocks with `pg_class` density and all-visible data | [heapam_handler.c#heapam_estimate_rel_size](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2072-L2171) |
| Ordinary and partial indexes follow different tuple-estimation paths | [plancat.c#get_relation_info-index-size](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L388-L407), [plancat.c#estimate_rel_size-index](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L946-L1040) |
| Plain/inherited column statistics use `(relid, attnum, inherit)` | [selfuncs.c#examine_simple_variable](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4709-L4737), [syscache.c#STATRELATTINH](../../../../raw/postgres-12/src/backend/utils/cache/syscache.c#L764-L773) |
| Expression-index statistics are separate `pg_statistic` rows; general expression selectivity ignores partial-index rows, while B-tree/BRIN costing can read their correlation | [analyze.c#index-expression-setup](../../../../raw/postgres-12/src/backend/commands/analyze.c#L413-L467), [selfuncs.c#expression-index-match](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4524-L4604), [selfuncs.c#btcostestimate-correlation](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L6118-L6213), [selfuncs.c#brincostestimate-correlation](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L7045-L7137) |
| Extended statistics are loaded only for built kinds and used before ordinary clause estimates | [plancat.c#get_relation_statistics](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1290-L1377), [clausesel.c#clauselist_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/clausesel.c#L53-L106) |
| FK metadata substitutes a join selectivity only after query-clause matching | [planmain.c#FK-match-position](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L244-L271), [costsize.c#get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4693-L4906) |
| Missing column statistics use fixed/default estimates, not cumulative counters | [selfuncs.h#default-estimates](../../../../raw/postgres-12/src/include/utils/selfuncs.h#L30-L49), [selfuncs.c#get_variable_numdistinct](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4985-L5117) |
| Collector changes affect planning only indirectly through auto-analyze and catalog refresh | [autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2927-L3095), [analyze.c#statistics-write-path](../../../../raw/postgres-12/src/backend/commands/analyze.c#L506-L640) |
| Table AMs and FDWs can replace core size estimates | [tableam.h#relation_estimate_size](../../../../raw/postgres-12/src/include/access/tableam.h#L586-L603), [allpaths.c#set_foreign_size](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L899-L914) |
| Extensions can supply statistics, selectivity, and AM cost behavior | [selfuncs.h#statistics-hooks](../../../../raw/postgres-12/src/include/utils/selfuncs.h#L115-L125), [intarray/_int_selfuncs.c#_int_matchsel](../../../../raw/postgres-12/contrib/intarray/_int_selfuncs.c#L119-L238), [bloom/blcost.c#blcostestimate](../../../../raw/postgres-12/contrib/bloom/blcost.c#L20-L45) |
| Catalog IDs/attribute numbers and statistics syscaches have generated build plumbing | [catalog/Makefile#catalog-and-generated-headers](../../../../raw/postgres-12/src/backend/catalog/Makefile#L27-L57), [catalog/Makefile#genbki-rule](../../../../raw/postgres-12/src/backend/catalog/Makefile#L71-L101), [syscache.c#statistics-cache-definitions](../../../../raw/postgres-12/src/backend/utils/cache/syscache.c#L731-L773) |
| Regression coverage distinguishes collector monitoring from catalog-based planner estimates | [stats.sql#collector-results](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L154-L175), [stats_ext.sql#estimated-row-tests](../../../../raw/postgres-12/src/test/regress/sql/stats_ext.sql#L122-L218), [join_hash.sql#forced-relation-estimates](../../../../raw/postgres-12/src/test/regress/sql/join_hash.sql#L55-L84) |

## Open Questions

- None for PostgreSQL 12 core or the shipped modules at pinned commit `45b88269a353ad93744772791feb6d01bc7e1e42`.
- An external extension can install the documented hooks or define custom statistics/selectivity behavior. Its implementation is outside this pinned checkout and must be reviewed separately.

## Source References

- [system_views.sql#pg_stats-and-pg_stats_ext](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L189-L294) - user-facing statistics views.
- [system_views.sql#pg_stat_all_tables](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L552-L581) - cumulative monitoring view.
- [pgstatfuncs.c#table-counter-functions](../../../../raw/postgres-12/src/backend/utils/adt/pgstatfuncs.c#L40-L360) - collector-backed SQL functions.
- [pgstat.h#PgStat_StatTabEntry](../../../../raw/postgres-12/src/include/pgstat.h#L633-L662) - cumulative table entry.
- [selfuncs.c#get_actual_variable_range](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L5250-L5417) - planner histogram-endpoint probe.
- [nbtsearch.c#planner-visible-index-scan-count](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L758-L770) - B-tree counter increment reached by that probe.
- [planmain.c#query_planner](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L65-L271) - base planner sequence.
- [relnode.c#build_simple_rel](../../../../raw/postgres-12/src/backend/optimizer/util/relnode.c#L175-L293) - base relation construction.
- [plancat.c#get_relation_info](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L83-L463) - relation, index, extended-statistics, FDW, and FK loading.
- [heapam_handler.c#heapam_estimate_rel_size](../../../../raw/postgres-12/src/backend/access/heap/heapam_handler.c#L2072-L2171) - heap size estimate.
- [plancat.c#estimate_rel_size](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L926-L1061) - relation-kind dispatcher and index estimate.
- [pathnodes.h#planner-statistics-structures](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L632-L882) - `RelOptInfo`, `IndexOptInfo`, FK, and extended-statistics structures.
- [selfuncs.h#statistics-data-and-defaults](../../../../raw/postgres-12/src/include/utils/selfuncs.h#L30-L131) - defaults, `VariableStatData`, and hooks.
- [selfuncs.c#examine_variable](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4430-L4697) - expression/index statistics matching.
- [selfuncs.c#examine_simple_variable](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L4699-L4959) - plain and inherited column lookup and security.
- [pg_statistic.h#FormData_pg_statistic](../../../../raw/postgres-12/src/include/catalog/pg_statistic.h#L20-L126) - per-attribute catalog.
- [pg_statistic.h#slot-kinds](../../../../raw/postgres-12/src/include/catalog/pg_statistic.h#L136-L271) - core and extension slot contract.
- [plancat.c#get_relation_statistics](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L1289-L1377) - extended-statistics planner metadata.
- [extended_stats.c#build-and-store](../../../../raw/postgres-12/src/backend/statistics/extended_stats.c#L75-L187) - build and built-kind checks.
- [extended_stats.c#statext_clauselist_selectivity](../../../../raw/postgres-12/src/backend/statistics/extended_stats.c#L1169-L1202) - MCV/dependency order.
- [costsize.c#set_baserel_size_estimates](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4390-L4423) - base output rows, width, and qual cost.
- [costsize.c#get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4693-L4906) - FK selectivity substitution.
- [analyze.c#statistics-write-path](../../../../raw/postgres-12/src/backend/commands/analyze.c#L390-L640) - columns, indexes, extended data, relation stats, and collector report.
- [analyze.c#acquire_sample_rows](../../../../raw/postgres-12/src/backend/commands/analyze.c#L976-L1127) - ordinary sampling.
- [analyze.c#acquire_inherited_sample_rows](../../../../raw/postgres-12/src/backend/commands/analyze.c#L1169-L1390) - inheritance sampling.
- [analyze.c#update_attstats](../../../../raw/postgres-12/src/backend/commands/analyze.c#L1394-L1547) - `pg_statistic` writes.
- [vacuum.c#vac_update_relstats](../../../../raw/postgres-12/src/backend/commands/vacuum.c#L1135-L1196) - `pg_class` writes.
- [autovacuum.c#relation_needs_vacanalyze](../../../../raw/postgres-12/src/backend/postmaster/autovacuum.c#L2927-L3095) - indirect collector threshold.
- [tableam.h#relation_estimate_size](../../../../raw/postgres-12/src/include/access/tableam.h#L586-L603) - table-AM size callback.
- [allpaths.c#set_foreign_size](../../../../raw/postgres-12/src/backend/optimizer/path/allpaths.c#L899-L914) - FDW size callback.
- [postgres_fdw.c#postgresGetForeignRelSize](../../../../raw/postgres-12/contrib/postgres_fdw/postgres_fdw.c#L563-L720) - local/remote foreign estimates.
- [catalog/Makefile#generated-catalog-headers](../../../../raw/postgres-12/src/backend/catalog/Makefile#L27-L101) - `genbki.pl` and `*_d.h` build path.
- [syscache.c#statistics-cache-definitions](../../../../raw/postgres-12/src/backend/utils/cache/syscache.c#L731-L773) - statistics syscache keys.
- [stats_ext.sql#complete-test](../../../../raw/postgres-12/src/test/regress/sql/stats_ext.sql#L1-L554) - extended-statistics regression coverage.
- [stats.sql#complete-test](../../../../raw/postgres-12/src/test/regress/sql/stats.sql#L1-L178) - cumulative collector regression coverage.

## Navigation

- [PostgreSQL 12 index](../../index.md)
- [Foreign-Key Join Optimization for Two-Table Joins](fk-join-optimization-two-tables.md)
- [PostgreSQL versions](../../../versions.md)
