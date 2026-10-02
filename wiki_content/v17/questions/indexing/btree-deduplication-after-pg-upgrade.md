---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# Checking Whether an Index Needs a Rebuild to Enable Deduplication After pg_upgrade From PostgreSQL 12 to 17 (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Short answer](#short-answer)
  - [Why every carried-over index is affected](#why-every-carried-over-index-is-affected)
  - [The one byte that decides it](#the-one-byte-that-decides-it)
  - [Check 1: read the flag with core SQL](#check-1-read-the-flag-with-core-sql)
  - [Privileges the probe needs](#privileges-the-probe-needs)
  - [Check 2: prove the byte offsets on your platform](#check-2-prove-the-byte-offsets-on-your-platform)
  - [Check 3: would a rebuild even help?](#check-3-would-a-rebuild-even-help)
  - [What the gate rejects, and why](#what-the-gate-rejects-and-why)
  - [When a true flag is the wrong answer](#when-a-true-flag-is-the-wrong-answer)
  - [The deduplicate_items trap](#the-deduplicate_items-trap)
  - [Unique and near-unique indexes get the flag but no size win](#unique-and-near-unique-indexes-get-the-flag-but-no-size-win)
  - [What a rebuild actually recovered](#what-a-rebuild-actually-recovered)
  - [How much duplication is worth a rebuild](#how-much-duplication-is-worth-a-rebuild)
  - [The cost of leaving it alone](#the-cost-of-leaving-it-alone)
  - [Separating deduplication from ordinary bloat](#separating-deduplication-from-ordinary-bloat)
  - [What sets the flag, and what does not](#what-sets-the-flag-and-what-does-not)
  - [Rebuild order and the statistics pg_upgrade leaves behind](#rebuild-order-and-the-statistics-pg_upgrade-leaves-behind)
  - [Second opinion: make the engine say it](#second-opinion-make-the-engine-say-it)
  - [Fallbacks when you cannot read server files](#fallbacks-when-you-cannot-read-server-files)
  - [Edge cases the check has to survive](#edge-cases-the-check-has-to-survive)
  - [Where this comes from in the source history](#where-this-comes-from-in-the-source-history)
  - [Settings this page touches](#settings-this-page-touches)
- [Measurement Script](#measurement-script)
  - [How to use it](#how-to-use-it)
  - [Prerequisites](#prerequisites)
  - [Where the results land](#where-the-results-land)
  - [The last run](#the-last-run)
  - [The script](#the-script)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

In PostgreSQL 17, question: after a database is upgraded from v12 to v17, how do I check if an index needs to be rebuilt to enable deduplication?

> Prompt note: filed as an approved grammar-corrected restatement of "in postgreql
> 17 , question: after an database is upgraded from v12 to v17, how to check if an
> index needs to be rebuild to enable de-duplication.", per the repository's
> prompt-hygiene rule. The asker chose the corrected wording, asked for the answer
> to be measured on a real `pg_upgrade` run rather than derived from source alone,
> and restricted the check itself to core SQL, with no extensions installed.
>
> Reviewed and re-measured on 2026-09-15 under the grammar-corrected review prompt
> *follow AGENTS.md; in PostgreSQL 17, review the question page "Checking Whether
> an Index Needs a Rebuild to Enable Deduplication After pg_upgrade From
> PostgreSQL 12 to 17"*, which the asker chose to correct and restate. Every
> number below comes from one run of [the script filed on this page](#the-script)
> against the current 17.11 pin; the superseded numbers were 17.10 measurements.
>
> Reviewed again on 2026-09-16 under the same prompt, restated the same way after
> the asker again chose **correct and restate** over keeping
> *follow agents.md, in postgresql 17, review : btree-deduplication-after-pg-upgrade.md*
> as written. That pass re-read every citation against the unchanged pin, re-ran
> the page's script end to end, and added the `interval_ops` case in
> [When a true flag is the wrong answer](#when-a-true-flag-is-the-wrong-answer),
> which is the one shape where this page's own check gave the wrong verdict.

## Answer

### Short answer

After a binary upgrade with `pg_upgrade`, **every** B-tree index that came from the
PostgreSQL 12 cluster is unable to deduplicate, and no amount of `VACUUM` will
change that. Deduplication safety is recorded once, in the index's metapage field
`btm_allequalimage`, at build time; PostgreSQL 12 never wrote that field, and
`pg_upgrade` copies the index file unchanged, so the field reads false forever until
the index is rebuilt
([nbtree.h#BTREE_VERSION-comment](../../../../raw/postgres-17/src/include/access/nbtree.h#L124-L147),
[nbtpage.c#_bt_metaversion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L719-L791)).

So the per-index check has two parts, and core SQL can do both:

1. **Is this index deduplicating right now?** Read byte 64 of block 0 of the index's
   main fork. That is `btm_allequalimage`. Core SQL reads it with
   `pg_read_binary_file()` plus `get_byte()`; no `pageinspect` needed. See
   [Check 1](#check-1-read-the-flag-with-core-sql).
2. **Would a rebuild help?** Mirror `_bt_allequalimage()` in the catalogs: no
   `INCLUDE` columns, every key opclass has a `pg_amproc` equal-image support
   function at `amprocnum = 4`, and no key collation is nondeterministic. See
   [Check 3](#check-3-would-a-rebuild-even-help).

An index needs a rebuild exactly when part 1 says false and part 2 says true. On the
12.2 → 17.11 run, 26 index files crossed the upgrade and **all 26 read false**; the
check flagged **20 of them** and refused 6. Rebuilding 17 of them anyway — every
index of the three main fixture tables, flagged or not — reclaimed **67.4% to 69.1%
on the eight duplicate-heavy indexes**, **0.00% on the three it flagged whose keys
are unique or near-unique**, and **0.00% on all six it refused**, byte for byte.

Do not check `btm_version` for this. PostgreSQL 12 already writes version 4, so
version is 4 both before and after the rebuild
([nbtree.h#BTREE_VERSION](../../../../raw/postgres-17/src/include/access/nbtree.h#L148-L152));
all 22 carried-over indexes in `public` reported version 4 while none of them could
deduplicate.

One exception runs the other way, and it is a correctness matter rather than a size
one: coming from PostgreSQL 13 through 16, an index on an `interval` column can
arrive with the flag already **true** when v17 says it must be false. Part 1 alone
would call that index finished. See
[When a true flag is the wrong answer](#when-a-true-flag-is-the-wrong-answer).

### Why every carried-over index is affected

The v17 source says so in two places, and a third in contrib:

- The comment above `BTREE_VERSION`: "Even version 4 indexes created on PostgreSQL
  v12 will need a REINDEX to make use of deduplication, though, since there is no
  other way to set btm_allequalimage to true (pg_upgrade hasn't been taught to set
  the metapage field)."
  ([nbtree.h#BTREE_VERSION-comment](../../../../raw/postgres-17/src/include/access/nbtree.h#L124-L147))
- `_bt_metaversion()`: "We rely on the assumption that btm_allequalimage will be
  zero'ed on heapkeyspace indexes that were pg_upgrade'd from Postgres 12."
  ([nbtpage.c#_bt_metaversion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L719-L791))
- `bt_metap()` repeats the same assumption
  ([btreefuncs.c#bt_metap](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L905-L922)).

`pg_upgrade` moves the index file without touching its contents. It selects every
valid index of every user table (plus TOAST heaps and `pg_largeobject`)
([info.c#get_rel_infos](../../../../raw/postgres-17/src/bin/pg_upgrade/info.c#L471-L524)),
has `pg_dump --binary-upgrade` preserve each index's OID and relfilenode
([pg_dump.c#binary_upgrade_set_next_index_relfilenode](../../../../raw/postgres-17/src/bin/pg_dump/pg_dump.c#L5563-L5572)),
and then copies or links the file
([relfilenumber.c#transfer_relfile](../../../../raw/postgres-17/src/bin/pg_upgrade/relfilenumber.c#L168-L266)).
Measured on the pin: after `pg_upgrade --copy` from 12.2 to 17.11, **all 26 carried-over
B-tree index files had identical MD5s** in the old and new data directories, and
`pg_class.oid` and `pg_class.relfilenode` were unchanged for every one of them. The 26
are the 22 indexes in `public`, the three TOAST indexes of the fixture tables, and
`pg_largeobject_loid_pn_index`.

Two consequences that surprise people:

- **`pg_upgrade` never mentions it.** The run produced exactly one script,
  `delete_old_cluster.sh`, and its completion banner talks only about statistics
  ([check.c#output_completion_banner](../../../../raw/postgres-17/src/bin/pg_upgrade/check.c#L760-L790)).
  Grepping the whole output tree for "reindex", "rebuild" or "deduplicat", case
  insensitively, found nothing. The only index-rebuild help it still offers is for
  pre-10 hash indexes, gated on `GET_MAJOR_VERSION(old_cluster.major_version) <= 906`
  ([check.c#issue_warnings_and_set_wal_level](../../../../raw/postgres-17/src/bin/pg_upgrade/check.c#L744-L757)),
  which a 12 → 17 upgrade never reaches. The reference page's promise that "all
  failure, rebuild, and reindex cases will be reported"
  ([pgupgrade.sgml#post-upgrade-scripts](../../../../raw/postgres-17/doc/src/sgml/ref/pgupgrade.sgml#L1078-L1086))
  does not cover this one; see [Open Questions](#open-questions).
- **This is a `pg_upgrade`-only problem.** A dump/restore upgrade issues ordinary
  `CREATE INDEX` statements, which build v17 metapages. It is the relfilenode
  preservation above that carries the old physical index across.

### The one byte that decides it

The metapage is block 0. Its contents start at `MAXALIGN(SizeOfPageHeaderData)`
([bufpage.h#PageGetContents](../../../../raw/postgres-17/src/include/storage/bufpage.h#L246-L258)),
and `BTMetaPageData` lays the fields out in this order
([nbtree.h#BTMetaPageData](../../../../raw/postgres-17/src/include/access/nbtree.h#L103-L119)).
Compiling `offsetof()` against the 17.11 build's own installed server headers gives:

| field | offset in struct | absolute byte in block 0 |
|---|---|---|
| `btm_magic` | 0 | 24 |
| `btm_version` | 4 | 28 |
| `btm_root` | 8 | 32 |
| `btm_level` | 12 | 36 |
| `btm_fastroot` | 16 | 40 |
| `btm_fastlevel` | 20 | 44 |
| `btm_last_cleanup_num_delpages` | 24 | 48 |
| `btm_last_cleanup_num_heap_tuples` | 32 | 56 |
| `btm_allequalimage` | 40 | **64** |

`MAXIMUM_ALIGNOF` was 8, `BLCKSZ` 8192, `SizeOfPageHeaderData` 24 and
`sizeof(BTMetaPageData)` 48, so a v17-built metapage sets `pd_lower` to 72
([nbtpage.c#_bt_initmetapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L63-L96)).
The same program compiled against the 12.2 build's headers fails with
`'BTMetaPageData' has no member named 'btm_last_cleanup_num_delpages'` and
`... no member named 'btm_allequalimage'`. Compiled for the fields 12.2 *does* have,
it reports `sizeof(BTMetaPageData)` 40, a `pd_lower` of 64, and
`btm_oldest_btpo_xact` where v17 reads deleted-page counts. That is why byte 64
reads zero on a carried-over index: the page ends before it, `_bt_pageinit()` zeroed
the buffer, and PostgreSQL 12 wrote nothing there. Measured side effect: every one
of the 22 carried-over metapages in `public` reported `pd_lower = 64`, and every
index built after the upgrade reported 72.

Who writes the byte:

- `_bt_initmetapage()` stores whatever `_bt_allequalimage()` returned at build time,
  for `CREATE INDEX`/`REINDEX`
  ([nbtsort.c#_bt_leafbuild](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L531-L565),
  [nbtsort.c#_bt_uppershutdown](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1118-L1128))
  and for an empty index
  ([nbtree.c#btbuildempty](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L158-L171)).
- `_bt_upgrademetapage()`, the only in-place metapage version bump, explicitly
  refuses to set it: "Only a REINDEX can set this field"
  ([nbtpage.c#_bt_upgrademetapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L98-L131)).
- WAL replay copies the value out of the record rather than recomputing it
  ([nbtxlog.c#_bt_restore_meta](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L101-L125)).
  Note that replay *does* rewrite `pd_lower` to 72, so `pd_lower` is a hint, not
  the answer; read byte 64.

Who reads it: `_bt_metaversion()` puts it in the insertion scan key on the write
path
([nbtutils.c#_bt_mkscankey](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L118-L160))
and `_bt_first()` calls it directly on the read path
([nbtsearch.c#_bt_first](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1314-L1324)).
Both deduplication paths then gate on it — the index build
([nbtsort.c#_bt_load](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1144-L1152))
and the insert-time pass that tries to avoid a page split
([nbtinsert.c#_bt_delete_or_dedup_one_page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2774-L2782)).
So a carried-over index does not deduplicate on insert either: it just splits.

Three more readers matter when reasoning about a carried-over metapage:

- Posting lists only exist in an index whose flag is set, so the code that
  searches one asserts the flag
  ([nbtsearch.c#_bt_binsrch_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L595-L620)),
  as does the path that splits one during insertion
  ([nbtinsert.c:1164-1171](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1164-L1171)).
- The metapage WAL records copy the flag out of the live metapage rather than
  recomputing it, both when an insert updates the metapage
  ([nbtinsert.c:1350-1357](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1350-L1357))
  and when a new root is created
  ([nbtinsert.c:2573-2580](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2573-L2580)),
  so replay can neither invent nor drop it.
- `contrib/amcheck` re-derives the rule and compares: it calls
  `_bt_metaversion()`, then errors with "metapage incorrectly indicates that
  deduplication is safe" when the stored flag is true but `_bt_allequalimage()`
  now returns false
  ([verify_nbtree.c#bt_index_check_internal](../../../../raw/postgres-17/contrib/amcheck/verify_nbtree.c#L365-L400)).
  That is the engine's own version of [Check 3](#check-3-would-a-rebuild-even-help),
  and it is what makes the `interval` case below detectable.

### Check 1: read the flag with core SQL

`pg_relation_filepath()` returns a path relative to the data directory
([dbsize.c#pg_relation_filepath](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L948-L1028)),
`pg_read_binary_file()` reads it, and `get_byte()` picks the byte out of the
`bytea`
([varlena.c#byteaGetByte](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L3246-L3268)).
Reading 72 bytes is enough and is block-size independent.

```sql
SET statement_timeout = '60s';
SET lock_timeout = '5s';

SELECT /* wiki_dedup_rebuild_check */
       n.nspname,
       c.relname,
       pg_size_pretty(pg_relation_size(c.oid))        AS index_size,
       m.allequalimage                                AS deduplicating_now,
       CASE
         WHEN m.allequalimage IS NULL
           THEN 'unknown: could not read metapage'
         WHEN m.allequalimage AND NOT e.equalimage_ok
           THEN 'rebuild for correctness: metapage says safe, catalogs disagree'
         WHEN m.allequalimage
           THEN 'no rebuild needed'
         WHEN i.indnatts <> i.indnkeyatts
           THEN 'no gain: INCLUDE index can never deduplicate'
         WHEN NOT e.equalimage_ok
           THEN 'no gain: key type or collation is not deduplication-safe'
         WHEN NOT coalesce(o.deduplicate_items, true)
           THEN 'no gain while deduplicate_items = off'
         WHEN i.indisunique
           THEN 'rebuild: unique index, no immediate size win'
         ELSE 'rebuild: REINDEX INDEX CONCURRENTLY enables deduplication'
       END                                            AS verdict
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_am a ON a.oid = c.relam
JOIN pg_index i ON i.indexrelid = c.oid
CROSS JOIN LATERAL (
       SELECT CASE WHEN octet_length(z.meta) = 72
                   THEN get_byte(z.meta, 64) <> 0 END AS allequalimage
       FROM (SELECT pg_read_binary_file(pg_relation_filepath(c.oid), 0, 72, true) AS meta) z
     ) m
CROSS JOIN LATERAL (
       SELECT NOT EXISTS (
                SELECT 1
                FROM generate_series(0, i.indnkeyatts - 1) AS k
                LEFT JOIN pg_opclass oc ON oc.oid = i.indclass[k]
                LEFT JOIN pg_amproc ap ON ap.amprocfamily = oc.opcfamily
                                      AND ap.amproclefttype = oc.opcintype
                                      AND ap.amprocrighttype = oc.opcintype
                                      AND ap.amprocnum = 4
                LEFT JOIN pg_collation col ON col.oid = i.indcollation[k]
                WHERE ap.amproc IS NULL
                   OR (ap.amproc = 'btvarstrequalimage'::regproc
                       AND NOT col.collisdeterministic)
              ) AS equalimage_ok
     ) e
LEFT JOIN LATERAL (
       SELECT lower(split_part(opt, '=', 2))::bool AS deduplicate_items
       FROM unnest(c.reloptions) AS opt
       WHERE split_part(opt, '=', 1) = 'deduplicate_items'
     ) o ON true
WHERE a.amname = 'btree'
  AND c.relkind = 'i'
  AND c.relpersistence <> 't'
ORDER BY (m.allequalimage IS NOT TRUE) DESC, pg_relation_size(c.oid) DESC;
```

The second branch is the `interval` guard added on 2026-09-16: it fires when the
metapage claims deduplication is safe and the catalogs say it is not, which is a
rebuild for correctness rather than for size. On a 12 → 17 upgrade it can never
fire, because v12 wrote the flag false everywhere, and on this run it matched 0
rows; see [When a true flag is the wrong answer](#when-a-true-flag-is-the-wrong-answer).

On the upgraded 17.11 cluster this printed 189 rows — every readable B-tree index in
the database, catalog and TOAST included — of which 27 read false: the 26 carried
over, plus one freshly built catalog index whose key is `float4`. The verdicts:

| verdict | rows | indexes |
|---|---|---|
| `rebuild: REINDEX INDEX CONCURRENTLY enables deduplication` | 15 | `i_dup10`, `i_dup1000`, `i_dup10b`, `i_txt`, `i_txt_pattern`, `i_expr`, `i_multi`, `i_partial`, `i_uuid`, `i_churn`, `i_ts`, `i_u_k`, `i_empty`, `p_main_1_k_idx`, `p_main_2_k_idx` |
| `rebuild: unique index, no immediate size win` | 5 | `i_uniq`, carried-over `pg_largeobject_loid_pn_index` and three carried-over TOAST indexes |
| `no gain: key type or collation is not deduplication-safe` | 6 | `i_num` (numeric), `i_flt` (float8), `i_js` (jsonb), `i_arr` (int[]), `i_multimixed` (int + numeric), and `pg_enum_typid_sortorder_index` (float4, not carried over) |
| `no gain: INCLUDE index can never deduplicate` | 1 | `i_inc` |
| `rebuild for correctness: metapage says safe, catalogs disagree` | 0 | none here; v12 never set the flag |
| `no rebuild needed` | 162 | 122 of the 124 `pg_catalog` B-tree indexes and 40 of the 43 in `pg_toast`, all built by the new cluster's `initdb` rather than transferred |

Re-running the same query after the rebuilds is a cheap self-check, and it moves
exactly as far as it should. `no rebuild needed` went from 162 to **176**: the 14
rebuilt indexes whose keys are equal-image, and only those. The 6 type-refusals and
the one `INCLUDE` refusal stayed put even though 6 of them were rebuilt too, and 6
rows stayed flagged — `i_dup10b` and `p_main_2_k_idx`, deliberately left alone for
the [twins](#separating-deduplication-from-ordinary-bloat) and the partition pair,
plus the four unique carried-over indexes (`pg_largeobject_loid_pn_index` and the
three TOAST indexes), which no rebuild touched.

Cross-checked against `pageinspect`'s `bt_metap()` — installed only as ground truth,
not as part of the check — the probe's `version`, `allequalimage` and
`last_cleanup_num_delpages` agreed in **all 189 rows** before the rebuilds and in
all 23 `public` rows after them.

### Privileges the probe needs

Measured on the pin, and consistent with
([genfile.c#convert_and_check_filename](../../../../raw/postgres-17/src/backend/utils/adt/genfile.c#L41-L92)):

- `pg_read_binary_file` is revoked from `PUBLIC`
  ([system_functions.sql:712-718](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L712-L718)),
  so a plain role gets `ERROR:  permission denied for function pg_read_binary_file`.
- **`GRANT pg_read_server_files` is not sufficient and not needed.** Granting only
  that role left the same permission error, because the predefined role widens
  *which paths* are legal, not *who may call the function*.
- What worked was `GRANT EXECUTE ON FUNCTION
  pg_read_binary_file(text,bigint,bigint,boolean) TO <role>`. The grant is
  per-signature: with only the four-argument form granted, the three-argument form
  still failed with the same error.
- With that grant and no `pg_read_server_files`, both the relative path
  `base/16384/16393` and an absolute path inside the data directory read 72 bytes,
  while `/etc/hostname` failed with `ERROR:  absolute path not allowed`. So the
  probe stays inside the data directory by construction.
- `pg_relation_filepath()` needed no grant at all; a plain role could call it.

### Check 2: prove the byte offsets on your platform

The offsets above are `MAXIMUM_ALIGNOF = 8` offsets. Before trusting the probe on a
platform this page did not measure, make the server answer a question you already
know the answer to: a freshly built index must report true.

```sql
CREATE TABLE wiki_dedup_selftest (k int);
INSERT INTO wiki_dedup_selftest VALUES (1), (1);
CREATE INDEX wiki_dedup_selftest_k ON wiki_dedup_selftest (k);

SELECT /* wiki_dedup_probe_selftest */
       octet_length(meta)                              AS meta_bytes,
       (get_byte(meta, 13) * 256) + get_byte(meta, 12) AS pd_lower,
       (get_byte(meta, 31)::bigint << 24) + (get_byte(meta, 30) << 16)
         + (get_byte(meta, 29) << 8) + get_byte(meta, 28) AS btm_version,
       get_byte(meta, 64) <> 0                         AS allequalimage
FROM (SELECT pg_read_binary_file(
               pg_relation_filepath('wiki_dedup_selftest_k'), 0, 72, true) AS meta) z;

DROP TABLE wiki_dedup_selftest;
```

On the pin this returned `72 | 72 | 4 | t`. If `btm_version` is not 4 or
`allequalimage` is not true here, the offsets do not apply to that build and the
probe's answers are meaningless. No checkpoint is needed first: an index build writes
its pages, metapage included, through the bulk-write path rather than shared buffers
([nbtsort.c#_bt_blwritepage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L631-L639)),
so the fresh metapage was already on disk when the probe read it.

### Check 3: would a rebuild even help?

`_bt_allequalimage()` is the whole rule
([nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5129-L5183)):

1. If the index has `INCLUDE` columns, return false immediately.
2. Otherwise, for each key column, look up support function 4
   (`BTEQUALIMAGE_PROC`,
   [nbtree.h#BTEQUALIMAGE_PROC](../../../../raw/postgres-17/src/include/access/nbtree.h#L686-L712))
   in the column's opfamily for its `opcintype`, and call it with the column's
   collation. Missing function, or a false answer, means false.

The `equalimage_ok` subquery in [Check 1](#check-1-read-the-flag-with-core-sql) is
that rule in SQL. Two support functions exist. `btequalimage` returns true
unconditionally
([datum.c#btequalimage](../../../../raw/postgres-17/src/backend/utils/adt/datum.c#L415-L438)),
and `btvarstrequalimage` returns true for a C collation, for the default collation,
or for any deterministic collation, and false otherwise
([varlena.c#btvarstrequalimage](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L2595-L2613)),
which is why the SQL applies the `collisdeterministic` test only to columns whose
support function is `btvarstrequalimage`.

The gate was scored against two oracles on 17 freshly built index shapes: the
metapage byte the build wrote, and the `DEBUG1` message `_bt_allequalimage()` emits
during a build. **The gate matched the metapage on 17 of 17**, and matched the
engine's message on the 16 shapes that produce one.

| fixture | key(s) | engine said | gate said | flag |
|---|---|---|---|---|
| `g_dup10`, `g_partial` | `int4`, plain and partial | can safely use deduplication | true | true |
| `g_txt` | `text`, default collation | can safely use deduplication | true | true |
| `g_txt_pattern` | `text` (`text_pattern_ops`) | can safely use deduplication | true | true |
| `g_expr` | `lower(txt)` | can safely use deduplication | true | true |
| `g_c` | `text COLLATE "C"` | can safely use deduplication | true | true |
| `g_det_b` | `text` under a deterministic ICU collation | can safely use deduplication | true | true |
| `g_uuid` | `uuid` | can safely use deduplication | true | true |
| `g_uniq` | `(text, int4, uuid)`, unique | can safely use deduplication | true | true |
| `g_num`, `g_multimixed` | `numeric` key | cannot use deduplication | false | false |
| `g_flt` | `float8` | cannot use deduplication | false | false |
| `g_js` | `jsonb` | cannot use deduplication | false | false |
| `g_arr` | `int[]` | cannot use deduplication | false | false |
| `g_nd_a`, `g_nd_a_off` | `text` under a nondeterministic ICU collation | cannot use deduplication | false | false |
| `g_inc` | `int4` `INCLUDE (text)` | *(silent)* | false | false |

The `INCLUDE` index is silent because `_bt_allequalimage()` returns before it
reaches the `elog(DEBUG1, ...)` block. Treat "no message" as "cannot deduplicate".
This gate is not the wiki's shared bloat suite: it says whether an index *can*
deduplicate, not how much space a rebuild returns; see
[Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md)
for the suite this page was not scored against, and
[Open Questions](#open-questions).

### What the gate rejects, and why

The documented list of unsafe cases
([btree.sgml#btree-deduplication](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L834-L909))
matches what the catalogs encode, and the tree tests the catalog side directly.
`opr_sanity` selects every B-tree opclass whose support function 4 is not
`btequalimage`, and its comment says the expected output has to be updated whenever
a new opclass cannot deduplicate
([opr_sanity.sql:1336-1353](../../../../raw/postgres-17/src/test/regress/sql/opr_sanity.sql#L1336-L1353)).
That expected output is therefore the authoritative refusal list, 16 rows on this
pin
([opr_sanity.out:2204-2222](../../../../raw/postgres-17/src/test/regress/expected/opr_sanity.out#L2204-L2222)):

| support function 4 | opclasses | what the gate does |
|---|---|---|
| `btvarstrequalimage` | `bpchar_ops`, `name_ops`, `text_ops`, `varchar_ops` | safe unless the key collation is nondeterministic |
| none at all | `array_ops`, `float4_ops`, `float8_ops`, `interval_ops`, `jsonb_ops`, `multirange_ops`, `numeric_ops`, `range_ops`, `record_image_ops`, `record_ops`, `tsquery_ops`, `tsvector_ops` | never safe, so a rebuild buys nothing |
| `btequalimage` | every other core B-tree opclass, including `text_pattern_ops` | always safe |

Anything the test does not list registers `btequalimage`, because its
`IS DISTINCT FROM` predicate catches the missing-row case too. Read that way, the
refusal set is wider than the documentation's four bullets:

- `numeric` (display scale), `jsonb` (numeric internally) and `float4`/`float8`
  (`-0` versus `0`) have no `amprocnum = 4` row at all, and neither do the
  container types — arrays, records, ranges and multiranges.
- **`interval`, `tsquery` and `tsvector` are plain scalar types that also carry
  none**, so "ordinary scalar types are safe" is not a rule you can apply by eye.
  `interval_ops` is the one that used to be safe and stopped being safe; see
  [When a true flag is the wrong answer](#when-a-true-flag-is-the-wrong-answer).
- `text` and `name` register `btvarstrequalimage` in the `text_ops` family
  ([pg_amproc.dat:201-212](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L201-L212)),
  `bpchar` registers it in its own family
  ([pg_amproc.dat:31-33](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L31-L33)),
  and `varchar_ops` is itself a `btree/text_ops` opclass over `text`
  ([pg_opclass.dat:145-146](../../../../raw/postgres-17/src/include/catalog/pg_opclass.dat#L145-L146)),
  so a nondeterministic collation disqualifies all of them.
- `INCLUDE` indexes are refused outright, regardless of key types.

One edge worth knowing: `text_pattern_ops` registers `btequalimage`
([pg_amproc.dat:240-241](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L240-L241)),
which would ignore a nondeterministic collation — but such an index cannot be
created in the first place
([index.c#index_create](../../../../raw/postgres-17/src/backend/catalog/index.c#L827-L848)).
Measured: `CREATE INDEX ... (a text_pattern_ops)` on a nondeterministic-collation
column failed with `ERROR:  nondeterministic collations are not supported for
operator class "text_pattern_ops"`, so the simpler and the proc-aware forms of the
collation test cannot disagree in practice.

### When a true flag is the wrong answer

Everything above assumes the carried-over flag can only be stale in the harmless
direction: false where a rebuild would make it true. Coming from PostgreSQL 13
through 16 there is one shape that is stale the other way, and this page's own
check answered it wrongly until 2026-09-16.

`interval_ops` used to register `btequalimage` as its support function 4.
`5f27b5f848a`, "Dissociate btequalimage() from interval_ops, ending its
deduplication", removed it. Its message states the reason — under `interval_ops`
some equal values are distinguishable, `'24:00:00'` and `'1 day'` among them — that
this "can cause incorrect results from index-only scans", that "users should REINDEX
any btree indexes having interval-type columns", and that in back branches
`btequalimage()` itself was taught to return false for `interval` while
`interval_ops` simply omits the function going forward. In this checkout the commit
is first contained by `REL_17_0`, and its own message records the back-patch to v13.

On a v17 cluster that leaves four facts that combine badly:

- The catalogs carry no support function 4 for `interval_ops`, so
  `_bt_allequalimage()` returns false for an `interval` key and
  [Check 3](#check-3-would-a-rebuild-even-help) refuses it exactly like `numeric`
  ([opr_sanity.out:2204-2222](../../../../raw/postgres-17/src/test/regress/expected/opr_sanity.out#L2204-L2222)).
- v17's `btequalimage()` returns true unconditionally
  ([datum.c#btequalimage](../../../../raw/postgres-17/src/backend/utils/adt/datum.c#L415-L438)),
  so the back branches' type-specific guard is not present here. Nothing in v17
  turns an old `true` into a `false`.
- `pg_upgrade` copies the index file, and the only in-place metapage upgrade
  refuses to touch the field — "Only a REINDEX can set this field"
  ([nbtpage.c#_bt_upgrademetapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L98-L131)).
  A `true` written by a pre-fix v13-v16 build therefore survives the upgrade
  unchanged, and byte 64 keeps reading 1.
- `amcheck` is what notices: a true flag plus a now-false rule raises
  `ERROR:  index "..." metapage incorrectly indicates that deduplication is safe`,
  with an `errhint` naming "interval" indexes "last built on a version predating
  2023-11"
  ([verify_nbtree.c#bt_index_check_internal](../../../../raw/postgres-17/contrib/amcheck/verify_nbtree.c#L365-L400)).

So on a 13 → 17 or 16 → 17 upgrade, "the flag is true" is not the end of the
triage. Do not short-circuit on the flag: compare it against the catalog gate, which
is what the `rebuild for correctness: metapage says safe, catalogs disagree` branch
of [Check 1](#check-1-read-the-flag-with-core-sql) now does, and rebuild whatever it
names. This page measured only 12 → 17, where every carried-over flag is false, so
that branch is source-verified and matched 0 rows on the run; see
[Open Questions](#open-questions).

### The deduplicate_items trap

The metapage flag and the `deduplicate_items` storage parameter are independent.
The build path needs both plus non-uniqueness
([nbtsort.c#_bt_load](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1144-L1152)),
and so does the insert path
([nbtinsert.c#_bt_delete_or_dedup_one_page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2774-L2782)),
but only `_bt_allequalimage()` feeds the metapage. Measured consequence: an already
rebuilt `i_dup1000` standing at 7,340,032 bytes went back to its full **22,519,808
bytes** after `ALTER INDEX i_dup1000 SET (deduplicate_items = off)` and a `REINDEX
INDEX CONCURRENTLY`, while the engine still logged "can safely use deduplication"
and byte 64 still read true. `RESET (deduplicate_items)` and one more rebuild
returned it to 7,340,032. That is why
[Check 1](#check-1-read-the-flag-with-core-sql) reads `reloptions` as well as the
metapage. The parameter defaults to on
([create_index.sgml#deduplicate_items](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L448-L476)),
takes `ShareUpdateExclusiveLock`, and changing it does not convert existing tuples
([reloptions.c:159-168](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L168)).

### Unique and near-unique indexes get the flag but no size win

`_bt_load()` skips deduplication for unique indexes, so rebuilding a carried-over
unique index changes its size by nothing: `i_uniq` measured 22,487,040 bytes before
and after, with byte 64 flipping from false to true. A non-unique index whose keys
happen to be distinct gets the same treatment from the data rather than from the
code: `i_uuid`, 1,000,000 distinct `uuid` values, measured 31,563,776 bytes before
and after. The value of those rebuilds is later: a unique index with the flag set
can run insert-time deduplication to absorb version churn and delay page splits
([btree.sgml#btree-deduplication](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L810-L833),
[nbtinsert.c#_bt_findinsertloc](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L899-L907)).
Rank those rebuilds below the duplicate-heavy non-unique ones.

### What a rebuild actually recovered

`REINDEX INDEX CONCURRENTLY`, one index at a time, over every index of `t_main`,
`t_churn` and `t_empty` on the freshly upgraded cluster. The fixtures were built
once on 12.2 and never updated, except `t_churn`, which took 200,000 extra inserts
first, so there is no ordinary bloat to confuse the numbers:

| index | keys | before | after | change | flag |
|---|---|---|---|---|---|
| `i_dup10` | `k10` (10 distinct) | 22,519,808 | 6,963,200 | −69.08% | false → true |
| `i_txt` | `txt` (100 distinct) | 22,519,808 | 6,979,584 | −69.01% | false → true |
| `i_txt_pattern` | `txt text_pattern_ops` | 22,519,808 | 6,979,584 | −69.01% | false → true |
| `i_expr` | `lower(txt)` | 22,519,808 | 6,979,584 | −69.01% | false → true |
| `i_partial` | `k10 WHERE st = 'open'` | 2,277,376 | 712,704 | −68.71% | false → true |
| `i_churn` | `k` (20 distinct), after 200,000 extra inserts | 8,904,704 | 2,801,664 | −68.54% | false → true |
| `i_dup1000` | `k1000` (1000 distinct) | 22,519,808 | 7,340,032 | −67.41% | false → true |
| `i_multi` | `(k10, k1000)` | 22,519,808 | 7,340,032 | −67.41% | false → true |
| `i_uniq` | `id`, unique | 22,487,040 | 22,487,040 | 0.00% | false → true |
| `i_uuid` | `u` (1,000,000 distinct) | 31,563,776 | 31,563,776 | 0.00% | false → true |
| `i_empty` | empty table | 8,192 | 8,192 | 0.00% | false → true |
| `i_num` | `num` numeric | 22,519,808 | 22,519,808 | 0.00% | false → false |
| `i_flt` | `flt` float8 | 22,519,808 | 22,519,808 | 0.00% | false → false |
| `i_js` | `js` jsonb | 49,733,632 | 49,733,632 | 0.00% | false → false |
| `i_arr` | `arr` int[] | 49,823,744 | 49,823,744 | 0.00% | false → false |
| `i_multimixed` | `(k10, num)` | 31,604,736 | 31,604,736 | 0.00% | false → false |
| `i_inc` | `k10` `INCLUDE (txt)` | 22,519,808 | 22,519,808 | 0.00% | false → false |

The six indexes the gate refused came out identical to the byte, which is the
strongest argument for running it: rebuilding them costs a full index build and buys
nothing. The three it flagged whose keys are unique, near-unique or absent also came
out identical, exactly as their verdict text predicts for a unique index.

### How much duplication is worth a rebuild

Fresh 1,000,000-row single-column builds on 17.11, each built twice, once with
`deduplicate_items = off` and once with the default, so the difference is
deduplication alone:

| rows per key | no-deduplication bytes | deduplicated bytes | saved |
|---|---|---|---|
| 1 | 22,487,040 | 22,487,040 | 0.0% |
| 2 | 22,487,040 | 20,275,200 | 9.8% |
| 5 | 22,511,616 | 11,681,792 | 48.1% |
| 20 | 22,519,808 | 7,782,400 | 65.4% |
| 100 | 22,519,808 | 6,873,088 | 69.5% |
| 1000 | 22,519,808 | 7,340,032 | 67.4% |

The curve is flat above roughly 20 rows per key, and the small reversal at 1000 is
expected: a posting list is capped, and the single-value split strategy uses a 96%
fill factor
([nbtree.h#BTREE_SINGLEVAL_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202)).
A practical reading: two rows per key is barely worth it, five or more is worth it,
and unique or near-unique keys are not.

### The cost of leaving it alone

The carried-over index does not stop growing at the old rate — it keeps splitting
where a deduplicating index would merge. Measured on the 20-distinct-value
`t_churn` fixture after the upgrade, inserting 200,000 more duplicate rows with both
indexes present:

| index | before insert | after insert |
|---|---|---|
| `i_churn` (carried over from 12.2) | 4,521,984 | 8,904,704 |
| `i_churn_new` (built on 17.11) | 1,400,832 | 2,850,816 |

The carried-over index ended 3.1x larger than the index built after the upgrade over
identical data.

### Separating deduplication from ordinary bloat

On a table that has taken updates since the upgrade, a rebuild reclaims both bloat
and the deduplication win, and a size drop alone cannot tell you which. Build two
twins and the arithmetic separates:

```sql
CREATE INDEX CONCURRENTLY /* wiki_dedup_twin_off */ twin_off ON t_main2 (k10)
  WITH (deduplicate_items = off);
CREATE INDEX CONCURRENTLY /* wiki_dedup_twin_on */ twin_on ON t_main2 (k10);
```

Measured, same index definition, on the carried-over `i_dup10b` after one `UPDATE`
of every row of its table:

| relation | bytes | reading |
|---|---|---|
| `i_dup10b`, carried over | 43,737,088 | current state |
| `twin_off`, fresh, deduplication disabled | 22,519,808 | bloat = 48.5% of the current index |
| `twin_on`, fresh, deduplication enabled | 6,963,200 | deduplication = 69.1% of what is left |

Before that `UPDATE`, the same comparison put `twin_off` at 22,519,808 bytes —
exactly the carried-over index's size, to the byte — which is the direct measurement
that a v12-built index is precisely a v17 index with deduplication turned off. Drop
the twins afterwards.

### What sets the flag, and what does not

| operation | index used | sets `btm_allequalimage` | measured |
|---|---|---|---|
| `REINDEX INDEX CONCURRENTLY` | the 17 above | yes | flag true on the 11 equal-image ones, `pd_lower` 72, a new `pg_class` OID per index |
| `REINDEX INDEX` | `i_ts` | yes | flag false → true, `pd_lower` 72, relfilenode 16421 → 16594, one `DEBUG1` line |
| `VACUUM FULL` | `i_u_k` | yes, it rebuilds every index of the table | flag false → true, relfilenode 16425 → 16598, one `DEBUG1` line |
| `CLUSTER` | `p_main_1_k_idx` | yes, same path | flag false → true, relfilenode 16436 → 16602, one `DEBUG1` line |
| `VACUUM (INDEX_CLEANUP ON)` | `i_ts` | no | flag stayed false, `pd_lower` stayed 64, same relfilenode, no `DEBUG1` line |
| `ALTER INDEX ... SET (deduplicate_items = off)` | `i_ts` | no | flag stayed false, `pd_lower` stayed 64, same relfilenode, no `DEBUG1` line |

`VACUUM FULL` and `CLUSTER` set it because they finish by rebuilding the table's
indexes
([cluster.c#finish_heap_swap](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1490-L1508)),
one `DEBUG1` line per index of the table they rewrite. `REINDEX INDEX` keeps the
index's `pg_class` row and gives it a new relfilenode
([index.c#reindex_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3783-L3789)),
while the concurrent form builds a second index and swaps the name onto it
([index.c#index_concurrently_swap](../../../../raw/postgres-17/src/backend/catalog/index.c#L1559-L1618)),
which is why the name ends up on a different OID. For a large production index,
prefer `REINDEX INDEX CONCURRENTLY`, which holds only
`ShareUpdateExclusiveLock`; its phases, waits and failure modes are covered in
[How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 17 (unverified)](reindex-index-concurrently.md).

### Rebuild order and the statistics pg_upgrade leaves behind

`pg_upgrade` restores the schema by creating empty indexes and then swapping files
in, and in binary-upgrade mode the build does not write statistics at all:
`index_update_stats()` skips the update when `IsBinaryUpgrade` is set, "because the
indexes are created before the data is moved into place"
([index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842)).
Measured: all **26 carried-over indexes had `relpages = 0`**, 25 of them
`reltuples = 0`, and one — `pg_largeobject_loid_pn_index`, whose row the new
cluster's `initdb` created rather than the restore — the `-1` unknown sentinel a new
relation starts with
([heap.c#AddNewRelationTuple](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1004-L1016)).
Any triage that divides by `reltuples`, including the sweep on
[Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified)](btree-index-bloat-core-sql-only.md),
is blind until the `vacuumdb --all --analyze-in-stages` that `pg_upgrade` itself
recommends has run
([check.c#output_completion_banner](../../../../raw/postgres-17/src/bin/pg_upgrade/check.c#L760-L790));
after that run, 0 of the 23 indexes in `public` were still at `relpages = 0`. The
metapage probe does not depend on statistics at all, which is its main advantage
right after an upgrade.

After analyzing, rank the flagged indexes by size and duplication:

```sql
SELECT /* wiki_dedup_rebuild_priority */
       c.relname,
       pg_size_pretty(pg_relation_size(c.oid)) AS index_size,
       c.reltuples::bigint                     AS index_reltuples,
       round(s.keys::numeric, 0)               AS distinct_keys,
       CASE WHEN s.keys > 0 AND c.reltuples > 0
            THEN round((c.reltuples / s.keys)::numeric, 1) END AS rows_per_key
FROM pg_class c
JOIN pg_index i ON i.indexrelid = c.oid
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN LATERAL (
       SELECT CASE WHEN count(*) = i.indnkeyatts
                   THEN exp(sum(ln(CASE WHEN st.n_distinct > 0 THEN st.n_distinct
                                        ELSE -st.n_distinct * greatest(t.reltuples, 1) END)))
              END AS keys
       FROM generate_series(0, i.indnkeyatts - 1) AS k
       JOIN pg_attribute a2 ON a2.attrelid = i.indrelid AND a2.attnum = i.indkey[k]
       JOIN pg_stats st ON st.schemaname = n.nspname AND st.tablename = t.relname
                       AND st.attname = a2.attname
       WHERE st.n_distinct <> 0
     ) s ON true
WHERE c.relkind = 'i'
  AND n.nspname = 'public'
  AND pg_relation_size(c.oid) > 8192
ORDER BY pg_relation_size(c.oid) DESC;
```

Measured behaviour after the staged analyze: `rows_per_key` came out 100,000.0 for
the 10-distinct-value index, 1000.0 for the 1000-value one, 100.0 for the two-column
index, 1.0 for the unique and the `uuid` index, and `NULL` for the expression index
`i_expr`, whose key has no `pg_stats` row under the table's column names.

The partial index is the row to distrust. It printed **9,673.4** rows per key from
an index `reltuples` of **96,734**, where the truth is **100,000 indexed rows over
exactly one distinct key value, so 100,000.0 rows per key** — an order of magnitude
out. Two independent errors stack: an index's `reltuples` is an `ANALYZE` estimate
of its own population rather than a count, and the divisor is the *table-wide*
`n_distinct` of `k10`, which is 10, while the predicate `st = 'open'` admits only
the rows whose `k10` is 0. Expression and partial indexes need the fuller model on
the bloat page cited above; this query only orders work.

### Second opinion: make the engine say it

`_bt_allequalimage()` logs its own decision at `DEBUG1` on every build, so a rebuild
can be made to state whether it enabled deduplication:

```sql
SET client_min_messages = debug1;
REINDEX INDEX CONCURRENTLY /* wiki_dedup_rebuild */ public.i_dup10;
-- DEBUG:  index "i_dup10_ccnew" can safely use deduplication
```

Two limits, both measured. The message names the transient `_ccnew` index, and it
reports `_bt_allequalimage()` only: it also said "can safely use deduplication" for
the index rebuilt under `deduplicate_items = off` that came out at full size. And it
is silent for `INCLUDE` indexes. It is a confirmation, not a pre-check.

### Fallbacks when you cannot read server files

If nobody will grant EXECUTE on `pg_read_binary_file`, two weaker options remain:

1. **Snapshot `relfilenode` right after the upgrade**, then treat any index whose
   relfilenode still matches the snapshot as un-rebuilt. Key the comparison on
   schema and name, not on the recorded index OID: `REINDEX INDEX CONCURRENTLY`
   swaps the name onto the newly built index's `pg_class` row
   ([index.c#index_concurrently_swap](../../../../raw/postgres-17/src/backend/catalog/index.c#L1559-L1618)),
   so the recorded OID is gone afterwards. Measured on a 190-row baseline after 20
   rebuilds: joined on the recorded OID it reported 170 unchanged, 3 moved and **17
   recorded OIDs that no longer exist** — the 17 concurrent rebuilds, silently
   dropped by the join — while joined on schema and name it reported 170 unchanged
   and all **20 moved**.

   ```sql
   CREATE TABLE wiki_dedup_baseline AS
   SELECT /* wiki_dedup_baseline */ c.oid AS indexrelid, c.relnamespace,
          c.relname, c.relfilenode, now() AS captured
   FROM pg_class c
   JOIN pg_am a ON a.oid = c.relam
   WHERE c.relkind = 'i' AND a.amname = 'btree';
   ```

2. **Build the two twins** from
   [Separating deduplication from ordinary bloat](#separating-deduplication-from-ordinary-bloat)
   and compare sizes. Definitive for one index, but it costs two index builds.

What does *not* work as a durable after-the-fact signal is `pg_class.xmin` or
relfilenode magnitude. `pg_upgrade` copies the old cluster's commit log and sets the
new cluster's XID counters from the old cluster's control data
([pg_upgrade.c#copy_xact_xlog_xid](../../../../raw/postgres-17/src/bin/pg_upgrade/pg_upgrade.c#L701-L737)),
and then asks `pg_resetwal -o` for the old cluster's next OID
([pg_upgrade.c#main](../../../../raw/postgres-17/src/bin/pg_upgrade/pg_upgrade.c#L155-L197)),
so restored rows do not sit at obviously low XIDs: the schema restore consumed the
XIDs from the old cluster's `NextXID` of 487 up to 552, leaving the new cluster's
`NextXID` at 553, and it wrote every carried-over `pg_class` row in the last of
them — all 26 share a single `xmin` of 552.

The OID side gives no band either. The carried-over relfilenodes
ran 16392 to 16441, the new cluster's control file reported `NextOID` 16449 both
immediately after the upgrade and later, and a table created after the upgrade got
OID 16503 — adjacent to the carried-over range, not separated from it. The band is
only recognizable if you recorded it at upgrade time.

### Edge cases the check has to survive

All measured on the upgraded cluster:

- **Partitioned indexes.** The parent (`relkind = 'I'`) has no storage and
  `pg_relation_filepath()` returns NULL, so the `relkind = 'i'` filter drops it;
  both leaf indexes read false and were flagged.
- **Unlogged tables.** `i_u_k` on an unlogged table probed normally, read
  `pd_lower = 64` and false, and was flagged.
- **Non-default tablespaces.** `i_ts` lives in a second tablespace; the path
  `pg_relation_filepath()` returns —
  `pg_tblspc/16385/PG_17_202406281/16384/16421` — resolves through the data
  directory's `pg_tblspc` symlink, so the probe worked unchanged.
- **Temporary indexes.** Excluded by `relpersistence <> 't'`. A temp index can be
  probed from its owning session only (`base/16384/t33_16513` read byte 64 = 1), and
  it is never carried over by an upgrade anyway.
- **TOAST indexes.** Carried over with their tables: 3 of the cluster's 43
  `pg_toast` B-tree indexes read false, and they are exactly the three belonging to
  fixture tables. Rebuilding one needs its schema-qualified name.
- **`pg_largeobject`.** This is the one system catalog whose files `pg_upgrade`
  transfers ([info.c#get_rel_infos](../../../../raw/postgres-17/src/bin/pg_upgrade/info.c#L471-L496)),
  and `pg_largeobject_loid_pn_index` was one of only two `pg_catalog` B-tree indexes
  with `pd_lower = 64` and byte 64 false. Its keys are equal-image, so a rebuild
  sets the flag, but it is unique, so expect no size change.
- **`pg_enum_typid_sortorder_index`.** The other false `pg_catalog` row, and the
  only freshly built one, because `enumsortorder` is `float4`. It reads
  `pd_lower = 72`, which is how a fresh false differs from a carried-over false.
  Nothing to do.
- **Zero-length or missing files.** The `octet_length(...) = 72` guard and
  `missing_ok => true` make the probe return NULL instead of raising. Measured
  against a deliberately short 40-byte read: the guarded form returned NULL with no
  error, the unguarded form raised
  `ERROR:  index 64 out of valid range, 0..39`
  ([varlena.c#byteaGetByte](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L3246-L3268)).

### Where this comes from in the source history

From this checkout's own history, with first release tags:

| commit | subject | first release |
|---|---|---|
| `612a1ab7672` | Add equalimage B-Tree support functions. | `REL_13_0` |
| `0d861bbb702` | Add deduplication to nbtree. | `REL_13_0` |
| `e5d8a999030` | Use full 64-bit XIDs in deleted nbtree pages. | `REL_14_0` |
| `9f3665fbfc3` | Don't consider newly inserted tuples in nbtree VACUUM. | `REL_14_0` |
| `5f27b5f848a` | Dissociate btequalimage() from interval_ops, ending its deduplication. | `REL_17_0` |

`0d861bbb702` is also the commit that introduced the "zero'ed on ... pg_upgrade'd
from Postgres 12" comment in `_bt_metaversion()`, and no commit in
`src/bin/pg_upgrade` has ever touched `allequalimage` (`git log -S allequalimage --
src/bin/pg_upgrade` is empty), so the gap the comment describes is still open in
17.11.

The two v14 commits matter to carried-over indexes for a different reason, and they
are easy to confuse. `e5d8a999030` is the one that repurposed the metapage's old
`btm_oldest_btpo_xact` field — its message says the field "has been repurposed and
renamed" to `btm_last_cleanup_num_delpages` — so a v12-built metapage can present a
stale XID where v17 reads a deleted-page count, which the code tolerates
deliberately
([nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L225-L263)).
`9f3665fbfc3` then deprecated the neighbouring `btm_last_cleanup_num_heap_tuples`,
dropped the `vacuum_cleanup_index_scale_factor` GUC and reloption, and cut the
`num_heap_tuples` argument out of `_bt_set_cleanup_info()`. Measured here as
harmless either way: the repurposed field read 0 on all 26 carried-over indexes, and
`pageinspect` agreed with the probe on that field in all 189 rows.

`5f27b5f848a` is the one commit here that can make a carried-over metapage *wrong*
rather than merely stale, because it withdrew an opclass's equal-image support
instead of adding the field. It is covered in
[When a true flag is the wrong answer](#when-a-true-flag-is-the-wrong-answer), and
it is out of reach of a 12 → 17 upgrade, whose flags are all false to begin with.

### Settings this page touches

| setting | value used | context | apply scope |
|---|---|---|---|
| `statement_timeout` | `60s` for the read-only checks | `PGC_USERSET` ([guc_tables.c:2611-2620](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2620)) | session or transaction |
| `lock_timeout` | `5s` for the read-only checks | `PGC_USERSET` ([guc_tables.c:2622-2632](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2622-L2632)) | session or transaction |
| `client_min_messages` | `debug1` to see the engine's verdict | `PGC_USERSET` ([guc_tables.c:4776-4785](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4776-L4785)) | session or transaction |
| `deduplicate_items` | leave at `on` | B-tree reloption, `ShareUpdateExclusiveLock` ([reloptions.c:159-168](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L168)) | per index, `ALTER INDEX` |

No restart or reload is needed for anything on this page. Do not raise
`statement_timeout` for the rebuilds themselves without thought: a long
`REINDEX INDEX CONCURRENTLY` that is cancelled leaves an invalid `_ccnew` index
behind, which the sibling page on `REINDEX INDEX CONCURRENTLY` describes.

## Measurement Script

Every number on this page comes from one script,
`dedup_upgrade_probe.sh`, filed in full under [The script](#the-script). It is Bash
and SQL only, plus two small C programs it compiles to read `offsetof()` out of each
build's own headers; a reviewer needs a compiler, a shell and this page.

### How to use it

| Item | What to give |
|---|---|
| Purpose | Builds PostgreSQL 12.2 and 17.11 from this repository's pinned checkouts, creates disposable 12.2 fixtures, upgrades them with `pg_upgrade --copy`, and measures every number this page reports: the metapage census, the core-SQL probe and its privileges, the catalog gate against the engine's `DEBUG1` verdict, the rebuild results, the `deduplicate_items` trap, the flag-setting matrix, the relfilenode fallback, the savings curve, the bloat/deduplication split, the churn comparison, the post-upgrade statistics including the partial index's exact population against `ANALYZE`'s estimate, the edge cases, and an audit of both server logs for `ERROR` lines that were not provoked on purpose |
| Invocation | `bash .wiki-runtime/tmp/pgdedup/dedup_upgrade_probe.sh [stage ...]`, run from the repository root. With no arguments it runs every stage except `clean`. Extract the fenced script below to that path first |
| Stages | Default order: `build12 build17 check reset fixtures upgrade offsets probe gate curve twins churn rebuild stats summary`. `build12`/`build17` configure and install out of tree and skip when the binary exists; `check` runs `make check` on both trees plus `contrib/pageinspect`; `reset` deletes both clusters and truncates both server logs but keeps the builds, so a full run always starts from the same state; `fixtures` initdbs 12.2 and builds the disposable fixtures, then stops it and digests every index file; `upgrade` initdbs 17.11 and runs `pg_upgrade --copy`; `offsets` compiles the two `offsetof()` programs against both header sets; `probe` starts 17.11 and takes the census, the self-test, the `pageinspect` cross-check, the digest comparison, the counters, the privilege matrix and the edge cases; `gate` builds the 17 gate shapes under `client_min_messages = debug1`; `curve` measures the savings curve; `twins` measures the bloat/deduplication split; `churn` measures the cost of leaving an index alone; `rebuild` runs the concurrent rebuilds, the trap, the flag matrix and the fallback; `stats` runs `vacuumdb --all --analyze-in-stages`, the priority query and the partial index's exact-population probe; `summary` collects everything into `out/summary.txt` and itemizes every `ERROR` line in both server logs. `clean` is not in the default order and must be run last |
| Environment | `REPO` (`$PWD`), `SRC17` (`$REPO/raw/postgres-17`), `SRC12` (`$REPO/raw/postgres-12`), `SANDBOX` (`$REPO/.wiki-runtime/tmp/pgdedup`), `JOBS` (`8`), `PORT12` (`55312`), `PORT17` (`55317`), `ROWS` (`1000000`), `CHURN_ROWS` (`200000`), `STMT_TIMEOUT` (`600s`), `LOCK_TIMEOUT` (`30s`), `EXTRA_CFLAGS12` (`-O2 -g -DTRUE=1 -DFALSE=0`) |
| Prerequisites | See [Prerequisites](#prerequisites) |
| Output | Everything lands under `$SANDBOX/out/`; see [Where the results land](#where-the-results-land). Read `out/summary.txt` first |
| Runtime | About 4 minutes from an empty sandbox on the recorded host: 236 s in total, of which 156 s is the two builds (70 s for 12.2, 86 s for 17.11), 31 s the three regression suites, and 49 s every measurement stage. A re-run from built trees is 76 s: 29 s of suites and 47 s of measurement |
| Cleanup | `bash dedup_upgrade_probe.sh clean` stops both servers, reports whether any `postmaster.pid` or matching `postgres` process survived, and deletes the whole sandbox |

### Prerequisites

- A C toolchain, `make`, `flex`, `bison` and `perl`. The recorded run used gcc
  13.3.0 on `Linux x86_64`. Both legs build their own server; no installed
  PostgreSQL is used, and the script never touches a cluster it did not create.
- Development headers for ICU, readline and zlib: both legs configure
  `--with-icu --with-readline --with-zlib`, and the gate's nondeterministic and
  deterministic ICU collations need ICU. `configure` finds ICU through
  `pkg-config`; on a host without it, export `ICU_CFLAGS` and `ICU_LIBS` before
  running.
- The 12.2 leg builds with `CFLAGS="-O2 -g -DTRUE=1 -DFALSE=0"`, because ICU 68
  removed the two macros that tree still uses. On a host whose ICU still defines
  them set `EXTRA_CFLAGS12="-O2 -g"`, not the empty string: `configure` treats an
  empty `CFLAGS` as set and then builds unoptimised.
- Both pinned checkouts present, at `raw/postgres-17` and `raw/postgres-12`.
- Ports 55312 and 55317 free, and about 3 GB under `.wiki-runtime/tmp/`.
- `md5sum`, and a `psql` reachable only through the sandbox's own socket
  directories. The script calls `psql -X -v ON_ERROR_STOP=1`, so a stray
  `~/.psqlrc` cannot change a result and no error passes silently.

### Where the results land

| File | What is in it |
|---|---|
| `summary.txt` | every section below, in one file, ending with the itemized `ERROR`-line audit of both server logs; read this first |
| `checks.txt`, `check*.log` | the three regression suites and their full logs |
| `configure*.log`, `make*.log`, `install*.log` | build diagnostics, copied out of the build trees so they outlive `reset` |
| `offsets.txt` | the three `offsetof()` runs: v17 fields on 17.11 headers, the same program refused by the 12.2 headers, and the v12 field set |
| `upgrade.log`, `upgrade_says.txt`, `upgrade_artifacts.txt` | the whole `pg_upgrade` run, the scripts it left, and the grep for reindex/rebuild/deduplicat |
| `census12.txt`, `census17_before.txt`, `census17_files.txt`, `census_summary.txt` | the index inventories on both clusters and the per-schema flag counts |
| `md5_old.txt`, `md5_new.txt`, `md5_compare.txt` | the file digests before and after the upgrade, and the per-index comparison |
| `stats_zero.txt`, `priority.txt` | `relpages`/`reltuples` as the upgrade left them, and the rebuild priority query after the staged analyze, followed by the partial index's exact population and `ANALYZE`'s estimate of it |
| `selftest.txt`, `crosscheck_before.txt`, `crosscheck_after.txt` | the platform self-test and the two `bt_metap()` cross-checks |
| `privileges.txt`, `edges.txt`, `counters.txt` | the seven privilege probes, the edge cases, and the XID/OID counters |
| `gate_build.txt`, `gate_debug1.txt`, `gate_rows.txt`, `gate_score.txt`, `gate_pattern.txt` | the gate fixtures, the engine's `DEBUG1` lines, and the scored table |
| `rebuild.txt`, `trap.txt`, `flagsets.txt`, `fallback.txt` | the rebuild results, the `deduplicate_items` trap, the flag-setting matrix and the two fallback joins |
| `curve.txt`, `twins.txt`, `churn.txt` | the savings curve, the bloat/deduplication split and the churn comparison |
| `check1_before.txt`, `check1_after.txt` | the filed core-SQL check, exactly as published, before and after the rebuilds |
| `server12.log`, `server17.log` | the two server logs |

### The last run

| Fact | Value |
|---|---|
| Date | 2026-09-16, the review that re-ran the script after editing it; it supersedes the 2026-09-15 run, which produced the same numbers except where noted |
| Host | `Linux x86_64`, Ubuntu 24.04, gcc 13.3.0, ICU 74.2, 22 cores, `JOBS=20` |
| Platform facts | `block_size` 8192, `max_data_alignment` 8, `database_block_size` 8192, `MAXIMUM_ALIGNOF` 8 |
| 17 leg | 17.11 from `786db8dcf168bd9df8f55047337525ac19118b1c`, `--enable-debug --with-icu --with-readline --with-zlib`; `make check` **All 225 tests passed**, `contrib/pageinspect` **All 8 tests passed** ([regress.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L40-L59)) |
| 12 leg | 12.2 from `45b88269a353ad93744772791feb6d01bc7e1e42`, the same flags plus `CFLAGS="-O2 -g -DTRUE=1 -DFALSE=0"`; `make check` **All 192 tests passed** |
| Clusters | `initdb --locale=C --encoding=UTF8` on both, `autovacuum = off`, `fsync = off`, `max_wal_size = 2GB` (all three `PGC_SIGHUP`, set in `postgresql.conf` before the first start), ports 55312 and 55317, sockets and data directories inside the sandbox |
| Fixtures | 1,000,000 rows in `t_main` and `t_main2`, 200,000 in `t_churn`, `t_ts`, `t_unlog` and `t_part`, an empty `t_empty`, a TOASTed `t_toast`, one large object; 22 B-tree indexes in `public` |
| Upgrade | `pg_upgrade --copy`, 12.2 → 17.11, one script left (`delete_old_cluster.sh`), 26 index files carried over, 26 of 26 digests identical |
| Reproducibility | the script ran four times on this host today, twice before the edits and twice after. Every scored cell came out identical on all four — the census, the 189-row check and its verdict counts, the offsets, the gate, the curve, the twins, the churn, the 17 rebuild rows, the trap, the flag matrix, the fallback joins and the counters. The one moving number is the partial index's sampled `reltuples`: 101,667, 104,734, 98,700 and 96,734, against 99,867 on 2026-09-15 and an exact population of 100,000 |
| Server logs | 6 `ERROR` lines on 17.11, every one provoked on purpose — 3 × `permission denied for function pg_read_binary_file`, 1 × `absolute path not allowed`, 1 × `index 64 out of valid range, 0..39`, 1 × `nondeterministic collations are not supported for operator class "text_pattern_ops"` — and 0 on 12.2 |
| Teardown | the `clean` stage stopped both servers and deleted the sandbox; see the log entry for the confirmation |

The numbers on this page and the script text below come from that one run. If the
script is edited afterwards, re-run it before changing any number. The 2026-09-16
review did edit it — a `rebuild for correctness` branch in the filed check, an
exact-population probe for the partial index, per-run truncation of the server logs
in `reset`, and the itemized log audit in `summary` — and then re-ran every stage.

### The script

```bash
#!/usr/bin/env bash
#
# dedup_upgrade_probe.sh - the measurement script for the wiki page
#   wiki/v17/questions/indexing/btree-deduplication-after-pg-upgrade.md
#
# It builds PostgreSQL 12.2 and 17.11 out of tree from this repository's
# pinned checkouts, creates disposable fixtures on 12.2, upgrades them with
# "pg_upgrade --copy", and then measures every number the page reports about
# btm_allequalimage after a binary upgrade: the metapage census, the core-SQL
# probe, the catalog gate against the engine's own DEBUG1 verdict, the rebuild
# results, the savings curve, the bloat/deduplication split and the edge cases.
#
# Everything it creates is disposable.  It runs its own two clusters, on
# non-default ports, under its own sandbox, and never touches a cluster it did
# not create.  The "clean" stage stops them and deletes the sandbox.
#
# Usage:
#   bash dedup_upgrade_probe.sh              # every stage except clean
#   bash dedup_upgrade_probe.sh probe gate   # selected stages, in order given
#   bash dedup_upgrade_probe.sh clean        # stop servers, delete sandbox
#
set -uo pipefail

REPO="${REPO:-$PWD}"
SRC17="${SRC17:-$REPO/raw/postgres-17}"
SRC12="${SRC12:-$REPO/raw/postgres-12}"
SANDBOX="${SANDBOX:-$REPO/.wiki-runtime/tmp/pgdedup}"
JOBS="${JOBS:-8}"
PORT12="${PORT12:-55312}"
PORT17="${PORT17:-55317}"
ROWS="${ROWS:-1000000}"
CHURN_ROWS="${CHURN_ROWS:-200000}"
STMT_TIMEOUT="${STMT_TIMEOUT:-600s}"
LOCK_TIMEOUT="${LOCK_TIMEOUT:-30s}"
# ICU 68 removed the TRUE/FALSE macros that the 12.2 tree still uses; put them
# back through CFLAGS.  Set this to "-O2 -g" on a host whose ICU still defines
# them: configure treats an empty CFLAGS as set and then builds unoptimised.
EXTRA_CFLAGS12="${EXTRA_CFLAGS12:--O2 -g -DTRUE=1 -DFALSE=0}"

BUILD12="$SANDBOX/build12"; INST12="$SANDBOX/install12"; DATA12="$SANDBOX/data12"
BUILD17="$SANDBOX/build17"; INST17="$SANDBOX/install17"; DATA17="$SANDBOX/data17"
BIN12="$INST12/bin"; BIN17="$INST17/bin"
SOCK12="$SANDBOX/sock12"; SOCK17="$SANDBOX/sock17"
TS12="$SANDBOX/ts12"; UPG="$SANDBOX/upgrade"
OUT="$SANDBOX/out"; SQLD="$SANDBOX/sql"; CD="$SANDBOX/c"
DB=dedup

note() { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
die()  { printf '[%s] FATAL: %s\n' "$(date +%H:%M:%S)" "$*" >&2; exit 1; }

# psql wrappers.  -X ignores ~/.psqlrc, ON_ERROR_STOP=1 lets no error pass
# silently, and the two timeouts are session-scoped (both PGC_USERSET).
p12() { local db="$1"; shift
  PGOPTIONS="-c statement_timeout=$STMT_TIMEOUT -c lock_timeout=$LOCK_TIMEOUT" \
  "$BIN12/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK12" -p "$PORT12" -d "$db" "$@"; }
p17() { local db="$1"; shift
  PGOPTIONS="-c statement_timeout=$STMT_TIMEOUT -c lock_timeout=$LOCK_TIMEOUT" \
  "$BIN17/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK17" -p "$PORT17" -d "$db" "$@"; }
q12() { local db="$1"; shift; p12 "$db" -At -c "$*"; }
q17() { local db="$1"; shift; p17 "$db" -At -c "$*"; }

start12() { "$BIN12/pg_ctl" -D "$DATA12" -l "$OUT/server12.log" -w -o "-p $PORT12 -k $SOCK12" start; }
stop12()  { [ -f "$DATA12/postmaster.pid" ] && "$BIN12/pg_ctl" -D "$DATA12" -m fast -w stop; true; }
start17() { "$BIN17/pg_ctl" -D "$DATA17" -l "$OUT/server17.log" -w -o "-p $PORT17 -k $SOCK17" start; }
stop17()  { [ -f "$DATA17/postmaster.pid" ] && "$BIN17/pg_ctl" -D "$DATA17" -m fast -w stop; true; }

# ---------------------------------------------------------------- build stages

stage_build12() {
  [ -x "$BIN12/postgres" ] && { note "12.2 already built, skipping"; return 0; }
  [ -x "$SRC12/configure" ] || die "no pinned checkout at $SRC12"
  mkdir -p "$BUILD12" "$OUT"
  note "configuring 12.2"
  ( cd "$BUILD12" && "$SRC12/configure" --prefix="$INST12" --enable-debug \
      --with-icu --with-readline --with-zlib CFLAGS="$EXTRA_CFLAGS12" \
      > configure.log 2>&1 ) || { cp "$BUILD12"/configure.log "$OUT/configure12.log"; die "12.2 configure failed"; }
  note "building 12.2"
  ( cd "$BUILD12" && make -j"$JOBS" > make.log 2>&1 && make install > install.log 2>&1 ) \
    || { for l in configure make install; do cp "$BUILD12/$l.log" "$OUT/${l}12.log" 2>/dev/null; done; die "12.2 build failed"; }
  for l in configure make install; do cp "$BUILD12/$l.log" "$OUT/${l}12.log" 2>/dev/null; done
  "$BIN12/postgres" --version > "$OUT/version12.txt" 2>&1
  note "12.2 installed: $(cat "$OUT/version12.txt")"
}

stage_build17() {
  [ -x "$BIN17/postgres" ] && { note "17.11 already built, skipping"; return 0; }
  [ -x "$SRC17/configure" ] || die "no pinned checkout at $SRC17"
  mkdir -p "$BUILD17" "$OUT"
  note "configuring 17.11"
  ( cd "$BUILD17" && "$SRC17/configure" --prefix="$INST17" --enable-debug \
      --with-icu --with-readline --with-zlib > configure.log 2>&1 ) \
    || { cp "$BUILD17"/configure.log "$OUT/configure17.log"; die "17.11 configure failed"; }
  note "building 17.11"
  ( cd "$BUILD17" && make -j"$JOBS" > make.log 2>&1 && make install > install.log 2>&1 ) \
    || { for l in configure make install; do cp "$BUILD17/$l.log" "$OUT/${l}17.log" 2>/dev/null; done; die "17.11 build failed"; }
  note "building contrib/pageinspect (ground truth only, not part of the check)"
  ( cd "$BUILD17/contrib/pageinspect" && make -j"$JOBS" >> "$BUILD17/make.log" 2>&1 \
      && make install >> "$BUILD17/install.log" 2>&1 ) || die "pageinspect build failed"
  for l in configure make install; do cp "$BUILD17/$l.log" "$OUT/${l}17.log" 2>/dev/null; done
  "$BIN17/postgres" --version > "$OUT/version17.txt" 2>&1
  note "17.11 installed: $(cat "$OUT/version17.txt")"
}

stage_check() {
  mkdir -p "$OUT"
  : > "$OUT/checks.txt"
  # The suites validate the build, not the probe.  Their result lines are
  # printed differently by the two majors, so match the text, not the column.
  result_line() { grep -E '(All [0-9]+ tests passed|[0-9]+ of [0-9]+ tests failed)' "$1" | tail -1 | sed -E 's/^[# ]+//; s/ +$//'; }
  note "make check on 17.11"
  ( cd "$BUILD17" && make check > "$OUT/check17.log" 2>&1 )
  printf '17 core      : %s\n' "$(result_line "$OUT/check17.log")" >> "$OUT/checks.txt"
  ( cd "$BUILD17/contrib/pageinspect" && make check > "$OUT/check17_pageinspect.log" 2>&1 )
  printf '17 pageinspect: %s\n' "$(result_line "$OUT/check17_pageinspect.log")" >> "$OUT/checks.txt"
  note "make check on 12.2"
  ( cd "$BUILD12" && make check > "$OUT/check12.log" 2>&1 )
  printf '12 core      : %s\n' "$(result_line "$OUT/check12.log")" >> "$OUT/checks.txt"
  for f in "$OUT"/check*.log; do
    grep -q 'tests failed' "$f" && cp "${f%.log}"*regression.diffs "$OUT/" 2>/dev/null
  done
  cat "$OUT/checks.txt" >&2
}

# Drop both clusters but keep the builds, so a full run always starts from the
# same state.  It never touches a data directory this script did not create.
stage_reset() {
  note "resetting the clusters this script created"
  stop17; stop12
  rm -rf "$DATA12" "$DATA17" "$TS12" "$UPG" "$SOCK12" "$SOCK17"
  rm -f "$OUT"/census*.txt "$OUT"/md5_*.txt
  # pg_ctl appends, so the server logs have to start empty too: the summary
  # audits them for unexpected ERROR lines, and a stale log would be counted.
  : > "$OUT/server12.log"; : > "$OUT/server17.log"
  mkdir -p "$SOCK12" "$SOCK17" "$TS12" "$UPG"
}

# ------------------------------------------------------------- fixtures on 12.2

stage_fixtures() {
  mkdir -p "$OUT" "$SQLD" "$SOCK12" "$TS12"
  if [ ! -f "$DATA12/PG_VERSION" ]; then
    note "initdb 12.2"
    "$BIN12/initdb" -D "$DATA12" --locale=C --encoding=UTF8 > "$OUT/initdb12.log" 2>&1 \
      || die "initdb 12 failed"
    # autovacuum and fsync are PGC_SIGHUP; set before first start so the whole
    # run sees them.  autovacuum off keeps index sizes deterministic, fsync off
    # only makes the fixtures faster.
    cat >> "$DATA12/postgresql.conf" <<'CONF'
autovacuum = off
fsync = off
max_wal_size = 2GB
CONF
  fi
  [ -f "$DATA12/postmaster.pid" ] || start12 || die "12.2 will not start"
  q12 postgres "SELECT /* wiki_dedup_db_exists */ 1 FROM pg_database WHERE datname = '$DB'" \
    | grep -q 1 || "$BIN12/createdb" -h "$SOCK12" -p "$PORT12" "$DB" || die "createdb failed"

  # Every statement below is a disposable fixture.  It creates and drops
  # objects and is not meant for a database anyone cares about.
  cat > "$SQLD/fixtures12.sql" <<SQL
\\set ON_ERROR_STOP on
DROP TABLE IF EXISTS t_main, t_main2, t_churn, t_ts, t_unlog, t_part, t_empty, t_toast CASCADE;

-- The main fixture: one 1,000,000-row table carrying every key shape the
-- deduplication gate has an opinion about.
CREATE TABLE /* wiki_dedup_fixture_main */ t_main (
  id       bigint,
  k10      int,
  k1000    int,
  txt      text,
  st       text,
  u        uuid,
  num      numeric,
  flt      float8,
  js       jsonb,
  arr      int[]
);
INSERT /* wiki_dedup_fixture_main_rows */ INTO t_main
SELECT i,
       i % 10,
       i % 1000,
       'v' || (i % 100),
       CASE WHEN i % 10 = 0 THEN 'open' ELSE 'closed' END,
       md5(i::text)::uuid,
       ((i % 1000)::numeric) / 10,
       (i % 1000)::float8,
       jsonb_build_object('k', i % 100),
       ARRAY[i % 10, i % 100]
FROM generate_series(1, $ROWS) i;

CREATE UNIQUE INDEX /* wiki_dedup_fixture_idx */ i_uniq         ON t_main (id);
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_dup10        ON t_main (k10);
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_dup1000      ON t_main (k1000);
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_txt          ON t_main (txt);
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_txt_pattern  ON t_main (txt text_pattern_ops);
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_expr         ON t_main (lower(txt));
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_multi        ON t_main (k10, k1000);
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_partial      ON t_main (k10) WHERE st = 'open';
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_uuid         ON t_main (u);
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_num          ON t_main (num);
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_flt          ON t_main (flt);
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_js           ON t_main (js);
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_arr          ON t_main (arr);
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_multimixed   ON t_main (k10, num);
CREATE INDEX        /* wiki_dedup_fixture_idx */ i_inc          ON t_main (k10) INCLUDE (txt);

-- A second copy of the same shape, reserved for the bloat-versus-
-- deduplication split.  It is never rebuilt, so it can be updated instead.
CREATE TABLE /* wiki_dedup_fixture_main2 */ t_main2 (id bigint, k10 int, pad text);
INSERT /* wiki_dedup_fixture_main2_rows */ INTO t_main2
SELECT i, i % 10, repeat('p', 20) FROM generate_series(1, $ROWS) i;
CREATE INDEX /* wiki_dedup_fixture_idx */ i_dup10b ON t_main2 (k10);

-- 20 distinct values, to be churned after the upgrade.
CREATE TABLE /* wiki_dedup_fixture_churn */ t_churn (k int);
INSERT /* wiki_dedup_fixture_churn_rows */ INTO t_churn
SELECT i % 20 FROM generate_series(1, $CHURN_ROWS) i;
CREATE INDEX /* wiki_dedup_fixture_idx */ i_churn ON t_churn (k);

CREATE TABLE /* wiki_dedup_fixture_ts_table */ t_ts (k int);
INSERT /* wiki_dedup_fixture_ts_rows */ INTO t_ts SELECT i % 50 FROM generate_series(1, 200000) i;
CREATE INDEX /* wiki_dedup_fixture_idx */ i_ts ON t_ts (k) TABLESPACE ts_dedup;

-- An unlogged table.
CREATE UNLOGGED TABLE /* wiki_dedup_fixture_unlogged */ t_unlog (k int);
INSERT /* wiki_dedup_fixture_unlogged_rows */ INTO t_unlog SELECT i % 50 FROM generate_series(1, 200000) i;
CREATE INDEX /* wiki_dedup_fixture_idx */ i_u_k ON t_unlog (k);

-- A declaratively partitioned table indexed through its parent.
CREATE TABLE /* wiki_dedup_fixture_part */ t_part (k int, v int) PARTITION BY RANGE (k);
CREATE TABLE /* wiki_dedup_fixture_part */ p_main_1 PARTITION OF t_part FOR VALUES FROM (0) TO (50);
CREATE TABLE /* wiki_dedup_fixture_part */ p_main_2 PARTITION OF t_part FOR VALUES FROM (50) TO (100);
INSERT /* wiki_dedup_fixture_part_rows */ INTO t_part SELECT i % 100, i FROM generate_series(1, 200000) i;
CREATE INDEX /* wiki_dedup_fixture_idx */ ON t_part (k);

-- An empty table, so the empty-build path is covered too.
CREATE TABLE /* wiki_dedup_fixture_empty */ t_empty (k int);
CREATE INDEX /* wiki_dedup_fixture_idx */ i_empty ON t_empty (k);

-- A TOAST table, whose index is carried over with its table.
CREATE TABLE /* wiki_dedup_fixture_toast */ t_toast (id int, big text);
INSERT /* wiki_dedup_fixture_toast_rows */ INTO t_toast
SELECT i, repeat('t', 20000) FROM generate_series(1, 50) i;

-- pg_largeobject, the one system catalog whose files pg_upgrade transfers.
SELECT /* wiki_dedup_fixture_lo */ lo_from_bytea(0, repeat('L', 4096)::bytea);
SQL
  # CREATE TABLESPACE cannot run inside a transaction block, so it is issued
  # on its own, and only when the cluster does not have it yet.
  q12 "$DB" "SELECT /* wiki_dedup_ts_exists */ 1 FROM pg_tablespace WHERE spcname = 'ts_dedup'" \
    | grep -q 1 \
    || q12 "$DB" "CREATE TABLESPACE /* wiki_dedup_fixture_ts */ ts_dedup LOCATION '$TS12'" > /dev/null \
    || die "CREATE TABLESPACE failed; is $TS12 empty?"
  note "building the 12.2 fixtures (this creates and drops objects; disposable)"
  p12 "$DB" -f "$SQLD/fixtures12.sql" > "$OUT/fixtures12.txt" 2>&1 || die "fixtures failed, see $OUT/fixtures12.txt"

  # The 12.2 side of the story: the index inventory, the metapage bytes as 12.2
  # left them, and the file digests pg_upgrade has to preserve.  Only the
  # indexes pg_upgrade transfers are listed: the user ones, their TOAST
  # indexes, and pg_largeobject's.  initdb builds every other catalog index in
  # the new cluster, so comparing those digests would compare nothing.
  q12 "$DB" "SELECT /* wiki_dedup_census12 */ n.nspname || '.' || c.relname || '|' ||
              c.oid || '|' || c.relfilenode || '|' || pg_relation_size(c.oid) || '|' ||
              coalesce(pg_relation_filepath(c.oid), 'none')
       FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
       JOIN pg_am a ON a.oid = c.relam
       JOIN pg_index i ON i.indexrelid = c.oid
       WHERE c.relkind = 'i' AND a.amname = 'btree' AND c.relpersistence <> 't'
         AND (n.nspname = 'public'
              OR c.relname = 'pg_largeobject_loid_pn_index'
              OR i.indrelid IN (SELECT u.reltoastrelid FROM pg_class u
                                JOIN pg_namespace un ON un.oid = u.relnamespace
                                WHERE u.reltoastrelid <> 0 AND un.nspname = 'public'))
       ORDER BY 1" > "$OUT/census12.txt"
  q12 "$DB" "SELECT /* wiki_dedup_srv12 */ current_setting('server_version') || ' / ' ||
              current_setting('server_version_num')" > "$OUT/serverversion12.txt"
  "$BIN12/pg_controldata" "$DATA12" > "$OUT/controldata12.txt" 2>&1

  note "stopping 12.2 before the upgrade"
  stop12
  # Digest every carried-over index file while both clusters are still cold.
  : > "$OUT/md5_old.txt"
  while IFS='|' read -r name oid relfile size path; do
    [ "$path" = none ] && continue
    if [ -f "$DATA12/$path" ]; then
      printf '%s|%s\n' "$name" "$(md5sum "$DATA12/$path" | cut -d' ' -f1)" >> "$OUT/md5_old.txt"
    elif [ -e "$DATA12/$path" ]; then
      printf '%s|%s\n' "$name" "$(md5sum "$DATA12/$path" | cut -d' ' -f1)" >> "$OUT/md5_old.txt"
    fi
  done < "$OUT/census12.txt"
  note "digested $(wc -l < "$OUT/md5_old.txt") old-cluster index files"
}

# ------------------------------------------------------------------ the upgrade

stage_upgrade() {
  mkdir -p "$OUT" "$SOCK17" "$UPG"
  stop12
  if [ ! -f "$DATA17/PG_VERSION" ]; then
    note "initdb 17.11"
    "$BIN17/initdb" -D "$DATA17" --locale=C --encoding=UTF8 > "$OUT/initdb17.log" 2>&1 \
      || die "initdb 17 failed"
    cat >> "$DATA17/postgresql.conf" <<'CONF'
autovacuum = off
fsync = off
max_wal_size = 2GB
CONF
  fi
  stop17
  note "pg_upgrade --copy, 12.2 -> 17.11"
  ( cd "$UPG" && "$BIN17/pg_upgrade" \
      -b "$BIN12" -B "$BIN17" -d "$DATA12" -D "$DATA17" \
      -p "$PORT12" -P "$PORT17" --copy > "$OUT/upgrade.log" 2>&1 ) \
    || { tail -40 "$OUT/upgrade.log" >&2; die "pg_upgrade failed, see $OUT/upgrade.log"; }
  ( cd "$UPG" && ls -1 ) > "$OUT/upgrade_artifacts.txt"
  # Both control files as the upgrade left them, before either cluster is
  # started again: this is where the XID and OID counters can be compared.
  "$BIN12/pg_controldata" "$DATA12" > "$OUT/controldata12_after.txt" 2>&1
  "$BIN17/pg_controldata" "$DATA17" > "$OUT/controldata17_after.txt" 2>&1
  # What the run says about rebuilding anything.
  { printf 'scripts and files left in the working directory:\n'; cat "$OUT/upgrade_artifacts.txt"
    printf '\nmatches for reindex/rebuild/deduplicat in the whole output tree:\n'
    grep -Rail -e reindex -e rebuild -e deduplicat "$OUT/upgrade.log" "$UPG" 2>/dev/null || printf '(none)\n'
    printf '\nthe completion banner:\n'; tail -12 "$OUT/upgrade.log"
  } > "$OUT/upgrade_says.txt"
  cat "$OUT/upgrade_says.txt" >&2
}

# --------------------------------------------------- struct offsets, per build

stage_offsets() {
  mkdir -p "$CD" "$OUT"
  # The v17 field set, including btm_allequalimage.
  cat > "$CD/offsets17.c" <<'C'
#include "postgres.h"
#include "access/nbtree.h"
#include "storage/bufpage.h"
/* postgres.h routes printf through pg_printf, which lives in libpgport; this
 * program links against nothing, so put the C library's printf back. */
#undef printf
#include <stdio.h>
#define SHOW(f) printf("%-33s %3zu %3zu\n", #f, (size_t) offsetof(BTMetaPageData, f), \
                       (size_t) (MAXALIGN(SizeOfPageHeaderData) + offsetof(BTMetaPageData, f)))
int
main(void)
{
    printf("MAXIMUM_ALIGNOF          %d\n", MAXIMUM_ALIGNOF);
    printf("BLCKSZ                   %d\n", BLCKSZ);
    printf("SizeOfPageHeaderData     %zu\n", (size_t) SizeOfPageHeaderData);
    printf("MAXALIGN(header)         %zu\n", (size_t) MAXALIGN(SizeOfPageHeaderData));
    printf("sizeof(BTMetaPageData)   %zu\n", sizeof(BTMetaPageData));
    printf("pd_lower a v17 build sets %zu\n",
           (size_t) (MAXALIGN(SizeOfPageHeaderData) + sizeof(BTMetaPageData)));
    printf("%-33s %3s %3s\n", "field", "off", "abs");
    SHOW(btm_magic); SHOW(btm_version); SHOW(btm_root); SHOW(btm_level);
    SHOW(btm_fastroot); SHOW(btm_fastlevel);
    SHOW(btm_last_cleanup_num_delpages);
    SHOW(btm_last_cleanup_num_heap_tuples);
    SHOW(btm_allequalimage);
    return 0;
}
C
  # The v12 field set: no btm_allequalimage, no btm_last_cleanup_num_delpages.
  cat > "$CD/offsets12.c" <<'C'
#include "postgres.h"
#include "access/nbtree.h"
#include "storage/bufpage.h"
#undef printf
#include <stdio.h>
#define SHOW(f) printf("%-33s %3zu %3zu\n", #f, (size_t) offsetof(BTMetaPageData, f), \
                       (size_t) (MAXALIGN(SizeOfPageHeaderData) + offsetof(BTMetaPageData, f)))
int
main(void)
{
    printf("MAXIMUM_ALIGNOF          %d\n", MAXIMUM_ALIGNOF);
    printf("SizeOfPageHeaderData     %zu\n", (size_t) SizeOfPageHeaderData);
    printf("sizeof(BTMetaPageData)   %zu\n", sizeof(BTMetaPageData));
    printf("pd_lower a v12 build sets %zu\n",
           (size_t) (MAXALIGN(SizeOfPageHeaderData) + sizeof(BTMetaPageData)));
    printf("%-33s %3s %3s\n", "field", "off", "abs");
    SHOW(btm_magic); SHOW(btm_version); SHOW(btm_root); SHOW(btm_level);
    SHOW(btm_fastroot); SHOW(btm_fastlevel);
    SHOW(btm_oldest_btpo_xact);
    SHOW(btm_last_cleanup_num_heap_tuples);
    return 0;
}
C
  local inc17 inc12
  inc17="$("$BIN17/pg_config" --includedir-server)"
  inc12="$("$BIN12/pg_config" --includedir-server)"
  {
    printf '== v17 field set against the 17.11 headers ==\n'
    if cc -I"$inc17" -o "$CD/offsets17" "$CD/offsets17.c" 2> "$CD/offsets17.err"; then
      "$CD/offsets17"
    else
      printf 'compile FAILED:\n'; head -5 "$CD/offsets17.err"
    fi
    printf '\n== v17 field set against the 12.2 headers ==\n'
    if cc -I"$inc12" -o "$CD/offsets17on12" "$CD/offsets17.c" 2> "$CD/offsets17on12.err"; then
      "$CD/offsets17on12"
    else
      printf 'compile FAILED, as expected:\n'
      grep -E 'error:' "$CD/offsets17on12.err" | head -4
    fi
    printf '\n== v12 field set against the 12.2 headers ==\n'
    if cc -I"$inc12" -o "$CD/offsets12" "$CD/offsets12.c" 2> "$CD/offsets12.err"; then
      "$CD/offsets12"
    else
      printf 'compile FAILED:\n'; head -5 "$CD/offsets12.err"
    fi
  } > "$OUT/offsets.txt" 2>&1
  cat "$OUT/offsets.txt" >&2
}

# ------------------------------------------------------- the probe, on 17.11

# The filed core-SQL check, one copy, used by every stage that needs a verdict.
write_probe_sql() {
  mkdir -p "$SQLD"
  cat > "$SQLD/check1.sql" <<'SQL'
SELECT /* wiki_dedup_rebuild_check */
       n.nspname,
       c.relname,
       pg_size_pretty(pg_relation_size(c.oid))        AS index_size,
       m.allequalimage                                AS deduplicating_now,
       CASE
         WHEN m.allequalimage IS NULL
           THEN 'unknown: could not read metapage'
         WHEN m.allequalimage AND NOT e.equalimage_ok
           THEN 'rebuild for correctness: metapage says safe, catalogs disagree'
         WHEN m.allequalimage
           THEN 'no rebuild needed'
         WHEN i.indnatts <> i.indnkeyatts
           THEN 'no gain: INCLUDE index can never deduplicate'
         WHEN NOT e.equalimage_ok
           THEN 'no gain: key type or collation is not deduplication-safe'
         WHEN NOT coalesce(o.deduplicate_items, true)
           THEN 'no gain while deduplicate_items = off'
         WHEN i.indisunique
           THEN 'rebuild: unique index, no immediate size win'
         ELSE 'rebuild: REINDEX INDEX CONCURRENTLY enables deduplication'
       END                                            AS verdict
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_am a ON a.oid = c.relam
JOIN pg_index i ON i.indexrelid = c.oid
CROSS JOIN LATERAL (
       SELECT CASE WHEN octet_length(z.meta) = 72
                   THEN get_byte(z.meta, 64) <> 0 END AS allequalimage
       FROM (SELECT pg_read_binary_file(pg_relation_filepath(c.oid), 0, 72, true) AS meta) z
     ) m
CROSS JOIN LATERAL (
       SELECT NOT EXISTS (
                SELECT 1
                FROM generate_series(0, i.indnkeyatts - 1) AS k
                LEFT JOIN pg_opclass oc ON oc.oid = i.indclass[k]
                LEFT JOIN pg_amproc ap ON ap.amprocfamily = oc.opcfamily
                                      AND ap.amproclefttype = oc.opcintype
                                      AND ap.amprocrighttype = oc.opcintype
                                      AND ap.amprocnum = 4
                LEFT JOIN pg_collation col ON col.oid = i.indcollation[k]
                WHERE ap.amproc IS NULL
                   OR (ap.amproc = 'btvarstrequalimage'::regproc
                       AND NOT col.collisdeterministic)
              ) AS equalimage_ok
     ) e
LEFT JOIN LATERAL (
       SELECT lower(split_part(opt, '=', 2))::bool AS deduplicate_items
       FROM unnest(c.reloptions) AS opt
       WHERE split_part(opt, '=', 1) = 'deduplicate_items'
     ) o ON true
WHERE a.amname = 'btree'
  AND c.relkind = 'i'
  AND c.relpersistence <> 't'
ORDER BY (m.allequalimage IS NOT TRUE) DESC, pg_relation_size(c.oid) DESC;
SQL
  # The same probe reduced to one row per index, for censuses and cross-checks.
  cat > "$SQLD/meta.sql" <<'SQL'
CREATE OR REPLACE VIEW wiki_dedup_meta AS
SELECT n.nspname, c.relname, c.oid AS indexrelid, c.relfilenode,
       pg_relation_size(c.oid) AS bytes,
       (get_byte(z.meta, 13) * 256) + get_byte(z.meta, 12)              AS pd_lower,
       (get_byte(z.meta, 31)::bigint << 24) + (get_byte(z.meta, 30) << 16)
         + (get_byte(z.meta, 29) << 8) + get_byte(z.meta, 28)           AS btm_version,
       get_byte(z.meta, 64) <> 0                                        AS allequalimage,
       (get_byte(z.meta, 51)::bigint << 24) + (get_byte(z.meta, 50) << 16)
         + (get_byte(z.meta, 49) << 8) + get_byte(z.meta, 48)           AS num_delpages
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_am a ON a.oid = c.relam
CROSS JOIN LATERAL (SELECT pg_read_binary_file(pg_relation_filepath(c.oid), 0, 72, true) AS meta) z
WHERE a.amname = 'btree' AND c.relkind = 'i' AND c.relpersistence <> 't'
  AND octet_length(z.meta) = 72;
SQL
}

stage_probe() {
  mkdir -p "$OUT"; write_probe_sql
  [ -f "$DATA17/postmaster.pid" ] || start17 || die "17.11 will not start"
  q17 "$DB" "SELECT /* wiki_dedup_platform */ 'block_size=' || current_setting('block_size') ||
             ' server=' || current_setting('server_version')" > "$OUT/platform.txt"
  q17 "$DB" "SELECT /* wiki_dedup_control_init */ 'max_data_alignment=' || max_data_alignment ||
             ' database_block_size=' || database_block_size FROM pg_control_init()" >> "$OUT/platform.txt"
  printf 'uname: %s\n' "$(uname -sm)" >> "$OUT/platform.txt"

  # Statistics as pg_upgrade left them, before anything analyzes.  The scope is
  # the carried-over set the 12.2 census named, not every index in the cluster.
  q17 "$DB" "SELECT /* wiki_dedup_stats_after_upgrade */
               count(*) || ' carried-over indexes, ' ||
               count(*) FILTER (WHERE c.relpages = 0) || ' with relpages = 0, ' ||
               count(*) FILTER (WHERE c.reltuples = 0) || ' with reltuples = 0, ' ||
               count(*) FILTER (WHERE c.reltuples = -1) || ' with reltuples = -1 (' ||
               coalesce(string_agg(c.relname, ', ') FILTER (WHERE c.reltuples = -1), 'none') || ')'
             FROM pg_class c JOIN pg_am a ON a.oid = c.relam
             JOIN pg_namespace n ON n.oid = c.relnamespace
             JOIN pg_index i ON i.indexrelid = c.oid
             WHERE c.relkind = 'i' AND a.amname = 'btree' AND c.relpersistence <> 't'
               AND (n.nspname = 'public'
                    OR c.relname = 'pg_largeobject_loid_pn_index'
                    OR i.indrelid IN (SELECT u.reltoastrelid FROM pg_class u
                                      JOIN pg_namespace un ON un.oid = u.relnamespace
                                      WHERE u.reltoastrelid <> 0 AND un.nspname = 'public'))" \
    > "$OUT/stats_zero.txt"

  p17 "$DB" -f "$SQLD/meta.sql" > /dev/null 2>&1 || die "meta view failed"
  p17 "$DB" -f "$SQLD/check1.sql" > "$OUT/check1_before.txt" 2>&1 || die "check 1 failed"

  # The census the page's tables are built from.
  q17 "$DB" "SELECT /* wiki_dedup_census */ nspname || '.' || relname || '|' || indexrelid || '|' ||
               relfilenode || '|' || bytes || '|' || pd_lower || '|' || btm_version || '|' ||
               allequalimage || '|' || num_delpages
             FROM wiki_dedup_meta ORDER BY 1" > "$OUT/census17_before.txt"
  q17 "$DB" "SELECT /* wiki_dedup_census_summary */ 'public: ' ||
               count(*) || ' indexes, pd_lower=64 on ' || count(*) FILTER (WHERE pd_lower = 64) ||
               ', version 4 on ' || count(*) FILTER (WHERE btm_version = 4) ||
               ', flag true on ' || count(*) FILTER (WHERE allequalimage) ||
               ', num_delpages<>0 on ' || count(*) FILTER (WHERE num_delpages <> 0)
             FROM wiki_dedup_meta WHERE nspname = 'public'" > "$OUT/census_summary.txt"
  q17 "$DB" "SELECT /* wiki_dedup_catalog_census */ 'pg_catalog: ' || count(*) ||
               ' btree indexes, flag true on ' || count(*) FILTER (WHERE allequalimage) ||
               ', false on ' || count(*) FILTER (WHERE NOT allequalimage) ||
               ' (' || coalesce(string_agg(relname, ', ') FILTER (WHERE NOT allequalimage), '-') || ')'
             FROM wiki_dedup_meta WHERE nspname = 'pg_catalog'" >> "$OUT/census_summary.txt"
  q17 "$DB" "SELECT /* wiki_dedup_toast_census */ 'pg_toast: ' || count(*) ||
               ' btree indexes, flag true on ' || count(*) FILTER (WHERE allequalimage) ||
               ', false on ' || count(*) FILTER (WHERE NOT allequalimage)
             FROM wiki_dedup_meta WHERE nspname = 'pg_toast'" >> "$OUT/census_summary.txt"
  cat "$OUT/census_summary.txt" "$OUT/stats_zero.txt" >&2

  # Check 2, the platform self-test: a freshly built index must read true.
  cat > "$SQLD/selftest.sql" <<'SQL'
CREATE TABLE wiki_dedup_selftest (k int);
INSERT INTO wiki_dedup_selftest VALUES (1), (1);
CREATE INDEX wiki_dedup_selftest_k ON wiki_dedup_selftest (k);

SELECT /* wiki_dedup_probe_selftest */
       octet_length(meta)                              AS meta_bytes,
       (get_byte(meta, 13) * 256) + get_byte(meta, 12) AS pd_lower,
       (get_byte(meta, 31)::bigint << 24) + (get_byte(meta, 30) << 16)
         + (get_byte(meta, 29) << 8) + get_byte(meta, 28) AS btm_version,
       get_byte(meta, 64) <> 0                         AS allequalimage
FROM (SELECT pg_read_binary_file(
               pg_relation_filepath('wiki_dedup_selftest_k'), 0, 72, true) AS meta) z;

DROP TABLE wiki_dedup_selftest;
SQL
  p17 "$DB" -f "$SQLD/selftest.sql" > "$OUT/selftest.txt" 2>&1 || die "self-test failed"
  cat "$OUT/selftest.txt" >&2

  # Ground truth: pageinspect's own reading of the same metapages.
  q17 "$DB" "CREATE EXTENSION /* wiki_dedup_ground_truth */ IF NOT EXISTS pageinspect" >/dev/null
  q17 "$DB" "SELECT /* wiki_dedup_crosscheck */ count(*) || ' rows compared, ' ||
               count(*) FILTER (WHERE m.btm_version = b.version) || ' version matches, ' ||
               count(*) FILTER (WHERE m.allequalimage = b.allequalimage) || ' flag matches, ' ||
               count(*) FILTER (WHERE m.num_delpages = b.last_cleanup_num_delpages) || ' delpage matches'
             FROM wiki_dedup_meta m
             CROSS JOIN LATERAL bt_metap(quote_ident(m.nspname) || '.' || quote_ident(m.relname)) b" \
      > "$OUT/crosscheck_before.txt"
  cat "$OUT/crosscheck_before.txt" >&2

  # The file digests pg_upgrade had to preserve, now on the new cluster.  One
  # census query, then the comparison in the shell.
  q17 "$DB" "SELECT /* wiki_dedup_census17_files */ n.nspname || '.' || c.relname || '|' ||
              c.oid || '|' || c.relfilenode || '|' || pg_relation_size(c.oid) || '|' ||
              coalesce(pg_relation_filepath(c.oid), 'none')
       FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
       JOIN pg_am a ON a.oid = c.relam
       JOIN pg_index i ON i.indexrelid = c.oid
       WHERE c.relkind = 'i' AND a.amname = 'btree' AND c.relpersistence <> 't'
         AND (n.nspname = 'public'
              OR c.relname = 'pg_largeobject_loid_pn_index'
              OR i.indrelid IN (SELECT u.reltoastrelid FROM pg_class u
                                JOIN pg_namespace un ON un.oid = u.relnamespace
                                WHERE u.reltoastrelid <> 0 AND un.nspname = 'public'))
       ORDER BY 1" > "$OUT/census17_files.txt"
  : > "$OUT/md5_new.txt"
  while IFS='|' read -r name oid relfile size path; do
    [ "$path" = none ] && continue
    [ -e "$DATA17/$path" ] || continue
    printf '%s|%s|%s|%s\n' "$name" "$(md5sum "$DATA17/$path" | cut -d' ' -f1)" "$oid" "$relfile" \
      >> "$OUT/md5_new.txt"
  done < "$OUT/census17_files.txt"
  {
    printf 'index|md5 old == md5 new|oid preserved|relfilenode preserved\n'
    same=0; total=0
    while IFS='|' read -r name oldmd5; do
      row="$(grep -F "$name|" "$OUT/md5_new.txt" | head -1)"
      [ -z "$row" ] && { printf '%s|MISSING ON NEW CLUSTER|-|-\n' "$name"; continue; }
      newmd5="$(printf '%s' "$row" | cut -d'|' -f2)"
      newoid="$(printf '%s' "$row" | cut -d'|' -f3)"
      newnode="$(printf '%s' "$row" | cut -d'|' -f4)"
      oldoid="$(grep -F "$name|" "$OUT/census12.txt" | head -1 | cut -d'|' -f2)"
      oldnode="$(grep -F "$name|" "$OUT/census12.txt" | head -1 | cut -d'|' -f3)"
      total=$((total + 1))
      [ "$oldmd5" = "$newmd5" ] && same=$((same + 1))
      printf '%s|%s|%s|%s\n' "$name" \
        "$([ "$oldmd5" = "$newmd5" ] && echo yes || echo NO)" \
        "$([ "$oldoid" = "$newoid" ] && echo yes || echo NO)" \
        "$([ "$oldnode" = "$newnode" ] && echo yes || echo NO)"
    done < "$OUT/md5_old.txt"
    printf 'identical digests: %s of %s\n' "$same" "$total"
  } > "$OUT/md5_compare.txt"
  tail -3 "$OUT/md5_compare.txt" >&2

  # Does an upgraded row look recognisably restored?  Three readings: the
  # transaction that restored it, the counters the two control files carry, and
  # the OID an object created after the upgrade actually gets.
  q17 "$DB" "SELECT /* wiki_dedup_xmin */ 'distinct pg_class xmin values on carried-over indexes: ' ||
               string_agg(DISTINCT c.xmin::text, ', ')
             FROM pg_class c JOIN pg_am a ON a.oid = c.relam
             JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'i' AND a.amname = 'btree' AND n.nspname = 'public'" > "$OUT/xmin.txt"
  q17 "$DB" "CREATE TABLE /* wiki_dedup_oid_probe */ wiki_dedup_oid_probe (x int)" > /dev/null
  q17 "$DB" "SELECT /* wiki_dedup_oid_probe_read */ 'an object created after the upgrade got oid ' ||
               c.oid || ' and relfilenode ' || c.relfilenode
             FROM pg_class c WHERE c.relname = 'wiki_dedup_oid_probe'" >> "$OUT/xmin.txt"
  q17 "$DB" "DROP TABLE /* wiki_dedup_oid_probe_drop */ wiki_dedup_oid_probe" > /dev/null
  q17 "$DB" "SELECT /* wiki_dedup_relfilenode_band */ 'carried-over relfilenodes run ' ||
               min(relfilenode) || ' to ' || max(relfilenode)
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'i' AND n.nspname = 'public'" >> "$OUT/xmin.txt"
  { printf 'old cluster control data, before the upgrade:\n'
    grep -E "NextXID|NextOID" "$OUT/controldata12.txt"
    printf 'new cluster control data, immediately after the upgrade:\n'
    grep -E "NextXID|NextOID" "$OUT/controldata17_after.txt"
    printf 'new cluster control data, now:\n'
    "$BIN17/pg_controldata" "$DATA17" | grep -E "NextXID|NextOID"
    cat "$OUT/xmin.txt"
  } > "$OUT/counters.txt"
  cat "$OUT/counters.txt" >&2

  # Privileges the probe needs.
  cat > "$SQLD/privs.sql" <<'SQL'
DROP ROLE IF EXISTS wiki_dedup_reader;
CREATE ROLE wiki_dedup_reader LOGIN;
GRANT USAGE ON SCHEMA public TO wiki_dedup_reader;
SQL
  p17 "$DB" -f "$SQLD/privs.sql" > /dev/null 2>&1 || die "role setup failed"
  {
    printf '1. plain role calls pg_read_binary_file:\n'
    PGOPTIONS="-c statement_timeout=$STMT_TIMEOUT" "$BIN17/psql" -X -h "$SOCK17" -p "$PORT17" \
      -U wiki_dedup_reader -d "$DB" -At \
      -c "SELECT /* wiki_dedup_priv_probe */ length(pg_read_binary_file(pg_relation_filepath('i_dup10'), 0, 72, true))" 2>&1 | head -2
    printf '2. plain role calls pg_relation_filepath:\n'
    "$BIN17/psql" -X -h "$SOCK17" -p "$PORT17" -U wiki_dedup_reader -d "$DB" -At \
      -c "SELECT /* wiki_dedup_priv_filepath */ pg_relation_filepath('i_dup10')" 2>&1 | head -2
    printf '3. after GRANT pg_read_server_files only:\n'
    q17 "$DB" "GRANT /* wiki_dedup_priv_grant_role */ pg_read_server_files TO wiki_dedup_reader" > /dev/null
    "$BIN17/psql" -X -h "$SOCK17" -p "$PORT17" -U wiki_dedup_reader -d "$DB" -At \
      -c "SELECT /* wiki_dedup_priv_probe */ length(pg_read_binary_file(pg_relation_filepath('i_dup10'), 0, 72, true))" 2>&1 | head -2
    q17 "$DB" "REVOKE /* wiki_dedup_priv_revoke_role */ pg_read_server_files FROM wiki_dedup_reader" > /dev/null
    printf '4. after GRANT EXECUTE on the four-argument form only:\n'
    q17 "$DB" "GRANT /* wiki_dedup_priv_grant_exec */ EXECUTE ON FUNCTION pg_read_binary_file(text,bigint,bigint,boolean) TO wiki_dedup_reader" > /dev/null
    "$BIN17/psql" -X -h "$SOCK17" -p "$PORT17" -U wiki_dedup_reader -d "$DB" -At \
      -c "SELECT /* wiki_dedup_priv_probe */ length(pg_read_binary_file(pg_relation_filepath('i_dup10'), 0, 72, true))" 2>&1 | head -2
    printf '5. same role, three-argument form:\n'
    "$BIN17/psql" -X -h "$SOCK17" -p "$PORT17" -U wiki_dedup_reader -d "$DB" -At \
      -c "SELECT /* wiki_dedup_priv_probe3 */ length(pg_read_binary_file(pg_relation_filepath('i_dup10'), 0, 72))" 2>&1 | head -2
    printf '6. same role, absolute path inside the data directory:\n'
    "$BIN17/psql" -X -h "$SOCK17" -p "$PORT17" -U wiki_dedup_reader -d "$DB" -At \
      -c "SELECT /* wiki_dedup_priv_abs */ length(pg_read_binary_file('$DATA17/' || pg_relation_filepath('i_dup10'), 0, 72, true))" 2>&1 | head -2
    printf '7. same role, a path outside it:\n'
    "$BIN17/psql" -X -h "$SOCK17" -p "$PORT17" -U wiki_dedup_reader -d "$DB" -At \
      -c "SELECT /* wiki_dedup_priv_outside */ length(pg_read_binary_file('/etc/hostname', 0, 8, true))" 2>&1 | head -2
  } > "$OUT/privileges.txt" 2>&1
  cat "$OUT/privileges.txt" >&2

  # Edge cases.
  {
    printf 'partitioned parent index (relkind I) filepath: '
    q17 "$DB" "SELECT /* wiki_dedup_edge_parent */ coalesce(pg_relation_filepath(c.oid)::text, 'NULL') ||
                 ' (relkind ' || c.relkind::text || ')'
               FROM pg_class c WHERE c.relname = 't_part_k_idx'"
    printf 'leaf partition indexes: '
    q17 "$DB" "SELECT /* wiki_dedup_edge_leaves */ string_agg(relname || '=' || allequalimage, ', ' ORDER BY relname)
               FROM wiki_dedup_meta WHERE relname LIKE 'p_main_%'"
    printf 'unlogged index i_u_k: '
    q17 "$DB" "SELECT /* wiki_dedup_edge_unlogged */ 'flag=' || allequalimage || ' pd_lower=' || pd_lower FROM wiki_dedup_meta WHERE relname = 'i_u_k'"
    printf 'tablespace index i_ts: path '
    q17 "$DB" "SELECT /* wiki_dedup_edge_ts */ pg_relation_filepath('i_ts') || ' flag=' || (SELECT allequalimage FROM wiki_dedup_meta WHERE relname = 'i_ts')"
    printf 'temporary index, own session: '
    p17 "$DB" -At -c "CREATE TEMP TABLE /* wiki_dedup_edge_temp */ wdt (k int);
        CREATE INDEX wdt_k ON wdt (k);
        SELECT pg_relation_filepath('wdt_k') || ' byte64=' ||
               get_byte(pg_read_binary_file(pg_relation_filepath('wdt_k'), 0, 72, true), 64);" 2>&1 | tail -1
    printf 'TOAST indexes reading false: '
    q17 "$DB" "SELECT /* wiki_dedup_edge_toast */ count(*) || ' of ' ||
                 (SELECT count(*) FROM wiki_dedup_meta WHERE nspname = 'pg_toast') || ' (' ||
                 string_agg(relname, ', ' ORDER BY relname) || ')'
               FROM wiki_dedup_meta WHERE nspname = 'pg_toast' AND NOT allequalimage"
    printf 'pg_largeobject index: '
    q17 "$DB" "SELECT /* wiki_dedup_edge_lo */ relname || ' flag=' || allequalimage || ' pd_lower=' || pd_lower
               FROM wiki_dedup_meta WHERE relname = 'pg_largeobject_loid_pn_index'"
    printf 'pg_enum_typid_sortorder_index: '
    q17 "$DB" "SELECT /* wiki_dedup_edge_enum */ relname || ' flag=' || allequalimage || ' pd_lower=' || pd_lower
               FROM wiki_dedup_meta WHERE relname = 'pg_enum_typid_sortorder_index'"
    printf 'short read guarded by octet_length: '
    q17 "$DB" "SELECT /* wiki_dedup_edge_short */ coalesce((CASE WHEN octet_length(z.meta) = 72 THEN get_byte(z.meta, 64) END)::text, 'NULL, no error')
               FROM (SELECT pg_read_binary_file(pg_relation_filepath('i_dup10'), 0, 40, true) AS meta) z"
    printf 'unguarded short read: '
    q17 "$DB" "SELECT /* wiki_dedup_edge_short_raw */ get_byte(pg_read_binary_file(pg_relation_filepath('i_dup10'), 0, 40, true), 64)" 2>&1 | head -1
  } > "$OUT/edges.txt" 2>&1
  cat "$OUT/edges.txt" >&2
}

# ------------------------------------------- the gate against DEBUG1 verdicts

stage_gate() {
  mkdir -p "$OUT"; write_probe_sql
  [ -f "$DATA17/postmaster.pid" ] || start17 || die "17.11 will not start"
  q17 postgres "SELECT /* wiki_dedup_gatedb_exists */ 1 FROM pg_database WHERE datname = 'gate'" \
    | grep -q 1 || "$BIN17/createdb" -h "$SOCK17" -p "$PORT17" gate
  cat > "$SQLD/gate.sql" <<'SQL'
SET client_min_messages = debug1;
DROP TABLE IF EXISTS g_main, g_nd CASCADE;
DROP COLLATION IF EXISTS nd_icu;
DROP COLLATION IF EXISTS det_icu;

CREATE TABLE /* wiki_dedup_gate_fixture */ g_main (
  k int, txt text, u uuid, num numeric, flt float8, js jsonb, arr int[]);
INSERT /* wiki_dedup_gate_rows */ INTO g_main
SELECT i % 10, 'v' || (i % 10), md5(i::text)::uuid, (i % 10)::numeric / 10,
       (i % 10)::float8, jsonb_build_object('k', i % 10), ARRAY[i % 10]
FROM generate_series(1, 1000) i;

CREATE INDEX        /* wiki_dedup_gate_idx */ g_dup10       ON g_main (k);
CREATE INDEX        /* wiki_dedup_gate_idx */ g_txt         ON g_main (txt);
CREATE INDEX        /* wiki_dedup_gate_idx */ g_txt_pattern ON g_main (txt text_pattern_ops);
CREATE INDEX        /* wiki_dedup_gate_idx */ g_expr        ON g_main (lower(txt));
CREATE INDEX        /* wiki_dedup_gate_idx */ g_uuid        ON g_main (u);
CREATE UNIQUE INDEX /* wiki_dedup_gate_idx */ g_uniq        ON g_main (txt, k, u);
CREATE INDEX        /* wiki_dedup_gate_idx */ g_num         ON g_main (num);
CREATE INDEX        /* wiki_dedup_gate_idx */ g_flt         ON g_main (flt);
CREATE INDEX        /* wiki_dedup_gate_idx */ g_js          ON g_main (js);
CREATE INDEX        /* wiki_dedup_gate_idx */ g_arr         ON g_main (arr);
CREATE INDEX        /* wiki_dedup_gate_idx */ g_multimixed  ON g_main (k, num);
CREATE INDEX        /* wiki_dedup_gate_idx */ g_inc         ON g_main (k) INCLUDE (txt);
CREATE INDEX        /* wiki_dedup_gate_idx */ g_partial     ON g_main (k) WHERE k = 1;
CREATE INDEX        /* wiki_dedup_gate_idx */ g_c           ON g_main (txt COLLATE "C");

-- Nondeterministic and deterministic ICU collations.
CREATE COLLATION /* wiki_dedup_gate_coll */ nd_icu  (provider = icu, locale = 'und-u-ks-level2', deterministic = false);
CREATE COLLATION /* wiki_dedup_gate_coll */ det_icu (provider = icu, locale = 'und');
CREATE TABLE /* wiki_dedup_gate_ndfixture */ g_nd (a text COLLATE nd_icu, b text COLLATE det_icu);
INSERT /* wiki_dedup_gate_ndrows */ INTO g_nd SELECT 'x' || (i % 5), 'y' || (i % 5) FROM generate_series(1, 200) i;
CREATE INDEX /* wiki_dedup_gate_idx */ g_nd_a     ON g_nd (a);
CREATE INDEX /* wiki_dedup_gate_idx */ g_nd_a_off ON g_nd (a) WITH (deduplicate_items = off);
CREATE INDEX /* wiki_dedup_gate_idx */ g_det_b    ON g_nd (b);
SQL
  note "building the gate fixtures with client_min_messages = debug1"
  p17 gate -f "$SQLD/gate.sql" > "$OUT/gate_build.txt" 2>&1 || die "gate fixtures failed"
  grep -E 'deduplication' "$OUT/gate_build.txt" | sed -E 's/^DEBUG:  //' > "$OUT/gate_debug1.txt"

  # The engine's verdict per index, from the DEBUG1 lines, against the gate.
  p17 gate -f "$SQLD/meta.sql" > /dev/null 2>&1
  q17 gate "SELECT /* wiki_dedup_gate_score */ c.relname || '|' ||
              (SELECT allequalimage FROM wiki_dedup_meta w WHERE w.relname = c.relname) || '|' ||
              e.equalimage_ok || '|' || (i.indnatts <> i.indnkeyatts) || '|' ||
              (e.equalimage_ok AND i.indnatts = i.indnkeyatts)
            FROM pg_class c
            JOIN pg_index i ON i.indexrelid = c.oid
            JOIN pg_am a ON a.oid = c.relam
            CROSS JOIN LATERAL (
              SELECT NOT EXISTS (
                SELECT 1 FROM generate_series(0, i.indnkeyatts - 1) AS k
                LEFT JOIN pg_opclass oc ON oc.oid = i.indclass[k]
                LEFT JOIN pg_amproc ap ON ap.amprocfamily = oc.opcfamily
                                      AND ap.amproclefttype = oc.opcintype
                                      AND ap.amprocrighttype = oc.opcintype
                                      AND ap.amprocnum = 4
                LEFT JOIN pg_collation col ON col.oid = i.indcollation[k]
                WHERE ap.amproc IS NULL
                   OR (ap.amproc = 'btvarstrequalimage'::regproc AND NOT col.collisdeterministic)
              ) AS equalimage_ok) e
            WHERE a.amname = 'btree' AND c.relkind = 'i' AND c.relname LIKE 'g\\_%'
            ORDER BY 1" > "$OUT/gate_rows.txt"
  {
    printf 'index|metapage flag|gate equalimage_ok|include index|gate verdict|engine DEBUG1\n'
    while IFS='|' read -r name flag ok inc verdict; do
      local said
      said="$(grep -E "index \"$name\" " "$OUT/gate_debug1.txt" | head -1 | sed -E 's/.*(can safely use|cannot use).*/\1/')"
      [ -z "$said" ] && said='(silent)'
      printf '%s|%s|%s|%s|%s|%s\n' "$name" "$flag" "$ok" "$inc" "$verdict" "$said"
    done < "$OUT/gate_rows.txt"
  } > "$OUT/gate_score.txt"
  # Agreement counts: the gate verdict against the metapage the build wrote.
  q17 gate "SELECT /* wiki_dedup_gate_agreement */ count(*) || ' gate fixtures, ' ||
              count(*) FILTER (WHERE w.allequalimage) || ' with the flag set'
            FROM wiki_dedup_meta w WHERE w.relname LIKE 'g\\_%'" >> "$OUT/gate_score.txt"
  cat "$OUT/gate_score.txt" >&2

  # The pattern-opclass refusal, and the DDL-time error text.
  { printf 'text_pattern_ops on a nondeterministic collation:\n'
    q17 gate "CREATE INDEX /* wiki_dedup_gate_pattern */ g_nd_pattern ON g_nd (a text_pattern_ops)" 2>&1 | head -2
  } > "$OUT/gate_pattern.txt"
  cat "$OUT/gate_pattern.txt" >&2
}

# ------------------------------------------------------------ the savings curve

stage_curve() {
  mkdir -p "$OUT"
  [ -f "$DATA17/postmaster.pid" ] || start17 || die "17.11 will not start"
  q17 postgres "SELECT /* wiki_dedup_curvedb_exists */ 1 FROM pg_database WHERE datname = 'curve'" \
    | grep -q 1 || "$BIN17/createdb" -h "$SOCK17" -p "$PORT17" curve
  cat > "$SQLD/curve.sql" <<SQL
DROP TABLE IF EXISTS c_curve;
CREATE TABLE /* wiki_dedup_curve_fixture */ c_curve (
  r1 int, r2 int, r5 int, r20 int, r100 int, r1000 int);
INSERT /* wiki_dedup_curve_rows */ INTO c_curve
SELECT i, i % ($ROWS / 2), i % ($ROWS / 5), i % ($ROWS / 20),
       i % ($ROWS / 100), i % ($ROWS / 1000)
FROM generate_series(1, $ROWS) i;
SQL
  note "building the curve fixture"
  p17 curve -f "$SQLD/curve.sql" > "$OUT/curve_build.txt" 2>&1 || die "curve fixture failed"
  : > "$OUT/curve.txt"
  printf 'rows per key|no-deduplication bytes|deduplicated bytes|saved %%\n' >> "$OUT/curve.txt"
  local r col off on saved
  for r in 1 2 5 20 100 1000; do
    col="r$r"
    q17 curve "CREATE INDEX /* wiki_dedup_curve_off */ c_off ON c_curve ($col) WITH (deduplicate_items = off)" > /dev/null || die "curve build failed"
    off="$(q17 curve "SELECT /* wiki_dedup_curve_size */ pg_relation_size('c_off')")"
    q17 curve "DROP INDEX /* wiki_dedup_curve_drop */ c_off" > /dev/null
    q17 curve "CREATE INDEX /* wiki_dedup_curve_on */ c_on ON c_curve ($col)" > /dev/null || die "curve build failed"
    on="$(q17 curve "SELECT /* wiki_dedup_curve_size */ pg_relation_size('c_on')")"
    q17 curve "DROP INDEX /* wiki_dedup_curve_drop */ c_on" > /dev/null
    saved="$(q17 curve "SELECT /* wiki_dedup_curve_pct */ round((100.0 * ($off - $on) / $off), 1)")"
    printf '%s|%s|%s|%s\n' "$r" "$off" "$on" "$saved" >> "$OUT/curve.txt"
  done
  cat "$OUT/curve.txt" >&2
}

# --------------------------------------- bloat versus deduplication, on t_main2

stage_twins() {
  mkdir -p "$OUT"; write_probe_sql
  [ -f "$DATA17/postmaster.pid" ] || start17 || die "17.11 will not start"
  p17 "$DB" -f "$SQLD/meta.sql" > /dev/null 2>&1
  {
    printf '== pristine: a carried-over index against fresh twins ==\n'
    q17 "$DB" "CREATE INDEX /* wiki_dedup_twin_off */ twin_off ON t_main2 (k10) WITH (deduplicate_items = off)" > /dev/null
    q17 "$DB" "CREATE INDEX /* wiki_dedup_twin_on */ twin_on ON t_main2 (k10)" > /dev/null
    q17 "$DB" "SELECT /* wiki_dedup_twin_sizes */ relname || '|' || pg_relation_size(oid)
               FROM pg_class WHERE relname IN ('i_dup10b', 'twin_off', 'twin_on') ORDER BY 1"
    q17 "$DB" "SELECT /* wiki_dedup_twin_equal */ 'carried-over equals the deduplication-off twin to the byte: ' ||
                 (pg_relation_size('i_dup10b') = pg_relation_size('twin_off'))"
    q17 "$DB" "DROP INDEX /* wiki_dedup_twin_drop */ twin_off, twin_on" > /dev/null

    printf '\n== after one rewrite of every row ==\n'
    q17 "$DB" "UPDATE /* wiki_dedup_twin_rewrite */ t_main2 SET pad = pad" > /dev/null
    q17 "$DB" "VACUUM /* wiki_dedup_twin_vacuum */ (ANALYZE) t_main2" > /dev/null
    q17 "$DB" "CREATE INDEX /* wiki_dedup_twin_off */ twin_off ON t_main2 (k10) WITH (deduplicate_items = off)" > /dev/null
    q17 "$DB" "CREATE INDEX /* wiki_dedup_twin_on */ twin_on ON t_main2 (k10)" > /dev/null
    q17 "$DB" "SELECT /* wiki_dedup_twin_sizes */ relname || '|' || pg_relation_size(oid)
               FROM pg_class WHERE relname IN ('i_dup10b', 'twin_off', 'twin_on') ORDER BY 1"
    q17 "$DB" "SELECT /* wiki_dedup_twin_split */ 'bloat share ' ||
                 round(100.0 * (pg_relation_size('i_dup10b') - pg_relation_size('twin_off'))
                       / pg_relation_size('i_dup10b'), 1) ||
                 '%, deduplication share of what is left ' ||
                 round(100.0 * (pg_relation_size('twin_off') - pg_relation_size('twin_on'))
                       / pg_relation_size('twin_off'), 1) || '%'"
    q17 "$DB" "DROP INDEX /* wiki_dedup_twin_drop */ twin_off, twin_on" > /dev/null
  } > "$OUT/twins.txt" 2>&1
  cat "$OUT/twins.txt" >&2
}

# -------------------------------------------- the cost of leaving it alone

stage_churn() {
  mkdir -p "$OUT"
  [ -f "$DATA17/postmaster.pid" ] || start17 || die "17.11 will not start"
  {
    q17 "$DB" "CREATE INDEX /* wiki_dedup_churn_new */ i_churn_new ON t_churn (k)" > /dev/null
    printf 'before the insert:\n'
    q17 "$DB" "SELECT /* wiki_dedup_churn_sizes */ relname || '|' || pg_relation_size(oid)
               FROM pg_class WHERE relname IN ('i_churn', 'i_churn_new') ORDER BY 1"
    q17 "$DB" "INSERT /* wiki_dedup_churn_insert */ INTO t_churn
                 SELECT i % 20 FROM generate_series(1, $CHURN_ROWS) i" > /dev/null
    printf 'after %s more duplicate rows:\n' "$CHURN_ROWS"
    q17 "$DB" "SELECT /* wiki_dedup_churn_sizes */ relname || '|' || pg_relation_size(oid)
               FROM pg_class WHERE relname IN ('i_churn', 'i_churn_new') ORDER BY 1"
    q17 "$DB" "SELECT /* wiki_dedup_churn_ratio */ 'carried-over is ' ||
                 round(pg_relation_size('i_churn')::numeric / pg_relation_size('i_churn_new'), 1) ||
                 'x the size of the index built after the upgrade'"
  } > "$OUT/churn.txt" 2>&1
  cat "$OUT/churn.txt" >&2
}

# ---------------------------------------------------------- what a rebuild does

stage_rebuild() {
  mkdir -p "$OUT"; write_probe_sql
  [ -f "$DATA17/postmaster.pid" ] || start17 || die "17.11 will not start"
  p17 "$DB" -f "$SQLD/meta.sql" > /dev/null 2>&1
  # A baseline table, for the relfilenode fallback.
  q17 "$DB" "DROP TABLE /* wiki_dedup_baseline_reset */ IF EXISTS wiki_dedup_baseline" > /dev/null
  q17 "$DB" "CREATE TABLE /* wiki_dedup_baseline */ wiki_dedup_baseline AS
               SELECT c.oid AS indexrelid, c.relnamespace, c.relname, c.relfilenode,
                      now() AS captured
               FROM pg_class c JOIN pg_am a ON a.oid = c.relam
               WHERE c.relkind = 'i' AND a.amname = 'btree'" > /dev/null

  # Only the indexes of t_main, t_churn and t_empty are rebuilt.  i_ts, i_u_k
  # and the two partition indexes are deliberately left alone, so the
  # flag-setting matrix below still has carried-over indexes to work on, and
  # t_main2's i_dup10b is left alone for the bloat/deduplication split.
  local list
  list="$(q17 "$DB" "SELECT /* wiki_dedup_rebuild_list */ string_agg(w.relname, ' ' ORDER BY w.relname)
                     FROM wiki_dedup_meta w
                     JOIN pg_index i ON i.indexrelid = w.indexrelid
                     WHERE w.nspname = 'public' AND NOT w.allequalimage
                       AND i.indrelid IN ('t_main'::regclass, 't_churn'::regclass, 't_empty'::regclass)")"
  : > "$OUT/rebuild.txt"
  printf 'index|before bytes|after bytes|change %%|flag before|flag after|DEBUG1\n' >> "$OUT/rebuild.txt"
  local idx before after pct flagb flaga said
  for idx in $list; do
    before="$(q17 "$DB" "SELECT /* wiki_dedup_rebuild_before */ pg_relation_size('$idx')")"
    flagb="$(q17 "$DB" "SELECT /* wiki_dedup_rebuild_flag */ allequalimage FROM wiki_dedup_meta WHERE relname = '$idx'")"
    said="$(PGOPTIONS="-c statement_timeout=$STMT_TIMEOUT -c lock_timeout=$LOCK_TIMEOUT -c client_min_messages=debug1" \
      "$BIN17/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK17" -p "$PORT17" -d "$DB" -At \
      -c "REINDEX /* wiki_dedup_rebuild */ INDEX CONCURRENTLY public.$idx" 2>&1 \
      | grep -E 'deduplication' | head -1 | sed -E 's/.*(can safely use deduplication|cannot use deduplication).*/\1/')"
    [ -z "$said" ] && said='(silent)'
    after="$(q17 "$DB" "SELECT /* wiki_dedup_rebuild_after */ pg_relation_size('$idx')")"
    flaga="$(q17 "$DB" "SELECT /* wiki_dedup_rebuild_flag */ allequalimage FROM wiki_dedup_meta WHERE relname = '$idx'")"
    pct="$(q17 "$DB" "SELECT /* wiki_dedup_rebuild_pct */ round((100.0 * ($after - $before) / $before), 2)")"
    printf '%s|%s|%s|%s|%s|%s|%s\n' "$idx" "$before" "$after" "$pct" "$flagb" "$flaga" "$said" >> "$OUT/rebuild.txt"
  done
  cat "$OUT/rebuild.txt" >&2

  # The deduplicate_items trap: the flag is set, the size is not reclaimed.
  {
    printf 'i_dup1000 rebuilt under deduplicate_items = off:\n'
    q17 "$DB" "ALTER INDEX /* wiki_dedup_trap_off */ i_dup1000 SET (deduplicate_items = off)" > /dev/null
    q17 "$DB" "SELECT /* wiki_dedup_trap_before */ 'size before ' || pg_relation_size('i_dup1000')"
    PGOPTIONS="-c statement_timeout=$STMT_TIMEOUT -c client_min_messages=debug1" \
      "$BIN17/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK17" -p "$PORT17" -d "$DB" -At \
      -c "REINDEX /* wiki_dedup_trap_rebuild */ INDEX CONCURRENTLY public.i_dup1000" 2>&1 | grep -E 'dedup' | head -1
    q17 "$DB" "SELECT /* wiki_dedup_trap_after */ 'size after ' || pg_relation_size('i_dup1000') ||
                 ', flag ' || (SELECT allequalimage FROM wiki_dedup_meta WHERE relname = 'i_dup1000') ||
                 ', reloptions ' || coalesce((SELECT reloptions::text FROM pg_class WHERE relname = 'i_dup1000'), '-')"
    q17 "$DB" "ALTER INDEX /* wiki_dedup_trap_reset */ i_dup1000 RESET (deduplicate_items)" > /dev/null
    q17 "$DB" "SELECT /* wiki_dedup_trap_final */ 'rebuilt again with the default: '"
    q17 "$DB" "REINDEX /* wiki_dedup_trap_rebuild2 */ INDEX CONCURRENTLY public.i_dup1000" > /dev/null
    q17 "$DB" "SELECT /* wiki_dedup_trap_final_size */ pg_relation_size('i_dup1000')"
  } > "$OUT/trap.txt" 2>&1
  cat "$OUT/trap.txt" >&2

  # What sets the flag, and what does not.  Each row names the index it used.
  {
    printf 'operation|index|flag before|flag after|pd_lower after|relfilenode before -> after|DEBUG1 lines\n'
    flag_row() { # operation, index, sql, database-wide debug count
      local op="$1" idx="$2" sql="$3" fb fa pl nb na dbg
      fb="$(q17 "$DB" "SELECT /* wiki_dedup_flag_before */ allequalimage FROM wiki_dedup_meta WHERE relname = '$idx'")"
      nb="$(q17 "$DB" "SELECT /* wiki_dedup_node_before */ relfilenode FROM pg_class WHERE relname = '$idx'")"
      dbg="$(PGOPTIONS="-c statement_timeout=$STMT_TIMEOUT -c client_min_messages=debug1" \
        "$BIN17/psql" -X -v ON_ERROR_STOP=1 -h "$SOCK17" -p "$PORT17" -d "$DB" -At -c "$sql" 2>&1 \
        | grep -c 'deduplication')"
      fa="$(q17 "$DB" "SELECT /* wiki_dedup_flag_after */ allequalimage FROM wiki_dedup_meta WHERE relname = '$idx'")"
      pl="$(q17 "$DB" "SELECT /* wiki_dedup_pdlower_after */ pd_lower FROM wiki_dedup_meta WHERE relname = '$idx'")"
      na="$(q17 "$DB" "SELECT /* wiki_dedup_node_after */ relfilenode FROM pg_class WHERE relname = '$idx'")"
      printf '%s|%s|%s|%s|%s|%s -> %s|%s\n' "$op" "$idx" "$fb" "$fa" "$pl" "$nb" "$na" "$dbg"
    }
    flag_row 'VACUUM (INDEX_CLEANUP ON)' i_ts   "VACUUM /* wiki_dedup_flag_vacuum */ (INDEX_CLEANUP ON) t_ts"
    flag_row 'ALTER INDEX SET dedup off' i_ts   "ALTER INDEX /* wiki_dedup_flag_alter */ i_ts SET (deduplicate_items = off)"
    q17 "$DB" "ALTER INDEX /* wiki_dedup_flag_alter_reset */ i_ts RESET (deduplicate_items)" > /dev/null
    flag_row 'REINDEX INDEX'             i_ts   "REINDEX /* wiki_dedup_flag_reindex */ INDEX public.i_ts"
    flag_row 'VACUUM FULL'               i_u_k  "VACUUM /* wiki_dedup_flag_vacuum_full */ FULL t_unlog"
    flag_row 'CLUSTER'                   p_main_1_k_idx "CLUSTER /* wiki_dedup_flag_cluster */ p_main_1 USING p_main_1_k_idx"
  } > "$OUT/flagsets.txt" 2>&1
  cat "$OUT/flagsets.txt" >&2

  # The fallback: which indexes still carry the relfilenode they arrived with.
  # Two joins, because they do not agree.  Joining on the recorded index OID
  # loses every index rebuilt with REINDEX ... CONCURRENTLY, which leaves the
  # name on a different pg_class row; joining on the name keeps them.
  { q17 "$DB" "SELECT /* wiki_dedup_fallback_by_oid */ 'joined on the recorded index oid: ' ||
                 count(*) FILTER (WHERE c.oid IS NOT NULL AND c.relfilenode = b.relfilenode) ||
                 ' unchanged, ' ||
                 count(*) FILTER (WHERE c.oid IS NOT NULL AND c.relfilenode <> b.relfilenode) ||
                 ' moved, ' || count(*) FILTER (WHERE c.oid IS NULL) ||
                 ' recorded oids that no longer exist, of ' || count(*) || ' baseline rows'
               FROM wiki_dedup_baseline b LEFT JOIN pg_class c ON c.oid = b.indexrelid"
    q17 "$DB" "SELECT /* wiki_dedup_fallback_by_name */ 'joined on schema and name: ' ||
                 count(*) FILTER (WHERE c.relfilenode = b.relfilenode) || ' unchanged, ' ||
                 count(*) FILTER (WHERE c.relfilenode <> b.relfilenode) || ' moved, of ' ||
                 count(*) || ' baseline rows'
               FROM wiki_dedup_baseline b
               JOIN pg_class c ON c.relname = b.relname AND c.relnamespace = b.relnamespace"
    q17 "$DB" "SELECT /* wiki_dedup_fallback_moved */ 'movers by name: ' ||
                 coalesce(string_agg(b.relname || ' ' || b.relfilenode || ' -> ' || c.relfilenode ||
                                     CASE WHEN c.oid <> b.indexrelid THEN ' (new pg_class oid '
                                          || c.oid || ')' ELSE '' END, ', ' ORDER BY b.relname), '(none)')
               FROM wiki_dedup_baseline b
               JOIN pg_class c ON c.relname = b.relname AND c.relnamespace = b.relnamespace
               WHERE c.relfilenode <> b.relfilenode OR c.oid <> b.indexrelid"
  } > "$OUT/fallback.txt"
  cat "$OUT/fallback.txt" >&2

  # The probe after the rebuilds, and pageinspect's second opinion again.
  p17 "$DB" -f "$SQLD/check1.sql" > "$OUT/check1_after.txt" 2>&1
  q17 "$DB" "SELECT /* wiki_dedup_crosscheck_after */ count(*) || ' rows compared, ' ||
               count(*) FILTER (WHERE m.btm_version = b.version) || ' version matches, ' ||
               count(*) FILTER (WHERE m.allequalimage = b.allequalimage) || ' flag matches'
             FROM wiki_dedup_meta m
             CROSS JOIN LATERAL bt_metap(quote_ident(m.nspname) || '.' || quote_ident(m.relname)) b
             WHERE m.nspname = 'public'" > "$OUT/crosscheck_after.txt"
  cat "$OUT/crosscheck_after.txt" >&2
}

# ------------------------------------------- statistics and the priority order

stage_stats() {
  mkdir -p "$OUT"
  [ -f "$DATA17/postmaster.pid" ] || start17 || die "17.11 will not start"
  note "vacuumdb --all --analyze-in-stages, as the completion banner recommends"
  "$BIN17/vacuumdb" -h "$SOCK17" -p "$PORT17" --all --analyze-in-stages > "$OUT/vacuumdb.log" 2>&1 \
    || die "vacuumdb failed"
  cat > "$SQLD/priority.sql" <<'SQL'
SELECT /* wiki_dedup_rebuild_priority */
       c.relname,
       pg_size_pretty(pg_relation_size(c.oid)) AS index_size,
       c.reltuples::bigint                     AS index_reltuples,
       round(s.keys::numeric, 0)               AS distinct_keys,
       CASE WHEN s.keys > 0 AND c.reltuples > 0
            THEN round((c.reltuples / s.keys)::numeric, 1) END AS rows_per_key
FROM pg_class c
JOIN pg_index i ON i.indexrelid = c.oid
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN LATERAL (
       SELECT CASE WHEN count(*) = i.indnkeyatts
                   THEN exp(sum(ln(CASE WHEN st.n_distinct > 0 THEN st.n_distinct
                                        ELSE -st.n_distinct * greatest(t.reltuples, 1) END)))
              END AS keys
       FROM generate_series(0, i.indnkeyatts - 1) AS k
       JOIN pg_attribute a2 ON a2.attrelid = i.indrelid AND a2.attnum = i.indkey[k]
       JOIN pg_stats st ON st.schemaname = n.nspname AND st.tablename = t.relname
                       AND st.attname = a2.attname
       WHERE st.n_distinct <> 0
     ) s ON true
WHERE c.relkind = 'i'
  AND n.nspname = 'public'
  AND pg_relation_size(c.oid) > 8192
ORDER BY pg_relation_size(c.oid) DESC;
SQL
  p17 "$DB" -f "$SQLD/priority.sql" > "$OUT/priority.txt" 2>&1
  q17 "$DB" "SELECT /* wiki_dedup_stats_after_analyze */ count(*) || ' carried-over indexes, ' ||
               count(*) FILTER (WHERE relpages = 0) || ' still at relpages = 0'
             FROM pg_class c JOIN pg_am a ON a.oid = c.relam
             JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relkind = 'i' AND a.amname = 'btree' AND n.nspname = 'public'" >> "$OUT/priority.txt"
  # rows_per_key divides a sampled reltuples, so record what the partial index's
  # population exactly is next to what ANALYZE estimated it to be.
  q17 "$DB" "SELECT /* wiki_dedup_partial_exact */ 'i_partial: ' || count(*) ||
               ' indexed rows over ' || count(DISTINCT k10) || ' distinct key value(s) = ' ||
               round(count(*)::numeric / count(DISTINCT k10), 1) || ' rows per key exactly; ' ||
               'ANALYZE estimated reltuples ' ||
               (SELECT reltuples::bigint FROM pg_class WHERE oid = 'i_partial'::regclass) ||
               ', and the n_distinct the priority query divides by is ' ||
               (SELECT n_distinct::bigint FROM pg_stats
                WHERE schemaname = 'public' AND tablename = 't_main' AND attname = 'k10')
             FROM t_main WHERE st = 'open'" >> "$OUT/priority.txt"
  cat "$OUT/priority.txt" >&2
}

stage_summary() {
  {
    printf '=== platform ===\n';            cat "$OUT/platform.txt" 2>/dev/null
    printf '\n=== builds ===\n';            cat "$OUT/version12.txt" "$OUT/version17.txt" 2>/dev/null
    printf '\n=== make check ===\n';        cat "$OUT/checks.txt" 2>/dev/null
    printf '\n=== offsets ===\n';           cat "$OUT/offsets.txt" 2>/dev/null
    printf '\n=== upgrade ===\n';           cat "$OUT/upgrade_says.txt" 2>/dev/null
    printf '\n=== digests ===\n';           tail -3 "$OUT/md5_compare.txt" 2>/dev/null
    printf '\n=== census ===\n';            cat "$OUT/census_summary.txt" "$OUT/stats_zero.txt" 2>/dev/null
    printf '\n=== self-test ===\n';         cat "$OUT/selftest.txt" 2>/dev/null
    printf '\n=== cross-check ===\n';       cat "$OUT/crosscheck_before.txt" "$OUT/crosscheck_after.txt" 2>/dev/null
    printf '\n=== privileges ===\n';        cat "$OUT/privileges.txt" 2>/dev/null
    printf '\n=== edges ===\n';             cat "$OUT/edges.txt" 2>/dev/null
    printf '\n=== gate ===\n';              cat "$OUT/gate_score.txt" "$OUT/gate_pattern.txt" 2>/dev/null
    printf '\n=== rebuild ===\n';           cat "$OUT/rebuild.txt" 2>/dev/null
    printf '\n=== trap ===\n';              cat "$OUT/trap.txt" 2>/dev/null
    printf '\n=== what sets the flag ===\n'; cat "$OUT/flagsets.txt" 2>/dev/null
    printf '\n=== fallback ===\n';          cat "$OUT/fallback.txt" 2>/dev/null
    printf '\n=== curve ===\n';             cat "$OUT/curve.txt" 2>/dev/null
    printf '\n=== twins ===\n';             cat "$OUT/twins.txt" 2>/dev/null
    printf '\n=== churn ===\n';             cat "$OUT/churn.txt" 2>/dev/null
    printf '\n=== statistics ===\n';        cat "$OUT/priority.txt" 2>/dev/null
    printf '\n=== counters ===\n';          cat "$OUT/counters.txt" 2>/dev/null
    printf '\n=== server log errors ===\n'
    # Every ERROR this run provokes is deliberate, so print them rather than a
    # bare count: an unexplained line here invalidates the run.  grep -c prints
    # 0 and exits 1 on no match, so take its output and ignore the status.
    err_count() { local n; n="$(grep -c 'ERROR:' "$1" 2>/dev/null)"; printf '%s' "${n:-0}"; }
    printf 'ERROR lines in server17.log: %s\n' "$(err_count "$OUT/server17.log")"
    grep -o 'ERROR:.*' "$OUT/server17.log" 2>/dev/null | sort | uniq -c | sort -rn
    printf 'ERROR lines in server12.log: %s\n' "$(err_count "$OUT/server12.log")"
  } > "$OUT/summary.txt" 2>&1
  note "summary written to $OUT/summary.txt"
}

stage_clean() {
  note "stopping every server this script started"
  stop17; stop12
  sleep 1
  local left
  left="$(pgrep -af "$SANDBOX" | grep -c postgres)"
  note "postgres processes still matching the sandbox: $left"
  [ -f "$DATA12/postmaster.pid" ] && note "WARNING: $DATA12/postmaster.pid still present"
  [ -f "$DATA17/postmaster.pid" ] && note "WARNING: $DATA17/postmaster.pid still present"
  note "deleting $SANDBOX"
  rm -rf "$SANDBOX"
  note "clean done"
}

DEFAULT_STAGES="build12 build17 check reset fixtures upgrade offsets probe gate curve twins churn rebuild stats summary"
STAGES="${*:-$DEFAULT_STAGES}"
mkdir -p "$OUT" "$SQLD"
for st in $STAGES; do
  note "stage $st"
  case "$st" in
    build12|build17|check|reset|fixtures|upgrade|offsets|probe|gate|curve|twins|churn|rebuild|stats|summary|clean)
      "stage_$st" || die "stage $st failed" ;;
    *) die "unknown stage: $st (known: $DEFAULT_STAGES clean)" ;;
  esac
done
note "done: $STAGES"
```

## Context Reviewed

- Metapage and deduplication implementation: `src/include/access/nbtree.h`,
  `src/backend/access/nbtree/nbtpage.c`, `nbtutils.c`, `nbtsort.c`, `nbtinsert.c`,
  `nbtdedup.c`, `nbtree.c`, `nbtxlog.c`, `nbtsearch.c`.
- Every reader of the flag in the tree, found by grepping the whole checkout for
  `allequalimage`: 15 files, of which `nbtsearch.c` (`_bt_first`,
  `_bt_binsrch_posting`) and `contrib/amcheck/verify_nbtree.c` were not covered
  before the 2026-09-16 review.
- Equal-image support functions and their catalog rows:
  `src/backend/utils/adt/datum.c`, `src/backend/utils/adt/varlena.c`,
  `src/include/catalog/pg_amproc.dat`, `src/include/catalog/pg_opclass.dat`,
  `src/include/catalog/pg_proc.dat`.
- Index creation, rebuild and statistics paths: `src/backend/catalog/index.c`
  (`index_create`, `index_update_stats`, `index_concurrently_swap`,
  `reindex_index`), `src/backend/catalog/heap.c` (`AddNewRelationTuple`,
  `InsertPgClassTuple`), `src/backend/commands/cluster.c`.
- Reloption plumbing: `src/backend/access/common/reloptions.c`.
- Core file/byte functions and their ACLs: `src/backend/utils/adt/genfile.c`,
  `src/backend/utils/adt/dbsize.c`, `src/backend/catalog/system_functions.sql`.
- `pg_upgrade`: `src/bin/pg_upgrade/pg_upgrade.c`, `check.c`, `info.c`,
  `relfilenumber.c`, and `src/bin/pg_dump/pg_dump.c` binary-upgrade support.
- Documentation: `doc/src/sgml/btree.sgml`, `doc/src/sgml/ref/create_index.sgml`,
  `doc/src/sgml/ref/pgupgrade.sgml`, `doc/src/sgml/regress.sgml`.
- Tests: `src/test/regress/sql/opr_sanity.sql` and its expected output, which
  enumerate the B-tree opclasses that cannot deduplicate unconditionally;
  `src/test/regress/sql/btree_index.sql` and its expected output,
  `src/test/regress/expected/collate.icu.utf8.out`,
  `src/bin/pg_amcheck/t/005_opclass_damage.pl`,
  `contrib/pageinspect/expected/btree.out`. Nothing in the tree exercises a
  carried-over metapage: `allequalimage` appears in 15 files, and the only test
  file among them is `contrib/pageinspect/expected/btree.out`, where a freshly
  built index reads true. The `pg_upgrade` behaviour itself is untested upstream,
  which is what the script on this page measures.
- Ground truth only, not part of the answer: `contrib/pageinspect/btreefuncs.c`.
  Read as a second implementation of the same rule, not as part of the check:
  `contrib/amcheck/verify_nbtree.c`.
- Source history: `git log`, `git tag --contains` and `git log -S` in this checkout
  for `612a1ab7672`, `0d861bbb702`, `e5d8a999030`, `9f3665fbfc3`, `5f27b5f848a`,
  for `interval_ops` under `src/include/catalog/pg_amproc.dat`, for
  `allequalimage` under `src/bin/pg_upgrade`, and for the repin range
  `54eeefaed..786db8dcf16`.
- Wiki concept layer: [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md),
  read for the deduplication-gate family and the suite's boundary. It was not
  edited, and this page is not scored against it; see
  [Open Questions](#open-questions).
- Live measurement, 2026-09-16: one isolated 12.2 cluster and one isolated 17.11
  cluster created from it by `pg_upgrade --copy`, both built from their pins by
  [the script on this page](#the-script) and both stopped and deleted afterwards.
  The script ran four times, the last two on the text published here.
- Pinned checkout `raw/postgres-17/` at commit
  `786db8dcf168bd9df8f55047337525ac19118b1c` (PostgreSQL 17.11,
  `REL_17_11-7-g786db8dcf16`); repinned from
  `54eeefaedbee0385529f3edf321bb99e49232aaa` (17.10) on 2026-08-17. In the
  `54eeefaed..786db8dcf16` range of 193 commits, the only change under
  `src/backend/access/nbtree` is `8434c938598`, "Fix another empty nbtree index SSI
  race", which touches `nbtsearch.c` and nothing this page cites; `nbtree.h`,
  `nbtpage.c`, `nbtsort.c`, `nbtutils.c`, `nbtinsert.c`, `nbtxlog.c`,
  `nbtdedup.c` and contrib `pageinspect` are untouched. Under `src/bin/pg_upgrade`
  the range holds one functional change, `01992176e08`, which checks that every
  output plugin used by a migrated logical replication slot is listed in the new
  cluster's `output_plugin_libraries`
  ([check.c#check_new_cluster_logical_replication_slots](../../../../raw/postgres-17/src/bin/pg_upgrade/check.c#L1865-L1943)),
  and one translation update, `3e85b223b06`, which edits `po/de.po` and `po/ru.po`.
  The new check runs only when the old cluster reports at least one logical
  replication slot (`if (nslots_on_old > 0)`), which these fixtures never create.

## Evidence Map

| Claim | Source |
|---|---|
| A v12-built index needs a `REINDEX` to deduplicate; `pg_upgrade` does not set the field | [nbtree.h#BTREE_VERSION-comment](../../../../raw/postgres-17/src/include/access/nbtree.h#L124-L147) |
| The field is assumed zero on indexes upgraded from 12 | [nbtpage.c#_bt_metaversion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L719-L791) |
| `pageinspect` relies on the same assumption | [btreefuncs.c#bt_metap](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L905-L922) |
| Version 4 predates 13, so version does not identify a v12 build | [nbtree.h#BTREE_VERSION](../../../../raw/postgres-17/src/include/access/nbtree.h#L148-L152) |
| Metapage field order and `pd_lower` | [nbtree.h#BTMetaPageData](../../../../raw/postgres-17/src/include/access/nbtree.h#L103-L119), [nbtpage.c#_bt_initmetapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L63-L96) |
| Page contents start at `MAXALIGN(SizeOfPageHeaderData)` | [bufpage.h#PageGetContents](../../../../raw/postgres-17/src/include/storage/bufpage.h#L246-L258) |
| Only a rebuild can set the field; the in-place upgrade refuses | [nbtpage.c#_bt_upgrademetapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L98-L131) |
| Replay copies the flag but rewrites `pd_lower` | [nbtxlog.c#_bt_restore_meta](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L101-L125) |
| Build stores the flag; empty build too | [nbtsort.c#_bt_leafbuild](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L531-L565), [nbtsort.c#_bt_uppershutdown](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1118-L1128), [nbtree.c#btbuildempty](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L158-L171) |
| A build writes its pages, metapage included, through the bulk-write path | [nbtsort.c#_bt_blwritepage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L631-L639) |
| Insert-time deduplication is gated on the flag and the reloption | [nbtinsert.c#_bt_delete_or_dedup_one_page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2774-L2782) |
| Build-time deduplication also requires non-uniqueness | [nbtsort.c#_bt_load](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1144-L1152) |
| Flag reaches inserts through the insertion scan key | [nbtutils.c#_bt_mkscankey](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L118-L160) |
| Scans read it directly in `_bt_first` | [nbtsearch.c#_bt_first](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1314-L1324) |
| Posting-list search and posting-list splits assert it | [nbtsearch.c#_bt_binsrch_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L595-L620), [nbtinsert.c:1164-1171](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1164-L1171) |
| Metapage WAL records copy the flag rather than recomputing it | [nbtinsert.c:1350-1357](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1350-L1357), [nbtinsert.c:2573-2580](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2573-L2580) |
| `amcheck` errors when a stored true flag disagrees with the live rule, hinting at `interval` | [verify_nbtree.c#bt_index_check_internal](../../../../raw/postgres-17/contrib/amcheck/verify_nbtree.c#L365-L400) |
| The authoritative list of B-tree opclasses that cannot deduplicate unconditionally, and the test that guards it | [opr_sanity.sql:1336-1353](../../../../raw/postgres-17/src/test/regress/sql/opr_sanity.sql#L1336-L1353), [opr_sanity.out:2204-2222](../../../../raw/postgres-17/src/test/regress/expected/opr_sanity.out#L2204-L2222) |
| Eligibility rule: `INCLUDE`, support function 4, collation | [nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5129-L5183), [nbtree.h#BTEQUALIMAGE_PROC](../../../../raw/postgres-17/src/include/access/nbtree.h#L686-L712) |
| `btequalimage` always true; `btvarstrequalimage` true for C, default or deterministic collations only | [datum.c#btequalimage](../../../../raw/postgres-17/src/backend/utils/adt/datum.c#L415-L438), [varlena.c#btvarstrequalimage](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L2595-L2613) |
| Which opclasses register which support function | [pg_amproc.dat:201-212](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L201-L212), [pg_amproc.dat:31-33](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L31-L33), [pg_amproc.dat:240-241](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L240-L241), [pg_opclass.dat:145-146](../../../../raw/postgres-17/src/include/catalog/pg_opclass.dat#L145-L146) |
| Documented unsafe cases and the unique-index note | [btree.sgml#btree-deduplication](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L810-L909) |
| Pattern opclasses reject nondeterministic collations at DDL time | [index.c#index_create](../../../../raw/postgres-17/src/backend/catalog/index.c#L827-L848) |
| `deduplicate_items` default, lock level, no retroactive effect | [create_index.sgml#deduplicate_items](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L448-L476), [reloptions.c:159-168](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L168), [nbtree.h#BTGetDeduplicateItems](../../../../raw/postgres-17/src/include/access/nbtree.h#L1129-L1151) |
| `pg_upgrade` transfers user indexes plus TOAST and `pg_largeobject` | [info.c#get_rel_infos](../../../../raw/postgres-17/src/bin/pg_upgrade/info.c#L471-L524) |
| Index OID and relfilenode are preserved by the dump | [pg_dump.c#binary_upgrade_set_next_index_relfilenode](../../../../raw/postgres-17/src/bin/pg_dump/pg_dump.c#L5563-L5572) |
| Files are copied or linked, not rewritten | [relfilenumber.c#transfer_relfile](../../../../raw/postgres-17/src/bin/pg_upgrade/relfilenumber.c#L168-L266) |
| Upgrades from 9.2 and later are allowed, so 12 → 17 is in scope | [check.c#check_cluster_versions](../../../../raw/postgres-17/src/bin/pg_upgrade/check.c#L795-L824) |
| The completion banner recommends analyzing, nothing about indexes | [check.c#output_completion_banner](../../../../raw/postgres-17/src/bin/pg_upgrade/check.c#L760-L790) |
| The only rebuild advice left is for pre-10 hash indexes | [check.c#issue_warnings_and_set_wal_level](../../../../raw/postgres-17/src/bin/pg_upgrade/check.c#L744-L757) |
| The reference page promises that rebuild and reindex cases are reported | [pgupgrade.sgml#post-upgrade-scripts](../../../../raw/postgres-17/doc/src/sgml/ref/pgupgrade.sgml#L1078-L1086) |
| XID counters come from the old cluster's control data | [pg_upgrade.c#copy_xact_xlog_xid](../../../../raw/postgres-17/src/bin/pg_upgrade/pg_upgrade.c#L701-L737) |
| The OID counter is set from the old cluster's control data with `pg_resetwal -o` | [pg_upgrade.c#main](../../../../raw/postgres-17/src/bin/pg_upgrade/pg_upgrade.c#L155-L197) |
| Binary upgrade skips the statistics an index build would write | [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2825-L2842) |
| A new relation's row starts at `relpages = 0`, `reltuples = -1` | [heap.c#AddNewRelationTuple](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1004-L1016) |
| `VACUUM FULL`/`CLUSTER` rebuild all of a table's indexes | [cluster.c#finish_heap_swap](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1490-L1508) |
| `REINDEX INDEX` keeps the row and takes a new relfilenode | [index.c#reindex_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3783-L3789) |
| `REINDEX ... CONCURRENTLY` swaps the name onto the new index's row | [index.c#index_concurrently_swap](../../../../raw/postgres-17/src/backend/catalog/index.c#L1559-L1618) |
| Path rules and the `pg_read_server_files` role | [genfile.c#convert_and_check_filename](../../../../raw/postgres-17/src/backend/utils/adt/genfile.c#L41-L92) |
| The binary-file readers are revoked from `PUBLIC`, per signature | [system_functions.sql:712-718](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L712-L718) |
| `pg_relation_filepath()` returns a `$PGDATA`-relative path, NULL without storage | [dbsize.c#pg_relation_filepath](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L948-L1028) |
| `get_byte()` errors outside the `bytea` bounds | [varlena.c#byteaGetByte](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L3246-L3268) |
| Single-value fill factor explains the flat top of the savings curve | [nbtree.h#BTREE_SINGLEVAL_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202) |
| Repurposed metapage field can hold a stale XID after an upgrade | [nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L225-L263) |
| Deduplication in unique indexes is exercised in the regression tests | [btree_index.sql:208-231](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L208-L231) |
| Pattern-opclass rejection is exercised in the ICU collation test | [collate.icu.utf8.out:1796-1801](../../../../raw/postgres-17/src/test/regress/expected/collate.icu.utf8.out#L1796-L1801) |
| `make check` and its "All N tests passed" line | [regress.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L40-L59) |
| Timeout and message GUC contexts | [guc_tables.c:2611-2632](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2632), [guc_tables.c:4776-4785](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4776-L4785) |

## Open Questions

- **The OID counter did not show up where the source says it is set.**
  `pg_upgrade` runs `pg_resetwal -o` with the old cluster's next OID and reported
  `Setting next OID for new cluster ok`
  ([pg_upgrade.c#main](../../../../raw/postgres-17/src/bin/pg_upgrade/pg_upgrade.c#L155-L197)),
  yet the new cluster's control file read `NextOID` 16449 immediately after the
  upgrade where the old cluster's was 24576, and the first object created afterwards
  got OID 16503. The page reports the measurement and draws only the conclusion the
  measurement supports — that OID magnitude is not a marker — and does not claim to
  know why the counter reads low. The `-o` step is not the XID step, which did
  carry over.
- **The documentation and this behaviour disagree.** `pgupgrade.sgml` says "All
  failure, rebuild, and reindex cases will be reported by `pg_upgrade` if they
  affect your installation"
  ([pgupgrade.sgml#post-upgrade-scripts](../../../../raw/postgres-17/doc/src/sgml/ref/pgupgrade.sgml#L1078-L1086)),
  and the deduplication rebuild is a rebuild case that is not reported: the run
  named no index and produced only `delete_old_cluster.sh`. Source wins, so the
  answer follows the code, and the documentation gap is recorded here.
- **This page was not scored against the wiki's shared bloat suite.** The gate was
  scored against the metapage byte and the engine's `DEBUG1` verdict on 17 shapes of
  this page's own making, not against the numbered fixtures of
  [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md),
  whose family 1 covers the same equal-image gate with custom operator classes,
  impostor support functions and mixed column orders this page never builds. The
  reclaim percentages here are measured rebuild deltas, not verdicts under that
  page's bands.
- **The byte offsets were verified on one platform.** `MAXIMUM_ALIGNOF` was 8,
  `BLCKSZ` 8192, on x86-64 Linux. The offsets follow from
  `MAXALIGN(SizeOfPageHeaderData)` plus the struct layout, so a 32-bit or
  unusually aligned build could shift `btm_allequalimage` away from byte 64. The
  self-test in [Check 2](#check-2-prove-the-byte-offsets-on-your-platform) detects
  that, but no such platform was tested.
- **No standby or crash-recovery run was made.** `_bt_restore_meta()` rewrites
  `pd_lower` on replay, so a carried-over metapage that has been through replay
  should report `pd_lower = 72` with byte 64 still false. That combination was
  reasoned from source, not observed; only primaries were measured.
- **The probe reads the file, not shared buffers.** A fresh build was visible
  immediately with no checkpoint because index builds bulk-write their pages, but
  no test forced a metapage update to sit dirty in shared buffers while the probe
  ran. `btm_allequalimage` never changes after build, so the risk is bounded, but
  it is unmeasured.
- **12.2 is the only old version measured, and it is the one version that cannot
  show the `interval` hazard.** An 11 or earlier cluster would also carry
  `btm_version = 3` metapages, where `_bt_upgrademetapage()` and the `heapkeyspace`
  differences matter; a 13 through 16 cluster is where a *true* flag can be carried
  into v17 and be wrong. Nothing here was run against either.
- **The `rebuild for correctness` branch is source-verified and unexercised.** It
  is derived from `5f27b5f848a`, the catalogs, `btequalimage()` and `amcheck`, and
  it matched 0 rows on the measured leg because v12 wrote every flag false. No
  fixture on this page produces a metapage whose flag is true while the catalogs
  refuse the key, which would need either a pre-fix 13-16 build or a hand-edited
  metapage. Its counterpart in the engine — the `amcheck` error — was likewise not
  triggered here.
- **The gate was scored on 17 index shapes, none of them `interval`.** It agreed
  with the metapage on all 17, but the space of opclasses is much larger:
  `opr_sanity` names 16 core opclasses that cannot deduplicate unconditionally,
  and the fixtures cover only `numeric`, `float8`, `jsonb`, `int[]` and
  nondeterministic `text` among them. User-defined opclasses that register support
  function 4 and return false for reasons other than collation would also defeat
  the SQL mirror, which cannot call the function. Nor was a nondeterministic
  collation with a C locale constructed, which is the only shape where
  `btvarstrequalimage`'s C short-circuit could disagree with `collisdeterministic`.
- **The earlier `INCLUDE` loss was not reproduced.** The superseded 17.10 text
  reported that `i_inc` lost six pages on rebuild and could not isolate the cause.
  On this run the `INCLUDE` index rebuilt byte-identical, at 22,519,808 bytes both
  before and after, so nothing remains to explain — but the fixture is not the same
  one: this `i_inc` includes a short `text` column that fits inside the tuple
  alignment of the key alone.
- **Partial-index triage is approximate, and on this fixture it is wrong by an
  order of magnitude.** `rows_per_key` divides the index's own `reltuples` by the
  table's `n_distinct`, which assumes the predicate does not correlate with the
  key. On `i_partial` the predicate *is* the key — `st = 'open'` holds exactly
  where `k10` is 0 — so the query printed 9,673.4 rows per key where the truth is
  100,000 rows over one distinct key value. The superseded text called 99,867 rows
  over 10 keys the "actual" figures; both halves of that were wrong, the row count
  because an index's `reltuples` is a sample and the key count because the subset
  holds one value. No general fix is filed here: correcting it needs statistics on
  the indexed subset, which `pg_stats` does not carry for a partial index.
- **The sampled `reltuples` behind that column moves every run.** Four runs on one
  host on 2026-09-16 gave 101,667, 104,734, 98,700 and 96,734 for a population that
  is exactly 100,000, and 2026-09-15 gave 99,867. Every other scored cell on this
  page reproduced exactly across those runs, so treat this one column as an
  estimate with a few percent of spread rather than a measurement.
- **No timing was recorded for the rebuilds.** Sizes were measured; wall-clock cost
  and WAL volume of the `REINDEX INDEX CONCURRENTLY` runs were not.
- **The carried-over catalog and TOAST indexes were flagged but not rebuilt.**
  `pg_largeobject_loid_pn_index` and the three TOAST indexes are unique, so no size
  change is expected, and whether `REINDEX` on them is acceptable in production was
  not tested.

## Source References

- [nbtree.h#BTMetaPageData](../../../../raw/postgres-17/src/include/access/nbtree.h#L103-L152)
- [nbtree.h#BTREE_SINGLEVAL_FILLFACTOR](../../../../raw/postgres-17/src/include/access/nbtree.h#L189-L202)
- [nbtree.h#BTEQUALIMAGE_PROC](../../../../raw/postgres-17/src/include/access/nbtree.h#L686-L712)
- [nbtree.h#BTGetDeduplicateItems](../../../../raw/postgres-17/src/include/access/nbtree.h#L1129-L1151)
- [nbtpage.c#_bt_initmetapage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L63-L131)
- [nbtpage.c#_bt_set_cleanup_info](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L225-L263)
- [nbtpage.c#_bt_metaversion](../../../../raw/postgres-17/src/backend/access/nbtree/nbtpage.c#L719-L791)
- [nbtutils.c#_bt_mkscankey](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L118-L160)
- [nbtutils.c#_bt_allequalimage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtutils.c#L5129-L5183)
- [nbtsort.c#_bt_leafbuild](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L531-L565)
- [nbtsort.c#_bt_blwritepage](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L631-L639)
- [nbtsort.c#_bt_load](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsort.c#L1118-L1152)
- [nbtinsert.c#_bt_findinsertloc](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L899-L907)
- [nbtinsert.c:1164-1171](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1164-L1171)
- [nbtinsert.c:1350-1357](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L1350-L1357)
- [nbtinsert.c:2573-2580](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2573-L2580)
- [nbtinsert.c#_bt_delete_or_dedup_one_page](../../../../raw/postgres-17/src/backend/access/nbtree/nbtinsert.c#L2654-L2782)
- [nbtsearch.c#_bt_binsrch_posting](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L595-L620)
- [nbtsearch.c#_bt_first](../../../../raw/postgres-17/src/backend/access/nbtree/nbtsearch.c#L1314-L1324)
- [nbtree.c#btbuildempty](../../../../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L158-L171)
- [nbtxlog.c#_bt_restore_meta](../../../../raw/postgres-17/src/backend/access/nbtree/nbtxlog.c#L101-L125)
- [bufpage.h#PageGetContents](../../../../raw/postgres-17/src/include/storage/bufpage.h#L246-L258)
- [datum.c#btequalimage](../../../../raw/postgres-17/src/backend/utils/adt/datum.c#L415-L438)
- [varlena.c#btvarstrequalimage](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L2595-L2613)
- [varlena.c#byteaGetByte](../../../../raw/postgres-17/src/backend/utils/adt/varlena.c#L3246-L3268)
- [pg_amproc.dat:31-33](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L31-L33)
- [pg_amproc.dat:201-212](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L201-L212)
- [pg_amproc.dat:240-241](../../../../raw/postgres-17/src/include/catalog/pg_amproc.dat#L240-L241)
- [pg_opclass.dat:145-146](../../../../raw/postgres-17/src/include/catalog/pg_opclass.dat#L145-L146)
- [pg_proc.dat#btvarstrequalimage](../../../../raw/postgres-17/src/include/catalog/pg_proc.dat#L1055-L1057)
- [heap.c#AddNewRelationTuple](../../../../raw/postgres-17/src/backend/catalog/heap.c#L1004-L1016)
- [heap.c#InsertPgClassTuple](../../../../raw/postgres-17/src/backend/catalog/heap.c#L898-L940)
- [index.c#index_create](../../../../raw/postgres-17/src/backend/catalog/index.c#L827-L848)
- [index.c#index_concurrently_swap](../../../../raw/postgres-17/src/backend/catalog/index.c#L1559-L1618)
- [index.c#index_update_stats](../../../../raw/postgres-17/src/backend/catalog/index.c#L2809-L2842)
- [index.c#reindex_index](../../../../raw/postgres-17/src/backend/catalog/index.c#L3783-L3789)
- [reloptions.c:159-168](../../../../raw/postgres-17/src/backend/access/common/reloptions.c#L159-L168)
- [cluster.c#finish_heap_swap](../../../../raw/postgres-17/src/backend/commands/cluster.c#L1437-L1508)
- [genfile.c#convert_and_check_filename](../../../../raw/postgres-17/src/backend/utils/adt/genfile.c#L41-L92)
- [dbsize.c#pg_relation_filepath](../../../../raw/postgres-17/src/backend/utils/adt/dbsize.c#L948-L1028)
- [system_functions.sql:712-718](../../../../raw/postgres-17/src/backend/catalog/system_functions.sql#L712-L718)
- [guc_tables.c:2611-2632](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L2611-L2632)
- [guc_tables.c:4776-4785](../../../../raw/postgres-17/src/backend/utils/misc/guc_tables.c#L4776-L4785)
- [pg_upgrade.c#main](../../../../raw/postgres-17/src/bin/pg_upgrade/pg_upgrade.c#L155-L197)
- [pg_upgrade.c#copy_xact_xlog_xid](../../../../raw/postgres-17/src/bin/pg_upgrade/pg_upgrade.c#L701-L737)
- [check.c#issue_warnings_and_set_wal_level](../../../../raw/postgres-17/src/bin/pg_upgrade/check.c#L744-L757)
- [check.c#output_completion_banner](../../../../raw/postgres-17/src/bin/pg_upgrade/check.c#L760-L790)
- [check.c#check_cluster_versions](../../../../raw/postgres-17/src/bin/pg_upgrade/check.c#L795-L824)
- [check.c#check_new_cluster_logical_replication_slots](../../../../raw/postgres-17/src/bin/pg_upgrade/check.c#L1865-L1943)
- [info.c#get_rel_infos](../../../../raw/postgres-17/src/bin/pg_upgrade/info.c#L471-L524)
- [relfilenumber.c#transfer_relfile](../../../../raw/postgres-17/src/bin/pg_upgrade/relfilenumber.c#L168-L266)
- [pg_dump.c#binary_upgrade_set_next_index_relfilenode](../../../../raw/postgres-17/src/bin/pg_dump/pg_dump.c#L5563-L5572)
- [btree.sgml#btree-deduplication](../../../../raw/postgres-17/doc/src/sgml/btree.sgml#L736-L911)
- [create_index.sgml#deduplicate_items](../../../../raw/postgres-17/doc/src/sgml/ref/create_index.sgml#L448-L476)
- [pgupgrade.sgml#post-upgrade-scripts](../../../../raw/postgres-17/doc/src/sgml/ref/pgupgrade.sgml#L1078-L1086)
- [regress.sgml#make-check](../../../../raw/postgres-17/doc/src/sgml/regress.sgml#L40-L59)
- [btree_index.sql:208-231](../../../../raw/postgres-17/src/test/regress/sql/btree_index.sql#L208-L231)
- [opr_sanity.sql:1336-1353](../../../../raw/postgres-17/src/test/regress/sql/opr_sanity.sql#L1336-L1353)
- [opr_sanity.out:2204-2222](../../../../raw/postgres-17/src/test/regress/expected/opr_sanity.out#L2204-L2222)
- [collate.icu.utf8.out:1796-1801](../../../../raw/postgres-17/src/test/regress/expected/collate.icu.utf8.out#L1796-L1801)
- [005_opclass_damage.pl:45-52](../../../../raw/postgres-17/src/bin/pg_amcheck/t/005_opclass_damage.pl#L45-L52)
- [btreefuncs.c#bt_metap](../../../../raw/postgres-17/contrib/pageinspect/btreefuncs.c#L828-L922)
- [btree.out:1-16](../../../../raw/postgres-17/contrib/pageinspect/expected/btree.out#L1-L16)
- [verify_nbtree.c#bt_index_check_internal](../../../../raw/postgres-17/contrib/amcheck/verify_nbtree.c#L365-L400)

## Navigation

- [v17/index](../../index.md)
- [Mandatory B-Tree Bloat Tests (unverified)](../../common-concepts/mandatory-btree-bloat-tests.md)
- [How REINDEX INDEX CONCURRENTLY Is Implemented in PostgreSQL 17 (unverified)](reindex-index-concurrently.md)
- [Testing the PostgreSQL 12 Core-SQL B-Tree Bloat Method on PostgreSQL 17 (unverified)](btree-index-bloat-core-sql-only.md)
- [How CREATE INDEX CONCURRENTLY Is Implemented in PostgreSQL 17 (unverified)](create-index-concurrently.md)
- [PostgreSQL 17 Codebase Navigation Guide (unverified)](../../codebase-navigation-guide.md)
- [versions](../../../versions.md)
- [Wiki Index](../../../index.md)
