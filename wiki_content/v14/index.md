# PostgreSQL 14.24

## Source Pin

- Branch: `REL_14_STABLE`
- Commit: `a92fbdfb830046e907813e9067b2c9de9708d600`
- Status: `active`
- Source path: `raw/postgres-14/`
- Added: 2026-06-30
- Repinned: 2026-08-17

## Coverage

Behavioral claims cite the matching pinned checkout under `raw/postgres-14/`. The 2026-08-17 repin from 14.23 `5c00f4e2e3b` to 14.24 `a92fbdfb830` reviewed all 133 commits in the range. Claim-changing commits: `f4174aa84a3` (CVE-2026-14666) registers `PlanCacheRoleCallback` on `pg_auth_members`/`pg_authid`/`pg_database`, which closes the former same-role RLS plan-cache staleness window for saved plans; `1a358b8f2a2` (CVE-2026-6470) requires `USAGE` on types used by policy, index, default, CHECK and partition-key expressions; `155dacbc547` (CVE-2026-14680) rejects calls to functions taking or returning type `internal`; `802dc79df63` removed replication-slot advice from the MultiXact wraparound hints and documented that slots do not hold back multixact cleanup; and `2bb60eb4fea` moved `RecordNewMultiXact()`'s SLRU lock acquisition later to fix a replay self-deadlock. Nothing was re-measured on 14.24, so previous-pin measurements are labelled as such.

- [PostgreSQL 14 Codebase Navigation Guide (unverified)](codebase-navigation-guide.md) - Mandatory root-level question-style map for navigating the pinned v14 source tree: layout, SQL statement flow, utility dispatch, generated/catalog artifacts, key structs, contrib boundaries, tests, and docs.
- [Wiki Glossary (unverified)](../glossary.md) - The one glossary shared by every version. PostgreSQL jargon, acronyms and source-code terms, each entry citing the pinned checkout it was checked on (PostgreSQL 12, 14, 17, 18 and 19; 319 terms).

## Questions

### Query Planning

- [Performance Implications of Functions and Procedures in a WHERE Clause in PostgreSQL 14, and How to Minimize the Overhead (unverified)](questions/query-planning/functions-procedures-in-where-clause.md) - Fully source-reviewed walkthrough of procedure, set-returning/aggregate/window, and (since 14.24, `155dacbc547`) `internal`-typed argument/result rejection in `WHERE`, the utility `CALL` path and its separately evaluated arguments, and scalar-function multiplicity across residual scan tuples and join pairs. Covers short-circuiting, `STRICT` null skips, SQL inlining, constant folding, pseudoconstant gating and rescans, index runtime keys, cost/selectivity and expression statistics, plain-index search-key limits plus expression indexes/generated columns/planner support, the distinct security-promotion and runtime-ordering rules (including the leakproof cost cutoff), parallel safety, JIT, `track_functions`, generated `pg_proc_d.h`, extension hooks/bitcode, tests, and source-backed mitigations.

### Storage and Vacuum

- [How MultiXact Works in PostgreSQL 14, and How Foreign Keys and Other Operations Degrade Performance When the Local Cache Spills to Secondary Storage (unverified)](questions/storage-and-vacuum/multixact-foreign-keys-cache-spill.md) - Fully source-reviewed walkthrough of tuple `xmax`/member statuses, immutable create/expand and conflict/wait paths, the offsets/members SLRUs, WAL/recovery, 2PC horizons, and vacuum-driven truncation. Corrects the premise: the backend-local transaction cache retains 256 entries and evicts with `pfree`; it never spills an entry to storage. A resolving local miss first reaches the shared 8-offset/16-member SLRU pools, and only an SLRU miss requests a filesystem read that may still hit the OS page cache. Separates system-wide MXID/member allocation from one backend's cache pressure; traces FK `FOR KEY SHARE` including null/partition edges and the compatible hot-row path, committed updaters, explicit locks, UPDATE/DELETE/update chains, executor/trigger/logical-apply callers, and the precise VACUUM replacement branches. Covers hot-row/`MultiXactGen`/SLRU contention, both MXID and member hard stops, aggressive vacuum, exact generated wait names, `pg_stat_slru` attribution limits, four direct GUCs plus reloptions and scopes, build/generated/WAL/tool/contrib boundaries, verified production SQL, the seven MultiXact isolation specs passing on the previous 14.23 pin, and explicit performance-test absence.

### Server Administration

- [Row-Level Security (RLS) in PostgreSQL 14: Implementation, Scalability and Performance, and Settings (unverified)](questions/server-administration/row-level-security-rls.md) - Fully source-reviewed implementation and follow-up analysis covering rewrite/WCO layering (including `ON CONFLICT`), policy and generated-catalog storage, relcache ordering, bypass/identity rules, index/pruning/partial-index, selectivity/cost and parallel-safety effects, and scalar-subquery InitPlans as lazy zero-or-once evaluations per surviving occurrence and outer-plan execution. The function-wrapper review covers RLS rewrite copies, residual filters, runtime keys and rescans, lossy rechecks, skew-sensitive estimates, partial indexes, volatility, privileges/leakproofness, and exact-pin call-count tests. Also covers aggregation mitigations, conditional MultiXact paths, and COPY/CTAS/RI/error boundaries. Distinguishes logical-replication initial-sync RLS from ongoing decoded WAL and subscriber apply, and records that 14.24 closed the former same-role plan-cache staleness window: `f4174aa84a3` (CVE-2026-14666) registers `PlanCacheRoleCallback` on `pg_auth_members`/`pg_authid`/`pg_database`, so membership, `INHERIT`, `BYPASSRLS`, `SUPERUSER`, and database-owner changes now invalidate role-dependent saved plans without `DISCARD PLANS`, with the superseded 14.23 reproduction and the two residual scopes (saved plans only; other databases' `pg_database` rows ignored) stated explicitly. Also covers the new 14.24 policy-expression type-`USAGE` requirement (`1a358b8f2a2`, CVE-2026-6470). Includes all direct GUC, table, role, policy, hook, inspection, dump/restore, and replication controls plus explicit test gaps.
