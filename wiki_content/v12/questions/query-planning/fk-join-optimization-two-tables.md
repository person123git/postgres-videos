---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: claude-fable-5 2026-06-10T18:48:46Z
---

# Foreign-Key Join Optimization for Two-Table Joins (unverified)

## Question

In PostgreSQL 12, produce a comprehensive analysis of how the query planner optimizes foreign-key joins in SQL queries that join two tables.

## Short Answer

In PostgreSQL 12 the planner does **not** use foreign-key (FK) constraints to choose a different join algorithm or rewrite away inner joins. FK information directly affects one planner decision: join row-count estimation.

When the join's equality clauses match an FK, [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709) replaces the per-clause independence estimate with `1 / referenced_table_tuples` for inner, left, and full joins. Related join-removal machinery can remove left joins or reduce semijoins when the inner side is provably unique, but that proof uses unique indexes or subquery distinctness, not FK metadata [join_is_removable](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L160) [reduce_unique_semijoins](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L511).

There is no FK-driven join-order change, no FK-driven algorithm choice (nested-loop / hash / merge), and no inner-join elimination. The FK affects the plan only through the cardinality estimate that path generation consumes [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709) [match_foreign_keys_to_quals](../../../../raw/postgres-12/src/backend/optimizer/plan/initsplan.c#L2413) [get_relation_foreign_keys](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L476).

## Detailed Answer

### Pipeline for a two-table join

For:

```sql
SELECT /* wiki_fk_join_demo */ *
FROM   orders  o
JOIN   customers c ON c.id = o.customer_id;
```

with `orders.customer_id REFERENCES customers(id)`, the planner runs these phases.

#### 1. Build `ForeignKeyOptInfo`s during catalog load

`get_relation_info` calls [get_relation_foreign_keys](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L476), which walks `RelationGetFKeyList(relation)` and creates one `ForeignKeyOptInfo` per `(referencing rel, referenced RTE)` pair seen in the query's range table. The result is appended to `root->fkey_list`.

Short-circuits inside [get_relation_foreign_keys](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L476):

- Skip if `rel->reloptkind != RELOPT_BASEREL`.
- Skip if `list_length(rtable) < 2` (single-table queries cannot benefit).
- Skip inheritance parents on the referencing side (`inhparent`).
- When scanning the range table for the referenced side, skip RTEs that are inheritance parents (`rte->inh`) — they don't really match the FK [plancat.c:541](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L541-L543).
- Skip self-referential FKs.

The data structure is [ForeignKeyOptInfo](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L845): per-column arrays for `conkey`, `confkey`, `conpfeqop`, plus the match bookkeeping (`nmatched_ec`, `nmatched_rcols`, `nmatched_ri`, `eclass[]`, `rinfos[]`) that gets filled in later.

#### 2. Match FK columns to query equalities

After equivalence-class (EC) generation and after join removal, `query_planner` calls [match_foreign_keys_to_quals](../../../../raw/postgres-12/src/backend/optimizer/plan/initsplan.c#L2413) [query_planner](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L55).

For each FK, for each FK column it tries:

- [match_eclasses_to_foreign_key_col](../../../../raw/postgres-12/src/backend/optimizer/path/equivclass.c#L2030): scan `root->eq_classes` for an EC containing both Vars whose `ec_opfamilies` matches the FK's `conpfeqop`. On a hit, set `eclass[colno]` and bump `nmatched_ec`.
- Otherwise, scan `con_rel->joininfo` for a "loose" binary `OpExpr` of the right shape (skipping `outerjoin_delayed` clauses) — used under outer joins where the equality cannot be promoted to an EC. Hits go into `rinfos[colno]` with `nmatched_rcols` / `nmatched_ri`.

Pruning rules:

- An FK is dropped if either side is not a `RELOPT_BASEREL` (covers inheritance otherrels and rels removed by join removal) [match_foreign_keys_to_quals](../../../../raw/postgres-12/src/backend/optimizer/plan/initsplan.c#L2413).
- After scanning, an FK is retained only if every FK column matched an EC or loose qual. This means a partially matched multicolumn FK is discarded in PostgreSQL 12 [match_foreign_keys_to_quals](../../../../raw/postgres-12/src/backend/optimizer/plan/initsplan.c#L2413).

#### 3. Apply FK selectivity in `calc_joinrel_size_estimate`

Every joinrel under consideration runs through [calc_joinrel_size_estimate](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4557), which calls [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709) before the normal `clauselist_selectivity`. The FK function peels matching clauses out of `restrictlist` and returns `fkselec` as a substitute estimate; remaining clauses still feed `clauselist_selectivity` to produce `jselec`.

Algorithm in [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709):

1. Skip the FK unless its `con_relid` and `ref_relid` straddle `outer_relids` and `inner_relids`.
2. For semi/anti joins, skip the FK if the referenced table is on the LHS, or the inner is more than one base rel.
3. Walk `restrictlist`. A clause matches an FK column if either:
   - its `parent_ec` equals `fkinfo->eclass[i]`, or
   - it is `list_member_ptr(fkinfo->rinfos[i], rinfo)`.

   Matches move into `removedlist`.
4. Sanity guard: if `length(removedlist) != fkinfo->nmatched_ec + fkinfo->nmatched_ri`, restore the clauses and skip this FK to avoid double-counting, for example when two FKs share one EC [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709).
5. Selectivity:
   - `JOIN_INNER` / `JOIN_LEFT` / `JOIN_FULL`: `fkselec *= 1.0 / Max(ref_rel->tuples, 1.0)` [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709).
   - `JOIN_SEMI` / `JOIN_ANTI` (only when the referenced table is the inner singleton): `fkselec *= ref_rel->rows / Max(ref_rel->tuples, 1.0)` [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709).

The final inner-join cardinality in [calc_joinrel_size_estimate](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4557) is:

$$
\text{nrows} = \text{outer\_rows} \cdot \text{inner\_rows} \cdot \text{fkselec} \cdot \text{jselec}
$$

clamped by `clamp_row_est`.

#### 4. Why this matters

For single-column FKs with current statistics, the FK estimate is usually close to what `eqjoinsel` would give from referenced-side MCVs / n-distinct. The dramatic improvement is for **multi-column FKs**, where `clauselist_selectivity` would multiply per-column selectivities under the independence assumption. The header comment of [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709) calls this out explicitly.

Caveats encoded in the same function:

- **NULL referencing columns are not derated.** May slightly overshoot when many FK columns are NULL.
- **Inheritance / partitioning.** The FK is treated as covering all children of an inheritance parent — fine on the referencing side, knowingly imperfect on the referenced side.

### Where FKs do not influence the plan

- **Join order / algorithm.** `add_paths_to_joinrel`, `make_join_rel`, GEQO and the dynamic-programming join search never read `fkey_list`. A source search finds `fkey_list` used for planner initialization, FK collection, FK matching, debug output, and FK selectivity, but not for join path construction or algorithm selection [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709) [match_foreign_keys_to_quals](../../../../raw/postgres-12/src/backend/optimizer/plan/initsplan.c#L2413) [get_relation_foreign_keys](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L476) [query_planner](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L55).
- **Inner-join elimination.** PostgreSQL 12 has no "trusted FK ⇒ drop the parent table" optimization. The planner's FK-specific path estimates selectivity; the uniqueness-driven removal path is limited to left joins and semijoins [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709) [join_is_removable](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L160) [reduce_unique_semijoins](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L511).
- **Outer-join removal.** [join_is_removable](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L160) succeeds on `LEFT JOIN customers ON c.id = o.customer_id` because `customers.id` is a unique key (PK), via `rel_supports_distinctness` / `rel_is_distinct_for`. The FK constraint is not consulted.
- **Semi-join reduction.** [reduce_unique_semijoins](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L511) likewise uses `innerrel_is_unique`, not FKs.
- The only reference from join-removal back to FK code is the comment that [match_foreign_keys_to_quals](../../../../raw/postgres-12/src/backend/optimizer/plan/initsplan.c#L2413) will later prune dead FKs, not the other way around [analyzejoins.c#remove_rel_from_query](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L441-L444).

### Optimizer pass ordering

From [query_planner](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L55):

1. `generate_base_implied_equalities` — finalize ECs.
2. `remove_useless_joins` — uniqueness-driven outer-join removal.
3. `reduce_unique_semijoins` — semi → inner where safe.
4. `match_foreign_keys_to_quals` — annotate and prune `root->fkey_list` (deferred until after join removal so dead rels' FKs are skipped).
5. Path generation in `make_one_rel`; every joinrel ultimately calls `calc_joinrel_size_estimate` → `get_foreign_key_join_selectivity`.

### Worked example (single-column FK, inner join)

Schema: `customers(id PK)` with N₁ rows; `orders(customer_id NOT NULL REFERENCES customers(id))` with N₂ rows.

- After [get_relation_foreign_keys](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L476): one entry, `con_relid = orders`, `ref_relid = customers`, `nkeys = 1`.
- After [match_foreign_keys_to_quals](../../../../raw/postgres-12/src/backend/optimizer/plan/initsplan.c#L2413): `c.id = o.customer_id` is in an EC with the right opfamily, so `eclass[0]` is set and `nmatched_ec = 1`.
- In [calc_joinrel_size_estimate](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4557) for `{orders, customers}`:
  - `get_foreign_key_join_selectivity` removes the clause and returns `fkselec = 1.0 / N₁`.
  - `jselec = 1.0`.
  - `JOIN_INNER`: `nrows = N₂ * N₁ * (1/N₁) * 1.0 = N₂` (then `clamp_row_est`).

The cardinality fingerprint of the FK is therefore `nrows ≈ N₂` regardless of column-stat quality.

Multi-column FKs traverse the same code; multiple per-column matches are required and `fkselec` stays at `1/N₁` rather than the product of per-column selectivities — that is the substantive win over `clauselist_selectivity`.

## Context Reviewed

- [ForeignKeyOptInfo](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L845)
- [get_relation_foreign_keys](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L476)
- [match_foreign_keys_to_quals](../../../../raw/postgres-12/src/backend/optimizer/plan/initsplan.c#L2413)
- [match_eclasses_to_foreign_key_col](../../../../raw/postgres-12/src/backend/optimizer/path/equivclass.c#L2030)
- [calc_joinrel_size_estimate](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4557)
- [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709)
- [query_planner](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L55)
- [join_is_removable](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L160) and [reduce_unique_semijoins](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L511)

## Evidence Map

| Claim | Source |
|---|---|
| FK info attached during base-rel info collection | [get_relation_foreign_keys](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L476) |
| Skip when single-RTE / non-baserel / inheritance parent | [get_relation_foreign_keys](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L476) |
| One `ForeignKeyOptInfo` per matching RTE pair; referenced-side inheritance-parent RTEs and self-FKs skipped | [get_relation_foreign_keys](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L476) [plancat.c:541](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L541-L543) |
| FK-to-clause matching uses EC then loose `joininfo` scan | [match_foreign_keys_to_quals](../../../../raw/postgres-12/src/backend/optimizer/plan/initsplan.c#L2413) |
| EC matching requires opfamily match | [match_eclasses_to_foreign_key_col](../../../../raw/postgres-12/src/backend/optimizer/path/equivclass.c#L2030) |
| Multicolumn FKs must match every column to be retained | [match_foreign_keys_to_quals](../../../../raw/postgres-12/src/backend/optimizer/plan/initsplan.c#L2413) |
| `get_foreign_key_join_selectivity` removes matched clauses, returns substitute | [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709) |
| Inner / left / full FK selectivity = `1 / ref_tuples` | [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709) |
| Semi / anti FK selectivity = `ref_rel->rows / ref_tuples` | [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709) |
| Sanity guard against double-counting when FKs share EC | [get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709) |
| FK matching ordered after join removal | [query_planner](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L55) |
| Outer-join removal uses uniqueness, not FK | [join_is_removable](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L160) |
| Semi → inner reduction uses uniqueness, not FK | [reduce_unique_semijoins](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L511) |

## Source References

- [pathnodes.h#ForeignKeyOptInfo](../../../../raw/postgres-12/src/include/nodes/pathnodes.h#L845) - FK planner metadata stored on `PlannerInfo`.
- [plancat.c#get_relation_foreign_keys](../../../../raw/postgres-12/src/backend/optimizer/util/plancat.c#L476) - catalog loading and FK short-circuit rules.
- [initsplan.c#match_foreign_keys_to_quals](../../../../raw/postgres-12/src/backend/optimizer/plan/initsplan.c#L2413) - FK-to-join-clause matching and pruning.
- [equivclass.c#match_eclasses_to_foreign_key_col](../../../../raw/postgres-12/src/backend/optimizer/path/equivclass.c#L2030) - equivalence-class matching for FK columns.
- [costsize.c#calc_joinrel_size_estimate](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4557) - join cardinality calculation site.
- [costsize.c#get_foreign_key_join_selectivity](../../../../raw/postgres-12/src/backend/optimizer/path/costsize.c#L4709) - FK selectivity replacement logic.
- [planmain.c#query_planner](../../../../raw/postgres-12/src/backend/optimizer/plan/planmain.c#L55) - planner pass ordering.
- [analyzejoins.c#join_is_removable](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L160) - uniqueness-based left-join removal.
- [analyzejoins.c#reduce_unique_semijoins](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L511) - uniqueness-based semijoin reduction.
- [analyzejoins.c#remove_rel_from_query](../../../../raw/postgres-12/src/backend/optimizer/plan/analyzejoins.c#L441-L444) - join-removal cleanup that leaves FK pruning to the later FK matching pass.

## Open Questions

- Whether any later v12 minor releases added FK-driven uniqueness shortcuts to `join_is_removable` / `innerrel_is_unique`. This page is pinned to commit `45b88269a353ad93744772791feb6d01bc7e1e42` (12.2) and was not checked against the full `REL_12_STABLE` history.
- NULL-fraction derating in multi-column FKs is intentionally omitted; the magnitude of the resulting overestimate has not been quantified here.

## Related Pages

- [v12/index](../../index.md)
- [versions](../../../versions.md)
