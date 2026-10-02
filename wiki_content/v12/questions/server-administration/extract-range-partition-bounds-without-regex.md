---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# Extracting Declarative Range Partition Bounds With SQL and No Regex in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Verdict](#verdict)
  - [What PostgreSQL 12 stores for a range partition](#what-postgresql-12-stores-for-a-range-partition)
  - [The exact grammar of a deparsed range bound](#the-exact-grammar-of-a-deparsed-range-bound)
  - [Why a plain split is unsafe](#why-a-plain-split-is-unsafe)
  - [The recipe](#the-recipe)
  - [Which partitions the query returns](#which-partitions-the-query-returns)
  - [Turning the text back into typed values](#turning-the-text-back-into-typed-values)
  - [Session settings that change the text](#session-settings-that-change-the-text)
  - [Locks privileges and cost](#locks-privileges-and-cost)
  - [Concurrency and error boundaries](#concurrency-and-error-boundaries)
  - [A simpler variant when the bounds are provably quote-free](#a-simpler-variant-when-the-bounds-are-provably-quote-free)
  - [Rejected alternatives](#rejected-alternatives)
  - [Exact-pin measurements](#exact-pin-measurements)
  - [Caller data-structure generated-header and test boundaries](#caller-data-structure-generated-header-and-test-boundaries)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 12, question: for a table partitioned using declarative range partitioning, propose a way using SQL with no regex to extract the partition range bounds.

## Answer

### Verdict

PostgreSQL 12 has no catalog column, view, or function that returns a range partition's bounds as typed values. The bounds have exactly two direct SQL-visible forms:

1. `pg_class.relpartbound`, an opaque `pg_node_tree` whose text form dumps each bound datum as raw bytes ([pg_class.h:137](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L137), [outfuncs.c#outDatum](../../../../raw/postgres-12/src/backend/nodes/outfuncs.c#L255-L288)).
2. The deparsed string from `pg_get_expr(relpartbound, oid)`, which is what `psql \d` and `pg_dump` themselves consume ([describe.c#Partition-of](../../../../raw/postgres-12/src/bin/psql/describe.c#L2111-L2134), [pg_dump.c#ATTACH-PARTITION](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L15986-L16005)).

`pg_get_partition_constraintdef(oid)` is a third, derived form, but it is a boolean expression rather than a bound list; [Rejected alternatives](#rejected-alternatives) explains why it is harder, not easier, to decompose.

So any SQL extraction must decompose form 2 — and that needs no regular expression, because the deparser emits a fixed, narrow grammar: the literal prefix `FOR VALUES FROM (`, the separator `) TO (`, elements separated by `, `, and each element either the bare keyword `MINVALUE`/`MAXVALUE` or a plain SQL literal with **no** `::type` decoration and no `COLLATE` clause ([ruleutils.c#get_range_partbound_string](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L11284-L11318), [ruleutils.c#T_PartitionBoundSpec](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L8985-L8994)).

The one hazard is that a `text`-typed bound can itself contain `, `, `) TO (`, or a quote, so splitting on those separators directly is wrong. The fix is still regex-free: split the string on the single-quote character with `string_to_array`, mask the literal contents, then locate the separators in the mask with `strpos`/`substr`. On the pinned 12.2 build this recipe reproduced all 95 control bound elements across 45 partitions, while the obvious `split_part` version got 9 of 41 partitions wrong. [The recipe](#the-recipe) has the query; [Exact-pin measurements](#exact-pin-measurements) has the numbers.

### What PostgreSQL 12 stores for a range partition

`CREATE TABLE ... PARTITION OF` and `ALTER TABLE ... ATTACH PARTITION` both run the bound through the same transform, then store `nodeToString()` of the resulting node in `pg_class.relpartbound` and set `relispartition` ([heap.c#StorePartitionBound](../../../../raw/postgres-12/src/backend/catalog/heap.c#L3757-L3770), [pg_class.h:117](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L117)). The parent relation is found through `pg_inherits.inhparent` ([pg_inherits.h#pg_inherits](../../../../raw/postgres-12/src/include/catalog/pg_inherits.h#L32-L37)).

Three properties of that stored node make text extraction reliable:

- **Every range bound datum is a `Const` of the partition key's type.** The grammar accepts a general `expr_list` ([gram.y#PartitionBoundSpec](../../../../raw/postgres-12/src/backend/parser/gram.y#L2752-L2765)), but `transformPartitionBoundValue` coerces the expression to the key column's type and typmod and then evaluates it to a `Const` carrying the key's collation ([parse_utilcmd.c#transformPartitionBoundValue](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c#L4021-L4088)). The documentation states the same contract: "The expression is evaluated once at table creation time, so it can even contain volatile expressions" ([create_table.sgml#partition_bound_expr](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L415-L423)). So `relpartbound` never holds a function call or an operator expression to re-evaluate.
- **A range bound is never NULL and never a subquery, aggregate, window function, or set-returning function.** `transformPartitionRangeBounds` rejects NULL explicitly ([parse_utilcmd.c#cannot-specify-NULL](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c#L3948-L3955)), and `EXPR_KIND_PARTITION_BOUND` rejects the rest ([parse_expr.c#subquery](../../../../raw/postgres-12/src/backend/parser/parse_expr.c#L1919-L1921), [parse_expr.c#column-reference](../../../../raw/postgres-12/src/backend/parser/parse_expr.c#L580-L582), [parse_agg.c#aggregate](../../../../raw/postgres-12/src/backend/parser/parse_agg.c#L509-L512), [parse_agg.c#window](../../../../raw/postgres-12/src/backend/parser/parse_agg.c#L921-L923), [parse_func.c#SRF](../../../../raw/postgres-12/src/backend/parser/parse_func.c#L2522-L2524)). On the pin, `FOR VALUES FROM ('c') TO ('c' || (SELECT ...))` failed with `cannot use subquery in partition bound`.
- **The key column's type cannot drift away from the stored `Const`.** `ALTER TABLE ... ALTER COLUMN ... TYPE` and `DROP COLUMN` both refuse a partition key column ([tablecmds.c#ATPrepAlterColumnType](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L10375-L10382), [tablecmds.c#ATExecDropColumn](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L7145-L7152)). That is what makes `pg_attribute.atttypid` a trustworthy cast target for the extracted text. Renaming a key column is allowed and is picked up automatically, because bounds are positional.

Reading the node tree directly is a dead end. `_outConst` writes `constvalue` as a byte dump, so a v12 `int4` bound of 1 stores `:constvalue 4 [ 1 0 0 0 0 0 0 0 ]` ([outfuncs.c#_outConst](../../../../raw/postgres-12/src/backend/nodes/outfuncs.c#L1079-L1097)), measured verbatim on the pin.

`relpartbound` is also one of the few toastable catalog columns in a catalog with no TOAST table, which the regression suite asserts ([misc_sanity.out#toastable-columns](../../../../raw/postgres-12/src/test/regress/expected/misc_sanity.out#L90-L110), `pg_class | relpartbound | pg_node_tree` at line 105). Long bounds therefore hit the heap tuple ceiling in `RelationGetBufferForTuple` ([hio.c#row-is-too-big](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L339-L346)); see [Concurrency and error boundaries](#concurrency-and-error-boundaries).

### The exact grammar of a deparsed range bound

`pg_get_expr` reconstructs the node with `stringToNode` and the standard deparser ([ruleutils.c#pg_get_expr](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L2344-L2385), [ruleutils.c#pg_get_expr_worker](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L2412-L2439)). For a `PartitionBoundSpec` the output is one of exactly four shapes ([ruleutils.c#T_PartitionBoundSpec](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L8945-L9002)):

| Partition | Deparsed text |
|---|---|
| default, any strategy | `DEFAULT` |
| hash | `FOR VALUES WITH (modulus M, remainder R)` |
| list | `FOR VALUES IN (` elements `)` |
| range | `FOR VALUES FROM (` elements `) TO (` elements `)` |

The two range tuples come from `get_range_partbound_string`, which writes `(`, joins elements with the two-character separator `", "`, and writes `)`. A `PartitionRangeDatum` whose `kind` is `PARTITION_RANGE_DATUM_MINVALUE` or `..._MAXVALUE` prints as the bare keyword; otherwise the `Const` prints through `get_const_expr(val, &context, -1)` ([ruleutils.c#get_range_partbound_string](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L11284-L11318), [parsenodes.h#PartitionRangeDatum](../../../../raw/postgres-12/src/include/nodes/parsenodes.h#L829-L850)).

The `showtype = -1` argument is what keeps the text simple: `get_const_expr` returns before it can append `::typename` or a `COLLATE` clause ([ruleutils.c#get_const_expr](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L9600-L9646)). What remains is a small per-type rule set ([ruleutils.c#get_const_expr-switch](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L9552-L9603)):

| Const type | Printed as | Measured example on the pin |
|---|---|---|
| `int4`, non-negative | bare digits | `FOR VALUES FROM (0) TO (100)` |
| `int4`, negative | quoted, still no cast, because `showtype < 0` returns first | `FOR VALUES FROM ('-100') TO (0)` |
| `numeric` that looks like a float and has no leading sign | bare | `FOR VALUES FROM (1.5) TO ('10')` |
| `numeric` otherwise, including integral values | quoted | `FOR VALUES FROM ('10') TO ('1000')` |
| `bool` | the SQL keyword `true` / `false` | `FOR VALUES FROM (false) TO (true)` |
| anything else | `simple_quote_literal` of the type's output text | `FOR VALUES FROM ('2020-01-01') TO ('2020-02-01')` |

Upstream expected output shows the negative-`int4` rule in the same statement as the positive one: `Partition of: partitioned2 FOR VALUES FROM ('-1', 'aaaaa') TO (100, 'ccccc')` ([create_table.out#negative-int4-bound](../../../../raw/postgres-12/src/test/regress/expected/create_table.out#L504-L512)), and the unbounded keywords appear at [create_table.out#MINVALUE-MAXVALUE](../../../../raw/postgres-12/src/test/regress/expected/create_table.out#L1022-L1031). A default partition's footer is `Partition of: range_parted DEFAULT` ([update.out#default-partition](../../../../raw/postgres-12/src/test/regress/expected/update.out#L714-L724)).

`simple_quote_literal` never emits an `E''` string; it doubles the quote character always and the backslash only when `standard_conforming_strings` is off ([ruleutils.c#simple_quote_literal](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L9668-L9691)). That single conditional is the only session-dependent part of the *quoting*; [Session settings that change the text](#session-settings-that-change-the-text) covers the value text itself.

Two more properties, both measured over 45 partitions on the pin:

- The `pretty` flag makes no difference for a range bound, and neither does passing `0` instead of the partition OID: all 45 partitions produced identical text for `pg_get_expr(relpartbound, oid)`, `pg_get_expr(relpartbound, 0)`, and `pg_get_expr(relpartbound, oid, true)`. `get_range_partbound_string` builds its own zeroed deparse context, so no indent flag reaches it ([ruleutils.c#get_range_partbound_string](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L11284-L11296)), and passing zero is documented as sufficient when no `Var` can appear ([func.sgml#pg_get_expr-notes](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L18854-L18874)).
- No bound text contained `::`, so the structural characters cannot be confused with a type name such as `numeric(10,2)`. Newlines appear only *inside* literals, never in the structure — two fixture bounds carried one.

The strongest evidence that this text is a complete, re-parseable literal is that `pg_dump` pastes it verbatim into `ALTER TABLE ONLY ... ATTACH PARTITION ... <bound>;` ([pg_dump.c#ATTACH-PARTITION](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L15986-L16005), [pg_dump.c#partbound-query](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L5984-L5989)), and the dump test asserts the exact string ([002_pg_dump.pl#attach-partition-bound](../../../../raw/postgres-12/src/bin/pg_dump/t/002_pg_dump.pl#L730-L742)).

### Why a plain split is unsafe

The obvious extraction is `split_part(bound_def, ') TO (', 1)` plus `split_part(tuple, ', ', n)` plus `btrim(elem, '''')`. It is regex-free, but it trusts three separators that a `text` bound can contain, and it cannot un-double an escaped quote. Measured against the control values on the pin, that version was wrong on 13 of 94 bound elements and 9 of 41 partitions:

| Partition and element | Correct value | What the plain split returned | Cause |
|---|---|---|---|
| `p_nasty_1` from 1 | `01) TO (x` | `01` | value contains the tuple separator |
| `p_nasty_1` to 1 | `02a'b` | `x` | same, cascading into the upper tuple |
| `p_nasty_2` from 1 | `02a'b` | `02a''b` | escaped quote not un-doubled |
| `p_nasty_2` to 1 | `03a''b` | `03a''''b` | same |
| `p_nasty_3` from 1 | `03a''b` | `03a''''b` | same |
| `p_nasty_3` to 1 | `04a, b` | `04a` | value contains the element separator |
| `p_nasty_4` from 1 | `04a, b` | `04a` | same |
| `p_nasty_8` to 1 | `09FOR VALUES FROM (x) TO (y)` | `09FOR VALUES FROM (x` | value contains the tuple separator |
| `p_nasty_9` from 1 | `09FOR VALUES FROM (x) TO (y)` | `09FOR VALUES FROM (x` | same |
| `p_nasty_9` to 1 | `10'quoted'` | `y)` | same |
| `p_nasty_10` from 1 | `10'quoted'` | `10''quoted` | `btrim` strips every quote at both ends of `'10''quoted'''` and leaves the interior pair doubled |
| `p_multi_c` to 2 | `m, m` | `m` | multi-column element contains `, ` |
| `p_multi_d` from 2 | `m, m` | `m` | same |

No upstream regression test covers a range bound whose literal contains a comma, a quote, or a backslash, so these shapes are only observable by construction; the two upstream near-misses are LIST bounds that are never deparsed. See [Open Questions](#open-questions).

### The recipe

The idea is to make the literals harmless before looking for structure. `string_to_array(bound_def, '''')` splits the text at every single-quote character, keeping empty elements ([varlena.c#text_to_array_internal](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L4744-L4783), asserted upstream as `{1,2,3,4,"",6}` in [arrays.out#string_to_array](../../../../raw/postgres-12/src/test/regress/expected/arrays.out#L1740-L1744)). Because `simple_quote_literal` writes the two quotes of an escaped quote adjacently, every odd-numbered segment that is *not* empty lies outside a literal, and every structural character lives in one of those segments. Replacing each even-numbered segment with an equal-length run of `x` yields a mask that has the same character length and the same structural characters as the original, so `strpos` on the mask gives positions valid in the original.

The query uses only non-regex functions: `string_to_array`, `array_to_string`, `array_agg`, `repeat`, `length`, `strpos`, `substr`, `replace`, `unnest ... WITH ORDINALITY`. It deliberately uses `substr` rather than `substring`, because only `substring(text, text)` resolves to the regex implementation `textregexsubstr` ([pg_proc.dat#substring-regex](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L5743-L5749), [gram.y#substring-overload](../../../../raw/postgres-12/src/backend/parser/gram.y#L14482-L14490)); `substr` has no `(text, text)` overload ([pg_proc.dat#substr](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L3403-L3405)).

```sql
SET statement_timeout = '30s';
SET lock_timeout = '2s';
SET standard_conforming_strings = on;

WITH part AS (
    SELECT i.inhparent AS parent_oid,
           c.oid       AS part_oid,
           p.partnatts,
           p.partattrs,
           pg_catalog.pg_get_expr(c.relpartbound, c.oid) AS bound_def
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_inherits i ON i.inhrelid = c.oid
    JOIN pg_catalog.pg_partitioned_table p ON p.partrelid = i.inhparent
    WHERE c.relispartition
      AND c.relkind = ANY (ARRAY['r', 'p', 'f'])
      AND p.partstrat = 'r'
), seg AS (
    SELECT part.*, s.ord, s.txt
    FROM part
    CROSS JOIN LATERAL unnest(string_to_array(part.bound_def, ''''))
                       WITH ORDINALITY AS s(txt, ord)
    WHERE part.bound_def <> 'DEFAULT'
), masked AS (
    SELECT parent_oid, part_oid, partnatts, partattrs, bound_def,
           array_to_string(
               array_agg(CASE WHEN ord % 2 = 0 THEN repeat('x', length(txt))
                              ELSE txt END
                         ORDER BY ord), '''') AS mask
    FROM seg
    GROUP BY parent_oid, part_oid, partnatts, partattrs, bound_def
), split AS (
    SELECT masked.*, strpos(mask, ') TO (') AS sep
    FROM masked
    WHERE substr(bound_def, 1, 17) = 'FOR VALUES FROM ('
), sides AS (
    SELECT parent_oid, part_oid, partnatts, partattrs, 'from'::text AS side,
           substr(bound_def, 18, sep - 18) AS tuple,
           substr(mask,      18, sep - 18) AS tuple_mask
    FROM split
    UNION ALL
    SELECT parent_oid, part_oid, partnatts, partattrs, 'to'::text,
           substr(bound_def, sep + 6, length(bound_def) - sep - 6),
           substr(mask,      sep + 6, length(mask)      - sep - 6)
    FROM split
), elem AS (
    SELECT sides.*, e.ord AS key_pos,
           substr(sides.tuple,
                  (sum(length(e.masked_elem) + 2)
                       OVER (PARTITION BY sides.part_oid, sides.side
                             ORDER BY e.ord)
                     - length(e.masked_elem) - 1)::int,
                  length(e.masked_elem)) AS elem
    FROM sides
    CROSS JOIN LATERAL unnest(string_to_array(sides.tuple_mask, ', '))
                       WITH ORDINALITY AS e(masked_elem, ord)
)
SELECT /* wiki_extract_range_partition_bounds */
       elem.parent_oid::regclass AS parent,
       elem.part_oid::regclass   AS partition,
       elem.side,
       elem.key_pos,
       a.attname                 AS key_column,
       a.atttypid::regtype       AS key_type,
       CASE elem.elem WHEN 'MINVALUE' THEN 'MINVALUE'
                      WHEN 'MAXVALUE' THEN 'MAXVALUE'
                      ELSE 'value' END AS kind,
       CASE WHEN elem.elem = 'MINVALUE' OR elem.elem = 'MAXVALUE' THEN NULL
            WHEN substr(elem.elem, 1, 1) = ''''
              THEN replace(substr(elem.elem, 2, length(elem.elem) - 2),
                           '''''', '''')
            ELSE elem.elem
       END AS bound_value
FROM elem
LEFT JOIN pg_catalog.pg_attribute a
       ON a.attrelid = elem.parent_oid
      AND a.attnum   = elem.partattrs[elem.key_pos - 1]
UNION ALL
SELECT i.inhparent::regclass, c.oid::regclass, 'default', NULL, NULL, NULL,
       'DEFAULT', NULL
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_inherits i ON i.inhrelid = c.oid
JOIN pg_catalog.pg_partitioned_table p ON p.partrelid = i.inhparent
WHERE c.relispartition
  AND c.relkind = ANY (ARRAY['r', 'p', 'f'])
  AND p.partstrat = 'r'
  AND pg_catalog.pg_get_expr(c.relpartbound, c.oid) = 'DEFAULT'
ORDER BY 1, 2, 3, 4;
```

All three settings are `PGC_USERSET`, so they apply to the session or transaction only — no reload and no restart ([guc.c#standard_conforming_strings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1721-L1730), [guc.c#statement_timeout-lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2396)). Use `SET LOCAL` inside a transaction if you do not want them to outlive it.

Output shape, one row per partition per side per key position:

| Column | Meaning |
|---|---|
| `parent`, `partition` | `regclass`, schema-qualified when the relation is not on `search_path` |
| `side` | `from`, `to`, or `default` |
| `key_pos` | 1-based partition key position; `NULL` on a `default` row |
| `key_column` | key column name, or `NULL` when that key position is an expression |
| `key_type` | the key column's type, the cast target for `bound_value` |
| `kind` | `value`, `MINVALUE`, `MAXVALUE`, or `DEFAULT` |
| `bound_value` | the unquoted bound text, `NULL` unless `kind = 'value'` |

`partattrs` is subscripted from zero because `int2vector` sets its array lower bound to 0 "for historical reasons" ([int.c#buildint2vector](../../../../raw/postgres-12/src/backend/utils/adt/int.c#L113-L135)); a zero entry marks an expression key ([catalogs.sgml#partattrs](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L4859-L4871)). Expression keys therefore return `key_column` and `key_type` as `NULL`, verified on a `PARTITION BY RANGE ((a + b))` fixture; use `pg_get_partkeydef(parent)` if you need the expression text.

### Which partitions the query returns

The `relispartition` + `pg_inherits` + `pg_partitioned_table` join with `partstrat = 'r'` is what scopes the result ([catalogs.sgml#partstrat](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L4831-L4839)). Measured behavior on the pin:

| Case | Result |
|---|---|
| List and hash partitions | excluded by `partstrat = 'r'`; their texts are `FOR VALUES IN (...)` and `FOR VALUES WITH (...)` |
| Default partition of a range parent | one row with `kind = 'DEFAULT'` |
| A partition that is itself partitioned | included, `relkind = 'p'`; its own sub-partitions are separate rows under it as parent |
| Foreign-table partition | admitted by `relkind = 'f'`, which the grammar allows ([gram.y#CREATE-FOREIGN-TABLE-PARTITION-OF](../../../../raw/postgres-12/src/backend/parser/gram.y#L5006-L5029)); untested here, see [Open Questions](#open-questions) |
| Index partitions | excluded; `relispartition` is also true for partitioned-index children, but they are filtered by `relkind` and carry no `relpartbound` |
| Detached partition | absent, because `ALTER TABLE ... DETACH PARTITION` sets `relpartbound` to NULL and `relispartition` to false ([tablecmds.c#DETACH-clears-relpartbound](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16288-L16309)) |
| Partition created by `ATTACH` rather than `PARTITION OF` | identical treatment; both paths call `StorePartitionBound` |
| Partition in another schema | included, rendered as `schema.table` by `regclass` output |

### Turning the text back into typed values

`bound_value` is the key type's own input/output text, because the stored `Const` has the key's type and the deparser used that type's output function. So `bound_value::<key type>` is the correct conversion, and it is what you should sort and compare on rather than the text:

```sql
SELECT /* wiki_range_partitions_by_lower_bound */
       partition, bound_value::date AS lower_bound
FROM ( /* the recipe above */ ) b
WHERE parent = 'measurement'::regclass AND side = 'from' AND kind = 'value'
ORDER BY bound_value::date;
```

Round-tripping every extracted value through its key type on the pin reproduced the text exactly in 78 of 81 cases. The three exceptions are the boolean bounds, where the deparser prints the SQL keywords `true`/`false` while `boolean`'s output function prints `t`/`f`; the cast back still succeeds. One more type-specific quirk: a `char(3)` bound deparses blank-padded as `'a  '`, which matches the `bpchar` output function but not `('a'::char(3))::text`.

Three semantic warnings:

- `MINVALUE`/`MAXVALUE` are not values. They are unbounded markers, and the documentation contrasts them with a storable `'infinity'`: `FROM ('infinity') TO (MAXVALUE)` is a one-value range, not an empty one ([create_table.sgml#MINVALUE-MAXVALUE-vs-infinity](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L478-L489)). A quoted `'MINVALUE'` is an ordinary `text` value; the `kind` column is what separates the two, and the recipe keeps them apart because it tests the element before unquoting.
- The lower bound is inclusive and the upper bound exclusive, compared row-wise across key columns ([create_table.sgml#bound-comparison](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L433-L447)).
- The key's collation is invisible in the text. `get_const_expr` skips `get_const_collation` at `showtype = -1`, so a `text` key declared `COLLATE "C"` deparses like any other. Order comparisons on extracted text must apply the key collation from `pg_partitioned_table.partcollation` yourself.

### Session settings that change the text

`get_const_expr` calls the type's output function, so every output-affecting `PGC_USERSET` setting changes the deparsed literal. Measured on the pin, one fixture partition per type:

| Setting | Value | Deparsed bound |
|---|---|---|
| `DateStyle` ([guc.c#DateStyle](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3612-L3622)) | `ISO, MDY` | `FOR VALUES FROM ('2020-01-01') TO ('2020-02-01')` |
| | `SQL, DMY` | `FOR VALUES FROM ('01/01/2020') TO ('01/02/2020')` |
| | `German` | `FOR VALUES FROM ('01.01.2020') TO ('01.02.2020')` |
| `TimeZone` ([guc.c#TimeZone](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3904-L3913)) | `UTC` | `FOR VALUES FROM ('2020-01-01 00:00:00+00') TO ('2020-02-01 00:00:00+00')` |
| | `Asia/Tokyo` | `FOR VALUES FROM ('2020-01-01 09:00:00+09') TO ('2020-02-01 09:00:00+09')` |
| | `America/New_York` | `FOR VALUES FROM ('2019-12-31 19:00:00-05') TO ('2020-01-31 19:00:00-05')` |
| `IntervalStyle` ([guc.c#IntervalStyle](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4275-L4284)) | `postgres` | `FOR VALUES FROM ('1 day') TO ('1 mon')` |
| | `iso_8601` | `FOR VALUES FROM ('P1D') TO ('P1M')` |
| `extra_float_digits` ([guc.c#extra_float_digits](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2690-L2700)) | `1` (v12 default) | `FOR VALUES FROM ('0.1') TO ('1234567890.12345')` |
| | `-3` | `FOR VALUES FROM ('0.1') TO ('1234567890.12')` |
| `bytea_output` ([guc.c#bytea_output](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4221-L4229)) | `hex` | `FOR VALUES FROM ('\x7830303031') TO ('\x7830306666')` |
| | `escape` | `FOR VALUES FROM ('x0001') TO ('x00ff')` |
| `standard_conforming_strings` ([guc.c#standard_conforming_strings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1721-L1730)) | `on` (default) | `FOR VALUES FROM ('05MINVALUE') TO ('06back\slash')` |
| | `off` | `FOR VALUES FROM ('05MINVALUE') TO ('06back\\slash')` |

Every one of these is `PGC_USERSET`, so pinning them is a session or transaction change; none needs a reload or restart. `client_encoding` is in the same class ([guc.c#client_encoding](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3581-L3588)).

Only the last one breaks the extraction rather than merely reformatting it: with `standard_conforming_strings = off`, the deparser doubles backslashes, and the recipe returned `06back\\slash` — 91 of 95 control rows correct, the four failures being two `bytea` bounds and two `text` bounds with a backslash. Pinning the setting, as the recipe does, restored 95 of 95. If you cannot control the setting, invert the doubling conditionally. Write the two patterns as `E''` escape strings, because `E''` is interpreted the same way under both settings:

```sql
SELECT /* wiki_range_bounds_backslash_safe */
       parent, partition, side, key_pos, kind,
       CASE WHEN kind <> 'value' THEN NULL
            WHEN current_setting('standard_conforming_strings')::bool
              THEN bound_value
            ELSE replace(bound_value, E'\\\\', E'\\')
       END AS bound_value
FROM ( /* the recipe above */ ) b;
```

That form scored 95 of 95 with the setting both on and off. The naive spelling `replace(bound_value, '\\', '\')` is a trap: submitted under `standard_conforming_strings = off` it does not even parse, failing with two `nonstandard use of \\ in a string literal` warnings and `ERROR: unterminated quoted string`, because `'\'` then consumes the closing quote. A view or function whose body was *parsed* while the setting was on keeps the parse-time meaning and keeps working, which is easy to mistake for the ad-hoc query being safe.

### Locks privileges and cost

The extraction reads catalogs only. Inside a transaction on the pin, with 1047 range partitions present and 2107 rows returned, the backend held 14 `AccessShareLock` relation locks — the catalogs, their indexes, and the wrapper view used for the test — and **no lock on any partition or parent table**. Nothing in the query opens a partition, so it cannot be blocked by DML and cannot block DDL beyond ordinary catalog access.

Any login role can read every bound. A freshly created `nopriv` role with no table privileges returned all 2109 rows of the recipe, and read `FOR VALUES FROM ('2020-01-01') TO ('2020-02-01')` for a partition whose schema it could not even access (`permission denied for schema pb` for a plain `SELECT`). That is expected: `pg_class`, `pg_inherits`, `pg_partitioned_table`, and `pg_attribute` are world-readable and `pg_get_expr` is executable by `PUBLIC` ([pg_proc.dat#pg_get_expr](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L3571-L3573)). Treat partition bounds as non-confidential metadata: they leak the key ranges of tables a role cannot read.

Cost, measured on the pin with 1048 range partitions producing 2109 rows: 44.9 ms then 39.9 ms for the masking recipe, 8.3 ms and 9.2 ms for the plain-split version, 1.8 ms for a bare catalog row count, and 31.9 ms of `EXPLAIN (ANALYZE)` execution time. The plan evaluates `pg_get_expr` twice per partition in the filter and once per surviving row, so the cost scales with partition count, not table size.

### Concurrency and error boundaries

- **A concurrently dropped partition yields a NULL deparse, not an error.** `pg_get_expr` returns NULL when `get_rel_name` cannot resolve the OID, deliberately, "to help avoid unwanted failures when examining catalog entries for just-deleted relations" ([ruleutils.c#pg_get_expr-missing-relation](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L2367-L2380)). Reproduced on the pin: in a `REPEATABLE READ` transaction whose snapshot predates a concurrent `DROP TABLE`, the `pg_class` row was still visible with `relpartbound` present, yet `pg_get_expr(relpartbound, c.oid)` was NULL and `c.oid::regclass::text` rendered the bare OID `31545`. The recipe silently drops such rows, because the `FOR VALUES FROM (` guard is NULL-false. `pg_get_expr(relpartbound, 0)` was **not** NULL in the same test, since passing zero skips the relation lookup; use it if you would rather see a stale row than lose one.
- **Very long bounds can exceed the `pg_class` tuple limit.** With no TOAST table for `pg_class`, a compressible 1000-character `text` bound stored in 337 bytes and extracted at full length, an incompressible 1280-character bound stored 1670 bytes and extracted at 1281 characters, and a 9600-character bound failed at DDL time with `ERROR 54000: row is too big: size 9304, maximum size 8160` ([hio.c#row-is-too-big](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L339-L346)). This is a partition-creation limit, not an extraction limit.
- **An empty-string bound works.** `FOR VALUES FROM ('') TO ('a')` extracted a zero-length `bound_value`. The `masked` CTE never sees an empty `bound_def`, which would produce a zero-element array from `string_to_array` ([varlena.c#empty-input](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L4712-L4714)), because a live partition always has a non-empty deparse.
- **Use the two-argument `string_to_array`.** The three-argument form with an empty null-string would turn empty segments into NULLs and break the mask ([func.sgml#string_to_array-null-string](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L14390-L14405)).

### A simpler variant when the bounds are provably quote-free

If a survey shows no bound text contains a quote at all — true whenever every key bound is a non-negative `int4`, a float-looking `numeric`, or `boolean` — no literal can hide a separator, and the raw element text *is* the value. Gate it explicitly rather than assuming it:

```sql
SELECT /* wiki_range_bounds_quote_free_gate */
       count(*) AS partitions_with_quoted_bounds
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_inherits i ON i.inhrelid = c.oid
JOIN pg_catalog.pg_partitioned_table p ON p.partrelid = i.inhparent
WHERE c.relispartition AND p.partstrat = 'r'
  AND strpos(pg_catalog.pg_get_expr(c.relpartbound, c.oid), '''') > 0;
```

If that returns 0, this is enough:

```sql
SELECT /* wiki_range_bounds_simple */
       i.inhparent::regclass AS parent,
       c.oid::regclass       AS partition,
       g.key_pos,
       split_part(substr(split_part(d.bound_def, ') TO (', 1), 18), ', ',
                  g.key_pos) AS lower_bound,
       split_part(btrim(split_part(d.bound_def, ') TO (', 2), ')'), ', ',
                  g.key_pos) AS upper_bound
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_inherits i ON i.inhrelid = c.oid
JOIN pg_catalog.pg_partitioned_table p ON p.partrelid = i.inhparent
CROSS JOIN LATERAL (SELECT pg_catalog.pg_get_expr(c.relpartbound, c.oid)) AS d(bound_def)
CROSS JOIN LATERAL generate_series(1, p.partnatts) AS g(key_pos)
WHERE c.relispartition
  AND c.relkind = ANY (ARRAY['r', 'p', 'f'])
  AND p.partstrat = 'r'
  AND substr(d.bound_def, 1, 17) = 'FOR VALUES FROM ('
ORDER BY 1, 2, 3;
```

This variant does no unquoting at all: it returns the element exactly as the deparser wrote it, so `MINVALUE`/`MAXVALUE` come back as those words and a quoted literal comes back with its quotes. That is why the gate matters. Measured on the pin over the fixture set, which contained 11 quote-free and 1036 quoted non-default range partitions: on the gated subset it matched the control on 18 of 18 elements; on the non-gated subset it matched only 19 of 76, the rest differing by the surrounding quotes or by a swallowed separator.

### Rejected alternatives

| Alternative | Why it does not work in v12 |
|---|---|
| `relpartbound::text` and parse the node tree | `constvalue` is a byte dump of the datum, machine-specific and not convertible in SQL ([outfuncs.c#outDatum](../../../../raw/postgres-12/src/backend/nodes/outfuncs.c#L255-L288)) |
| `pg_get_partition_constraintdef(oid)` | Returns a boolean expression, not bounds: `((a IS NOT NULL) AND (b IS NOT NULL) AND (a = 1) AND (b >= 'a'::text) AND (b < 'z'::text))` on the pin. It carries `::type` decorations, `AND`/`OR` structure, and is negated for the default partition, so it is strictly harder to decompose ([ruleutils.c#pg_get_partition_constraintdef](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L1808-L1837)) |
| `pg_partition_tree`, `pg_partition_root`, `pg_partition_ancestors` | Return only `relid`, `parentrelid`, `isleaf`, `level`; no bound column ([func.sgml#partitioning-functions](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L21553-L21603), [partition_info.sql#pg_partition_tree](../../../../raw/postgres-12/src/test/regress/sql/partition_info.sql#L53-L66)). Useful for walking a multi-level tree, then join to the recipe |
| `information_schema` | Has no partition-bound view in v12 |
| Regex extraction | Excluded by the question. It also buys nothing here: the grammar is fixed, and the quote-parity problem needs the same masking step |

### Exact-pin measurements

Environment: the repo's exact-pin 12.2 build under `.wiki-runtime/pg12`, an isolated cluster on a Unix socket, database `partbounds`, schema `pb`. Correctness matrix: 18 range-partitioned parents covering `int4`, `int8`, `numeric`, `date`, `timestamptz`, `text` with and without `COLLATE "C"`, a two-column `(int4, text)` key, an expression key `((a + b))`, `boolean`, `float8`, `bytea`, `interval`, `char(3)`, `uuid`, plus a sub-partitioned parent, one list and one hash parent, a partitioned index, a detached partition, and an attached-by-`ALTER TABLE` partition — 45 live range partitions and 95 control bound elements. Four more parents were added later for the edge-case and scale tests. Ground truth was recorded at creation time from the server itself, never typed by hand.

| Measurement | Result |
|---|---|
| Reconstructed deparse rules vs `pg_get_expr` | 41 of 41 partitions matched, including the negative-`int4`, integral-`numeric`, `boolean`, and blank-padded `char(3)` cases |
| Masking recipe vs control | 95 of 95 elements correct, 0 wrong |
| Plain-split recipe vs control | 81 of 94 elements correct, 13 wrong, 9 of 41 partitions wrong |
| Elements per side vs `partnatts` | 0 mismatches |
| `pg_get_expr(relpartbound, 0)` vs `(…, oid)` | identical for 45 of 45 |
| `pg_get_expr(…, oid, true)` vs `(…, oid)` | identical for 45 of 45 |
| Bound texts containing `::` | 0 |
| Bound texts containing a newline | 2, both inside a `text` literal |
| Value round trip through the key type | 78 of 81 exact; 3 boolean rows print `true`/`false` versus output text `t`/`f` |
| `standard_conforming_strings = off`, plain unquoting | 91 of 95 correct; failures were 2 `bytea` and 2 backslash-bearing `text` bounds |
| `standard_conforming_strings = off`, `E''`-string hardened unquoting | 95 of 95 correct, and also 95 of 95 with the setting on |
| `replace(x, '\\', '\')` typed under `standard_conforming_strings = off` | does not parse: `ERROR: unterminated quoted string` plus two `nonstandard use of \\` warnings |
| Quote-free gate over the fixture set | 11 of 1047 non-default range partitions quote-free; the simple variant scored 18 of 18 elements there and 19 of 76 elsewhere |
| Locks held while extracting at 1047 partitions | 14 `AccessShareLock` relation locks, all catalogs plus the wrapper view; none on partitions or parents |
| Unprivileged role | 2109 of 2109 rows returned; bound readable for a partition whose schema the role cannot use |
| Timing at 1048 range partitions, 2109 rows | 44.9 ms and 39.9 ms masked, 8.3 ms and 9.2 ms plain-split, 1.8 ms catalog-only count, 31.9 ms `EXPLAIN (ANALYZE)` execution |
| Long bounds | 1000-char compressible: 337 stored bytes, extracted 1001 chars. 1280-char incompressible: 1670 stored bytes, extracted 1281 chars. 9600-char: `ERROR 54000 row is too big: size 9304, maximum size 8160` |
| Concurrent drop under `REPEATABLE READ` | `pg_class` row visible, `relpartbound` present, `pg_get_expr(…, oid)` NULL, `pg_get_expr(…, 0)` non-NULL, `regclass` printed `31545` |
| Key column rename | `key_column` follows the catalog; bounds unchanged |
| `ALTER COLUMN TYPE` on a key column | rejected: `cannot alter column "a" because it is part of the partition key of relation "f_int"` |
| Subquery in a bound | rejected: `cannot use subquery in partition bound` |
| Empty-string bound | extracted with length 0 |
| Cross-schema partition | rendered `pb_other.p_other` |
| Detached, list, hash, index partitions | 0 rows each |

`psql \d` on the same fixtures printed exactly the strings the recipe consumed, for example `Partition of: f_nasty FOR VALUES FROM ('01) TO (x') TO ('02a''b')` and `Partition of: f_multi FOR VALUES FROM (2, MINVALUE) TO (2, 'm, m')`.

### Caller data-structure generated-header and test boundaries

- **Callers of the same text.** `psql` pastes the deparse into the `Partition of:` footer and, for a parent, into `Partitions:` — sorting default partitions last with the string test `pg_get_expr(...) = 'DEFAULT'` ([describe.c#Partition-of](../../../../raw/postgres-12/src/bin/psql/describe.c#L2111-L2134), [describe.c#Partitions-list](../../../../raw/postgres-12/src/bin/psql/describe.c#L3124-L3133)). `pg_dump` emits it inside `ATTACH PARTITION` ([pg_dump.c#ATTACH-PARTITION](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L15986-L16005)). Neither parses it, which is why the recipe is a client-side responsibility.
- **Data structures.** Stored form: `PartitionBoundSpec` with `lowerdatums`/`upperdatums` lists of `PartitionRangeDatum` ([parsenodes.h#PartitionBoundSpec](../../../../raw/postgres-12/src/include/nodes/parsenodes.h#L802-L850)). Relcache form of the key: `PartitionKeyData`, whose `parttypid[i]` comes from `atttypid` for a column key and `exprType()` for an expression key ([partcache.h#PartitionKeyData](../../../../raw/postgres-12/src/include/utils/partcache.h#L24-L47), [partcache.c#RelationBuildPartitionKey](../../../../raw/postgres-12/src/backend/utils/cache/partcache.c#L204-L231)). Runtime form used for routing and pruning: `PartitionBoundInfoData`, which stores one datum tuple per distinct range datum plus a parallel `PartitionRangeDatumKind` array, sorted by the key's operator classes and collations ([partbounds.h#PartitionBoundInfoData](../../../../raw/postgres-12/src/include/partitioning/partbounds.h#L21-L76)). The recipe reads none of these; it reads the catalog text, so it is unaffected by relcache state.
- **Generated headers.** `Anum_pg_class_relpartbound` and `Anum_pg_partitioned_table_partattrs` come from the `genbki.pl`-generated `pg_class_d.h` and `pg_partitioned_table_d.h` ([pg_partitioned_table.h#CATALOG](../../../../raw/postgres-12/src/include/catalog/pg_partitioned_table.h#L19-L54)), and `pg_get_expr`'s fmgr symbol from `pg_proc.dat` ([pg_proc.dat#pg_get_expr](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L3571-L3573)). A SQL-only recipe needs no build step and no extension.
- **Test coverage that exists.** 84 deparsed bound footers across `src/test/regress/expected/`, including `MINVALUE`/`MAXVALUE` and `DEFAULT` shapes ([create_table.out#MINVALUE-MAXVALUE](../../../../raw/postgres-12/src/test/regress/expected/create_table.out#L1022-L1031), [update.out#default-partition](../../../../raw/postgres-12/src/test/regress/expected/update.out#L714-L724)); the `pg_dump` ATTACH round trip ([002_pg_dump.pl#attach-partition-bound](../../../../raw/postgres-12/src/bin/pg_dump/t/002_pg_dump.pl#L730-L742)); and `string_to_array`'s empty-element behavior ([arrays.sql#string_to_array](../../../../raw/postgres-12/src/test/regress/sql/arrays.sql#L532-L545), [arrays.out#string_to_array](../../../../raw/postgres-12/src/test/regress/expected/arrays.out#L1740-L1744)).
- **Test coverage that does not exist.** No test anywhere in the tree calls `pg_get_expr(relpartbound, ...)` from SQL, none decomposes a bound string with SQL string functions, and no RANGE bound in any test contains a comma, quote, or backslash inside a literal. `partition_info.sql` selects only tree columns and never a bound ([partition_info.sql#pg_partition_tree](../../../../raw/postgres-12/src/test/regress/sql/partition_info.sql#L53-L66)). The measurements above are therefore the only evidence for the adversarial cases.
- **Documentation gaps in v12.** `catalogs.sgml` describes `relpartbound` without pointing at `pg_get_expr`, unlike the `pg_attrdef.adbin` row that does ([catalogs.sgml#relpartbound](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L2011-L2019), [catalogs.sgml#adbin](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L952-L959)). `ddl.sgml` never mentions `MINVALUE`, `MAXVALUE`, or default partitions; that prose lives only in `create_table.sgml` ([ddl.sgml#declarative-example](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L3801-L3827), [create_table.sgml#partition_bound_spec](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L92-L97)). `pg_get_partition_constraintdef` and `pg_get_partkeydef` are undocumented in v12; their only definitions are in `pg_proc.dat` and `ruleutils.c` ([pg_proc.dat#pg_get_partition_constraintdef](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L3558-L3564)).

## Context Reviewed

- Pinned checkout `45b88269a353ad93744772791feb6d01bc7e1e42` (`REL_12_2`).
- Storage path: grammar for `PARTITION OF`/`ATTACH PARTITION`, bound transform, coercion and evaluation to a `Const`, NULL and expression-kind rejections, `StorePartitionBound`, `DETACH` clearing, and the partition-key column protections.
- Deparse path: `pg_get_expr`, `pg_get_expr_ext`, `pg_get_expr_worker`, the `T_PartitionBoundSpec` arm, `get_range_partbound_string`, `get_const_expr` per-type rules, `simple_quote_literal`, and `pg_get_partition_constraintdef`.
- Node output path: `_outConst` and `outDatum`, to establish why the raw `pg_node_tree` text is unusable.
- Catalog metadata: `pg_class.relispartition`/`relpartbound`, `pg_inherits`, `pg_partitioned_table` columns, `int2vector` zero-based subscripting, and `pg_attribute` join for key names and types.
- Data structures: `PartitionBoundSpec`, `PartitionRangeDatum`, `PartitionKeyData`, `PartitionBoundInfoData`.
- String-function surface: `string_to_array`/`text_to_array_internal` empty-element and NULL behavior, `strpos`, `substr` versus the regex `substring(text, text)` overload, `replace`, `repeat`, `array_to_string`, and the grammar note on `substring` overload resolution.
- Consumers: `psql` child and parent footers including the `= 'DEFAULT'` sort, and `pg_dump`'s `ATTACH PARTITION` emission with its TAP assertion.
- Settings: `standard_conforming_strings`, `DateStyle`, `TimeZone`, `IntervalStyle`, `extra_float_digits`, `bytea_output`, `client_encoding`, `statement_timeout`, `lock_timeout`.
- Error paths: oversize heap tuple, subquery/aggregate/window/SRF/column-reference rejection, missing-relation NULL from `pg_get_expr`.
- Documentation: `catalogs.sgml` for `pg_class` and `pg_partitioned_table`, `func.sgml` for `pg_get_expr`, partitioning functions, and the string-function tables including the regex ones being avoided, `ddl.sgml` and `create_table.sgml` for declarative partitioning semantics.
- Tests: deparsed-bound expected output across `create_table`, `insert`, `alter_table`, `update`, `indexing`, `foreign_key`; `partition_info`; `arrays` for `string_to_array`; `strings` for `strpos`/`substr`/`replace`/`split_part`; `misc_sanity` for the untoastable `relpartbound`; `002_pg_dump.pl`.
- Isolated exact-pin execution: 22 parents, 45 range partitions, 95 control elements, a 1000-partition scale set, GUC sweeps, lock and privilege probes, a `REPEATABLE READ` drop race, and long-bound limits. Fixtures, the test server, and the temporary database were removed afterward.

## Evidence Map

| Claim | Primary evidence |
|---|---|
| Bounds are stored only as a `pg_node_tree` in `pg_class` | [pg_class.h:137](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L137), [heap.c#StorePartitionBound](../../../../raw/postgres-12/src/backend/catalog/heap.c#L3757-L3770) |
| The raw node text cannot be decoded in SQL | [outfuncs.c#_outConst](../../../../raw/postgres-12/src/backend/nodes/outfuncs.c#L1079-L1097), [outfuncs.c#outDatum](../../../../raw/postgres-12/src/backend/nodes/outfuncs.c#L255-L288) |
| A range bound datum is always a `Const` of the key type | [parse_utilcmd.c#transformPartitionBoundValue](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c#L4021-L4088), [create_table.sgml#partition_bound_expr](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L415-L423) |
| The deparsed range shape is `FOR VALUES FROM (...) TO (...)` with `, ` separators | [ruleutils.c#T_PartitionBoundSpec](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L8985-L8994), [ruleutils.c#get_range_partbound_string](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L11284-L11318) |
| Bound literals carry no `::type` and no `COLLATE` | [ruleutils.c#get_const_expr](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L9600-L9646) |
| Negative `int4` and integral `numeric` bounds are quoted | [ruleutils.c#get_const_expr-switch](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L9552-L9603), [create_table.out#negative-int4-bound](../../../../raw/postgres-12/src/test/regress/expected/create_table.out#L504-L512) |
| Quoting doubles quotes always, backslashes only when `standard_conforming_strings` is off | [ruleutils.c#simple_quote_literal](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L9668-L9691), [guc.c#standard_conforming_strings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1721-L1730) |
| Default partitions deparse to exactly `DEFAULT` | [ruleutils.c#is_default](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L8951-L8955), [update.out#default-partition](../../../../raw/postgres-12/src/test/regress/expected/update.out#L714-L724) |
| Splitting on the quote character keeps empty segments, so quote parity is decidable | [varlena.c#text_to_array_internal](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L4744-L4783), [arrays.out#string_to_array](../../../../raw/postgres-12/src/test/regress/expected/arrays.out#L1740-L1744) |
| `substr` cannot resolve to a regex implementation, `substring(text, text)` can | [pg_proc.dat#substr](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L3403-L3405), [pg_proc.dat#substring-regex](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L5743-L5749), [gram.y#substring-overload](../../../../raw/postgres-12/src/backend/parser/gram.y#L14482-L14490) |
| `partattrs` is zero-based and a zero entry marks an expression key | [int.c#buildint2vector](../../../../raw/postgres-12/src/backend/utils/adt/int.c#L113-L135), [catalogs.sgml#partattrs](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L4859-L4871) |
| Only range parents are selected by `partstrat = 'r'` | [catalogs.sgml#partstrat](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L4831-L4839) |
| Detached partitions disappear from the result | [tablecmds.c#DETACH-clears-relpartbound](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16288-L16309) |
| A key column's type cannot change under the stored bound | [tablecmds.c#ATPrepAlterColumnType](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L10375-L10382) |
| `MINVALUE`/`MAXVALUE` are unbounded markers, not values | [create_table.sgml#MINVALUE-MAXVALUE-vs-infinity](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L478-L489), [parse_utilcmd.c#validateInfiniteBounds](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c#L3982-L4016) |
| A concurrently dropped partition yields NULL, not an error | [ruleutils.c#pg_get_expr-missing-relation](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L2367-L2380) |
| Passing relation OID zero is legitimate for a Var-free node | [func.sgml#pg_get_expr-notes](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L18854-L18874) |
| `relpartbound` cannot be TOASTed, so long bounds hit the tuple limit | [misc_sanity.out#toastable-columns](../../../../raw/postgres-12/src/test/regress/expected/misc_sanity.out#L90-L110), [hio.c#row-is-too-big](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L339-L346) |
| The same text is what `psql` and `pg_dump` consume, unparsed | [describe.c#Partition-of](../../../../raw/postgres-12/src/bin/psql/describe.c#L2111-L2134), [pg_dump.c#ATTACH-PARTITION](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L15986-L16005) |
| The partition-tree functions expose no bounds | [func.sgml#partitioning-functions](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L21553-L21603), [partition_info.sql#pg_partition_tree](../../../../raw/postgres-12/src/test/regress/sql/partition_info.sql#L53-L66) |
| The constraint deparse is a boolean expression, not bounds | [ruleutils.c#pg_get_partition_constraintdef](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L1808-L1837) |

## Open Questions

- No upstream regression test deparses a RANGE bound whose literal contains a comma, a single quote, or a backslash, and none extracts bounds with SQL string functions. Every adversarial result above comes from fixtures built for this page on one platform, so the grammar guarantees rest on `get_range_partbound_string` and `get_const_expr` rather than on upstream coverage.
- The `relkind = 'f'` branch is untested here. `CREATE FOREIGN TABLE ... PARTITION OF ... SERVER` is grammatical in v12 ([gram.y#CREATE-FOREIGN-TABLE-PARTITION-OF](../../../../raw/postgres-12/src/backend/parser/gram.y#L5006-L5029)), but the pin's build installed no FDW, so no foreign-table partition was exercised.
- For an expression key the recipe returns `NULL` for `key_column` and `key_type`. Deriving the expression's type in SQL would require decomposing the comma-separated `pg_get_expr(partexprs, partrelid)` list, whose commas can sit at any parenthesis depth; that needs a depth-aware scan the mask alone does not provide. `pg_opclass.opcintype` is a proxy, not proven equal to `PartitionKeyData.parttypid`.
- The NULL-deparse race was reproduced only with a snapshot taken before the `DROP` in `REPEATABLE READ`. The same code path could in principle fire in `READ COMMITTED` if a drop commits mid-statement; that timing was not observed.
- Timings were measured warm, single-client, on one host at 1048 partitions with `pg_get_expr` evaluated up to three times per partition. The per-partition cost curve beyond a few thousand partitions, and the effect of a cold catalog cache, were not measured.
- The measured cluster used `America/New_York` and a UTF-8 database. `lc_collate`-dependent ordering of extracted text, non-UTF-8 server encodings, and `client_encoding` conversion of bound literals were not exercised.
- Two ground-truth forms disagree for exactly two types: `boolean` (deparsed `true`/`false` versus output `t`/`f`) and `char(3)` (deparsed blank-padded versus `::text`). Whether any other type in a full `pg_type` sweep behaves this way was not checked.

## Source References

- [ruleutils.c#pg_get_expr](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L2344-L2385)
- [ruleutils.c#pg_get_expr-missing-relation](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L2367-L2380)
- [ruleutils.c#pg_get_expr_ext](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L2387-L2410)
- [ruleutils.c#pg_get_expr_worker](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L2412-L2439)
- [ruleutils.c#pg_get_partition_constraintdef](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L1808-L1837)
- [ruleutils.c#is_default](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L8951-L8955)
- [ruleutils.c#T_PartitionBoundSpec](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L8945-L9002)
- [ruleutils.c#get_const_expr](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L9521-L9646)
- [ruleutils.c#get_const_expr-switch](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L9552-L9603)
- [ruleutils.c#simple_quote_literal](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L9668-L9691)
- [ruleutils.c#get_range_partbound_string](../../../../raw/postgres-12/src/backend/utils/adt/ruleutils.c#L11284-L11318)
- [outfuncs.c#outDatum](../../../../raw/postgres-12/src/backend/nodes/outfuncs.c#L255-L288)
- [outfuncs.c#_outConst](../../../../raw/postgres-12/src/backend/nodes/outfuncs.c#L1079-L1097)
- [heap.c#StorePartitionBound](../../../../raw/postgres-12/src/backend/catalog/heap.c#L3736-L3770)
- [tablecmds.c#ATExecDropColumn](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L7145-L7152)
- [tablecmds.c#ATPrepAlterColumnType](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L10375-L10382)
- [tablecmds.c#DETACH-clears-relpartbound](../../../../raw/postgres-12/src/backend/commands/tablecmds.c#L16288-L16309)
- [parse_utilcmd.c#transformPartitionRangeBounds](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c#L3860-L3974)
- [parse_utilcmd.c#cannot-specify-NULL](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c#L3948-L3955)
- [parse_utilcmd.c#validateInfiniteBounds](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c#L3982-L4016)
- [parse_utilcmd.c#transformPartitionBoundValue](../../../../raw/postgres-12/src/backend/parser/parse_utilcmd.c#L4021-L4088)
- [parse_expr.c#column-reference](../../../../raw/postgres-12/src/backend/parser/parse_expr.c#L580-L582)
- [parse_expr.c#subquery](../../../../raw/postgres-12/src/backend/parser/parse_expr.c#L1919-L1921)
- [parse_agg.c#aggregate](../../../../raw/postgres-12/src/backend/parser/parse_agg.c#L509-L512)
- [parse_agg.c#window](../../../../raw/postgres-12/src/backend/parser/parse_agg.c#L921-L923)
- [parse_func.c#SRF](../../../../raw/postgres-12/src/backend/parser/parse_func.c#L2522-L2524)
- [gram.y#PartitionBoundSpec](../../../../raw/postgres-12/src/backend/parser/gram.y#L2685-L2776)
- [gram.y#CREATE-FOREIGN-TABLE-PARTITION-OF](../../../../raw/postgres-12/src/backend/parser/gram.y#L5006-L5029)
- [gram.y#SUBSTRING](../../../../raw/postgres-12/src/backend/parser/gram.y#L13804-L13810)
- [gram.y#substring-overload](../../../../raw/postgres-12/src/backend/parser/gram.y#L14482-L14490)
- [partcache.c#RelationBuildPartitionKey](../../../../raw/postgres-12/src/backend/utils/cache/partcache.c#L204-L231)
- [partcache.h#PartitionKeyData](../../../../raw/postgres-12/src/include/utils/partcache.h#L24-L47)
- [partbounds.h#PartitionBoundInfoData](../../../../raw/postgres-12/src/include/partitioning/partbounds.h#L21-L76)
- [parsenodes.h#PartitionBoundSpec](../../../../raw/postgres-12/src/include/nodes/parsenodes.h#L802-L850)
- [parsenodes.h#PartitionRangeDatum](../../../../raw/postgres-12/src/include/nodes/parsenodes.h#L829-L850)
- [pg_class.h:117](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L117)
- [pg_class.h:137](../../../../raw/postgres-12/src/include/catalog/pg_class.h#L137)
- [pg_inherits.h#pg_inherits](../../../../raw/postgres-12/src/include/catalog/pg_inherits.h#L32-L37)
- [pg_partitioned_table.h#CATALOG](../../../../raw/postgres-12/src/include/catalog/pg_partitioned_table.h#L19-L54)
- [pg_proc.dat#substr](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L3403-L3405)
- [pg_proc.dat#pg_get_partition_constraintdef](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L3558-L3564)
- [pg_proc.dat#pg_get_expr](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L3571-L3573)
- [pg_proc.dat#substring-regex](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L5743-L5749)
- [pg_proc.dat#string_to_array](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L1499-L1501)
- [pg_proc.dat#strpos](../../../../raw/postgres-12/src/include/catalog/pg_proc.dat#L3379-L3381)
- [int.c#buildint2vector](../../../../raw/postgres-12/src/backend/utils/adt/int.c#L113-L135)
- [varlena.c#empty-input](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L4712-L4714)
- [varlena.c#text_to_array_internal](../../../../raw/postgres-12/src/backend/utils/adt/varlena.c#L4744-L4783)
- [hio.c#row-is-too-big](../../../../raw/postgres-12/src/backend/access/heap/hio.c#L339-L346)
- [guc.c#standard_conforming_strings](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1721-L1730)
- [guc.c#statement_timeout-lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2377-L2396)
- [guc.c#extra_float_digits](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2690-L2700)
- [guc.c#client_encoding](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3581-L3588)
- [guc.c#DateStyle](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3612-L3622)
- [guc.c#TimeZone](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L3904-L3913)
- [guc.c#bytea_output](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4221-L4229)
- [guc.c#IntervalStyle](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L4275-L4284)
- [describe.c#Partition-of](../../../../raw/postgres-12/src/bin/psql/describe.c#L2111-L2134)
- [describe.c#Partitions-list](../../../../raw/postgres-12/src/bin/psql/describe.c#L3124-L3133)
- [pg_dump.c#partbound-query](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L5984-L5989)
- [pg_dump.c#ATTACH-PARTITION](../../../../raw/postgres-12/src/bin/pg_dump/pg_dump.c#L15986-L16005)
- [002_pg_dump.pl#attach-partition-bound](../../../../raw/postgres-12/src/bin/pg_dump/t/002_pg_dump.pl#L730-L742)
- [create_table.out#negative-int4-bound](../../../../raw/postgres-12/src/test/regress/expected/create_table.out#L504-L512)
- [create_table.out#MINVALUE-MAXVALUE](../../../../raw/postgres-12/src/test/regress/expected/create_table.out#L1022-L1031)
- [update.out#default-partition](../../../../raw/postgres-12/src/test/regress/expected/update.out#L714-L724)
- [misc_sanity.out#toastable-columns](../../../../raw/postgres-12/src/test/regress/expected/misc_sanity.out#L90-L110)
- [arrays.sql#string_to_array](../../../../raw/postgres-12/src/test/regress/sql/arrays.sql#L532-L545)
- [arrays.out#string_to_array](../../../../raw/postgres-12/src/test/regress/expected/arrays.out#L1740-L1744)
- [partition_info.sql#pg_partition_tree](../../../../raw/postgres-12/src/test/regress/sql/partition_info.sql#L53-L66)
- [catalogs.sgml#adbin](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L952-L959)
- [catalogs.sgml#relpartbound](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L2011-L2019)
- [catalogs.sgml#partstrat](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L4831-L4839)
- [catalogs.sgml#partattrs](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L4859-L4871)
- [func.sgml#string_to_array](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L14330-L14341)
- [func.sgml#string_to_array-null-string](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L14390-L14405)
- [func.sgml#strpos](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L2350-L2366)
- [func.sgml#substring-from-pattern](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L1609-L1619)
- [func.sgml#pg_get_expr](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L18643-L18654)
- [func.sgml#pg_get_expr-notes](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L18854-L18874)
- [func.sgml#partitioning-functions](../../../../raw/postgres-12/doc/src/sgml/func.sgml#L21553-L21603)
- [ddl.sgml#declarative-example](../../../../raw/postgres-12/doc/src/sgml/ddl.sgml#L3801-L3827)
- [create_table.sgml#partition_bound_spec](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L92-L97)
- [create_table.sgml#partition_bound_expr](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L415-L423)
- [create_table.sgml#bound-comparison](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L433-L447)
- [create_table.sgml#MINVALUE-MAXVALUE-vs-infinity](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L478-L489)

## Navigation

- [v12/index](../../index.md)
- [versions](../../../versions.md)
- [wiki index](../../../index.md)
- [Table Partitioning Optimizations and Configuration During Query Planning and Execution in PostgreSQL 12 (unverified)](../query-planning/partitioning-planning-execution-optimizations.md)
- [Can ALTER TABLE ... ATTACH PARTITION Drop Indexes in PostgreSQL 12? (unverified)](../indexing/attach-partition-index-drops.md)
- [PostgreSQL 12 Database Health Checklist (unverified)](database-health-checklist.md)
