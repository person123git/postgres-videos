---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# Can ALTER TABLE ... ATTACH PARTITION Drop Indexes in PostgreSQL 12? (unverified)

## Question

In PostgreSQL 12, in what scenarios can indexes be dropped from a table during
ALTER TABLE ... ATTACH PARTITION on a declarative partitioned table?

## Answer

**None. `ALTER TABLE ... ATTACH PARTITION` never drops an index from the table
being attached.** The index-handling subroutine is strictly *match-or-create*:
for each index on the partitioned parent it either **attaches** a compatible
existing index on the partition (re-parenting it, keeping its data) or
**creates** a new one. It has no code path that drops, replaces, or rebuilds an
existing index, and any extra or incompatible indexes on the partition are left
in place.

All of this happens in `AttachPartitionEnsureIndexes`, called by
`ATExecAttachPartition` after the new partition's catalog wiring (inheritance and
partition bound) is in place
([tablecmds.c#ATExecAttachPartition](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15765-L15771),
[tablecmds.c#AttachPartitionEnsureIndexes](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15872-L16040)).
The function comment states the rule it enforces: "every partition must have an
index attached to each index on the partitioned table"
([tablecmds.c:15867-15869](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15867-L15869)).

### What ATTACH PARTITION does instead of dropping

For every **partitioned index** on the parent (plain, non-partitioned indexes on
the parent are ignored —
[tablecmds.c:15949-15953](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15949-L15953)),
ATTACH scans the partition's existing indexes and takes exactly one of two
actions:

| Situation on the partition being attached | What ATTACH does | Index dropped? |
|---|---|---|
| No compatible index exists | **Creates** a cloned index via `generateClonedIndexStmt` + `DefineIndex` ([tablecmds.c:16016-16029](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16016-L16029)) | No — one is *added* |
| A compatible, unattached, same-definition index exists (and, if the parent index backs a constraint, *any* child constraint) | **Re-parents** it via `IndexSetParentIndex` — kept, not rebuilt ([tablecmds.c:16000-16008](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16000-L16008)) | No — reused/absorbed |
| An incompatible index exists (different columns/AM, partial, or expression) | Ignores it; creates a new matching index | No — incompatible one is kept, now redundant |
| Attaching a **foreign table** while the parent has any unique/PK index | Raises an error; nothing is attached ([tablecmds.c:15910-15930](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15910-L15930)) | No — operation refused |

The matching test is `CompareIndexInfo`
([tablecmds.c:15976-15982](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15976-L15982)).
In v12 the candidate loop applies exactly **two** guards before accepting a
match:

1. The candidate must not already be a partition of another index
   (`relispartition`,
   [tablecmds.c:15972-15974](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15972-L15974)).
2. When the parent index backs a constraint, the partition must have *a*
   constraint on the candidate index — the code only checks that one exists, not
   its type
   ([tablecmds.c:15990-15998](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15990-L15998)).

If all match, the only catalog change is re-parenting (`IndexSetParentIndex` plus,
for constraint-backed indexes, `ConstraintSetParentConstraint`) — no drop
([tablecmds.c:16000-16008](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16000-L16008)).
`IndexSetParentIndex` itself only inserts/deletes a `pg_inherits` row and fixes
`pg_depend`; it does not drop the index relation
([indexcmds.c#IndexSetParentIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3398-L3405)).
If nothing matches, a new index is *created* via `DefineIndex`
([tablecmds.c:16016-16029](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16016-L16029)),
which is the opposite of dropping.

Note v12's matching is deliberately *looser* than current PostgreSQL minor
releases in two ways that are visible directly in the v12 source: the candidate
loop has **no `indisvalid` guard** (it goes straight from the `relispartition`
check to `CompareIndexInfo`,
[tablecmds.c:15967-15982](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15967-L15982)),
and the constraint check **does not compare constraint type**
([tablecmds.c:15990-15998](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15990-L15998)).
Both differences only affect *whether an existing partition index is reused or a
fresh one is created* — neither introduces a drop. (For how these matching rules
were tightened in later releases, see the v17 page linked under
[Navigation](#navigation).)

The regression suite demonstrates each branch:

- Attaching a table with **no** index to a parent that has two indexes
  **creates** both on the partition — after ATTACH, `\d idxpart1` lists
  `idxpart1_a_idx` and `idxpart1_b_c_idx`, each shown as "Partition of:" the
  parent index
  ([indexing.out:78-122](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L78-L122)).
- Attaching a table that **already has a matching** index does **not** create a
  duplicate; the existing index is attached and gains `inhparent =
  idxpart_a_b_idx`
  ([indexing.out:125-150](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L125-L150)).
- Attaching a table with four **incompatible** indexes (hash, partial,
  expression, `(a,a)`) keeps all four and merely **adds** one matching index —
  the `\d idxpart1` output after ATTACH lists every original index plus the new
  `idxpart1_a_idx2`
  ([indexing.out:222-243](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L222-L243)).

### Confirming there is no drop path

A whole-file check of `tablecmds.c` shows every `performDeletion` /
`RemoveInheritance` call lives outside the attach path:
`ATExecDetachPartition` (`RemoveInheritance` at
[tablecmds.c:16286](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16286),
constraint `performDeletion` at
[tablecmds.c:16407-16421](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16407-L16421)),
the DROP CONSTRAINT path, and the trigger/sequence paths. The attach path that
runs after `AttachPartitionEnsureIndexes` clones triggers and foreign keys onto
the partition and queues partition-constraint validation
([tablecmds.c:15771-15820](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15771-L15820));
none of that drops an index. The inheritance step `CreateInheritance` that runs
just *before* index handling merges only CHECK constraints
(`MergeConstraintsIntoExisting` skips everything where `contype !=
CONSTRAINT_CHECK`,
[tablecmds.c:13219-13252](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L13219-L13252)),
so it never touches indexes either.

### The closest things to a "drop" (and why they are not)

Three behaviors are sometimes mistaken for "ATTACH dropped my index":

1. **A matched index is *absorbed*, not removed.** After re-parenting, the
   partition's index has `relispartition = true` and can no longer be dropped on
   its own — `DROP INDEX` on it errors with *"cannot drop index ... because
   index ... requires it"*
   ([indexing.out:157-159](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L157-L159)).
   The index still exists and still holds its data; only its independent
   droppability changes.

2. **The redundant CHECK constraint you drop is not an index.** The documented
   fast-attach recipe is to add a `CHECK` constraint matching the partition
   bound *before* ATTACH (to skip the validation scan), then **manually** drop
   that now-redundant `CHECK` constraint afterward
   ([ddl.sgml:3960-3971](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L3960-L3971)).
   That is a CHECK constraint and a manual step — ATTACH itself drops nothing.

3. **Later `DROP INDEX` on the parent cascades.** Dropping the parent
   partitioned index removes the attached child indexes too, and dropping the
   partition table removes its index
   ([indexing.out:160-177](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L160-L177)).
   That is a separate `DROP` command, not part of ATTACH.

### `ALTER INDEX ... ATTACH PARTITION` also never drops

The companion command that attaches one index to a partitioned index,
`ALTER INDEX ... ATTACH PARTITION` (`ATExecAttachPartitionIdx`), likewise only
re-parents or errors. It is a no-op if the index is already in the right state
([tablecmds.c:16543-16546](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16543-L16546)),
refuses with *"Another index is already attached for partition"* if the slot is
taken (`refuseDupeIndexAttach`,
[tablecmds.c:16561](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16561),
[tablecmds.c:16658-16673](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16658-L16673)),
and errors with *"The index definitions do not match"* on a `CompareIndexInfo`
mismatch
([tablecmds.c:16598-16610](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16598-L16610)).
When everything checks out it calls `IndexSetParentIndex` and
`validatePartitionedIndex` — re-parent, never replace
([tablecmds.c:16635-16643](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16635-L16643)).
The error cases are exercised by the regression suite
([indexing.out:180-213](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L180-L213)).

### Recommended workflow to avoid a costly index *build* during ATTACH

Because the "no match" branch builds a full index on the partition under the
attach's lock, the docs recommend pre-building it so ATTACH only re-parents:
`CREATE INDEX ON ONLY parent` (creates an invalid parent index), then
`CREATE INDEX` on each partition, then
`ALTER INDEX parent_idx ATTACH PARTITION child_idx`; the parent index is marked
valid once all partitions are attached
([ddl.sgml:3973-3996](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L3973-L3996)).
This avoids the rebuild — it does not avoid any drop, because there is none.
(Note v12 cannot use `CREATE INDEX CONCURRENTLY` on a partitioned table, so the
per-partition builds in this recipe are plain `CREATE INDEX`,
[indexing.out:56-57](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L56-L57).)

### Test coverage

`src/test/regress/sql/indexing.sql` (expected output in
`expected/indexing.out`) is the primary coverage:

- auto-create on attach
  ([indexing.out:78-122](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L78-L122));
- reuse/attach an existing matching index, no duplicate
  ([indexing.out:125-150](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L125-L150));
- incompatible indexes kept, matching one added
  ([indexing.out:222-243](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L222-L243));
- DROP semantics of an attached child index vs. the parent
  ([indexing.out:153-177](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L153-L177));
- `ALTER INDEX ... ATTACH PARTITION` error cases including dupe rejection
  ([indexing.out:180-213](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L180-L213)).

## Context Reviewed

- `wiki/versions.md`, `wiki/index.md`, `wiki/v12/index.md`, and recent
  `wiki/log.md` entries (navigation only).
- The companion v17 page
  [Can ALTER TABLE ... ATTACH PARTITION Drop Indexes in PostgreSQL 17?](../../../v17/questions/indexing/attach-partition-index-drops.md)
  (navigation/cross-version reference only; all factual claims here re-cited
  against the v12 checkout).
- Pinned checkout `raw/postgres-12/` at commit
  `45b88269a353ad93744772791feb6d01bc7e1e42` (Stamp 12.2).
- `ATExecAttachPartition`, `AttachPartitionEnsureIndexes`, and
  `ATExecAttachPartitionIdx` in `src/backend/commands/tablecmds.c`;
  `CreateInheritance` → `MergeConstraintsIntoExisting` (CHECK-only) confirmed not
  to touch indexes.
- A `tablecmds.c`-wide check that every `performDeletion` / `RemoveInheritance`
  call sits in the DETACH, DROP CONSTRAINT, trigger, or sequence paths, never the
  attach path.
- `DefineIndex` (10-parameter v12 signature, no `total_parts`) and
  `IndexSetParentIndex` in `src/backend/commands/indexcmds.c`.
- `doc/src/sgml/ddl.sgml` partitioning maintenance section.
- Tests `src/test/regress/expected/indexing.out`.

## Evidence Map

| Claim | Source |
|---|---|
| Attach index handling is match-or-create; no drop path | [tablecmds.c:15872-16040](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15872-L16040) |
| Called from `ATExecAttachPartition` | [tablecmds.c:15765-15771](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15765-L15771) |
| Only partitioned indexes on the parent drive matching | [tablecmds.c:15949-15953](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15949-L15953) |
| Match test is `CompareIndexInfo` | [tablecmds.c:15976-15982](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15976-L15982) |
| Skip already-attached (`relispartition`) candidates | [tablecmds.c:15972-15974](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15972-L15974) |
| v12 constraint guard checks existence only, not type | [tablecmds.c:15990-15998](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15990-L15998) |
| v12 has no `indisvalid` skip in the candidate loop | [tablecmds.c:15967-15982](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15967-L15982) |
| Match → re-parent via `IndexSetParentIndex` (kept) | [tablecmds.c:16000-16008](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16000-L16008) |
| No match → create cloned index via `DefineIndex` | [tablecmds.c:16016-16029](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16016-L16029) |
| `IndexSetParentIndex` only edits `pg_inherits`/`pg_depend` | [indexcmds.c:3398-3405](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3398-L3405) |
| `DefineIndex` v12 signature (10 params, no `total_parts`) | [indexcmds.c:430-439](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L430-L439) |
| Foreign-table attach refused if parent has unique/PK index | [tablecmds.c:15910-15930](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15910-L15930) |
| `MergeConstraintsIntoExisting` is CHECK-only | [tablecmds.c:13219-13252](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L13219-L13252) |
| `performDeletion` lives in DETACH path, not attach | [tablecmds.c:16407-16421](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16407-L16421) |
| Auto-create on attach (test) | [indexing.out:78-122](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L78-L122) |
| Reuse matching index, no duplicate; re-parented | [indexing.out:125-150](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L125-L150) |
| Incompatible indexes kept; matching one added | [indexing.out:222-243](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L222-L243) |
| Attached child index cannot be dropped on its own | [indexing.out:157-159](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L157-L159) |
| Dropping parent index / partition table cascades | [indexing.out:160-177](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L160-L177) |
| Drop redundant CHECK constraint is a manual, non-index step | [ddl.sgml:3960-3971](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L3960-L3971) |
| Pre-build + `ALTER INDEX ATTACH` recommended workflow | [ddl.sgml:3973-3996](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L3973-L3996) |
| `ALTER INDEX ATTACH` refuses dupes / mismatches, only re-parents | [tablecmds.c:16504-16652](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16504-L16652) |

## Open Questions

- The note that v12's matching is *looser* than later minor releases (no
  `indisvalid` skip, no constraint-type check) is stated only from the absence of
  those guards in the v12 source; the precise downstream commits that added them
  are documented on the cross-version
  [v17 page](../../../v17/questions/indexing/attach-partition-index-drops.md) and are not
  re-cited here, per the one-version-per-page citation rule.
- This page does not separately re-derive the `convert_tuples_by_name_map` attribute-mapping
  behavior; it is cited only as the attribute map fed to `CompareIndexInfo` and
  `generateClonedIndexStmt`, neither of which drops an index.

## Source References

- [tablecmds.c#ATExecAttachPartition](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15581-L15861)
- [tablecmds.c#AttachPartitionEnsureIndexes](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L15872-L16040)
- [tablecmds.c#ATExecAttachPartitionIdx](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16504-L16652)
- [tablecmds.c#MergeConstraintsIntoExisting](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L13219-L13252)
- [indexcmds.c#DefineIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L430-L439)
- [indexcmds.c#IndexSetParentIndex](../../../../raw/postgres-12/src/backend/commands/indexcmds.c#L3398-L3405)
- [ddl.sgml#partition-maintenance](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L3960-L3996)
- [indexing.out#attach-partition](../../../../raw/postgres-12/src/test/regress/expected/indexing.out#L78-L243)

## Navigation

- [v12 index](../../index.md)
- [versions](../../../versions.md)
- [wiki index](../../../index.md)
- [v17: Can ATTACH PARTITION Drop Indexes? (changes since v12)](../../../v17/questions/indexing/attach-partition-index-drops.md)
- [v12: CREATE INDEX CONCURRENTLY](create-index-concurrently.md)
