---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: claude-opus-5-max 2026-07-29T21:23:49Z
---

# Comprehensive plan_cache_mode Analysis in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [The GUC definition and apply scope](#the-guc-definition-and-apply-scope)
  - [Where the decision happens](#where-the-decision-happens)
  - [The eight decision rules in source order](#the-eight-decision-rules-in-source-order)
  - [What plan_cache_mode cannot override](#what-plan_cache_mode-cannot-override)
  - [The auto heuristic and its cost arithmetic](#the-auto-heuristic-and-its-cost-arithmetic)
  - [The correction step](#the-correction-step)
  - [Why parameter values change the plan](#why-parameter-values-change-the-plan)
  - [Key data structures](#key-data-structures)
  - [Callers that reach the decision](#callers-that-reach-the-decision)
  - [Invalidation keeps the cost history](#invalidation-keeps-the-cost-history)
  - [Generic plans lock every relation in the plan](#generic-plans-lock-every-relation-in-the-plan)
  - [Observability in PostgreSQL 12](#observability-in-postgresql-12)
  - [Error and edge paths](#error-and-edge-paths)
  - [Exact-pin measurements](#exact-pin-measurements)
  - [Practical guidance](#practical-guidance)
  - [Build and extension boundaries](#build-and-extension-boundaries)
  - [Tests](#tests)
  - [Source history](#source-history)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

What is a comprehensive analysis of plan_cache_mode in PostgreSQL 12?

## Answer

`plan_cache_mode` is a session-settable enum GUC that overrides one specific
decision: for each execution of a **cached plan**, does the backend run the
statement's *generic* plan (planned once, without parameter values) or build a
fresh *custom* plan (planned with this execution's parameter values)? The whole
policy lives in one static function,
[plancache.c#choose_custom_plan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1010-L1063),
which `GetCachedPlan` calls on every execution
([plancache.c#GetCachedPlan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1152-L1156)).

Three values are allowed, `auto` is the default, and the setting is read at
execution time rather than at `PREPARE` time
([guc.c#plan_cache_mode_options](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L429-L434),
[guc.c#plan_cache_mode](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4503-L4514),
[config.sgml#plan_cache_mode](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5393-L5410)).

| Value | Effect | Position in the rule order |
|---|---|---|
| `auto` (default) | Five custom plans, then a cost comparison decides each execution | Falls through to rules 7-8 |
| `force_generic_plan` | Generic plan, no cost comparison | Rule 4 |
| `force_custom_plan` | Custom plan, no cost comparison | Rule 5 |

Two facts about that table matter more than the values themselves:

1. `force_*` is checked **after** three unconditional rules, so it cannot
   override one-shot plans, parameterless statements, or transaction control
   statements
   ([plancache.c#choose_custom_plan-unconditional](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1020-L1029)).
2. Nothing in the setting affects statements that never enter the plan cache at
   all - the simple query protocol plans directly
   ([postgres.c#exec_simple_query-plan](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1143-L1144)),
   and SQL-level `DECLARE CURSOR` calls `pg_plan_query` itself
   ([portalcmds.c#PerformCursorOpen](../../../../raw/postgres-12/src/backend/commands/portalcmds.c#L91-L92)).

### The GUC definition and apply scope

| Property | Value | Evidence |
|---|---|---|
| Type | enum, values `auto`, `force_generic_plan`, `force_custom_plan` | [guc.c#plan_cache_mode_options](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L429-L434) |
| C variable | `int plan_cache_mode`, backed by the `PlanCacheMode` enum | [plancache.c:119](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L119), [plancache.h#PlanCacheMode](../../../../raw/postgres-12/src/include/utils/plancache.h#L26-L35) |
| Context | `PGC_USERSET` | [guc.c#plan_cache_mode](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4503-L4514) |
| Group | `QUERY_TUNING_OTHER` | [guc.c#plan_cache_mode](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4503-L4514) |
| Flags | `GUC_EXPLAIN`, so `EXPLAIN (SETTINGS)` reports it when non-default | [guc.c#plan_cache_mode](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4503-L4514), [explain.c#ExplainPrintSettings](../../../../raw/postgres-12/src/backend/commands/explain.c#L603-L664) |
| Default | `PLAN_CACHE_MODE_AUTO` | [guc.c#plan_cache_mode](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4511-L4513) |
| Sample file | commented-out `#plan_cache_mode = auto` | [postgresql.conf.sample:409-410](../../../../raw/postgres-12/src/backend/utils/misc/postgresql.conf.sample#L409-L410) |
| Check/validate hooks | none | [guc.c#plan_cache_mode](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4511-L4513) |

**Apply scope.** `PGC_USERSET` maps to session/transaction scope: `SET`,
`SET LOCAL`, `ALTER ROLE ... SET`, `ALTER DATABASE ... SET`, and libpq
`options=-c ...` all work, and **no restart is required**. A value placed in
`postgresql.conf` becomes the server-wide default after a **reload**; a session
that never issued its own `SET` picks the new default up on that reload, while a
local `SET` in the session wins over it (measured in
[Exact-pin measurements](#exact-pin-measurements)). Nothing about this setting
is `postmaster`-scoped.

The documentation states the timing rule explicitly: "This setting is considered
when a cached plan is to be executed, not when it is prepared."
([config.sgml#plan_cache_mode](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5407-L5409)).
The source backs it: `choose_custom_plan` reads the global on every
`GetCachedPlan` call
([plancache.c#choose_custom_plan-guc](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1031-L1035)).

### Where the decision happens

`GetCachedPlan` is the single decision point. Its documented contract is that
the caller cannot tell which kind of plan it will receive
([plancache.c#GetCachedPlan-comment](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1119-L1136)).
Per call it:

1. Revalidates the analyzed-and-rewritten query tree and takes parse-time locks
   ([plancache.c#GetCachedPlan-revalidate](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1152-L1153)).
2. Calls `choose_custom_plan`
   ([plancache.c#GetCachedPlan-choose](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1155-L1156)).
3. On "generic", reuses `plansource->gplan` if `CheckCachedPlan` says it is
   still valid and lockable
   ([plancache.c#GetCachedPlan-reuse](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1158-L1165),
   [plancache.c#CheckCachedPlan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L783-L858)),
   otherwise builds one with `boundParams = NULL`, caches it, records
   `generic_cost`, and re-runs the decision
   ([plancache.c#GetCachedPlan-build-generic](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1166-L1189)).
4. On "custom", plans with the actual parameter values and accumulates the cost
   counters
   ([plancache.c#GetCachedPlan-custom](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1211-L1221)).

Both plan kinds come from the same builder; the only difference passed down to
the planner is whether `boundParams` is `NULL`
([plancache.c#BuildCachedPlan-comment](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L860-L875),
[plancache.c#BuildCachedPlan-plan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L930-L933)).

### The eight decision rules in source order

`choose_custom_plan` returns `true` for a custom plan and `false` for a generic
plan. The first matching rule wins, so order is the whole story.

| # | Condition | Result | Evidence |
|---|---|---|---|
| 1 | `plansource->is_oneshot` | custom | [plancache.c:1020-1022](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1020-L1022) |
| 2 | `boundParams == NULL` | generic | [plancache.c:1024-1026](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1024-L1026) |
| 3 | `IsTransactionStmtPlan(plansource)` | generic | [plancache.c:1027-1029](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1027-L1029), [plancache.c#IsTransactionStmtPlan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L78-L84) |
| 4 | `plan_cache_mode == PLAN_CACHE_MODE_FORCE_GENERIC_PLAN` | generic | [plancache.c:1031-1033](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1031-L1033) |
| 5 | `plan_cache_mode == PLAN_CACHE_MODE_FORCE_CUSTOM_PLAN` | custom | [plancache.c:1034-1035](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1034-L1035) |
| 6 | `cursor_options & CURSOR_OPT_GENERIC_PLAN` / `CURSOR_OPT_CUSTOM_PLAN` | generic / custom | [plancache.c:1037-1041](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1037-L1041), [parsenodes.h#CURSOR_OPT_GENERIC_PLAN](../../../../raw/postgres-12/src/include/nodes/parsenodes.h#L2688-L2692) |
| 7 | `num_custom_plans < 5` | custom | [plancache.c:1043-1045](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1043-L1045) |
| 8 | `generic_cost < avg_custom_cost` | generic, else custom | [plancache.c:1047-1062](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1047-L1062) |

Notes on the less obvious rules:

- **Rule 3** is reachable only through the protocol. SQL `PREPARE` accepts only
  `SELECT`, `INSERT`, `UPDATE`, and `DELETE`
  ([gram.y#PreparableStmt](../../../../raw/postgres-12/src/backend/parser/gram.y#L10737-L10742)),
  and a transaction control statement has no parameters to bind, so rule 2
  normally fires first. The same macro also short-circuits revalidation,
  invalidation, and `ResetPlanCache` for those statements
  ([plancache.c#RevalidateCachedQuery-oneshot](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L564-L575),
  [plancache.c#ResetPlanCache](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1962-L2024)).
- **Rule 6** has no in-core setter in v12. `CURSOR_OPT_GENERIC_PLAN` and
  `CURSOR_OPT_CUSTOM_PLAN` are defined in `parsenodes.h`, read only by
  `choose_custom_plan`, and documented as an SPI-level door via
  `SPI_prepare_cursor`
  ([spi.sgml#SPI_execute_plan-notes](../../../../raw/postgres-12/doc/src/sgml/spi.sgml#L891-L905),
  [spi.sgml#SPI_prepare_cursor-notes](../../../../raw/postgres-12/doc/src/sgml/spi.sgml#L1029-L1037)).
  Plain `SPI_prepare` passes `cursorOptions = 0`
  ([spi.c#SPI_prepare](../../../../raw/postgres-12/src/backend/executor/spi.c#L673-L677)).
  An extension that sets these flags therefore wins over `plan_cache_mode`,
  because rule 6 is only reached when the GUC is `auto`.
- **Rule 7** hard-codes 5. There is no GUC for it
  ([plancache.c:1043-1045](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1043-L1045)).

### What plan_cache_mode cannot override

| Case | Actual behavior | Why | Evidence |
|---|---|---|---|
| One-shot plans (`SPI_execute`, `SPI_execute_with_args`, PL/pgSQL dynamic `EXECUTE ... USING`) | always custom, `force_generic_plan` ignored | rule 1 precedes the GUC | [plancache.c:1020-1022](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1020-L1022), [spi.c#_SPI_prepare_oneshot_plan](../../../../raw/postgres-12/src/backend/executor/spi.c#L2041-L2086), [spi.c#SPI_execute_with_args](../../../../raw/postgres-12/src/backend/executor/spi.c#L626-L671), [pl_exec.c#exec_stmt_dynexecute](../../../../raw/postgres-12/src/pl/plpgsql/src/pl_exec.c#L4343-L4355) |
| Statements with no parameters | always generic, `force_custom_plan` ignored | rule 2 precedes the GUC | [plancache.c:1024-1026](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1024-L1026), [prepare.sgml#generic-vs-custom](../../../../raw/postgres-12/doc/src/sgml/ref/prepare.sgml#L129-L139) |
| Extended-protocol Bind with zero parameters | same as above, because `params` stays `NULL` | `exec_bind_message` only builds a `ParamListInfo` when `numParams > 0` | [postgres.c#exec_bind_message-null-params](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1854-L1855) |
| PL/pgSQL simple expressions | always the generic plan | `SPI_plan_get_cached_plan` passes `boundParams = NULL` and asserts it got `gplan` | [spi.c#SPI_plan_get_cached_plan](../../../../raw/postgres-12/src/backend/executor/spi.c#L1821-L1824), [pl_exec.c#exec_eval_simple_expr](../../../../raw/postgres-12/src/pl/plpgsql/src/pl_exec.c#L6098-L6112) |
| Simple query protocol | no cached plan at all | `exec_simple_query` calls `pg_plan_queries` with `NULL` bound params | [postgres.c#exec_simple_query-plan](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1143-L1144) |
| SQL `DECLARE CURSOR` | no cached plan at all | `PerformCursorOpen` plans directly | [portalcmds.c#PerformCursorOpen](../../../../raw/postgres-12/src/backend/commands/portalcmds.c#L91-L92) |
| Unnamed protocol statements under `auto` | never reach rule 8 in practice | each `Parse` of the unnamed statement drops the previous one and builds a fresh `CachedPlanSource` with zeroed counters | [postgres.c#exec_parse_message-unnamed](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1368-L1384), [postgres.c#exec_parse_message-save](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1513-L1527), [plancache.c#CreateCachedPlan-init](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L213-L221) |

The last row is the one that surprises application developers: a driver that
uses the extended protocol without naming its prepared statements re-parses on
every execution, so the counter never reaches 5 and `auto` behaves like
`force_custom_plan`. `force_generic_plan` still works there, because rule 4 does
not consult the counters. Both halves are measured below.

### The auto heuristic and its cost arithmetic

Under `auto`, executions 1-5 of a parameterized statement are custom
(rule 7). From execution 6 on, the comparison is

```text
avg_custom_cost = total_custom_cost / num_custom_plans
use generic  <=>  generic_cost < avg_custom_cost
```

([plancache.c#choose_custom_plan-cost](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1047-L1062)).

The asymmetry is in how the two sides are computed. `cached_plan_cost` sums
`planTree->total_cost` over the non-utility statements in the plan list, and for
custom plans **only** it adds a planning-effort charge
([plancache.c#cached_plan_cost](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1065-L1117)):

```c
result += 1000.0 * cpu_operator_cost * (nrelations + 1);
```

([plancache.c:1110-1112](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1110-L1112)).

- `nrelations` is `list_length(plannedstmt->rtable)` of the *finished* plan, so a
  custom plan that pruned partitions away at plan time is also charged less
  ([plancache.c:1110](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1110)); the
  measured lock counts in
  [Exact-pin measurements](#exact-pin-measurements) show the same range-table
  difference from the other side.
- The generic side is called with `include_planner = false`
  ([plancache.c:1188-1189](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1188-L1189));
  the custom side with `true`
  ([plancache.c:1216-1220](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1216-L1220)).
- The source calls this "a very crude estimate of planning effort" and notes the
  `1000 * cpu_operator_cost` multiplier "is probably on the low side"
  ([plancache.c#cached_plan_cost-comment](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1089-L1109)).
- `num_custom_plans` stops accumulating at `INT_MAX`, which freezes the average
  rather than overflowing it
  ([plancache.c:1216-1220](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1216-L1220)).
- Because `cpu_operator_cost` is itself a `PGC_USERSET` GUC, raising it inflates
  the charge and biases `auto` toward generic plans; the measurement section
  shows that flip.

Worked example at the pin, using the `plancache` regression fixture (1000 rows
with `a = 1`, one row with `a = 2`, index on `a`, one range-table entry, default
`cpu_operator_cost = 0.0025`, so the charge is `1000 * 0.0025 * 2 = 5.00`):

| Executions use | Custom `total_cost` | Charged custom cost | `generic_cost` | Rule 8 | Observed at execution 6 |
|---|---|---|---|---|---|
| `a = 1` (1000 rows) | 20.02 | 25.02 | 18.77 | `18.77 < 25.02` -> generic | generic (`Filter: (a = $1)`) |
| `a = 2` (1 row) | 8.30 | 13.30 | 18.77 | `18.77 >= 13.30` -> custom | custom (`Index Cond: (a = 2)`) |

The `a = 1` row reproduces the in-tree test
([plancache.out#plan_cache_mode](../../../../raw/postgres-12/src/test/regress/expected/plancache.out#L281-L357)).
The documentation summarizes the same rule less precisely, as the generic plan
being used "if its cost is not so much higher than the average custom-plan cost
as to make repeated replanning seem preferable"
([prepare.sgml#auto-heuristic](../../../../raw/postgres-12/doc/src/sgml/ref/prepare.sgml#L141-L152));
in code the comparison is strict `<` against an average that already contains
the replanning charge.

### The correction step

At the first execution that reaches rule 8, `generic_cost` is still the initial
`-1` sentinel
([plancache.c#CreateCachedPlan-init](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L213-L221)),
so the comparison always prefers generic - the source comment says so
([plancache.c:1049-1060](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1049-L1060)).
`GetCachedPlan` therefore builds the generic plan, caches it, sets
`generic_cost` from it, and immediately re-runs `choose_custom_plan`; if the
real number says custom, it discards the decision and plans again with
parameters
([plancache.c#GetCachedPlan-correction](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1188-L1207)).
The comment names the purpose: avoid "actually execut[ing]" a generic plan that
is a loser when custom plans are "consistently big winners"
([plancache.c:1191-1199](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1191-L1199)).

Three consequences worth knowing:

- The generic plan is built and kept even when it is never executed. It stays
  linked in `plansource->gplan` with a refcount
  ([plancache.c:1168-1174](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1168-L1174)).
  A later `force_generic_plan` can execute that already-cached plan without
  replanning, which is why a plan built under different session settings can
  reappear later; this is measured below.
- Execution 6 of a custom-favoring statement pays for two planner runs.
- After that, `generic_cost` is known, so rule 8 answers without rebuilding
  anything.

### Why parameter values change the plan

A custom plan is not merely "planned again" - the parameter values become
constants. `BuildCachedPlan` forwards `boundParams` to `pg_plan_queries`
([plancache.c#BuildCachedPlan-plan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L930-L933)),
and `eval_const_expressions` replaces a `PARAM_EXTERN` `Param` with a `Const`
when the value is present and flagged `PARAM_FLAG_CONST`
([clauses.c#eval_const_expressions_mutator-Param](../../../../raw/postgres-12/src/backend/optimizer/util/clauses.c#L2339-L2400)).
Every in-core caller sets that flag:

| Caller | Flag site |
|---|---|
| Extended protocol `Bind` | [postgres.c#exec_bind_message-const](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1846-L1851) |
| SQL `EXECUTE` / `EXPLAIN EXECUTE` | [prepare.c#EvaluateParams](../../../../raw/postgres-12/src/backend/commands/prepare.c#L396-L410) |
| SPI with argument arrays | [spi.c#_SPI_convert_params](../../../../raw/postgres-12/src/backend/executor/spi.c#L2440-L2466) |
| PL/pgSQL variables | [pl_exec.c#plpgsql_param_fetch](../../../../raw/postgres-12/src/pl/plpgsql/src/pl_exec.c#L6375-L6380) |

Selectivity estimation is where this pays off: with a `Const` the planner takes
the MCV-aware `var_eq_const` path, and without one it falls back to
`var_eq_non_const`
([selfuncs.c#eqsel_internal](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L264-L278),
[selfuncs.c#var_eq_non_const](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L437-L445)).
That is exactly the 1000-versus-500-row difference in the worked example above:
the generic plan estimates the skewed `a = 1` predicate at half the table.
`BuildCachedPlan`'s own comment states the weaker fallback - without
`PARAM_FLAG_CONST` "the planner will treat the value as a hint rather than a
hard constant"
([plancache.c#BuildCachedPlan-comment](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L860-L875)).

For partitioned tables the difference is structural rather than statistical: a
custom plan prunes at plan time and can collapse to a single scan, while a
generic plan keeps an `Append` and prunes at run time, reporting
`Subplans Removed`
([partition_prune.out#force_generic_plan](../../../../raw/postgres-12/src/test/regress/expected/partition_prune.out#L3843-L3857)).

### Key data structures

| Field | Meaning | Evidence |
|---|---|---|
| `CachedPlanSource.is_oneshot` | rule 1; also disables revalidation and invalidation | [plancache.h#CachedPlanSource](../../../../raw/postgres-12/src/include/utils/plancache.h#L118-L130), [plancache.c#CreateOneShotCachedPlan-init](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L280-L288) |
| `CachedPlanSource.cursor_options` | rule 6 input, set by `CompleteCachedPlan` | [plancache.h#CachedPlanSource-cursor_options](../../../../raw/postgres-12/src/include/utils/plancache.h#L101-L106), [plancache.c:426](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L426) |
| `CachedPlanSource.gplan` | the cached generic plan, or `NULL` | [plancache.h#CachedPlanSource-gplan](../../../../raw/postgres-12/src/include/utils/plancache.h#L117-L118) |
| `CachedPlanSource.generic_cost` | last generic plan cost, `-1` when unknown | [plancache.h#CachedPlanSource](../../../../raw/postgres-12/src/include/utils/plancache.h#L127-L130) |
| `CachedPlanSource.total_custom_cost` | running sum of charged custom costs | [plancache.h#CachedPlanSource](../../../../raw/postgres-12/src/include/utils/plancache.h#L127-L130) |
| `CachedPlanSource.num_custom_plans` | rule 7 counter and the averaging divisor | [plancache.h#CachedPlanSource](../../../../raw/postgres-12/src/include/utils/plancache.h#L127-L130) |
| `CachedPlan.is_valid` / `saved_xmin` | generic-plan reuse gates checked by `CheckCachedPlan` | [plancache.h#CachedPlan](../../../../raw/postgres-12/src/include/utils/plancache.h#L143-L157), [plancache.c#CheckCachedPlan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L783-L858) |
| `CachedPlan.generation` | bumped for every plan built, generic or custom; PL/pgSQL uses it to notice a replan | [plancache.c:1002-1003](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1002-L1003), [pl_exec.c#exec_eval_simple_expr-generation](../../../../raw/postgres-12/src/pl/plpgsql/src/pl_exec.c#L6114-L6121) |
| `CachedPlan.planRoleId` / `dependsOnRole` | a generic plan is invalidated when the role changes and the plan depends on it | [plancache.c#CheckCachedPlan-role](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L808-L813), [plancache.c#BuildCachedPlan-role](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L969-L988) |
| `PlanCacheMode` | the enum behind the GUC | [plancache.h#PlanCacheMode](../../../../raw/postgres-12/src/include/utils/plancache.h#L26-L32) |

`CopyCachedPlan` copies the three heuristic fields along with the statement, so
a copied plan source inherits the decision history
([plancache.c#CopyCachedPlan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1396-L1399)).

### Callers that reach the decision

| Path | Call site | Parameters | Notes |
|---|---|---|---|
| Extended protocol `Bind` | [postgres.c#exec_bind_message-getplan](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1871-L1876) | `params`, `NULL` if none | named statements accumulate counters; unnamed ones do not |
| `EXECUTE`, `CREATE TABLE AS EXECUTE` | [prepare.c#ExecuteQuery](../../../../raw/postgres-12/src/backend/commands/prepare.c#L245-L247) | `paramLI` from `EvaluateParams` | |
| `EXPLAIN EXECUTE` | [prepare.c#ExplainExecuteQuery](../../../../raw/postgres-12/src/backend/commands/prepare.c#L662-L666) | same | counts as an execution, so `EXPLAIN` advances the 5-plan counter |
| SPI saved plans, PL/pgSQL static SQL | [spi.c#_SPI_execute_plan](../../../../raw/postgres-12/src/backend/executor/spi.c#L2211-L2216) | `paramLI` | `plan->saved` decides resource-owner bookkeeping |
| PL/pgSQL simple expressions | [spi.c#SPI_plan_get_cached_plan](../../../../raw/postgres-12/src/backend/executor/spi.c#L1821-L1824) | always `NULL` | generic only |
| SPI one-shot | [spi.c#_SPI_prepare_oneshot_plan](../../../../raw/postgres-12/src/backend/executor/spi.c#L2041-L2086) | `paramLI` | custom only |

The documentation for both user-visible entry points matches this: `PREPARE`
describes the five-execution rule
([prepare.sgml#auto-heuristic](../../../../raw/postgres-12/doc/src/sgml/ref/prepare.sgml#L141-L152)),
and the SPI notes describe the same behavior for `SPI_execute_plan`
([spi.sgml#SPI_execute_plan-notes](../../../../raw/postgres-12/doc/src/sgml/spi.sgml#L891-L905)).
PL/pgSQL's manual states the practical consequence of the one-shot rule: a
dynamic `EXECUTE` "will re-plan the command on each execution", unlike a static
statement where PL/pgSQL "may otherwise create a generic plan and cache it"
([plpgsql.sgml#execute-replans](../../../../raw/postgres-12/doc/src/sgml/plpgsql.sgml#L1253-L1267)).

### Invalidation keeps the cost history

Plan invalidation does **not** reset the heuristic. `RevalidateCachedQuery`
rebuilds the query tree and says so in a comment: "we do not reset generic_cost
or total_custom_cost ... we're better retaining our hard-won knowledge about the
relative costs"
([plancache.c#RevalidateCachedQuery-retain](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L768-L775)).
`ResetPlanCache`, which backs `DISCARD PLANS` and `DISCARD ALL`, only flips
`is_valid` on the query tree and the generic plan
([plancache.c#ResetPlanCache](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1962-L2024),
[discard.c#DiscardCommand](../../../../raw/postgres-12/src/backend/commands/discard.c#L27-L54),
[discard.c#DiscardAll](../../../../raw/postgres-12/src/backend/commands/discard.c#L56-L78)).

So a statement that has settled on a generic plan keeps choosing generic after
`ANALYZE`, after DDL, and after `DISCARD PLANS`. The only ways back to the
five-custom-plan warmup are a new `CachedPlanSource` - `DEALLOCATE` plus
`PREPARE`, a new session, a re-`Parse` of the statement name - or a
session-scoped `force_custom_plan`. All four behaviors are measured below.

### Generic plans lock every relation in the plan

Reusing a generic plan still costs one lock per relation in the cached plan's
range table, taken on each execution by `AcquireExecutorLocks`
([plancache.c#AcquireExecutorLocks](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1555-L1604)),
using the rewriter-recorded `rte->rellockmode`
([plancache.c:1585-1601](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1585-L1601)).
Run-time pruning removes subplans from execution, not range-table entries from
the plan, so the locks stay. On a four-partition table at the pin, a custom plan
took 2 relation locks and the generic plan took 5 (see
[Exact-pin measurements](#exact-pin-measurements)).

This is the main hidden cost of `force_generic_plan` on wide partition sets, and
it is separate from planning time.

### Observability in PostgreSQL 12

| Question | How to answer it in v12 | Evidence |
|---|---|---|
| Which plan kind did this execution use? | `EXPLAIN EXECUTE`: a generic plan shows `$n`, a custom plan shows the values | [prepare.sgml#explain-execute](../../../../raw/postgres-12/doc/src/sgml/ref/prepare.sgml#L164-L173) |
| Is the setting active? | `EXPLAIN (SETTINGS)`, because the GUC carries `GUC_EXPLAIN` | [guc.c#plan_cache_mode](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4503-L4514), [explain.c#ExplainPrintSettings](../../../../raw/postgres-12/src/backend/commands/explain.c#L603-L664) |
| How much planning did this execution cost? | `EXPLAIN (ANALYZE) EXECUTE` reports `Planning Time` measured around statement lookup, parameter evaluation, and `GetCachedPlan` | [prepare.c#ExplainExecuteQuery-planstart](../../../../raw/postgres-12/src/backend/commands/prepare.c#L633-L666) |
| How many custom plans has this statement built? | **not exposed.** `pg_prepared_statements` has five columns and no plan counters | [prepare.c#pg_prepared_statement](../../../../raw/postgres-12/src/backend/commands/prepare.c#L723-L737), [system_views.sql#pg_prepared_statements](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L332-L333) |

The counter gap matters for tuning: `generic_cost`, `total_custom_cost`, and
`num_custom_plans` are backend-private struct fields with no SQL surface
([plancache.h#CachedPlanSource](../../../../raw/postgres-12/src/include/utils/plancache.h#L127-L130)),
so `EXPLAIN EXECUTE` output is the only in-core evidence of which way a
statement went.

### Error and edge paths

| Path | Behavior | Evidence |
|---|---|---|
| Invalid enum value | `ERROR: invalid value for parameter "plan_cache_mode"` with a `HINT` listing the three values | [guc.c#plan_cache_mode_options](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L429-L434), measured below |
| `useResOwner` on an unsaved plan source | `elog(ERROR, "cannot apply ResourceOwner to non-saved cached plan")` | [plancache.c:1148-1150](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1148-L1150) |
| `EXPLAIN EXECUTE` of a variable-result plan | `elog(ERROR, "EXPLAIN EXECUTE does not support variable-result cached plans")` | [prepare.c:641-643](../../../../raw/postgres-12/src/backend/commands/prepare.c#L641-L643) |
| Invalidation observed while building the rejected generic plan | `BuildCachedPlan` redoes `RevalidateCachedQuery` rather than trusting the stale tree | [plancache.c#BuildCachedPlan-revalidate](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L888-L902) |
| Generic plan invalid at reuse time | `CheckCachedPlan` releases the locks it just took and returns false, forcing a rebuild | [plancache.c#CheckCachedPlan-race](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L838-L857) |
| `num_custom_plans` at `INT_MAX` | counters stop moving; the average freezes | [plancache.c:1216-1220](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1216-L1220) |

### Exact-pin measurements

Environment: one isolated PostgreSQL 12.2 server built from this page's pinned
commit `45b88269a353ad93744772791feb6d01bc7e1e42`, with `contrib/auto_explain`
installed from the same build tree so nested PL/pgSQL and protocol-level plans
could be read from the server log. Fixtures follow the in-tree `plancache`
fixture (1000 rows `a = 1`, one row `a = 2`, index on `a`)
([plancache.sql#plan_cache_mode](../../../../raw/postgres-12/src/test/regress/sql/plancache.sql#L181-L212)).
Data directory, scripts, and logs remain under `.wiki-runtime/`; the server was
stopped afterwards.

**1. The switch happens exactly at execution 6, and `EXPLAIN` counts.** Six
`EXPLAIN EXECUTE pp(1)` calls: the first five printed
`Seq Scan on test_mode ... Filter: (a = 1)` under an `Aggregate` costed
`20.01..20.02`, the sixth printed `Filter: (a = $1)` under an `Aggregate` costed
`18.76..18.77` with `rows=500` on the scan. Charged custom cost
`20.02 + 5.00 = 25.02` versus `generic_cost = 18.77` matches rule 8, and the
switch on the sixth `EXPLAIN` shows that `EXPLAIN EXECUTE` itself advances the
counter.

**2. A selective parameter keeps custom plans forever.** With `pp(2)`, the
custom plan is `Index Only Scan ... Index Cond: (a = 2)` at `8.29..8.30`
(charged `13.30`), so `18.77 >= 13.30` and executions 6-8 stayed custom.

**3. The rejected generic plan is really built and cached.** Continuing that
session: `set enable_seqscan = off; set plan_cache_mode = force_generic_plan;`
returned the cached `Seq Scan ... Filter: (a = $1)` plan at `18.76..18.77` -
a plan the planner cannot produce with sequential scans disabled. A freshly
prepared control statement under the same settings produced
`Index Only Scan ... Index Cond: (a = $1)` at `28.27..28.29`. The stale Seq Scan
therefore came from execution 6 of the earlier run, where it was built,
priced, cached, and then not executed.

**4. `force_custom_plan` cannot replan a parameterless statement.** After a
first execution cached the generic `Index Only Scan`, disabling
`enable_indexscan`, `enable_indexonlyscan`, and `enable_bitmapscan` and setting
`force_custom_plan` still returned the cached `Index Only Scan`; a newly
prepared control statement under the same settings returned `Seq Scan`.

**5. PL/pgSQL static SQL follows the same counter.** A function whose body runs
`select count(*) from test_mode where a = p` logged `Filter: (a = 1)` for calls
1-5 and `Filter: (a = $1)` for calls 6-7.

**6. PL/pgSQL dynamic `EXECUTE ... USING` ignores `force_generic_plan`.** Six
calls with `plan_cache_mode = force_generic_plan` all logged `Filter: (a = 1)`,
confirming the one-shot rule wins.

**7. Invalidation keeps the decision; a new plansource resets it.** After the
statement settled on generic: `DISCARD PLANS` -> still generic;
`ANALYZE test_mode` -> still generic; `DEALLOCATE` plus `PREPARE` -> custom
`Index Only Scan` again.

**8. The planning charge alone can select the generic plan.** With
`cpu_operator_cost = 1` the charge becomes `1000 * 1 * 2 = 2000`. The custom
plan cost `120.02..120.03`, so the charged average was about `2120`, while the
generic plan cost `1135.50..1135.51`; execution 6 switched to generic
(`Index Cond: (a = $1)`, `rows=500`) even though the custom plan was the cheaper
one to execute. The same statement at the default `cpu_operator_cost` stayed
custom.

**9. Protocol shape decides whether `auto` ever reaches rule 8.** `pgbench` on
one connection with a parameterized query, eight transactions per run (four for
the last row):

| Mode | Logged plans | Reading |
|---|---|---|
| `-M prepared` | 5 x `Filter: (a = 1)`, then 3 x `Filter: (a = $1)` | named statement, counters accumulate |
| `-M extended` | 8 x `Filter: (a = 1)` | unnamed statement re-parsed each execution |
| `-M simple` | 8 x `Filter: (a = 1)` | no cached plan |
| `-M extended` + `force_generic_plan` | 4 x `Filter: (a = $1)` | rule 4 needs no counters |

**10. Generic plans lock every partition.** On a four-partition range table with
`prepare pq (int) as select count(*) from pcm_part where id = $1`, inside one
transaction:

| Mode | Plan | Relation locks held |
|---|---|---|
| `force_custom_plan` | `Seq Scan on pcm_part2`, `Filter: (id = 150)` | `pcm_part`, `pcm_part2` |
| `force_generic_plan` | `Append`, `Subplans Removed: 3` | `pcm_part`, `pcm_part1`, `pcm_part2`, `pcm_part3`, `pcm_part4` |

All locks were `AccessShareLock`.

**11. Planning time saved by a generic plan.** For a six-way join with one
parameter, `EXPLAIN (ANALYZE) EXECUTE` reported:

| Mode | `Planning Time` per execution | `Execution Time` |
|---|---|---|
| `force_custom_plan` | 0.556 ms, 0.690 ms, 0.664 ms | 0.092 / 0.068 / 0.059 ms |
| `force_generic_plan` | 0.602 ms, then 0.007 ms, 0.006 ms | 0.050 / 0.052 / 0.050 ms |

Planning dominated execution for this statement, and the generic plan removed
about 0.65 ms of work per execution after the first.

**12. But a wide partition set can make `auto` and `force_custom_plan`
identical.** On a 64-partition table, `auto` stayed custom at execution 6
(single pruned `Seq Scan`, `Filter: (id = 500)`) because the generic `Append`
over 64 partitions is estimated far above the average custom cost; forcing
generic produced `Subplans Removed: 63`. Four-second `pgbench -M prepared` runs
on one connection measured 13374 tps / 0.075 ms with `auto`, 13684 tps /
0.073 ms with `force_custom_plan`, and 14386 tps / 0.070 ms with
`force_generic_plan` - a much smaller margin than the join case, and paid for by
locking all 64 partitions on each execution instead of the single surviving one,
by the mechanism measured in item 10.

**13. Every fenced SQL block on this page ran clean.** The two snippets in
[Practical guidance](#practical-guidance) were executed verbatim at the pin
against the four-partition fixture with `ON_ERROR_STOP=1` and finished with exit
status 0; `EXPLAIN (SETTINGS, COSTS OFF) EXECUTE pq(150)` printed no `Settings:`
line while `plan_cache_mode` was at its default, matching `GUC_EXPLAIN`
non-default-only reporting.

**14. GUC mechanics.** `pg_settings` reported
`context = user`, `vartype = enum`,
`enumvals = {auto,force_generic_plan,force_custom_plan}`, `boot_val = auto`.
`set plan_cache_mode = 'bogus'` failed with
`ERROR: invalid value for parameter "plan_cache_mode": "bogus"` and
`HINT: Available values: auto, force_generic_plan, force_custom_plan.`
`EXPLAIN (SETTINGS)` printed
`Settings: plan_cache_mode = 'force_generic_plan'` while set and omitted the
line after `RESET`. Adding the setting to `postgresql.conf` and calling
`pg_reload_conf()` changed the value in an already-open session that had never
set it locally; a later local `SET` overrode it and survived a further reload.

### Practical guidance

Start from the observation that `auto` is usually right, then treat the two
force modes as targeted, session-scoped overrides. All three values are
`PGC_USERSET`, so prefer `SET`/`SET LOCAL` around the affected statements over a
server-wide default; a `postgresql.conf` change needs only a reload, but it
applies to every statement in every session that has not set its own value
([guc.c#plan_cache_mode](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4503-L4514)).

Use `force_custom_plan` when:

- Parameter values decide the plan - skewed distributions, `LIKE`-style range
  predicates, or partition keys - because only a custom plan folds the value to
  a `Const` and gets MCV-based selectivity
  ([clauses.c#eval_const_expressions_mutator-Param](../../../../raw/postgres-12/src/backend/optimizer/util/clauses.c#L2339-L2400),
  [selfuncs.c#eqsel_internal](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L264-L278)).
- You want plan-time partition pruning and the smaller lock footprint it brings
  ([plancache.c#AcquireExecutorLocks](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1555-L1604)).
- Cost: one planner run per execution, measured at roughly 0.65 ms for a
  six-way join at the pin.

Use `force_generic_plan` when:

- Planning cost dominates and the plan shape does not depend on the values -
  the measured six-way join dropped from about 0.65 ms of planning per execution
  to about 0.006 ms.
- The generic plan's estimate is misleadingly high, which is exactly the case
  the documentation names for this mode
  ([prepare.sgml#force-modes](../../../../raw/postgres-12/doc/src/sgml/ref/prepare.sgml#L154-L162)).
- Costs: no parameter folding, run-time instead of plan-time pruning, and one
  lock per relation left in the plan on every execution.

Operational notes:

- The 5-execution threshold and the `1000 * cpu_operator_cost * (nrelations + 1)`
  charge are not tunable
  ([plancache.c:1043-1045](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1043-L1045),
  [plancache.c:1110-1112](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1110-L1112)).
  `cpu_operator_cost` moves the charge but also re-prices every plan, so it is
  not a safe proxy knob.
- `DISCARD PLANS` frees cached plans but not the decision history; use
  `DEALLOCATE` plus `PREPARE`, or a new session, to restart the warmup
  ([plancache.c#RevalidateCachedQuery-retain](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L768-L775)).
- If an application uses the extended protocol without named statements, the
  `auto` heuristic never advances; `force_generic_plan` is the only way to get
  plan reuse there, and it still re-parses and re-analyzes each time
  ([postgres.c#exec_parse_message-unnamed](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1368-L1384)).

Verified session-scoped snippets at the pin. `plan_cache_mode`,
`statement_timeout`, and `lock_timeout` are all `PGC_USERSET`, so none of this
needs a restart or a reload
([guc.c#plan_cache_mode](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4503-L4514),
[guc.c#statement_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2386),
[guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2388-L2397)):

```sql
SET /* wiki_pcm_session_guard */ statement_timeout = '30s';
SET /* wiki_pcm_session_guard */ lock_timeout = '5s';

-- Which plan kind is this statement getting right now?
EXPLAIN /* wiki_pcm_inspect_plan */ (SETTINGS, COSTS OFF) EXECUTE pq(150);

-- Force a per-execution custom plan for one transaction only.
BEGIN;
SET LOCAL /* wiki_pcm_force_custom */ plan_cache_mode = force_custom_plan;
EXECUTE /* wiki_pcm_force_custom */ pq(150);
COMMIT;

-- Restart the five-execution warmup for one statement.
DEALLOCATE /* wiki_pcm_reset_history */ pq;
```

`pg_settings` confirms the scope before any change:

```sql
SET /* wiki_pcm_scope_check */ statement_timeout = '30s';
SET /* wiki_pcm_scope_check */ lock_timeout = '5s';

SELECT /* wiki_pcm_scope_check */ name, setting, context, vartype, enumvals, boot_val
  FROM pg_settings
 WHERE name IN ('plan_cache_mode', 'cpu_operator_cost');
```

### Build and extension boundaries

- No catalog, parser, or generated-header change is involved: the GUC is a plain
  `config_enum` entry, and `guc.c` reaches the variable by including
  `utils/plancache.h`
  ([guc.c:90](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L90),
  [plancache.h#PlanCacheMode](../../../../raw/postgres-12/src/include/utils/plancache.h#L26-L35)).
- The tree carries a consistency script that compares `guc.c` against
  `postgresql.conf.sample`, which is why a new GUC needs the sample entry
  ([check_guc:1-40](../../../../raw/postgres-12/src/backend/utils/misc/check_guc#L1-L40),
  [postgresql.conf.sample:409-410](../../../../raw/postgres-12/src/backend/utils/misc/postgresql.conf.sample#L409-L410)).
- SQL visibility comes from the generic `pg_settings` machinery, not from a
  dedicated view; `pg_prepared_statements` exposes no plan-choice columns
  ([system_views.sql#pg_prepared_statements](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L332-L333)).
- Extension surface: an extension can set the GUC like any other
  `PGC_USERSET` value, or bypass it entirely for its own SPI statements by
  passing `CURSOR_OPT_GENERIC_PLAN` / `CURSOR_OPT_CUSTOM_PLAN` to
  `SPI_prepare_cursor`, which rule 6 honours only when the GUC is `auto`
  ([spi.sgml#SPI_prepare_cursor-notes](../../../../raw/postgres-12/doc/src/sgml/spi.sgml#L1029-L1037),
  [plancache.c:1037-1041](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1037-L1041)).
- No shipped contrib module in the pinned tree references `plan_cache_mode`.

### Tests

| Coverage | Location |
|---|---|
| The only direct test: custom for the first executions, `force_generic_plan`, the 5-execution switch, then `force_custom_plan` | [plancache.sql#plan_cache_mode](../../../../raw/postgres-12/src/test/regress/sql/plancache.sql#L181-L212), [plancache.out#plan_cache_mode](../../../../raw/postgres-12/src/test/regress/expected/plancache.out#L281-L357) |
| `force_generic_plan` used as a tool to exercise executor run-time pruning | [partition_prune.out#exec-pruning](../../../../raw/postgres-12/src/test/regress/expected/partition_prune.out#L2511-L2559), [partition_prune.out#force_generic_plan](../../../../raw/postgres-12/src/test/regress/expected/partition_prune.out#L3843-L3865) |

Explicit gaps in the pinned tree: no test covers rule 1 (one-shot plans ignoring
`force_generic_plan`), rule 2 (parameterless statements ignoring
`force_custom_plan`), rule 3, rule 6 (`CURSOR_OPT_*`), the correction step in
`GetCachedPlan`, the retention of `generic_cost` across invalidation, or the
PL/pgSQL and protocol paths. There is no isolation spec and no TAP test naming
the setting; the measurements above stand in for that coverage.

### Source history

All five commits below are ancestors of the pin.

| Commit | Date | Subject | Relevance |
|---|---|---|---|
| `e6faf910d75` | 2011-09-16 | Redesign the plancache mechanism for more flexibility and efficiency | origin of the `num_custom_plans < 5` rule and the cost comparison the GUC later overrides |
| `f7cb2842bf4` | 2018-07-16 | Add plan_cache_mode setting | introduced the GUC, the enum, and the two force rules; credited to Pavel Stehule in the v12 release notes ([release-12.sgml#plan_cache_mode](../../../../raw/postgres-12/doc/src/sgml/release-12.sgml#L3666-L3681)) |
| `f9fe269ca21` | 2018-08-22 | Provide plan_cache_mode options in postgresql.conf.sample | added the sample-file entry now at [postgresql.conf.sample:409-410](../../../../raw/postgres-12/src/backend/utils/misc/postgresql.conf.sample#L409-L410) |
| `9b6fb9fbb48` | 2018-11-04 | Fix ExecuteCallStmt to not scribble on the passed-in parse tree | a plan-cache-adjacent fix whose message notes the bug was easy to exhibit "by messing with plan_cache_mode" |
| `ca0b3828504` | 2019-09-30 | Doc: improve PREPARE documentation, cross-referencing to plan_cache_mode | produced the `PREPARE` notes cited above ([prepare.sgml#auto-heuristic](../../../../raw/postgres-12/doc/src/sgml/ref/prepare.sgml#L141-L162)) |

The heuristic predates the GUC by seven years: `e6faf910d75` introduced the
5-plan rule and the cost comparison, `f7cb2842bf4` only added rules 4 and 5 in
front of them, and no later `plancache.c` commit in the pinned history changes
the policy
([plancache.c#choose_custom_plan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1010-L1063)).

## Context Reviewed

- Pinned checkout `raw/postgres-12/` at commit
  `45b88269a353ad93744772791feb6d01bc7e1e42` (Stamp 12.2).
- `src/backend/utils/cache/plancache.c` in full: `CreateCachedPlan`,
  `CreateOneShotCachedPlan`, `CompleteCachedPlan`, `SaveCachedPlan`,
  `ReleaseGenericPlan`, `RevalidateCachedQuery`, `CheckCachedPlan`,
  `BuildCachedPlan`, `choose_custom_plan`, `cached_plan_cost`, `GetCachedPlan`,
  `CopyCachedPlan`, `AcquireExecutorLocks`, the three inval callbacks, and
  `ResetPlanCache`.
- `src/include/utils/plancache.h`: `PlanCacheMode`, `CachedPlanSource`,
  `CachedPlan`, `CachedExpression`.
- `src/backend/utils/misc/guc.c` enum table, GUC entry, and `plancache.h`
  include; `postgresql.conf.sample`; `check_guc`.
- Callers: `src/backend/tcop/postgres.c` (`exec_simple_query`,
  `exec_parse_message`, `exec_bind_message`),
  `src/backend/commands/prepare.c` (`ExecuteQuery`, `EvaluateParams`,
  `ExplainExecuteQuery`, `pg_prepared_statement`),
  `src/backend/executor/spi.c` (`SPI_prepare`, `SPI_prepare_cursor`,
  `SPI_execute_with_args`, `_SPI_prepare_oneshot_plan`, `_SPI_execute_plan`,
  `_SPI_convert_params`, `SPI_plan_get_cached_plan`),
  `src/pl/plpgsql/src/pl_exec.c` (`exec_stmt_dynexecute`,
  `exec_eval_using_params`, `exec_eval_simple_expr`, `plpgsql_param_fetch`),
  `src/backend/commands/portalcmds.c`, `src/backend/commands/discard.c`.
- Planner-side consequences: `src/backend/optimizer/util/clauses.c` `T_Param`
  folding, `src/backend/utils/adt/selfuncs.c` `eqsel_internal` /
  `var_eq_const` / `var_eq_non_const`.
- `src/backend/commands/explain.c` `ExplainPrintSettings`;
  `src/backend/catalog/system_views.sql`; `src/backend/parser/gram.y`
  `PreparableStmt`; `src/include/nodes/parsenodes.h` cursor-option flags.
- Docs: `config.sgml`, `ref/prepare.sgml`, `spi.sgml`, `plpgsql.sgml`,
  `release-12.sgml`.
- Tests: `src/test/regress/{sql,expected}/plancache.*`,
  `src/test/regress/expected/partition_prune.out`; tree-wide search for other
  `plan_cache_mode` references in `src/`, `contrib/`, and
  `src/test/isolation/`.
- Source history: `git log` on `plancache.c` plus ancestry checks against the
  pin for every commit whose message mentions `plan_cache_mode`.
- Exact-pin execution: one isolated PostgreSQL 12.2 server built from the pinned
  commit with `contrib/auto_explain` installed, used for all measurements in
  [Exact-pin measurements](#exact-pin-measurements). The server was stopped
  afterwards; its disposable data directory, SQL scripts, and logs remain under
  `.wiki-runtime/`.

## Evidence Map

| Claim | Source |
|---|---|
| Three enum values, `auto` default | [guc.c#plan_cache_mode_options](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L429-L434), [guc.c#plan_cache_mode](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4503-L4514) |
| `PGC_USERSET`, `GUC_EXPLAIN`, `QUERY_TUNING_OTHER`, no hooks | [guc.c#plan_cache_mode](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4503-L4514) |
| Enum type and global variable | [plancache.h#PlanCacheMode](../../../../raw/postgres-12/src/include/utils/plancache.h#L26-L35), [plancache.c:119](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L119) |
| Sample-file entry | [postgresql.conf.sample:409-410](../../../../raw/postgres-12/src/backend/utils/misc/postgresql.conf.sample#L409-L410) |
| Considered at execution, not at prepare | [config.sgml#plan_cache_mode](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5393-L5410), [plancache.c#GetCachedPlan-choose](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1152-L1156) |
| Whole policy in `choose_custom_plan` | [plancache.c#choose_custom_plan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1010-L1063) |
| Rule 1 one-shot -> custom | [plancache.c:1020-1022](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1020-L1022) |
| Rule 2 no params -> generic | [plancache.c:1024-1026](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1024-L1026) |
| Rule 3 transaction statements -> generic | [plancache.c:1027-1029](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1027-L1029), [plancache.c#IsTransactionStmtPlan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L78-L84) |
| `PREPARE` cannot hold a transaction statement | [gram.y#PreparableStmt](../../../../raw/postgres-12/src/backend/parser/gram.y#L10737-L10742) |
| Rules 4-5 GUC force | [plancache.c:1031-1035](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1031-L1035) |
| Rule 6 cursor options, no in-core setter | [plancache.c:1037-1041](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1037-L1041), [parsenodes.h#CURSOR_OPT_GENERIC_PLAN](../../../../raw/postgres-12/src/include/nodes/parsenodes.h#L2688-L2692), [spi.sgml#SPI_prepare_cursor-notes](../../../../raw/postgres-12/doc/src/sgml/spi.sgml#L1029-L1037) |
| `SPI_prepare` passes `cursorOptions = 0` | [spi.c#SPI_prepare](../../../../raw/postgres-12/src/backend/executor/spi.c#L673-L677) |
| Rule 7 hard-coded 5 | [plancache.c:1043-1045](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1043-L1045) |
| Rule 8 strict cost comparison, `-1` sentinel bias | [plancache.c:1047-1062](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1047-L1062) |
| Planning charge added to custom costs only | [plancache.c#cached_plan_cost](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1065-L1117), [plancache.c:1110-1112](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1110-L1112) |
| Charge is "very crude", multiplier "on the low side" | [plancache.c#cached_plan_cost-comment](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1089-L1109) |
| `generic_cost` set only when a generic plan is built | [plancache.c:1188-1189](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1188-L1189) |
| Custom counters, `INT_MAX` guard | [plancache.c:1211-1221](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1211-L1221) |
| Correction step builds then discards the generic choice | [plancache.c#GetCachedPlan-correction](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1188-L1207) |
| Rejected generic plan stays cached in `gplan` | [plancache.c:1168-1174](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1168-L1174) |
| Generic reuse gated by `CheckCachedPlan` | [plancache.c#CheckCachedPlan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L783-L858) |
| Role-dependent plans invalidated on role change | [plancache.c#CheckCachedPlan-role](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L808-L813) |
| Only `boundParams` differs between the two builds | [plancache.c#BuildCachedPlan-comment](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L860-L875), [plancache.c#BuildCachedPlan-plan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L930-L933) |
| `PARAM_FLAG_CONST` params fold to `Const` | [clauses.c#eval_const_expressions_mutator-Param](../../../../raw/postgres-12/src/backend/optimizer/util/clauses.c#L2339-L2400) |
| Bind, `EXECUTE`, SPI, and PL/pgSQL all set the flag | [postgres.c#exec_bind_message-const](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1846-L1851), [prepare.c#EvaluateParams](../../../../raw/postgres-12/src/backend/commands/prepare.c#L396-L410), [spi.c#_SPI_convert_params](../../../../raw/postgres-12/src/backend/executor/spi.c#L2440-L2466), [pl_exec.c#plpgsql_param_fetch](../../../../raw/postgres-12/src/pl/plpgsql/src/pl_exec.c#L6375-L6380) |
| `Const` gets MCV-based selectivity, `Param` does not | [selfuncs.c#eqsel_internal](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L264-L278), [selfuncs.c#var_eq_non_const](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L437-L445) |
| Generic plans prune at run time (`Subplans Removed`) | [partition_prune.out#force_generic_plan](../../../../raw/postgres-12/src/test/regress/expected/partition_prune.out#L3843-L3857) |
| Heuristic state fields | [plancache.h#CachedPlanSource](../../../../raw/postgres-12/src/include/utils/plancache.h#L118-L130) |
| `cursor_options` filled by `CompleteCachedPlan` | [plancache.c:426](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L426) |
| `generation` bumped per built plan; PL/pgSQL notices replans through it | [plancache.c:1002-1003](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1002-L1003), [pl_exec.c#exec_eval_simple_expr-generation](../../../../raw/postgres-12/src/pl/plpgsql/src/pl_exec.c#L6114-L6121) |
| Fields initialized per plansource, including one-shot | [plancache.c#CreateCachedPlan-init](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L213-L221), [plancache.c#CreateOneShotCachedPlan-init](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L280-L288) |
| `CopyCachedPlan` copies the history | [plancache.c#CopyCachedPlan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1396-L1399) |
| Bind call site, `params = NULL` when no parameters | [postgres.c:1871-1876](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1871-L1876), [postgres.c#exec_bind_message-null-params](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1854-L1855) |
| Named vs unnamed statement handling | [postgres.c#exec_parse_message-unnamed](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1368-L1384), [postgres.c#exec_parse_message-save](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1513-L1527) |
| `EXECUTE` call site | [prepare.c#ExecuteQuery](../../../../raw/postgres-12/src/backend/commands/prepare.c#L245-L247) |
| `EXPLAIN EXECUTE` also calls `GetCachedPlan` | [prepare.c#ExplainExecuteQuery](../../../../raw/postgres-12/src/backend/commands/prepare.c#L662-L666) |
| `Planning Time` window for `EXPLAIN EXECUTE` | [prepare.c#ExplainExecuteQuery-planstart](../../../../raw/postgres-12/src/backend/commands/prepare.c#L633-L666) |
| SPI saved-plan call site | [spi.c#_SPI_execute_plan](../../../../raw/postgres-12/src/backend/executor/spi.c#L2211-L2216) |
| One-shot SPI plans | [spi.c#_SPI_prepare_oneshot_plan](../../../../raw/postgres-12/src/backend/executor/spi.c#L2041-L2086), [spi.c#SPI_execute_with_args](../../../../raw/postgres-12/src/backend/executor/spi.c#L626-L671) |
| PL/pgSQL dynamic `EXECUTE` uses the one-shot path | [pl_exec.c#exec_stmt_dynexecute](../../../../raw/postgres-12/src/pl/plpgsql/src/pl_exec.c#L4343-L4355), [plpgsql.sgml#execute-replans](../../../../raw/postgres-12/doc/src/sgml/plpgsql.sgml#L1253-L1267) |
| PL/pgSQL simple expressions always generic | [spi.c#SPI_plan_get_cached_plan](../../../../raw/postgres-12/src/backend/executor/spi.c#L1821-L1824), [pl_exec.c#exec_eval_simple_expr](../../../../raw/postgres-12/src/pl/plpgsql/src/pl_exec.c#L6098-L6112) |
| Simple protocol plans without the cache | [postgres.c#exec_simple_query-plan](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1143-L1144) |
| SQL `DECLARE CURSOR` plans without the cache | [portalcmds.c#PerformCursorOpen](../../../../raw/postgres-12/src/backend/commands/portalcmds.c#L91-L92) |
| Cost history survives invalidation, by design | [plancache.c#RevalidateCachedQuery-retain](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L768-L775) |
| `DISCARD PLANS` only invalidates | [plancache.c#ResetPlanCache](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1962-L2024), [discard.c#DiscardCommand](../../../../raw/postgres-12/src/backend/commands/discard.c#L27-L54) |
| Cached plans lock every relation per execution | [plancache.c#AcquireExecutorLocks](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1555-L1604), [plancache.c:1585-1601](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1585-L1601) |
| `$n` versus values distinguishes the plan kind | [prepare.sgml#explain-execute](../../../../raw/postgres-12/doc/src/sgml/ref/prepare.sgml#L164-L173) |
| `EXPLAIN (SETTINGS)` prints `GUC_EXPLAIN` settings | [explain.c#ExplainPrintSettings](../../../../raw/postgres-12/src/backend/commands/explain.c#L603-L664) |
| `pg_prepared_statements` has no plan counters | [prepare.c#pg_prepared_statement](../../../../raw/postgres-12/src/backend/commands/prepare.c#L723-L737), [system_views.sql#pg_prepared_statements](../../../../raw/postgres-12/src/backend/catalog/system_views.sql#L332-L333) |
| Unsaved-plansource resource-owner error | [plancache.c:1148-1150](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1148-L1150) |
| Variable-result `EXPLAIN EXECUTE` error | [prepare.c:641-643](../../../../raw/postgres-12/src/backend/commands/prepare.c#L641-L643) |
| Re-revalidation inside `BuildCachedPlan` | [plancache.c#BuildCachedPlan-revalidate](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L888-L902) |
| Lock-release race path in `CheckCachedPlan` | [plancache.c#CheckCachedPlan-race](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L838-L857) |
| `guc.c` includes `plancache.h` | [guc.c:90](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L90) |
| Sample-file consistency script | [check_guc:1-40](../../../../raw/postgres-12/src/backend/utils/misc/check_guc#L1-L40) |
| Only direct regression coverage | [plancache.sql#plan_cache_mode](../../../../raw/postgres-12/src/test/regress/sql/plancache.sql#L181-L212), [plancache.out#plan_cache_mode](../../../../raw/postgres-12/src/test/regress/expected/plancache.out#L281-L357) |
| Pruning tests use `force_generic_plan` as a tool | [partition_prune.out#exec-pruning](../../../../raw/postgres-12/src/test/regress/expected/partition_prune.out#L2511-L2559) |
| New in v12, credited to Pavel Stehule | [release-12.sgml#plan_cache_mode](../../../../raw/postgres-12/doc/src/sgml/release-12.sgml#L3666-L3681) |
| Documented purpose of the force modes | [prepare.sgml#force-modes](../../../../raw/postgres-12/doc/src/sgml/ref/prepare.sgml#L154-L162) |
| `statement_timeout` and `lock_timeout` are `PGC_USERSET` | [guc.c#statement_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2386), [guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2388-L2397) |
| SPI-level description of the same heuristic | [spi.sgml#SPI_execute_plan-notes](../../../../raw/postgres-12/doc/src/sgml/spi.sgml#L891-L905) |

## Open Questions

- The `PREPARE` documentation describes rule 8 as using the generic plan when
  its cost "is not so much higher than the average custom-plan cost as to make
  repeated replanning seem preferable"
  ([prepare.sgml#auto-heuristic](../../../../raw/postgres-12/doc/src/sgml/ref/prepare.sgml#L141-L152)),
  which reads as a tolerance band. The code applies a strict `<` comparison
  against an average that already includes the replanning charge
  ([plancache.c:1047-1062](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1047-L1062)).
  Source wins; the wording difference is recorded here rather than treated as
  behavior.
- Rule 3 (`IsTransactionStmtPlan`) could not be exercised at the pin. SQL
  `PREPARE` rejects transaction control statements
  ([gram.y#PreparableStmt](../../../../raw/postgres-12/src/backend/parser/gram.y#L10737-L10742)),
  and reaching the rule would require a client that declares parameters on a
  transaction statement and binds values to them. The claim rests on the code
  path alone.
- Rule 6 has no in-core setter in the pinned tree, so the `CURSOR_OPT_*`
  precedence over `plan_cache_mode` is asserted from rule order in
  `choose_custom_plan` plus the SPI documentation, not from an executed test.
- The `pgbench -M extended` result is explained by the unnamed-statement reset in
  `exec_parse_message`
  ([postgres.c#exec_parse_message-unnamed](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1368-L1384)).
  Whether a specific third-party driver names its prepared statements is outside
  this checkout and was not tested.
- The measured latency and planning-time numbers come from one machine and two
  fixture shapes. They demonstrate direction and order of magnitude, not
  portable constants.
- This page does not re-derive the plan-cache role/RLS revalidation rules beyond
  the fields `CheckCachedPlan` tests; the fuller treatment lives on the
  cross-version RLS pages and is not re-cited here under the one-version rule.

## Source References

- [plancache.c#choose_custom_plan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1010-L1063)
- [plancache.c#cached_plan_cost](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1065-L1117)
- [plancache.c#GetCachedPlan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1119-L1245)
- [plancache.c#CheckCachedPlan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L783-L858)
- [plancache.c#BuildCachedPlan](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L860-L1008)
- [plancache.c#RevalidateCachedQuery](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L538-L781)
- [plancache.c#AcquireExecutorLocks](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1555-L1604)
- [plancache.c#ResetPlanCache](../../../../raw/postgres-12/src/backend/utils/cache/plancache.c#L1962-L2024)
- [plancache.h#CachedPlanSource](../../../../raw/postgres-12/src/include/utils/plancache.h#L93-L131)
- [guc.c#plan_cache_mode](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4503-L4514)
- [guc.c#plan_cache_mode_options](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L429-L434)
- [postgresql.conf.sample:409-410](../../../../raw/postgres-12/src/backend/utils/misc/postgresql.conf.sample#L409-L410)
- [postgres.c#exec_bind_message](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L1846-L1876)
- [prepare.c#ExecuteQuery](../../../../raw/postgres-12/src/backend/commands/prepare.c#L245-L247)
- [prepare.c#ExplainExecuteQuery](../../../../raw/postgres-12/src/backend/commands/prepare.c#L621-L668)
- [spi.c#SPI_plan_get_cached_plan](../../../../raw/postgres-12/src/backend/executor/spi.c#L1788-L1830)
- [pl_exec.c#exec_eval_simple_expr](../../../../raw/postgres-12/src/pl/plpgsql/src/pl_exec.c#L6098-L6112)
- [clauses.c#eval_const_expressions_mutator-Param](../../../../raw/postgres-12/src/backend/optimizer/util/clauses.c#L2339-L2400)
- [selfuncs.c#eqsel_internal](../../../../raw/postgres-12/src/backend/utils/adt/selfuncs.c#L264-L278)
- [config.sgml#plan_cache_mode](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L5386-L5412)
- [ref/prepare.sgml#notes](../../../../raw/postgres-12/doc/src/sgml/ref/prepare.sgml#L126-L173)
- [spi.sgml#SPI_execute_plan-notes](../../../../raw/postgres-12/doc/src/sgml/spi.sgml#L891-L905)
- [plpgsql.sgml#execute-replans](../../../../raw/postgres-12/doc/src/sgml/plpgsql.sgml#L1253-L1267)
- [release-12.sgml#plan_cache_mode](../../../../raw/postgres-12/doc/src/sgml/release-12.sgml#L3666-L3681)
- [plancache.sql#plan_cache_mode](../../../../raw/postgres-12/src/test/regress/sql/plancache.sql#L181-L212)
- [plancache.out#plan_cache_mode](../../../../raw/postgres-12/src/test/regress/expected/plancache.out#L281-L357)
- [partition_prune.out#force_generic_plan](../../../../raw/postgres-12/src/test/regress/expected/partition_prune.out#L3843-L3865)

## Navigation

- [v12 index](../../index.md)
- [versions](../../../versions.md)
- [wiki index](../../../index.md)
- [v12 codebase navigation guide](../../codebase-navigation-guide.md)
- [v12: Table partitioning optimizations during planning and execution](partitioning-planning-execution-optimizations.md)
- [v12: Query planner statistics sources](query-planner-statistics-sources.md)
