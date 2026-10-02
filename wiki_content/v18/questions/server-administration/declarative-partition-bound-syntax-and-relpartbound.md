---
type: question
version: 18
pinned_commit: baa7b142aace6821ce085906f314a75bcc4d95c8
verified: false
verified_by_agent: not yet
---

# Changes to Declarative Partition Bound Syntax and pg_class.relpartbound Since Partitioning Was Introduced, as of PostgreSQL 18 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Verdict](#verdict)
  - [The bound syntax PostgreSQL 18 accepts](#the-bound-syntax-postgresql-18-accepts)
  - [Syntax changes since declarative partitioning was introduced](#syntax-changes-since-declarative-partitioning-was-introduced)
  - [What the syntax still does not have](#what-the-syntax-still-does-not-have)
  - [How pg_class.relpartbound stores the bound datum](#how-pg_classrelpartbound-stores-the-bound-datum)
  - [Changes to the stored representation since declarative partitioning was introduced](#changes-to-the-stored-representation-since-declarative-partitioning-was-introduced)
  - [The relpartbound lifecycle](#the-relpartbound-lifecycle)
  - [How PostgreSQL 18 exposes the bound](#how-postgresql-18-exposes-the-bound)
  - [Exposure changes since declarative partitioning was introduced](#exposure-changes-since-declarative-partitioning-was-introduced)
  - [Caller callee and data-structure boundary](#caller-callee-and-data-structure-boundary)
  - [Error paths](#error-paths)
  - [Generated-header and build implications](#generated-header-and-build-implications)
  - [Previous-pin measurements](#previous-pin-measurements)
  - [Tests and test gaps](#tests-and-test-gaps)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 18: since the introduction of declarative partitioning, are there any changes to the syntax and/or changes to `pg_class.relpartbound`, in how PostgreSQL describes and exposes the declarative partitioning bound datum?

## Answer

### Verdict

Yes on both counts, but every substantive change landed early and nothing has moved for six major releases.

| Layer | Changed since PostgreSQL 10? | Last release that changed it |
|---|---|---|
| Bound syntax (`FOR VALUES ...` / `DEFAULT`) | Yes — three changes | PostgreSQL 12 |
| `pg_class.relpartbound` column definition | No | never (introduced with the feature) |
| Content of the stored `pg_node_tree` | Yes — two changes | PostgreSQL 17 |
| Deparsed text from `pg_get_expr` | No | never |
| Exposure surfaces (functions, psql, pg_dump) | Yes — additions only | PostgreSQL 14 |

Concretely:

- **Syntax.** `MINVALUE`/`MAXVALUE` replaced `UNBOUNDED` before 10.0 shipped ([`d363d42bb9a`](#syntax-changes-since-declarative-partitioning-was-introduced)); PostgreSQL 11 added `DEFAULT` and the hash form `WITH (MODULUS m, REMAINDER r)`; PostgreSQL 12 replaced the literal-only bound element with a general expression. After that PostgreSQL 12 commit the grammar production has been touched exactly twice: one whole-tree indentation run in 15.0, and one PostgreSQL 18 commit that added error cursors to two hash-bound errors.
- **`relpartbound` the column.** Unchanged. It is still the last variable-length `pg_class` attribute, still `pg_node_tree`, still defaulting to null [pg_class.h#relpartbound](../../../../raw/postgres-18/src/include/catalog/pg_class.h#L134-L144).
- **`relpartbound` the value.** Two changes. PostgreSQL 11 added `is_default`, `modulus`, and `remainder` to the serialized node; PostgreSQL 17 made `nodeToString()` write `-1` for every parse-location field, so bound node trees stored on 17 and later no longer carry the original cursor offsets.
- **Exposure.** No typed accessor was ever added. The bound is still only readable as (a) the opaque `pg_node_tree`, (b) the deparsed `FOR VALUES ...` string from `pg_get_expr(relpartbound, oid)`, or (c) a derived boolean via `pg_get_partition_constraintdef(oid)`. PostgreSQL 14 added the `DETACH PENDING` annotation that psql prints next to the bound, and that is the newest change to any exposure surface.

Because the deparsed text never changed, a `pg_dump` from PostgreSQL 10 and a `pg_dump` from PostgreSQL 18 emit byte-comparable `ATTACH PARTITION ... FOR VALUES` clauses for the same bound. Because the stored node text did change, a tool that parses `relpartbound` directly must handle both the pre-11 field set and the pre-17 location values.

### The bound syntax PostgreSQL 18 accepts

One grammar production, `PartitionBoundSpec`, serves every context that takes a bound [gram.y#PartitionBoundSpec](../../../../raw/postgres-18/src/backend/parser/gram.y#L3145-L3238). Its four alternatives are:

| Form | Strategy | Node fields set |
|---|---|---|
| `FOR VALUES WITH ( MODULUS m, REMAINDER r )` | hash | `modulus`, `remainder` |
| `FOR VALUES IN ( expr [, ...] )` | list | `listdatums` |
| `FOR VALUES FROM ( ... ) TO ( ... )` | range | `lowerdatums`, `upperdatums` |
| `DEFAULT` | inherited from parent | `is_default` |

Three details of the v18 grammar are easy to get wrong:

- **`MODULUS` and `REMAINDER` are not keywords.** The hash form parses as a `DefElem` list of `NonReservedWord Iconst` pairs, and the action loop then matches the downcased names `"modulus"` and `"remainder"` [gram.y#hash_partbound](../../../../raw/postgres-18/src/backend/parser/gram.y#L3240-L3256) [gram.y#hash_partbound-loop](../../../../raw/postgres-18/src/backend/parser/gram.y#L3155-L3195). Neither name appears in `kwlist.h`. Consequences: the two options may be given in either order, each may appear only once, and any third name raises `unrecognized hash partition bound specification`.
- **`MINVALUE` and `MAXVALUE` are not part of the bound grammar either.** They are ordinary unreserved keywords [kwlist.h:276](../../../../raw/postgres-18/src/include/parser/kwlist.h#L276) [kwlist.h:281](../../../../raw/postgres-18/src/include/parser/kwlist.h#L281), so they arrive inside `expr_list` as a one-field `ColumnRef`, and `transformPartitionRangeBounds()` recognizes them by string comparison against `"minvalue"` and `"maxvalue"` [parse_utilcmd.c#transformPartitionRangeBounds](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4450-L4560). The recognition is therefore case-insensitive through the lexer's downcasing, and a *quoted* lowercase `"minvalue"` is also accepted as the sentinel, while `"MINVALUE"` is not (see [Previous-pin measurements](#previous-pin-measurements)).
- **A bound element is a general expression, not a literal.** `transformPartitionBoundValue()` runs `transformExpr()` with `EXPR_KIND_PARTITION_BOUND`, coerces the result to the key column's type and typmod, then evaluates it to a `Const` carrying the key's collation [parse_utilcmd.c#transformPartitionBoundValue](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4607-L4676). The documentation states the same contract: the expression "is evaluated once at table creation time, so it can even contain volatile expressions such as `CURRENT_TIMESTAMP`" [create_table.sgml#partition_bound_expr](../../../../raw/postgres-18/doc/src/sgml/ref/create_table.sgml#L480-L488).

The same production is reused by `CREATE TABLE ... PARTITION OF` [gram.y#CREATE-TABLE-PARTITION-OF](../../../../raw/postgres-18/src/backend/parser/gram.y#L3694-L3714), `CREATE FOREIGN TABLE ... PARTITION OF` [gram.y#CREATE-FOREIGN-TABLE-PARTITION-OF](../../../../raw/postgres-18/src/backend/parser/gram.y#L5712-L5733), and `ALTER TABLE ... ATTACH PARTITION` [gram.y#partition_cmd](../../../../raw/postgres-18/src/backend/parser/gram.y#L2324-L2338). The documented synopses match [create_table.sgml#partition_bound_spec](../../../../raw/postgres-18/doc/src/sgml/ref/create_table.sgml#L93-L98) [alter_table.sgml#ATTACH-PARTITION](../../../../raw/postgres-18/doc/src/sgml/ref/alter_table.sgml#L1033-L1044).

### Syntax changes since declarative partitioning was introduced

The list below is the complete set of commits that touched either the `PartitionBoundSpec:` grammar production or `transformPartitionBound()` between the `REL_10_0` tag and the pinned commit, taken from the pinned checkout's own history via two `git log -L` line-range walks. The "First release" column is the earliest `REL_NN_0` tag that contains each commit.

| Commit | First release | Effect on bound syntax |
|---|---|---|
| `d363d42bb9a` | 10.0 | Replaced `UNBOUNDED` with `MINVALUE`/`MAXVALUE` for range bounds, and introduced the `PartitionRangeDatumKind` three-way enum in place of a boolean "infinite" flag. Landed during the v10 cycle, so `UNBOUNDED` never shipped in a release. |
| `6f6b99d1335` | 11.0 | Added the `DEFAULT` alternative. |
| `1aba8e651ac` | 11.0 | Added hash partitioning and the `FOR VALUES WITH (MODULUS ..., REMAINDER ...)` alternative. |
| `9361f6f54e3` | 11.0 | Added `validateInfiniteBounds()`: after a `MINVALUE` or `MAXVALUE`, every following column must repeat the same sentinel. |
| `8237f27b504` | 11.0 | Function rename (`get_relid_attribute_name` to `get_attname`) only. |
| `95931133a95` | 12.0 | Comment typo only. |
| `7c079d7417a` | 12.0 | Replaced the literal-only bound element with `expr_list`, moved `MINVALUE`/`MAXVALUE` recognition out of the grammar into `transformPartitionRangeBounds()`, and added `transformPartitionBoundValue()`. |
| `be76af171cd` | 12.0 | pgindent only. |
| `12afc7145c0` | 13.0 | Comment only. |
| `2b00db4fb0c` | 15.0 | `lfirst_node()` cleanup only. |
| `170aec63cd7` | 15.0 | Reworded the modulus error message. |
| `30ed71e423e` | 15.0 | Indentation of `.y` files only. |
| `2d8bff603c9` | 18.0 | Added `parser_errposition(@3)` to the "modulus for hash partition must be specified" and "remainder for hash partition must be specified" errors. |

Reading that as user-visible syntax:

- **PostgreSQL 10** shipped list and range only, with bound elements restricted to a numeric literal, a string literal, `NULL`, `MINVALUE`, or `MAXVALUE`. The 10.0 synopsis spells that out exactly.
- **PostgreSQL 11** added `DEFAULT` and hash bounds, and widened the documented literal set with `TRUE`/`FALSE`.
- **PostgreSQL 12** collapsed the whole enumeration to one nonterminal, `partition_bound_expr`. This is the last change to what the parser accepts.
- **PostgreSQL 13 through 18** made no change to what the parser accepts. PostgreSQL 18's single contribution, `2d8bff603c9`, only adds a `LINE 1: ... ^` cursor to two existing errors.

The documented synopsis is the cleanest witness. It is textually identical in the 12.0, 13.0, 14.0, 15.0, 16.0, 17.0 and pinned-18 trees, and the pinned form reads [create_table.sgml#partition_bound_spec](../../../../raw/postgres-18/doc/src/sgml/ref/create_table.sgml#L93-L98):

```text
IN ( partition_bound_expr [, ...] ) |
FROM ( { partition_bound_expr | MINVALUE | MAXVALUE } [, ...] )
  TO ( { partition_bound_expr | MINVALUE | MAXVALUE } [, ...] ) |
WITH ( MODULUS numeric_literal, REMAINDER numeric_literal )
```

### What the syntax still does not have

Three absences matter operationally, and all three are confirmed against the pin rather than assumed:

- **No statement modifies an existing bound.** `PartitionBoundSpec` appears only in create and attach positions; there is no `ALTER TABLE ... ALTER PARTITION ... FOR VALUES`. Changing a bound means `DETACH` then `ATTACH`.
- **No `MERGE`/`SPLIT PARTITION`.** Both were committed during the v17 cycle (`87c21bb9412`, `1adf16b8fba`) and then reverted by `3890d90c150`, whose first containing release tag is `REL_18_0`. So v18 ships without them, and the syntax errors are plain `syntax error at or near "SPLIT"` / `"MERGE"`.
- **No hash `DEFAULT`.** `transformPartitionBound()` rejects it: "a hash-partitioned table may not have a default partition" [parse_utilcmd.c#transformPartitionBound](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4309-L4330).

### How pg_class.relpartbound stores the bound datum

The column is declared inside the `CATALOG_VARLEN` block of `pg_class`, as the third and last variable-length attribute [pg_class.h#relpartbound](../../../../raw/postgres-18/src/include/catalog/pg_class.h#L134-L144):

```c
	/* partition bound node tree */
	pg_node_tree relpartbound BKI_DEFAULT(_null_);
```

The catalog documentation describes it as, "If table is a partition (see `relispartition`), internal representation of the partition bound" [catalogs.sgml#relpartbound](../../../../raw/postgres-18/doc/src/sgml/catalogs.sgml#L2307-L2315).

The write path is a two-step affair. `heap_create_with_catalog()` always inserts the `pg_class` row with `relpartbound` null [heap.c#relpartbound-null](../../../../raw/postgres-18/src/backend/catalog/heap.c#L980-L983), and `StorePartitionBound()` then updates that row, serializing the parse-analyzed node and setting `relispartition` in the same tuple [heap.c#StorePartitionBound](../../../../raw/postgres-18/src/backend/catalog/heap.c#L4091-L4144):

```c
	new_val[Anum_pg_class_relpartbound - 1] = CStringGetTextDatum(nodeToString(bound));
```

Two callers reach it: `DefineRelation()` for `CREATE TABLE ... PARTITION OF` [tablecmds.c:1207](../../../../raw/postgres-18/src/backend/commands/tablecmds.c#L1207) and `ATExecAttachPartition()` for `ALTER TABLE ... ATTACH PARTITION` [tablecmds.c:20520](../../../../raw/postgres-18/src/backend/commands/tablecmds.c#L20520). Both pass the output of `transformPartitionBound()`, so the stored node is always fully resolved: strategy filled in, expressions evaluated to `Const`, duplicates removed from list bounds, and the parent's strategy copied onto a `DEFAULT` spec.

What `nodeToString()` writes is the generic node-tree text format, one `:field value` pair per struct member in declaration order [parsenodes.h#PartitionBoundSpec](../../../../raw/postgres-18/src/include/nodes/parsenodes.h#L916-L964). Four properties are worth naming precisely:

- **The node label is upper-cased.** The generator emits `WRITE_NODE_TYPE("PARTITIONBOUNDSPEC")` because the output format "starts with upper case node type name" [gen_node_support.pl#out-funcs](../../../../raw/postgres-18/src/backend/nodes/gen_node_support.pl#L917-L946).
- **All fields are written, including the ones the strategy does not use.** There is no omit-if-default rule on the write side, so a list bound still carries `:modulus 0 :remainder 0` and empty `:lowerdatums <>`.
- **Every location field reads `-1`.** `WRITE_LOCATION_FIELD` consults the file-static `write_location_fields` flag, which `nodeToString()` leaves false; only `nodeToStringWithLocations()` sets it [outfuncs.c#WRITE_LOCATION_FIELD](../../../../raw/postgres-18/src/backend/nodes/outfuncs.c#L98-L100) [outfuncs.c#nodeToString](../../../../raw/postgres-18/src/backend/nodes/outfuncs.c#L774-L814). `StorePartitionBound()` calls the plain form.
- **The bound datum itself is stored as raw bytes, not as text.** `_outConst()` ends by calling `outDatum()`, which prints the datum's length and then each byte as a decimal integer [outfuncs.c#outDatum](../../../../raw/postgres-18/src/backend/nodes/outfuncs.c#L343-L376). That representation is host-endian and type-length dependent, which is why nothing outside the backend should parse it.

`relpartbound` is `pg_node_tree`, whose `attstorage` is `extended`, so the value can be compressed inline — but `pg_class` deliberately has no TOAST table, a fact asserted by a regression test [misc_sanity.out#no-toast-catalogs](../../../../raw/postgres-18/src/test/regress/expected/misc_sanity.out#L50-L70). A bound too large to compress into the tuple therefore fails at DDL time rather than being pushed out of line; see [Previous-pin measurements](#previous-pin-measurements).

### Changes to the stored representation since declarative partitioning was introduced

Comparing the write function across release tags of the pinned repository isolates exactly two changes to the stored text.

| Change | First release | Effect on the stored value |
|---|---|---|
| `is_default`, `modulus`, `remainder` added to `PartitionBoundSpec` | 11.0 | Three new `:field value` pairs appear in every bound, including list and range bounds that do not use them. |
| `d20d8fbd3e4` — "Do not output actual value of location fields in node serialization by default" | 17.0 | Every `:location` in the bound tree, including those inside nested `Const` and `PartitionRangeDatum` nodes, becomes `-1` instead of the original cursor offset. |

Two candidate changes turn out to be no-ops for this column, and both are worth stating so the negative is on record:

- **PostgreSQL 16 made node support functions generated** (`964d01ae90c` introduced `src/backend/nodes/gen_node_support.pl`). The generated `_outPartitionBoundSpec()` reproduces the hand-written one field for field: `char` → `WRITE_CHAR_FIELD`, `bool` → `WRITE_BOOL_FIELD`, `int` → `WRITE_INT_FIELD`, `List *` → `WRITE_NODE_FIELD`, `ParseLoc` → `WRITE_LOCATION_FIELD`, with the same upper-cased label [gen_node_support.pl#field-types](../../../../raw/postgres-18/src/backend/nodes/gen_node_support.pl#L1014-L1067). The stored text is unaffected.
- **The primitives did not move.** `outDatum()` is byte-identical between the `REL_10_0` tree and the pin, `_outConst()` likewise, and the `WRITE_CHAR_FIELD`, `WRITE_BOOL_FIELD`, `WRITE_INT_FIELD` and `WRITE_NODE_FIELD` macros produce identical output [outfuncs.c#WRITE-macros](../../../../raw/postgres-18/src/backend/nodes/outfuncs.c#L93-L106).

Practical reading: a `relpartbound` value written by PostgreSQL 11 through 16 and one written by 17 or 18 differ only in the `:location` numbers. A value written by 10 additionally lacks three fields. `pg_upgrade` does not carry the text across anyway — `pg_dump` re-emits DDL and the new server re-serializes — so the divergence matters for external tools that read the column, not for upgrades.

### The relpartbound lifecycle

`relpartbound` is written once and cleared once. There is no in-place edit path, because no statement alters an existing bound.

1. **Set** by `StorePartitionBound()` at `CREATE TABLE ... PARTITION OF` or `ALTER TABLE ... ATTACH PARTITION`. An assertion documents the write-once contract: the tuple must not already be a partition and `relpartbound` must be null [heap.c#StorePartitionBound](../../../../raw/postgres-18/src/backend/catalog/heap.c#L4110-L4121).
2. **Cleared** by `DetachPartitionFinalize()`, which nulls the attribute and resets `relispartition` in one `heap_modify_tuple()` [tablecmds.c#DetachPartitionFinalize](../../../../raw/postgres-18/src/backend/commands/tablecmds.c#L21413-L21435).

`DETACH PARTITION CONCURRENTLY` splits step 2 across two transactions: the first marks `pg_inherits.inhdetachpending`, commits, and only the second nulls `relpartbound` [tablecmds.c#ATExecDetachPartition](../../../../raw/postgres-18/src/backend/commands/tablecmds.c#L20971-L20980). During the gap the bound is still readable, which the isolation suite asserts directly with `SELECT relpartbound IS NULL FROM pg_class` before and after the blocking session commits [detach-partition-concurrently-1.spec](../../../../raw/postgres-18/src/test/isolation/specs/detach-partition-concurrently-1.spec#L35-L46).

Partitioned *indexes* never get a bound. An index attached with `ALTER INDEX ... ATTACH PARTITION` has null `relpartbound` on both parent and child, which the regression suite checks by selecting the column [indexing.sql#relpartbound](../../../../raw/postgres-18/src/test/regress/sql/indexing.sql#L70-L75) [indexing.out#relpartbound](../../../../raw/postgres-18/src/test/regress/expected/indexing.out#L128-L137).

### How PostgreSQL 18 exposes the bound

There are exactly three SQL-visible forms, plus two client tools that consume the second one.

**1. The raw `pg_node_tree`.** Readable by any role with `SELECT` on `pg_class`, which is world-readable. Opaque by design and documented only as "internal representation" [catalogs.sgml#relpartbound](../../../../raw/postgres-18/doc/src/sgml/catalogs.sgml#L2307-L2315).

**2. `pg_get_expr(relpartbound, oid)`** — the canonical deparse. `pg_get_expr_worker()` runs `stringToNode()`, rejects query trees and out-of-scope `Var`s, opens the relation under `AccessShareLock` when a nonzero relid is given, and deparses [ruleutils.c#pg_get_expr_worker](../../../../raw/postgres-18/src/backend/utils/adt/ruleutils.c#L2711-L2788). A `PartitionBoundSpec` reaches `get_rule_expr()`'s `T_PartitionBoundSpec` arm, which produces the same text the grammar accepts [ruleutils.c#T_PartitionBoundSpec](../../../../raw/postgres-18/src/backend/utils/adt/ruleutils.c#L10431-L10488):

| Stored spec | Deparsed text |
|---|---|
| `is_default` | `DEFAULT` |
| hash | `FOR VALUES WITH (modulus %d, remainder %d)` — lower-case option names |
| list | `FOR VALUES IN (` elements joined by `, ` `)` |
| range | `FOR VALUES FROM (...) TO (...)` via `get_range_partbound_string()` |

Two deparse rules govern the elements. `get_range_partbound_string()` emits the bare, upper-case keywords `MINVALUE` and `MAXVALUE` for the two sentinel kinds [ruleutils.c#get_range_partbound_string](../../../../raw/postgres-18/src/backend/utils/adt/ruleutils.c#L13704-L13742). Every real value goes through `get_const_expr(val, context, -1)`, and `showtype = -1` means "never show `::typename` decoration" [ruleutils.c#get_const_expr](../../../../raw/postgres-18/src/backend/utils/adt/ruleutils.c#L11453-L11468). That is what makes the output paste-able into `ATTACH PARTITION`, and also what makes it lossy: the text does not record which type the literal belongs to.

**3. `pg_get_partition_constraintdef(oid)`** — a derived boolean. It calls `get_partition_qual_relid()` and deparses the resulting expression [ruleutils.c#pg_get_partition_constraintdef](../../../../raw/postgres-18/src/backend/utils/adt/ruleutils.c#L2092-L2121), documented as "Reconstructs the definition of a partition constraint" [func.sgml#pg_get_partition_constraintdef](../../../../raw/postgres-18/doc/src/sgml/func.sgml#L26393-L26406). This is a different shape of information: it includes the inherited quals of every ancestor and the `IS NOT NULL` guards, so it is not a bound list.

**Clients.** psql's `\d` on a partition runs `pg_get_expr(c.relpartbound, c.oid)` and prints `Partition of: <parent> <bound>`, appending ` DETACH PENDING` when `pg_inherits.inhdetachpending` is set, and adds `Partition constraint:` from `pg_get_partition_constraintdef()` under `\d+` [describe.c#Partition-of](../../../../raw/postgres-18/src/bin/psql/describe.c#L2197-L2248). `\d+` on the parent lists each child with its bound and deliberately sorts the default partition last by testing the deparsed text against the literal `'DEFAULT'` [describe.c#child-tables](../../../../raw/postgres-18/src/bin/psql/describe.c#L3476-L3504). `pg_dump` uses the same deparse to build `ALTER TABLE ONLY ... ATTACH PARTITION ... <bound>;` [pg_dump.c#dumpTableAttach](../../../../raw/postgres-18/src/bin/pg_dump/pg_dump.c#L17926-L17971).

**What is not exposed.** There is no catalog column, view, or function that returns a bound as a typed value or as one row per bound element. `pg_partition_tree()`, `pg_partition_ancestors()` and `pg_partition_root()` expose hierarchy, not bounds. `\dP` lists partitioned relations without bounds. The engine's own internal form, `PartitionBoundInfoData` — the sorted `Datum **datums` array with its parallel `PartitionRangeDatumKind **kind`, `indexes`, `null_index` and `default_index` [partbounds.h#PartitionBoundInfoData](../../../../raw/postgres-18/src/include/partitioning/partbounds.h#L79-L96) — has no SQL surface at all.

### Exposure changes since declarative partitioning was introduced

Additions only; nothing was removed and no output format changed.

| Change | First release | Effect |
|---|---|---|
| `1848b73d457` | 10.0 | Added `pg_get_partition_constraintdef()` and taught `\d+` to print the partition constraint. |
| `05b6ec39d72` | 11.0 | `\d+` on a partitioned table lists partitions with their bounds. |
| `3bae43ca4dc` | 11.0 | Sorts the default partition to the bottom of that list. |
| `24f62e93f31`, `4e784f35145` | 13.0 | Reworked `\d` output for partitioned tables and partitioned indexes. |
| `71f4c8c6f74` | 14.0 | `DETACH PARTITION ... CONCURRENTLY`; psql gained the ` DETACH PENDING` suffix on the bound line. |
| `4438eb4a495`, `e3fcbbd623b`, `be85727a3df` | 15.0 | `pg_dump` refactors: the bound query moved into a prepared statement. Same SQL, same output. |

The `pg_get_expr` deparse path itself has no functional commit in that window; the only change to `get_range_partbound_string()` since 10.0 is a comment fix (`0896ae561b6`, first in 13.0).

### Caller callee and data-structure boundary

The read direction is where the stored text is turned back into engine structures, and it has three distinct entry points — worth knowing because each has a different failure mode.

- **`RelationBuildPartitionDesc()`** reads every child's `relpartbound` to build the parent's partition descriptor. It tries the syscache first, then falls back to a direct `pg_class` scan, precisely because a concurrent `ATTACH` may not be visible yet and a concurrent `DETACH CONCURRENTLY` may have already nulled the column. If the bound is still missing it retries once, then errors with `missing relpartbound for relation %u`, and it type-checks the deserialized node with `invalid relpartbound for relation %u` [partdesc.c#RelationBuildPartitionDesc](../../../../raw/postgres-18/src/backend/partitioning/partdesc.c#L179-L282).
- **`generate_partition_qual()`** reads a single partition's bound to build its check constraint, caching the result in the relcache entry [partcache.c#generate_partition_qual](../../../../raw/postgres-18/src/backend/utils/cache/partcache.c#L364-L381).
- **`get_qual_for_range()`** reads the *siblings'* bounds when constructing a default partition's constraint, using `SysCacheGetAttrNotNull()` since a listed partition must have one [partbounds.c#default-partition-qual](../../../../raw/postgres-18/src/backend/partitioning/partbounds.c#L4315-L4326).

The pinned checkout contains one v18-era change on this path: `c899c6839f5`, "Fix creation of partition descriptor during concurrent detach+drop", which added the missing null-tuple check in the direct-scan fallback. It changed neither syntax nor stored format.

Two adjacent 18.4/18.6 changes touch the partition machinery without touching the bound grammar or `relpartbound`:

- `0c06ebf126a`, "Prevent satisfies_hash_partition from crashing with VARIADIC NULL.", makes `satisfies_hash_partition(..., VARIADIC NULL::sometype[])` return false instead of crashing, on both the cached-`FmgrInfo` and the deconstruct-array paths [partbounds.c#variadic-null-cached](../../../../raw/postgres-18/src/backend/partitioning/partbounds.c#L4871-L4876) [partbounds.c#variadic-null-array](../../../../raw/postgres-18/src/backend/partitioning/partbounds.c#L4951-L4958). That function evaluates the *derived* hash-partition constraint at runtime; it neither parses nor stores a bound.
- `2780538433f` makes `StorePartitionKey()` check `USAGE` on the types reached by partition-*key* expressions before recording their dependencies [heap.c#StorePartitionKey-type-USAGE](../../../../raw/postgres-18/src/backend/catalog/heap.c#L4030-L4043). That is a key-side privilege check on `CREATE TABLE ... PARTITION BY`, not a bound-side change.

### Error paths

| Condition | Message | Source |
|---|---|---|
| Hash bound missing `MODULUS` | `modulus for hash partition must be specified` (with cursor, new in 18) | [gram.y#hash_partbound-loop](../../../../raw/postgres-18/src/backend/parser/gram.y#L3185-L3195) |
| Unknown hash option | `unrecognized hash partition bound specification "%s"` | [gram.y#hash_partbound-loop](../../../../raw/postgres-18/src/backend/parser/gram.y#L3177-L3183) |
| `MODULUS 0` or negative | `modulus for hash partition must be an integer value greater than zero` | [parse_utilcmd.c#hash-checks](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4332-L4351) |
| `REMAINDER >= MODULUS` | `remainder for hash partition must be less than modulus` | [parse_utilcmd.c#hash-checks](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4332-L4351) |
| Bound form does not match parent strategy | `invalid bound specification for a {hash,list,range} partition` | [parse_utilcmd.c#transformPartitionBound](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4332-L4440) |
| Wrong column count in `FROM`/`TO` | `FROM must specify exactly one value per partitioning column` | [parse_utilcmd.c#range-arity](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4419-L4426) |
| `NULL` in a range bound | `cannot specify NULL in range bound` | [parse_utilcmd.c#null-range](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4539-L4542) |
| Sentinel followed by a value | `every bound following MINVALUE must also be MINVALUE` | [parse_utilcmd.c#validateInfiniteBounds](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4568-L4602) |
| Uncoercible element | `specified value cannot be cast to type %s for column "%s"` | [parse_utilcmd.c#transformPartitionBoundValue](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4637-L4642) |
| `DEFAULT` on a hash parent | `a hash-partitioned table may not have a default partition` | [parse_utilcmd.c#transformPartitionBound](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4309-L4330) |

### Generated-header and build implications

Nothing about the bound is hand-maintained in a generated artifact, which is why the PostgreSQL 16 generator switch was invisible here:

- `Anum_pg_class_relpartbound` and `Natts_pg_class` come from the generated `pg_class_d.h`, produced by `genbki.pl` from `pg_class.h`. Every read site uses the symbol, never a literal ordinal.
- `T_PartitionBoundSpec`, `_outPartitionBoundSpec()`, `_readPartitionBoundSpec()`, `_copyPartitionBoundSpec()` and `_equalPartitionBoundSpec()` are all generated from the `parsenodes.h` struct by `gen_node_support.pl` [gen_node_support.pl#out-funcs](../../../../raw/postgres-18/src/backend/nodes/gen_node_support.pl#L917-L946). The struct carries no `pg_node_attr()` marking, so it gets the default full read/write/copy/equal treatment. Adding a field to `PartitionBoundSpec` would silently change the on-disk `relpartbound` text.
- `pg_get_partition_constraintdef` is registered in `pg_proc.dat` at OID 3408 and reaches SQL through the generated `fmgrtab.c`.

### Previous-pin measurements

Measured on the previous pin `6cb307251c5c6261286c1566496920976640108e` (18.3 line), not re-run for the 2026-08-17 repin to `baa7b142aace6821ce085906f314a75bcc4d95c8`. Built that commit out of tree under `.wiki-runtime/pg18/` and ran an isolated server (unix socket only, port 55018). `raw/postgres-18/` was not modified.

Every measured result below is still supported at the new pin, verified by re-reading the 18.4/18.6 range: `src/backend/parser/gram.y` has no commit in the range, so the bound grammar is byte-identical; `src/backend/utils/adt/ruleutils.c` changed twice but only in `get_func_sql_syntax()` (EXTRACT deparse) and `get_json_agg_constructor()`, both outside partition-bound deparse; `src/backend/parser/parse_utilcmd.c` changed twice in `expandTableLikeClause()` and `generateClonedIndexStmt()`/`generateClonedExtStatsStmt()`, which shifted `transformPartitionBound()` from L4283 to L4297 and `transformPartitionRangeBounds()` from L4437 to L4451 without changing either function's body; and `pg_class` still declares no TOAST table [misc_sanity.out#no-toast-catalogs](../../../../raw/postgres-18/src/test/regress/expected/misc_sanity.out#L50-L70). No measured number was changed.

**Stored node text.** Four partitions of four shapes, read straight out of `pg_class`:

```text
hp_0   {PARTITIONBOUNDSPEC :strategy h :is_default false :modulus 4 :remainder 0
        :listdatums <> :lowerdatums <> :upperdatums <> :location -1}
lp_def {PARTITIONBOUNDSPEC :strategy l :is_default true :modulus 0 :remainder 0
        :listdatums <> :lowerdatums <> :upperdatums <> :location -1}
lp_1   {PARTITIONBOUNDSPEC :strategy l :is_default false :modulus 0 :remainder 0
        :listdatums ({CONST :consttype 23 ... :constisnull false :location -1
                      :constvalue 4 [ 3 0 0 0 0 0 0 0 ]} ...
                     {CONST ... :constisnull true :location -1 :constvalue <>})
        :lowerdatums <> :upperdatums <> :location -1}
rp_1   {PARTITIONBOUNDSPEC :strategy r ...
        :lowerdatums ({PARTITIONRANGEDATUM :kind 0 :value {CONST ... :constvalue 4 [ 1 0 0 0 0 0 0 0 ]} :location -1}
                      {PARTITIONRANGEDATUM :kind -1 :value <> :location -1})
        :upperdatums ({PARTITIONRANGEDATUM :kind 0 :value {CONST ... :constvalue 4 [ 10 0 0 0 0 0 0 0 ]} :location -1}
                      {PARTITIONRANGEDATUM :kind 1 :value <> :location -1}) :location -1}
```

Every claim above shows up in that output: the upper-case `PARTITIONBOUNDSPEC` label; all eight fields written regardless of strategy; `:location -1` at every level (14 of 14 bound values in the database had no non-`-1` location); the `DEFAULT` spec carrying the parent's `:strategy l`; `:kind -1`/`0`/`1` for `MINVALUE`/value/`MAXVALUE`; and the datum printed as raw little-endian bytes.

**Bound expressions are evaluated at DDL time.** `FOR VALUES IN ((2+1), 5, NULL)` stored a `Const` of `3` and deparsed to `FOR VALUES IN (3, 5, NULL)`. The regression suite makes the same point: `PARTITION OF list_parted FOR VALUES IN ((2+1))` prints as `part_p3 FOR VALUES IN (3)` [create_table.out#part_p3](../../../../raw/postgres-18/src/test/regress/expected/create_table.out#L424-L437).

**Hash options are order-independent.** `FOR VALUES WITH (REMAINDER 0, MODULUS 4)` was accepted and deparsed back in canonical order as `FOR VALUES WITH (modulus 4, remainder 0)`.

**Quoted sentinels.** `FROM (1, "minvalue") TO (2, "maxvalue")` was accepted and deparsed as `FROM (1, MINVALUE) TO (2, MAXVALUE)`, because the quoted lowercase identifier still yields a one-field `ColumnRef` whose name matches. `"MINVALUE"` was rejected with `cannot use column reference in partition bound expression` — quoting preserves case, so the `strcmp` fails. `FOR VALUES IN (minvalue)` on a list parent was rejected the same way, confirming the sentinels are range-only.

**Deparse quoting is not type-faithful.** `FOR VALUES FROM (-5) TO (0)` on an `integer` key deparsed as `FOR VALUES FROM ('-5') TO (0)`: `get_const_expr` quotes the negative literal. The suite shows the same for a two-column bound: `FOR VALUES FROM ('-1', 'aaaaa') TO (100, 'ccccc')` [create_table.out#part2_1](../../../../raw/postgres-18/src/test/regress/expected/create_table.out#L330-L337).

**Pretty-printing is a no-op for bounds.** `pg_get_expr(relpartbound, oid, true) = pg_get_expr(relpartbound, oid)` was true for all 14 bounds present.

**Round trip.** Detaching and re-attaching with the deparsed text reproduced the identical bound, and `pg_dump -s` emitted `ALTER TABLE ONLY public.rp ATTACH PARTITION public.rp_1 FOR VALUES FROM (1, MINVALUE) TO (10, MAXVALUE);`.

**Detach clears the column.** Before `ALTER TABLE lp DETACH PARTITION lp_1`: `relpartbound IS NULL` false, `relispartition` true. After: true and false.

**No TOAST, so bounds have a size cliff.** Inline compression hides it for a while: a `repeat('x', 9000)` list bound produced 36,285 characters of node text that stored in 671 bytes. With incompressible hex literals the boundary appeared between 8,000 characters (stored, `pg_column_size` 7,627, node text 25,720 characters) and 8,400 characters, which failed with `row is too big: size 8216, maximum size 8160`.

**PostgreSQL 18's grammar change is observable.** The two hash-bound errors now carry a cursor:

```text
ERROR:  modulus for hash partition must be specified
LINE 1: CREATE TABLE hp_bad PARTITION OF hp FOR VALUES WITH (REMAIND...
                                                       ^
```

**MERGE/SPLIT are absent.** `ALTER TABLE rp SPLIT PARTITION ...` and `ALTER TABLE rp MERGE PARTITIONS ...` both failed with `syntax error at or near`.

The server was stopped and its data directory removed after testing.

### Tests and test gaps

Covered in the pinned tree:

- Bound syntax across all four forms, overlap detection, arity errors, sentinel ordering, forbidden expressions, and the volatile-bound case [create_table.sql#bound-syntax](../../../../raw/postgres-18/src/test/regress/sql/create_table.sql#L310-L420) [create_table.sql#volatile-bound](../../../../raw/postgres-18/src/test/regress/sql/create_table.sql#L709-L716).
- Deparse output, indirectly but thoroughly, through every `\d`/`\d+` block in `create_table.out`.
- `relpartbound` being null for partitioned indexes [indexing.out#relpartbound](../../../../raw/postgres-18/src/test/regress/expected/indexing.out#L128-L137).
- `relpartbound` remaining set until the concurrent detach's blocking transaction commits [detach-partition-concurrently-1.spec](../../../../raw/postgres-18/src/test/isolation/specs/detach-partition-concurrently-1.spec#L35-L46).
- `pg_class` having no TOAST table, which is what makes the size cliff possible [misc_sanity.out#no-toast-catalogs](../../../../raw/postgres-18/src/test/regress/expected/misc_sanity.out#L50-L70).

Explicit gaps found in the pinned tree:

- **No test asserts the stored node text.** Searching the whole tree for `PARTITIONBOUNDSPEC` returns no test file. The two tests that read `relpartbound` directly either expect null or test `IS NULL`. So the serialized field set and the `:location -1` behavior are unverified by the suite, and a change to either would not fail `make check`.
- **No test covers the size cliff.** Nothing exercises a bound large enough to overflow the `pg_class` tuple.
- **No test covers the quoted-sentinel behavior** (`"minvalue"` accepted, `"MINVALUE"` rejected).

## Context Reviewed

- [gram.y#PartitionBoundSpec](../../../../raw/postgres-18/src/backend/parser/gram.y#L3145-L3256) - the whole bound production plus the hash `DefElem` helpers.
- [gram.y#bound-use-sites](../../../../raw/postgres-18/src/backend/parser/gram.y#L2324-L2338) - `ATTACH PARTITION`, and the two `CREATE ... PARTITION OF` forms at L3694-L3714 and L5712-L5733.
- [parsenodes.h#PartitionBoundSpec](../../../../raw/postgres-18/src/include/nodes/parsenodes.h#L896-L975) - `PartitionStrategy`, `PartitionBoundSpec`, `PartitionRangeDatumKind`, `PartitionRangeDatum`, `PartitionCmd`.
- [parse_utilcmd.c#bound-transforms](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4291-L4676) - all four bound transform functions.
- [heap.c#StorePartitionBound](../../../../raw/postgres-18/src/backend/catalog/heap.c#L4080-L4169) - serialization and relcache invalidation, plus the null-at-creation site at L977-L980.
- [tablecmds.c#detach-paths](../../../../raw/postgres-18/src/backend/commands/tablecmds.c#L20971-L20980) - concurrent-detach two-step comment, and the clearing code at L21346-L21368.
- [partdesc.c#RelationBuildPartitionDesc](../../../../raw/postgres-18/src/backend/partitioning/partdesc.c#L179-L282) - syscache/direct-scan read path and retry.
- [partcache.c#generate_partition_qual](../../../../raw/postgres-18/src/backend/utils/cache/partcache.c#L345-L390) - single-partition read path.
- [partbounds.c#default-partition-qual](../../../../raw/postgres-18/src/backend/partitioning/partbounds.c#L4295-L4335) - sibling read path for the default partition's constraint.
- [partbounds.c#variadic-null-cached](../../../../raw/postgres-18/src/backend/partitioning/partbounds.c#L4871-L4876) and [partbounds.c#variadic-null-array](../../../../raw/postgres-18/src/backend/partitioning/partbounds.c#L4951-L4958) - the 18.4/18.6 `satisfies_hash_partition` VARIADIC NULL guards.
- [heap.c#StorePartitionKey-type-USAGE](../../../../raw/postgres-18/src/backend/catalog/heap.c#L4030-L4043) - the 18.6 partition-key type `USAGE` check, adjacent to but distinct from the bound.
- [partbounds.h#PartitionBoundInfoData](../../../../raw/postgres-18/src/include/partitioning/partbounds.h#L79-L109) - the internal, non-SQL-visible bound form.
- [ruleutils.c#deparse-and-accessors](../../../../raw/postgres-18/src/backend/utils/adt/ruleutils.c#L10431-L10488) - `T_PartitionBoundSpec`; plus `get_range_partbound_string` L13671-L13709, `get_const_expr` L11450-L11465, `pg_get_expr` L2650-L2786, `pg_get_partition_constraintdef` L2090-L2119.
- [outfuncs.c#serialization](../../../../raw/postgres-18/src/backend/nodes/outfuncs.c#L93-L106) - the `WRITE_*` macros; `outDatum` L343-L376; `nodeToString`/`nodeToStringWithLocations` L774-L814.
- [gen_node_support.pl#out-funcs](../../../../raw/postgres-18/src/backend/nodes/gen_node_support.pl#L917-L1067) - generated out/read function shape and field-type mapping.
- [pg_class.h#relpartbound](../../../../raw/postgres-18/src/include/catalog/pg_class.h#L134-L149) - the column and `CLASS_TUPLE_SIZE`.
- [kwlist.h:276](../../../../raw/postgres-18/src/include/parser/kwlist.h#L276) and [kwlist.h:281](../../../../raw/postgres-18/src/include/parser/kwlist.h#L281) - `maxvalue`/`minvalue` keyword categories; no `modulus`/`remainder` entries.
- [describe.c#Partition-of](../../../../raw/postgres-18/src/bin/psql/describe.c#L2197-L2248) and [describe.c#child-tables](../../../../raw/postgres-18/src/bin/psql/describe.c#L3476-L3504) - psql exposure.
- [pg_dump.c#dumpTableAttach](../../../../raw/postgres-18/src/bin/pg_dump/pg_dump.c#L17926-L17979) - dump exposure.
- [catalogs.sgml#relpartbound](../../../../raw/postgres-18/doc/src/sgml/catalogs.sgml#L2307-L2315), [create_table.sgml#partition-clause](../../../../raw/postgres-18/doc/src/sgml/ref/create_table.sgml#L459-L556), [alter_table.sgml#ATTACH-PARTITION](../../../../raw/postgres-18/doc/src/sgml/ref/alter_table.sgml#L1033-L1044), [func.sgml#pg_get_expr](../../../../raw/postgres-18/doc/src/sgml/func.sgml#L26265-L26280) - same-version documentation.
- Pinned-checkout history: `git log -L` over the `PartitionBoundSpec:` production and `transformPartitionBound()` for `REL_10_0..baa7b142aac`; `git tag --contains` for each commit's first `REL_NN_0`; `git show <tag>:src/backend/nodes/outfuncs.c` for `_outPartitionBoundSpec`, `_outConst` and `outDatum` at REL_10_0, REL_11_0, REL_12_0, REL_13_0, REL_14_0 and REL_15_0; `git show <tag>:doc/src/sgml/ref/create_table.sgml` for the synopsis at every major tag from 10.0.

## Evidence Map

| Claim | Source |
|---|---|
| One grammar production serves all bound contexts; four alternatives | [gram.y#PartitionBoundSpec](../../../../raw/postgres-18/src/backend/parser/gram.y#L3145-L3238) |
| `MODULUS`/`REMAINDER` are `NonReservedWord` `DefElem`s, order-independent, dup-checked | [gram.y#hash_partbound](../../../../raw/postgres-18/src/backend/parser/gram.y#L3240-L3256) [gram.y#hash_partbound-loop](../../../../raw/postgres-18/src/backend/parser/gram.y#L3155-L3195) |
| `MINVALUE`/`MAXVALUE` arrive as `ColumnRef` and are matched by string | [parse_utilcmd.c#transformPartitionRangeBounds](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4473-L4507) [kwlist.h:281](../../../../raw/postgres-18/src/include/parser/kwlist.h#L281) |
| Bound elements are evaluated to `Const` at DDL time | [parse_utilcmd.c#transformPartitionBoundValue](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4607-L4676) [create_table.sgml#partition_bound_expr](../../../../raw/postgres-18/doc/src/sgml/ref/create_table.sgml#L480-L488) [create_table.out#part_p3](../../../../raw/postgres-18/src/test/regress/expected/create_table.out#L424-L437) |
| Syntax changes: `d363d42bb9a` (10.0), `6f6b99d1335` + `1aba8e651ac` + `9361f6f54e3` (11.0), `7c079d7417a` (12.0), `2d8bff603c9` (18.0) | Pinned-checkout history: `git log -L` over the `PartitionBoundSpec:` production in `src/backend/parser/gram.y` and over `transformPartitionBound()` in `src/backend/parser/parse_utilcmd.c`, both for `REL_10_0..baa7b142aac`, plus `git tag --contains` per commit |
| Documented synopsis is unchanged from 12.0 through the pin | `git show REL_{12,13,14,15,16,17}_0:doc/src/sgml/ref/create_table.sgml` versus [create_table.sgml#partition_bound_spec](../../../../raw/postgres-18/doc/src/sgml/ref/create_table.sgml#L93-L98) |
| MERGE/SPLIT PARTITION were reverted before 18.0 | Pinned history: `87c21bb9412`, `1adf16b8fba`, revert `3890d90c150` whose first major tag is `REL_18_0` |
| No hash default partition | [parse_utilcmd.c#transformPartitionBound](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c#L4309-L4330) |
| Column is `pg_node_tree`, defaults to null, last varlena attribute | [pg_class.h#relpartbound](../../../../raw/postgres-18/src/include/catalog/pg_class.h#L134-L144) [catalogs.sgml#relpartbound](../../../../raw/postgres-18/doc/src/sgml/catalogs.sgml#L2307-L2315) |
| Written by `StorePartitionBound()` via `nodeToString()`, from two callers | [heap.c#StorePartitionBound](../../../../raw/postgres-18/src/backend/catalog/heap.c#L4091-L4144) [tablecmds.c:1207](../../../../raw/postgres-18/src/backend/commands/tablecmds.c#L1207) [tablecmds.c:20520](../../../../raw/postgres-18/src/backend/commands/tablecmds.c#L20520) |
| Row is inserted with `relpartbound` null first | [heap.c#relpartbound-null](../../../../raw/postgres-18/src/backend/catalog/heap.c#L980-L983) |
| Node label is upper-cased; all fields always written | [gen_node_support.pl#out-funcs](../../../../raw/postgres-18/src/backend/nodes/gen_node_support.pl#L917-L946) |
| Location fields serialize as `-1` under `nodeToString()` | [outfuncs.c#WRITE_LOCATION_FIELD](../../../../raw/postgres-18/src/backend/nodes/outfuncs.c#L98-L100) [outfuncs.c#nodeToString](../../../../raw/postgres-18/src/backend/nodes/outfuncs.c#L774-L814) |
| The datum is stored as raw bytes | [outfuncs.c#outDatum](../../../../raw/postgres-18/src/backend/nodes/outfuncs.c#L343-L376) |
| Stored-format changes: 3 fields added in 11.0; `d20d8fbd3e4` location change in 17.0 | `git show REL_{10,11,12,13,14,15}_0:src/backend/nodes/outfuncs.c` `_outPartitionBoundSpec`; `git log -S nodeToStringWithLocations` plus `git tag --contains d20d8fbd3e4` |
| PostgreSQL 16's generator switch did not change the output | [gen_node_support.pl#field-types](../../../../raw/postgres-18/src/backend/nodes/gen_node_support.pl#L1014-L1067); `outDatum`/`_outConst` byte-identical to `REL_10_0`; [outfuncs.c#WRITE-macros](../../../../raw/postgres-18/src/backend/nodes/outfuncs.c#L93-L106) |
| Cleared by `DetachPartitionFinalize()`; concurrent detach clears in a second transaction | [tablecmds.c#DetachPartitionFinalize](../../../../raw/postgres-18/src/backend/commands/tablecmds.c#L21413-L21435) [tablecmds.c#ATExecDetachPartition](../../../../raw/postgres-18/src/backend/commands/tablecmds.c#L20971-L20980) [detach-partition-concurrently-1.spec](../../../../raw/postgres-18/src/test/isolation/specs/detach-partition-concurrently-1.spec#L35-L46) |
| Deparse forms per strategy; `MINVALUE`/`MAXVALUE` bare and upper-case | [ruleutils.c#T_PartitionBoundSpec](../../../../raw/postgres-18/src/backend/utils/adt/ruleutils.c#L10431-L10488) [ruleutils.c#get_range_partbound_string](../../../../raw/postgres-18/src/backend/utils/adt/ruleutils.c#L13704-L13742) |
| Elements deparse with `showtype = -1`, so no `::type` decoration | [ruleutils.c#get_const_expr](../../../../raw/postgres-18/src/backend/utils/adt/ruleutils.c#L11453-L11468) |
| `pg_get_expr` takes `AccessShareLock` on the relation when relid is nonzero | [ruleutils.c#pg_get_expr_worker](../../../../raw/postgres-18/src/backend/utils/adt/ruleutils.c#L2764-L2788) |
| `pg_get_partition_constraintdef` returns a derived boolean, not a bound | [ruleutils.c#pg_get_partition_constraintdef](../../../../raw/postgres-18/src/backend/utils/adt/ruleutils.c#L2092-L2121) [func.sgml#pg_get_partition_constraintdef](../../../../raw/postgres-18/doc/src/sgml/func.sgml#L26393-L26406) |
| psql prints the bound, ` DETACH PENDING`, and sorts DEFAULT last | [describe.c#Partition-of](../../../../raw/postgres-18/src/bin/psql/describe.c#L2197-L2248) [describe.c#child-tables](../../../../raw/postgres-18/src/bin/psql/describe.c#L3476-L3504) |
| `pg_dump` pastes the deparsed text into `ATTACH PARTITION` | [pg_dump.c#dumpTableAttach](../../../../raw/postgres-18/src/bin/pg_dump/pg_dump.c#L17926-L17971) |
| Exposure additions and their releases | Pinned history: `git log -G relpartbound -- src/bin/psql/describe.c src/bin/pg_dump/pg_dump.c`, `git log -S pg_get_partition_constraintdef`, with `git tag --contains` per commit |
| `pg_class` has no TOAST table, so `relpartbound` cannot go out of line | [misc_sanity.out#no-toast-catalogs](../../../../raw/postgres-18/src/test/regress/expected/misc_sanity.out#L50-L70) |
| Read paths and their errors | [partdesc.c#RelationBuildPartitionDesc](../../../../raw/postgres-18/src/backend/partitioning/partdesc.c#L179-L282) [partcache.c#generate_partition_qual](../../../../raw/postgres-18/src/backend/utils/cache/partcache.c#L364-L381) [partbounds.c#default-partition-qual](../../../../raw/postgres-18/src/backend/partitioning/partbounds.c#L4315-L4326) |
| Internal bound form has no SQL surface | [partbounds.h#PartitionBoundInfoData](../../../../raw/postgres-18/src/include/partitioning/partbounds.h#L79-L96) |
| No test asserts the stored node text | Tree-wide search for `PARTITIONBOUNDSPEC` under `src/` and `doc/` returns no match; the only direct readers are [indexing.sql#relpartbound](../../../../raw/postgres-18/src/test/regress/sql/indexing.sql#L70-L75) and [detach-partition-concurrently-1.spec](../../../../raw/postgres-18/src/test/isolation/specs/detach-partition-concurrently-1.spec#L35-L46) |

## Open Questions

- **Where the 8,160-byte cliff actually bites is workload-specific and was measured on one platform.** The 8,000-versus-8,400-character boundary above holds for hex literals of a `text` key on this x86-64 build with default `BLCKSZ`; the effective limit depends on compressibility, the key type's on-disk width, and how much of the `pg_class` row the other attributes occupy. No source-level constant expresses "maximum bound size".
- **Whether the `d20d8fbd3e4` location change was considered for its catalog side effects is not established from the pinned tree.** The commit message frames it as a debugging/readability change for node serialization generally; the pin contains no note about `relpartbound`, `pg_index.indexprs`, `pg_attrdef.adbin` or other `pg_node_tree` columns whose stored text it also altered.
- **The `"minvalue"`-quoted-accepted / `"MINVALUE"`-quoted-rejected asymmetry is observed behavior with no documentation or test in the pin.** Whether it is intended or an accident of `transformPartitionRangeBounds()` matching a downcased string cannot be settled from the pinned checkout.
- **Foreign-table partitions were not measured.** `CREATE FOREIGN TABLE ... PARTITION OF` uses the same production, but no exact-pin test was run for it here, so the storage and deparse claims are source-derived rather than observed for that relkind.
- The page is marked `(unverified)` because `verified:` is human-only and `verified_by_agent` has not been advanced after a separate full-page re-check.

## Source References

- [gram.y](../../../../raw/postgres-18/src/backend/parser/gram.y) - bound grammar production, hash option list, and all bound use sites.
- [parse_utilcmd.c](../../../../raw/postgres-18/src/backend/parser/parse_utilcmd.c) - bound transform, sentinel recognition, sentinel ordering, and element evaluation.
- [parsenodes.h](../../../../raw/postgres-18/src/include/nodes/parsenodes.h) - `PartitionBoundSpec`, `PartitionRangeDatum`, `PartitionRangeDatumKind`, `PartitionCmd`.
- [pg_class.h](../../../../raw/postgres-18/src/include/catalog/pg_class.h) - the `relpartbound` column definition.
- [heap.c](../../../../raw/postgres-18/src/backend/catalog/heap.c) - `StorePartitionBound` and the null-at-creation site.
- [tablecmds.c](../../../../raw/postgres-18/src/backend/commands/tablecmds.c) - attach/detach callers and the clearing code.
- [outfuncs.c](../../../../raw/postgres-18/src/backend/nodes/outfuncs.c) - node serialization primitives, `outDatum`, and the location-field policy.
- [gen_node_support.pl](../../../../raw/postgres-18/src/backend/nodes/gen_node_support.pl) - generation of the bound node's out/read/copy/equal functions.
- [ruleutils.c](../../../../raw/postgres-18/src/backend/utils/adt/ruleutils.c) - bound deparse, `pg_get_expr`, `pg_get_partition_constraintdef`.
- [partdesc.c](../../../../raw/postgres-18/src/backend/partitioning/partdesc.c) - partition-descriptor read path and retry logic.
- [partcache.c](../../../../raw/postgres-18/src/backend/utils/cache/partcache.c) - per-partition qual generation from the stored bound.
- [partbounds.c](../../../../raw/postgres-18/src/backend/partitioning/partbounds.c) - default-partition constraint construction from sibling bounds.
- [partbounds.h](../../../../raw/postgres-18/src/include/partitioning/partbounds.h) - the internal `PartitionBoundInfoData` form.
- [kwlist.h](../../../../raw/postgres-18/src/include/parser/kwlist.h) - keyword categories for `minvalue`/`maxvalue`.
- [describe.c](../../../../raw/postgres-18/src/bin/psql/describe.c) - psql `\d`/`\d+` bound output.
- [pg_dump.c](../../../../raw/postgres-18/src/bin/pg_dump/pg_dump.c) - `ATTACH PARTITION` emission.
- [catalogs.sgml](../../../../raw/postgres-18/doc/src/sgml/catalogs.sgml) - `pg_class.relpartbound` description.
- [create_table.sgml](../../../../raw/postgres-18/doc/src/sgml/ref/create_table.sgml) - bound synopsis and semantics.
- [alter_table.sgml](../../../../raw/postgres-18/doc/src/sgml/ref/alter_table.sgml) - `ATTACH PARTITION` synopsis.
- [func.sgml](../../../../raw/postgres-18/doc/src/sgml/func.sgml) - `pg_get_expr` and `pg_get_partition_constraintdef` documentation.
- [create_table.sql](../../../../raw/postgres-18/src/test/regress/sql/create_table.sql) and [create_table.out](../../../../raw/postgres-18/src/test/regress/expected/create_table.out) - bound syntax and deparse coverage.
- [indexing.sql](../../../../raw/postgres-18/src/test/regress/sql/indexing.sql) and [indexing.out](../../../../raw/postgres-18/src/test/regress/expected/indexing.out) - null `relpartbound` for partitioned indexes.
- [detach-partition-concurrently-1.spec](../../../../raw/postgres-18/src/test/isolation/specs/detach-partition-concurrently-1.spec) - `relpartbound` visibility during concurrent detach.
- [misc_sanity.out](../../../../raw/postgres-18/src/test/regress/expected/misc_sanity.out) - catalogs without TOAST tables.

## Navigation

- [v18/index](../../index.md)
- [versions](../../../versions.md)
- [wiki index](../../../index.md)
- [PostgreSQL 18 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [Extracting Declarative Range Partition Bounds With SQL and No Regex in PostgreSQL 12 (unverified)](../../../v12/questions/server-administration/extract-range-partition-bounds-without-regex.md)
- [Table Partitioning Optimizations and Configuration During Query Planning and Execution in PostgreSQL 17 (unverified)](../../../v17/questions/query-planning/partitioning-planning-execution-optimizations.md)
