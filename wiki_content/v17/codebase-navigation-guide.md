---
type: codebase-navigation-guide
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# PostgreSQL 17 Codebase Navigation Guide (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Fast Map](#fast-map)
  - [SQL Statement Path](#sql-statement-path)
  - [Generated And Catalog Files](#generated-and-catalog-files)
  - [Key Data Structures](#key-data-structures)
  - [Tests And Docs](#tests-and-docs)
  - [Navigation Checklist](#navigation-checklist)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

Create a codebase navigation guide document for PostgreSQL 17.

Prompt note: this is the canonical mandatory guide prompt for `type: codebase-navigation-guide`.

## Answer

Use the PostgreSQL 17 checkout as a set of subsystem maps. The top-level `src/Makefile` names the major source families, and the backend makefile narrows server code into `access`, `archive`, `backup`, `bootstrap`, `catalog`, `parser`, `commands`, `executor`, `optimizer`, `postmaster`, `replication`, `rewrite`, `statistics`, `storage`, `tcop`, `utils`, and `jit` [src/Makefile#SUBDIRS](../../raw/postgres-17/src/Makefile#L15-L35) [backend/Makefile#SUBDIRS](../../raw/postgres-17/src/backend/Makefile#L19-L24).

### Fast Map

| Need | Start here | Evidence |
|---|---|---|
| Server subsystems | `src/backend/` | `src/backend/Makefile` is the short ownership map for parser, planner, executor, storage, replication, commands, and utility code [backend/Makefile#SUBDIRS](../../raw/postgres-17/src/backend/Makefile#L19-L24). |
| [Access methods](../glossary.md#access-method) | `src/backend/access/` | The access makefile separates BRIN, common AM code, GIN, GiST, hash, heap, index, B-tree, resource-manager descriptions, SP-GiST, table AM, table sampling, and transaction code [access/Makefile#SUBDIRS](../../raw/postgres-17/src/backend/access/Makefile#L11-L14). |
| Storage and locks | `src/backend/storage/` | Storage is split into AIO, buffer, file, freespace, IPC, large-object, lock-manager, page, smgr, and sync directories [storage/Makefile#SUBDIRS](../../raw/postgres-17/src/backend/storage/Makefile#L11-L11). |
| Client programs | `src/bin/` | Client and maintenance programs are listed under `src/bin`, with Windows `pgevent` added conditionally [bin/Makefile#SUBDIRS](../../raw/postgres-17/src/bin/Makefile#L16-L40). |
| Frontend APIs | `src/interfaces/` | PostgreSQL 17 builds `libpq` and `ecpg` from `src/interfaces` [interfaces/Makefile#SUBDIRS](../../raw/postgres-17/src/interfaces/Makefile#L15-L15). |
| [Extensions](../glossary.md#extension) | `contrib/` | The [contrib](../glossary.md#contrib) makefile lists built contrib modules and adds platform/language-conditional modules such as `pgcrypto`, `uuid-ossp`, `xml2`, `sepgsql`, and PL transform modules [contrib/Makefile#SUBDIRS](../../raw/postgres-17/contrib/Makefile#L7-L85). |

### SQL Statement Path

1. For the simple-query protocol, start in `exec_simple_query()`. It parses the query string with `pg_parse_query()`, then proceeds through analysis, rewrite, planning, [portal](../glossary.md#portal) setup, and execution for each raw statement [postgres.c#exec_simple_query](../../raw/postgres-17/src/backend/tcop/postgres.c#L1018-L1210) [postgres.c#pg_parse_query](../../raw/postgres-17/src/backend/tcop/postgres.c#L616-L642).
2. Parse analysis and rewrite live behind the `pg_analyze_and_rewrite_*()` wrappers and `pg_rewrite_query()`. The normal statement path reaches `QueryRewrite()` before planning [postgres.c#pg_analyze_and_rewrite](../../raw/postgres-17/src/backend/tcop/postgres.c#L676-L846) [rewriteHandler.c#QueryRewrite](../../raw/postgres-17/src/backend/rewrite/rewriteHandler.c#L4556-L4605).
3. [Planning](../glossary.md#planner) begins at `pg_plan_queries()`. Normal queries enter `planner()`, which either uses `planner_hook` or `standard_planner()`, and `subquery_planner()` builds the per-query planner state [postgres.c#pg_plan_queries](../../raw/postgres-17/src/backend/tcop/postgres.c#L977-L1015) [planner.c#planner](../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L275-L310) [planner.c#subquery_planner](../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L629-L700).
4. Execution is portal-driven. `PortalRun()` dispatches portal execution, and the [executor](../glossary.md#executor) entry points are `ExecutorStart()` and `ExecutorRun()` with hook-aware standard implementations [pquery.c#PortalRun](../../raw/postgres-17/src/backend/tcop/pquery.c#L686-L850) [execMain.c#ExecutorStart-Run](../../raw/postgres-17/src/backend/executor/execMain.c#L121-L340).
5. [Utility commands](../glossary.md#utility-command) are routed outside normal plan execution. `ProcessUtility()` exposes `ProcessUtility_hook`, a [hook](../glossary.md#hook); without a hook it calls `standard_ProcessUtility()` [utility.c#ProcessUtility](../../raw/postgres-17/src/backend/tcop/utility.c#L499-L590).

### Generated And Catalog Files

Treat generated headers and [catalog](../glossary.md#catalog) artifacts as part of the navigation surface. The backend `generated-headers` target depends on [LWLock](../glossary.md#lwlock) names, catalog headers, node headers, utility headers, and `parser/gram.h` from the [grammar](../glossary.md#grammar) [backend/Makefile#generated-headers](../../raw/postgres-17/src/backend/Makefile#L140-L145). Catalog headers generate through `src/include/catalog/Makefile`, and `pg_index.h` shows the catalog-header pattern with `CATALOG()` plus generated index declarations [catalog/Makefile#generated-headers](../../raw/postgres-17/src/include/catalog/Makefile#L126-L130) [pg_index.h#CATALOG](../../raw/postgres-17/src/include/catalog/pg_index.h#L29-L72).

### Key Data Structures

Keep these structs open when tracing behavior:

| Structure | Why it matters |
|---|---|
| `RawStmt` and `Query` | Raw [parse trees](../glossary.md#parse-tree) become analyzed `Query` trees before rewrite and planning [parsenodes.h#Query](../../raw/postgres-17/src/include/nodes/parsenodes.h#L117-L170) [parsenodes.h#RawStmt](../../raw/postgres-17/src/include/nodes/parsenodes.h#L2017-L2038). |
| `PlannedStmt` | [Planner output](../glossary.md#plannedstmt) and utility wrappers are represented as `PlannedStmt` nodes [plannodes.h#PlannedStmt](../../raw/postgres-17/src/include/nodes/plannodes.h#L46-L120). |
| `PlannerGlobal`, `RelOptInfo`, and `Path` | These are the planner's global state, [relation state](../glossary.md#reloptinfo), and alternative access/join [path](../glossary.md#path) records [pathnodes.h#PlannerGlobal](../../raw/postgres-17/src/include/nodes/pathnodes.h#L95-L170) [pathnodes.h#RelOptInfo](../../raw/postgres-17/src/include/nodes/pathnodes.h#L853-L930) [pathnodes.h#Path](../../raw/postgres-17/src/include/nodes/pathnodes.h#L1622-L1660). |
| `QueryDesc`, `EState`, and `PlanState` | Executor entry points receive a `QueryDesc`, build query-wide `EState`, and execute a `PlanState` tree [execdesc.h#QueryDesc](../../raw/postgres-17/src/include/executor/execdesc.h#L33-L56) [execnodes.h#EState](../../raw/postgres-17/src/include/nodes/execnodes.h#L621-L710) [execnodes.h#PlanState](../../raw/postgres-17/src/include/nodes/execnodes.h#L1113-L1175). |
| `RelationData`, `TableAmRoutine`, and `IndexAmRoutine` | [Relation cache](../glossary.md#relcache) state points at table and index access-method callback tables [rel.h#RelationData](../../raw/postgres-17/src/include/utils/rel.h#L55-L135) [tableam.h#TableAmRoutine](../../raw/postgres-17/src/include/access/tableam.h#L296-L390) [amapi.h#IndexAmRoutine](../../raw/postgres-17/src/include/access/amapi.h#L214-L300). |
| `MemoryContextData` | [Memory contexts](../glossary.md#memory-context) form the allocation tree used by backend code [memnodes.h#MemoryContextData](../../raw/postgres-17/src/include/nodes/memnodes.h#L117-L134). |

### Tests And Docs

Use `src/test/Makefile` to choose between Perl/[TAP](../glossary.md#tap-test), postmaster, [regression](../glossary.md#regression-test), [isolation](../glossary.md#isolation-test), modules, authentication, recovery, and subscription test areas [test/Makefile#SUBDIRS](../../raw/postgres-17/src/test/Makefile#L15-L27). SQL regression tests build `pg_regress` and expose `check`/`installcheck` targets, while isolation tests build `isolationtester` and `pg_isolation_regress` [regress/GNUmakefile#targets](../../raw/postgres-17/src/test/regress/GNUmakefile#L36-L123) [isolation/Makefile#targets](../../raw/postgres-17/src/test/isolation/Makefile#L21-L64). Test-only extension modules live under `src/test/modules` [test/modules/Makefile#SUBDIRS](../../raw/postgres-17/src/test/modules/Makefile#L7-L63). Developer docs in `doc/src/sgml/filelist.sgml` include [BKI](../glossary.md#bki), catalogs, table AM, index AM, source-layout, storage, and contrib docs [filelist.sgml#developer-docs](../../raw/postgres-17/doc/src/sgml/filelist.sgml#L84-L116).

### Navigation Checklist

1. Confirm the target version and pin before reading source.
2. Use makefiles to find ownership before following call graphs.
3. For SQL behavior, separate the normal query path from `ProcessUtility()`.
4. Keep the relevant node structs open while reading planner or executor code.
5. Check generated-header, catalog, and test surfaces before drafting behavioral claims.

## Context Reviewed

- Version navigation: `wiki/versions.md`, `wiki/index.md`, recent `wiki/log.md`, and `wiki/v17/index.md`.
- Source layout: top-level, backend, access, storage, bin, interfaces, contrib, and test makefiles.
- Query path: `postgres.c`, `pquery.c`, `utility.c`, `rewriteHandler.c`, `planner.c`, and `execMain.c`.
- Data structures: parser, planner, executor, relation cache, table AM, index AM, and memory-context headers.
- Generated and test surfaces: backend generated-header rules, catalog generation rules, catalog headers, regression tests, isolation tests, test modules, and SGML file lists.

## Evidence Map

| Claim area | Primary evidence |
|---|---|
| Source layout | `src/Makefile`, `src/backend/Makefile`, subsystem makefiles, `contrib/Makefile`. |
| Normal SQL path | `exec_simple_query()`, `pg_parse_query()`, `pg_analyze_and_rewrite_*()`, `pg_rewrite_query()`, `pg_plan_queries()`, `PortalRun()`, executor entry points. |
| Utility path | `ProcessUtility()` and `standard_ProcessUtility()`. |
| Generated/catalog artifacts | backend generated-header target, catalog generated-header target, `pg_index.h`. |
| Key structs | `RawStmt`, `Query`, `PlannedStmt`, planner structs, executor structs, `RelationData`, AM routines, memory contexts. |
| Tests/docs | regression, isolation, test modules, and SGML file-list entries. |

## Open Questions

None for this navigation-scope page. Subsystem pages still need fresh caller/callee, struct, macro, generated-file, error-path, and test review for their exact behavior.

## Source References

- [src/Makefile#SUBDIRS](../../raw/postgres-17/src/Makefile#L15-L35)
- [backend/Makefile#SUBDIRS](../../raw/postgres-17/src/backend/Makefile#L19-L24)
- [postgres.c#exec_simple_query](../../raw/postgres-17/src/backend/tcop/postgres.c#L1018-L1210)
- [postgres.c#pg_plan_queries](../../raw/postgres-17/src/backend/tcop/postgres.c#L977-L1015)
- [pquery.c#PortalRun](../../raw/postgres-17/src/backend/tcop/pquery.c#L686-L850)
- [utility.c#ProcessUtility](../../raw/postgres-17/src/backend/tcop/utility.c#L499-L590)
- [planner.c#planner](../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L275-L310)
- [planner.c#subquery_planner](../../raw/postgres-17/src/backend/optimizer/plan/planner.c#L629-L700)
- [execMain.c#ExecutorStart-Run](../../raw/postgres-17/src/backend/executor/execMain.c#L121-L340)
- [backend/Makefile#generated-headers](../../raw/postgres-17/src/backend/Makefile#L140-L145)
- [pg_index.h#CATALOG](../../raw/postgres-17/src/include/catalog/pg_index.h#L29-L72)
- [parsenodes.h#RawStmt](../../raw/postgres-17/src/include/nodes/parsenodes.h#L2017-L2038)
- [pathnodes.h#RelOptInfo](../../raw/postgres-17/src/include/nodes/pathnodes.h#L853-L930)
- [execnodes.h#PlanState](../../raw/postgres-17/src/include/nodes/execnodes.h#L1113-L1175)
- [tableam.h#TableAmRoutine](../../raw/postgres-17/src/include/access/tableam.h#L296-L390)
- [amapi.h#IndexAmRoutine](../../raw/postgres-17/src/include/access/amapi.h#L214-L300)
- [regress/GNUmakefile#targets](../../raw/postgres-17/src/test/regress/GNUmakefile#L36-L123)
- [isolation/Makefile#targets](../../raw/postgres-17/src/test/isolation/Makefile#L21-L64)

## Navigation

- [PostgreSQL 17.11 index](index.md)
- [Wiki index](../index.md)
- [Versions](../versions.md)
- [Wiki Glossary (unverified)](../glossary.md)
