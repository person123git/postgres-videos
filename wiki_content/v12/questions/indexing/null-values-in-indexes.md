---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: GPT-5-5-XHigh-Thinking 2026-06-17T17:30:21Z
---

# How NULL Values Are Handled in PostgreSQL 12 Indexes (unverified)

## Contents

- [Question](#question)
- [Answer](#answer)
  - [Short Answer](#short-answer)
  - [Shared Index API](#shared-index-api)
  - [B-tree](#b-tree)
  - [Hash](#hash)
  - [GiST](#gist)
  - [SP-GiST](#sp-gist)
  - [GIN](#gin)
  - [BRIN](#brin)
  - [Contrib Bloom](#contrib-bloom)
  - [Practical Summary](#practical-summary)
  - [Test Coverage](#test-coverage)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Open Questions](#open-questions)
- [Source References](#source-references)
- [Navigation](#navigation)

## Question

How are NULL values handled in indexes? Create a section by type of index.

Prompt note: the original request had typos. The user approved correcting the prompt before filing this page.

## Answer

PostgreSQL 12 does not use one universal NULL rule for all index access methods. The executor passes each index access method both datum values and an `isnull[]` array. Each access method then decides whether to store NULLs, summarize them, skip them, or represent them as special keys. The planner can generate a plain indexed `IS NULL` or `IS NOT NULL` scan only for access methods whose handler advertises `amsearchnulls = true` in `IndexAmRoutine`.[index.c#FormIndexDatum](../../../../raw/postgres-12/src/backend/catalog/index.c#L2578-L2648) [execIndexing.c#ExecInsertIndexTuples](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L314-L400) [indexam.c#index_insert](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L165-L189) [amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L163-L199) [indxpath.c#match_clause_to_indexcol](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2408-L2444)

PostgreSQL 12's built-in index methods are B-tree, hash, GiST, SP-GiST, GIN, and BRIN. `CREATE INDEX` uses B-tree by default, and the built-in method list is also present in the pinned catalog data.[pg_am.dat#built-in-index-ams](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L18-L35) [create_index.sgml#access-method](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L230-L239)

### Short Answer

| Index type | NULL storage or summary | Plain `IS NULL` / `IS NOT NULL` index scan | Important consequence |
| --- | --- | --- | --- |
| B-tree | Stores NULLs in index tuples, with NULL ordering controlled by scan/index options.[nbtutils.c#_bt_mkscankey](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L95-L154) [nbtsearch.c#_bt_compare](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L545-L625) | Yes, because `amsearchnulls = true`.[nbtree.c#bthandler](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L102-L130) | Unique B-tree indexes allow multiple rows where any indexed key column is NULL.[nbtinsert.c#btinsert](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L90-L116) |
| Hash | Does not insert NULL values.[hashutil.c#_hash_convert_tuple](../../../../raw/postgres-12/src/backend/access/hash/hashutil.c#L312-L343) | No, because `amsearchnulls = false`.[hash.c#hashhandler](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L54-L83) | A NULL equality search key is treated as unable to match.[hashsearch.c#_hash_first](../../../../raw/postgres-12/src/backend/access/hash/hashsearch.c#L325-L330) |
| GiST | Stores NULL markers in index tuples and avoids opclass compression for NULL key attributes.[gistutil.c#gistFormTuple](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L576-L624) | Yes, because `amsearchnulls = true`.[gist.c#gisthandler](../../../../raw/postgres-12/src/backend/access/gist/gist.c#L55-L82) | Internal GiST decisions treat `IS NULL` conservatively on non-leaf pages because a child union can hide NULL entries.[gistget.c#gistindex_keytest](../../../../raw/postgres-12/src/backend/access/gist/gistget.c#L173-L191) |
| SP-GiST | Stores NULL entries in a separate NULL tree rooted at block 2.[spgist_private.h#SPGIST_NULL_BLKNO](../../../../raw/postgres-12/src/include/access/spgist_private.h#L24-L62) [spgdoinsert.c#spgdoinsert](../../../../raw/postgres-12/src/backend/access/spgist/spgdoinsert.c#L1963-L2058) | Yes, because `amsearchnulls = true`.[spgutils.c#spghandler](../../../../raw/postgres-12/src/backend/access/spgist/spgutils.c#L36-L62) | SP-GiST core handles NULLs before opclass methods see the value.[spgist.sgml#null-values](../../../../raw/postgres-12/doc/src/sgml/spgist.sgml#L272-L280) |
| GIN | Stores special categories for NULL items, NULL keys, empty items, and empty queries.[ginblock.h#GinNullCategory](../../../../raw/postgres-12/src/include/access/ginblock.h#L199-L216) [ginutil.c#ginExtractEntries](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L484-L600) | No generic column `IS NULL` path, because `amsearchnulls = false`.[ginutil.c#ginhandler](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L33-L58) | NULL handling is part of GIN key extraction and opclass query semantics, not the planner's generic `NullTest` path.[ginscan.c#startScanKey](../../../../raw/postgres-12/src/backend/access/gin/ginscan.c#L296-L365) |
| BRIN | Stores per-range `hasnulls` and `allnulls` flags.[brin_tuple.c#tuple-layout](../../../../raw/postgres-12/src/backend/access/brin/brin_tuple.c#L15-L24) [brin_tuple.h#BrinValues](../../../../raw/postgres-12/src/include/access/brin_tuple.h#L23-L45) | Yes, because `amsearchnulls = true`.[brin.c#brinhandler](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L81-L107) | BRIN answers NULL tests at block-range granularity and returns lossy bitmap scans for executor recheck.[brin.sgml#intro](../../../../raw/postgres-12/doc/src/sgml/brin.sgml#L14-L40) |
| Contrib Bloom | Skips NULL columns when building the Bloom signature.[blutils.c#BloomFormTuple](../../../../raw/postgres-12/contrib/bloom/blutils.c#L286-L302) | No, because `amsearchnulls = false`.[blutils.c#blhandler](../../../../raw/postgres-12/contrib/bloom/blutils.c#L101-L122) | The Bloom documentation explicitly says Bloom does not support searching NULL values.[bloom.sgml#limitations](../../../../raw/postgres-12/doc/src/sgml/bloom.sgml#L228-L259) |

### Shared Index API

The executor computes index column values with `FormIndexDatum`, including expression index values, and keeps a parallel `isnull[]` array for each key. It then calls `index_insert`, which dispatches to the access method's `aminsert` callback.[index.c#FormIndexDatum](../../../../raw/postgres-12/src/backend/catalog/index.c#L2578-L2648) [execIndexing.c#ExecInsertIndexTuples](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L314-L400) [indexam.c#index_insert](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L165-L189)

The common `IndexTuple` format can store a NULL bitmap. `index_form_tuple` sets `INDEX_NULL_MASK` when any input attribute is NULL and allocates the bitmap used later by `index_getattr`.[itup.h#IndexTupleHasNulls](../../../../raw/postgres-12/src/include/access/itup.h#L65-L89) [itup.h#index_getattr](../../../../raw/postgres-12/src/include/access/itup.h#L100-L127) [indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L112-L188)

Scan keys have explicit flags for NULL behavior. `SK_ISNULL` marks a NULL comparison datum, while `SK_SEARCHNULL` and `SK_SEARCHNOTNULL` represent `IS NULL` and `IS NOT NULL` search conditions. The header comment states that those search flags are supported only by access methods that set `amsearchnulls`.[skey.h#ScanKey-flags](../../../../raw/postgres-12/src/include/access/skey.h#L43-L51) [skey.h#ScanKey-flags-definitions](../../../../raw/postgres-12/src/include/access/skey.h#L115-L122) [amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L163-L199)

The planner uses that access-method capability. In `match_clause_to_indexcol`, a `NullTest` clause becomes an indexable condition only when the index reports `amsearchnulls` and the clause targets the indexed expression.[indxpath.c#match_clause_to_indexcol](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2408-L2444)

### B-tree

B-tree indexes store NULLs as index tuple attributes. `_bt_mkscankey` reads each index attribute with `index_getattr`; if the attribute is NULL, it marks the scan key with `SK_ISNULL` and records that the insertion key has a NULL component.[nbtutils.c#_bt_mkscankey](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L95-L154)

B-tree supports indexed `IS NULL` and `IS NOT NULL` searches because its handler sets `amsearchnulls = true`. The planner can therefore match `NullTest` clauses to B-tree indexes, and the B-tree preprocessing code describes `x IS NULL` as an equality-like search and `x IS NOT NULL` as a boundary condition based on the index's NULL ordering.[nbtree.c#bthandler](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L102-L130) [indxpath.c#match_clause_to_indexcol](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2408-L2444) [nbtutils.c#_bt_preprocess_keys](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1182-L1222)

B-tree has a defined sort position for NULLs. The comparison code treats NULLs as sortable values: two NULLs compare equal for ordering, and a NULL-vs-non-NULL comparison follows the `SK_BT_NULLS_FIRST` flag. Documentation states that a default ascending B-tree index stores NULLs last, a backward scan produces descending order with NULLs first, and index definitions can specify `NULLS FIRST` or `NULLS LAST`.[nbtsearch.c#_bt_compare](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L545-L625) [indices.sgml#indexes-ordering](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L505-L529) [create_index.sgml#NULLS-FIRST-LAST](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L304-L320)

Unique B-tree indexes do not treat NULLs as equal for uniqueness checks. During insertion, if uniqueness is being checked and any key column is NULL, `btinsert` bypasses the duplicate-check path because the core code treats NULL as unequal to every value, including another NULL. The `CREATE TABLE` reference says the same rule for unique constraints, which are implemented by unique B-tree indexes.[nbtinsert.c#btinsert](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L90-L116) [nbtinsert.c#_bt_check_unique](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L338-L380) [create_table.sgml#unique-constraints](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L878-L899)

### Hash

Hash indexes do not store NULL index entries. `hashinsert` converts the table value to the stored hash key by calling `_hash_convert_tuple`; that helper returns `false` for a NULL input, and `hashinsert` returns without inserting an index tuple.[hash.c#hashinsert](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L239-L269) [hashutil.c#_hash_convert_tuple](../../../../raw/postgres-12/src/backend/access/hash/hashutil.c#L312-L343)

Hash indexes do not support generic `IS NULL` or `IS NOT NULL` index scans because the handler sets `amsearchnulls = false`. This also matches the search code: if the equality scan argument is NULL, hash scan startup assumes the qual cannot match any stored tuple.[hash.c#hashhandler](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L54-L83) [hashsearch.c#_hash_first](../../../../raw/postgres-12/src/backend/access/hash/hashsearch.c#L325-L330)

### GiST

GiST stores NULL key attributes as NULL attributes in the index tuple. `gistFormTuple` puts a zero datum placeholder in the compressed-attribute array for NULL key values and does not call the opclass compression function for that key; the original `isnull[]` value is then passed to `index_form_tuple`.[gist.c#gistinsert](../../../../raw/postgres-12/src/backend/access/gist/gist.c#L146-L183) [gistutil.c#gistFormTuple](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L576-L624)

GiST supports indexed `IS NULL` and `IS NOT NULL` searches because its handler sets `amsearchnulls = true`. During scan setup, a normal operator qual with a NULL comparison constant is treated as impossible unless the key is explicitly `SK_SEARCHNULL` or `SK_SEARCHNOTNULL`.[gist.c#gisthandler](../../../../raw/postgres-12/src/backend/access/gist/gist.c#L55-L82) [gistscan.c#gistrescan](../../../../raw/postgres-12/src/backend/access/gist/gistscan.c#L242-L272)

On leaf pages, GiST can test the actual tuple NULL state: `SK_SEARCHNULL` rejects non-NULL tuples, and `SK_SEARCHNOTNULL` rejects NULL tuples. On non-leaf pages, `SK_SEARCHNULL` cannot reject a child solely because the downlink value is non-NULL, since GiST union construction can produce a non-NULL union value for a subtree that also contains NULLs.[gistget.c#gistindex_keytest](../../../../raw/postgres-12/src/backend/access/gist/gistget.c#L173-L191) [gistutil.c#gistMakeUnionItVec](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L151-L210) [gistutil.c#gistMakeUnionKey](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L234-L276)

### SP-GiST

SP-GiST stores NULL entries separately from non-NULL entries. Its private header defines `SPGIST_ROOT_BLKNO` as the normal root and `SPGIST_NULL_BLKNO` as the NULL root, and the page flag `SPGIST_NULLS` marks pages that store NULL entries.[spgist_private.h#SPGIST-layout](../../../../raw/postgres-12/src/include/access/spgist_private.h#L24-L62)

Index initialization creates both the normal root page and the NULL root page. The NULL root page is initialized as a leaf page with the `SPGIST_NULLS` flag.[spginsert.c#spgbuildempty](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L84-L110)

Insertion chooses the NULL root when the indexed value is NULL and the normal root when it is not. The core insertion path skips opclass choose/compress work for NULLs, verifies that each page matches the expected NULL-vs-non-NULL kind, and forms the leaf tuple with the stored NULL flag.[spginsert.c#spginsert](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L207-L232) [spgdoinsert.c#spgdoinsert-null-opclass-boundary](../../../../raw/postgres-12/src/backend/access/spgist/spgdoinsert.c#L1890-L1925) [spgdoinsert.c#spgdoinsert-null-root](../../../../raw/postgres-12/src/backend/access/spgist/spgdoinsert.c#L1963-L2058)

SP-GiST supports indexed `IS NULL` and `IS NOT NULL` searches because its handler sets `amsearchnulls = true`. Scan preprocessing separates `SK_SEARCHNULL` and `SK_SEARCHNOTNULL` from regular operator keys, marks ordinary NULL operator arguments as impossible, and chooses whether to search the NULL tree, the non-NULL tree, or both.[spgutils.c#spghandler](../../../../raw/postgres-12/src/backend/access/spgist/spgutils.c#L36-L62) [spgscan.c#spgPrepareScanKeys](../../../../raw/postgres-12/src/backend/access/spgist/spgscan.c#L192-L297) [spgscan.c#resetSpGistScanOpaque](../../../../raw/postgres-12/src/backend/access/spgist/spgscan.c#L145-L168) [spgscan.c#spgAddStartItem](../../../../raw/postgres-12/src/backend/access/spgist/spgscan.c#L121-L133)

SP-GiST opclasses do not handle SQL NULL values directly. The SGML documentation states that SP-GiST core stores NULL entries, hides NULL values from opclass methods, and assumes indexed operators are strict.[spgist.sgml#null-values](../../../../raw/postgres-12/doc/src/sgml/spgist.sgml#L272-L280)

### GIN

GIN is an inverted index: it stores keys extracted from an indexed item and maps each key to posting information for rows that contain that key. The GIN documentation describes this key/posting-list model rather than storing the full indexed item as the lookup key.[gin.sgml#intro](../../../../raw/postgres-12/doc/src/sgml/gin.sgml#L14-L36)

GIN has its own NULL categories. `GinNullCategory` distinguishes a normal key, a NULL key, an empty item placeholder, a NULL item placeholder, and an empty query marker.[ginblock.h#GinNullCategory](../../../../raw/postgres-12/src/include/access/ginblock.h#L199-L216)

Insertion uses those categories. If the whole indexed item is SQL NULL, `ginExtractEntries` does not call the opclass extract function and emits one `GIN_CAT_NULL_ITEM` placeholder. If a non-NULL item extracts no keys, it emits `GIN_CAT_EMPTY_ITEM`. If the opclass reports per-key NULL flags, GIN stores those keys with `GIN_CAT_NULL_KEY` rather than the normal category.[ginutil.c#ginExtractEntries](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L484-L600) [gininsert.c#ginEntryInsert](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L468-L532)

GIN does not support the planner's generic `IS NULL` or `IS NOT NULL` index qualification for the indexed column, because its handler sets `amsearchnulls = false`. A plain `NullTest` on the indexed expression therefore is not matched to a GIN index by the generic planner path.[ginutil.c#ginhandler](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L33-L58) [indxpath.c#match_clause_to_indexcol](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2408-L2444)

GIN NULL behavior is instead mediated through operator-class query extraction and consistency checks. For example, the built-in array GIN support extracts array elements with per-element NULL flags, and its consistency functions give special results for NULL query elements: overlap cannot prove a match from a NULL element alone, and contains requires all elements to match with no NULL query element.[ginarrayproc.c#ginarrayextract](../../../../raw/postgres-12/src/backend/access/gin/ginarrayproc.c#L30-L58) [ginarrayproc.c#ginqueryarrayextract](../../../../raw/postgres-12/src/backend/access/gin/ginarrayproc.c#L82-L112) [ginarrayproc.c#ginarrayconsistent](../../../../raw/postgres-12/src/backend/access/gin/ginarrayproc.c#L154-L185) [ginarrayproc.c#ginarraytriconsistent](../../../../raw/postgres-12/src/backend/access/gin/ginarrayproc.c#L230-L270)

### BRIN

BRIN does not store one index tuple per row. It stores summary information for a range of heap blocks, returns lossy bitmap scans, and relies on the executor to recheck the real rows.[brin.sgml#intro](../../../../raw/postgres-12/doc/src/sgml/brin.sgml#L14-L40)

BRIN summaries carry explicit NULL flags. The tuple layout uses two bits per indexed column: `hasnulls` means the range contains at least one NULL value, and `allnulls` means every value in the range is NULL. The in-memory `BrinValues` structure carries the same `bv_hasnulls` and `bv_allnulls` fields.[brin_tuple.c#tuple-layout](../../../../raw/postgres-12/src/backend/access/brin/brin_tuple.c#L15-L24) [brin_tuple.h#BrinValues](../../../../raw/postgres-12/src/include/access/brin_tuple.h#L23-L45) [README#BRIN-tuples](../../../../raw/postgres-12/src/backend/access/brin/README#L50-L62)

BRIN builds and updates those flags through opclass `addValue` callbacks. The build callback passes each heap value and its `isnull` state into the opclass, and both the minmax and inclusion opclasses set `bv_hasnulls` for NULL input while leaving range values absent until the first non-NULL value arrives.[brin.c#brinbuildCallback](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L645-L655) [brin.c#brinbuild](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L723-L724) [brin_minmax.c#brin_minmax_add_value](../../../../raw/postgres-12/src/backend/access/brin/brin_minmax.c#L75-L106) [brin_inclusion.c#brin_inclusion_add_value](../../../../raw/postgres-12/src/backend/access/brin/brin_inclusion.c#L148-L177)

BRIN supports indexed `IS NULL` and `IS NOT NULL` searches because its handler sets `amsearchnulls = true`. Minmax and inclusion consistency functions return a range as potentially matching `IS NULL` when `allnulls` or `hasnulls` is set, and they return a range as potentially matching `IS NOT NULL` when the range is not all NULL. Ordinary strict comparisons with a NULL scan key cannot match.[brin.c#brinhandler](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L81-L107) [brin_minmax.c#brin_minmax_consistent](../../../../raw/postgres-12/src/backend/access/brin/brin_minmax.c#L154-L188) [brin_inclusion.c#brin_inclusion_consistent](../../../../raw/postgres-12/src/backend/access/brin/brin_inclusion.c#L266-L300)

### Contrib Bloom

The contrib Bloom index access method is not one of the built-in core methods listed for `CREATE INDEX`, but PostgreSQL 12 ships it under `contrib/bloom`. Its documentation says Bloom supports equality-style searches through Bloom signatures and lists limitations, including that it does not support searching NULL values.[create_index.sgml#access-method](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L230-L239) [bloom.sgml#operator-classes](../../../../raw/postgres-12/doc/src/sgml/bloom.sgml#L214-L225) [bloom.sgml#limitations](../../../../raw/postgres-12/doc/src/sgml/bloom.sgml#L228-L259)

The Bloom handler sets `amsearchnulls = false`, so the generic planner path cannot turn a plain `IS NULL` or `IS NOT NULL` clause into a Bloom index condition. When building a Bloom signature, `BloomFormTuple` skips NULL index columns. During scan startup, a NULL search key makes the scan return no matches.[blutils.c#blhandler](../../../../raw/postgres-12/contrib/bloom/blutils.c#L101-L122) [blutils.c#BloomFormTuple](../../../../raw/postgres-12/contrib/bloom/blutils.c#L286-L302) [blscan.c#blgetbitmap](../../../../raw/postgres-12/contrib/bloom/blscan.c#L89-L113)

### Practical Summary

Use B-tree when the application needs ordered NULL handling, `IS NULL` or `IS NOT NULL` index scans, or unique indexes where multiple NULL keys are allowed by SQL semantics.[nbtree.c#bthandler](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L102-L130) [indices.sgml#indexes-ordering](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L505-L529) [nbtinsert.c#btinsert](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L90-L116)

Use GiST or SP-GiST only when the operator class and data type need those access methods; both can search NULL and non-NULL entries through the generic `NullTest` path, but both also have access-method-specific NULL storage rules.[gist.c#gisthandler](../../../../raw/postgres-12/src/backend/access/gist/gist.c#L55-L82) [gistutil.c#gistFormTuple](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L576-L624) [spgutils.c#spghandler](../../../../raw/postgres-12/src/backend/access/spgist/spgutils.c#L36-L62) [spgdoinsert.c#spgdoinsert-null-root](../../../../raw/postgres-12/src/backend/access/spgist/spgdoinsert.c#L1963-L2058)

Use BRIN when range summaries fit the data and false positives are acceptable; BRIN records whether a range has NULLs or is all NULLs, and a bitmap heap scan rechecks rows after the lossy range match.[brin.sgml#intro](../../../../raw/postgres-12/doc/src/sgml/brin.sgml#L14-L40) [brin_tuple.c#tuple-layout](../../../../raw/postgres-12/src/backend/access/brin/brin_tuple.c#L15-L24) [brin_minmax.c#brin_minmax_consistent](../../../../raw/postgres-12/src/backend/access/brin/brin_minmax.c#L154-L188)

Do not expect hash, GIN, or contrib Bloom to accelerate a plain `indexed_column IS NULL` condition through the generic planner `NullTest` path in PostgreSQL 12. Hash skips NULL index entries, GIN advertises no generic NULL-search support even though it stores NULL categories for GIN key semantics, and Bloom skips NULL columns in signatures and rejects NULL scan keys.[hashutil.c#_hash_convert_tuple](../../../../raw/postgres-12/src/backend/access/hash/hashutil.c#L312-L343) [hash.c#hashhandler](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L54-L83) [ginutil.c#ginhandler](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L33-L58) [ginblock.h#GinNullCategory](../../../../raw/postgres-12/src/include/access/ginblock.h#L199-L216) [blutils.c#blhandler](../../../../raw/postgres-12/contrib/bloom/blutils.c#L101-L122) [blutils.c#BloomFormTuple](../../../../raw/postgres-12/contrib/bloom/blutils.c#L286-L302)

### Test Coverage

PostgreSQL 12 regression tests exercise B-tree `IS NULL` and `IS NOT NULL` predicates after building unique B-tree indexes with different NULL ordering options. The expected output shows correct result counts; this block does not include `EXPLAIN`, so it is result coverage rather than plan-shape coverage.[create_index.sql#btree-null-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L603-L676) [create_index.out#btree-null-tests](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1566-L1724)

The regression suite also tests unique expression indexes with NULL inputs. The SQL inserts rows where one expression result is NULL, and the expected output shows that the duplicate non-NULL expression value fails while the NULL-containing case is accepted.[create_index.sql#unique-expression-null-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L393-L423) [create_index.out#unique-expression-null-tests](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1274-L1315)

GiST tests insert a NULL point value and use a GiST point index for `IS NULL` and `IS NOT NULL` index-only scans.[create_index.sql#gist-null-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L80-L149) [create_index.out#gist-null-results](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L196-L205) [create_index.out#gist-null-plans](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L538-L559)

SP-GiST tests insert NULL point values and show index-only scans for `p IS NULL` and `p IS NOT NULL`.[create_index_spgist.sql#spgist-null-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index_spgist.sql#L1-L40) [create_index_spgist.out#spgist-null-plans](../../../../raw/postgres-12/src/test/regress/expected/create_index_spgist.out#L181-L205)

GIN tests cover indexed array operator plans and array NULL query semantics. The plan evidence is for array containment using the GIN index; the NULL-specific array expectations show the built-in array operator semantics that the GIN array opclass code implements, not a plain indexed-column `IS NULL` path.[create_index.sql#gin-array-index-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L250-L287) [create_index.out#gin-array-index-plan](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L672-L690) [create_index.sql#array-null-semantics](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L288-L301) [create_index.out#array-null-semantics](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L903-L920)

BRIN tests generate `IS` and `IS NOT` NULL conditions for BRIN operator classes, force BRIN bitmap scans, compare them with sequential-scan results, and raise a warning if the result sets differ.[brin.sql#brin-null-test-data](../../../../raw/postgres-12/src/test/regress/sql/brin.sql#L101-L130) [brin.sql#brin-null-operators](../../../../raw/postgres-12/src/test/regress/sql/brin.sql#L276-L282) [brin.sql#brin-test-loop](../../../../raw/postgres-12/src/test/regress/sql/brin.sql#L292-L366) [brin.out#brin-null-operators](../../../../raw/postgres-12/src/test/regress/expected/brin.out#L276-L324)

The reviewed hash and contrib Bloom regression files did not include direct NULL-search regression tests. Their NULL behavior above is source-backed by insertion and scan code, and Bloom is also documented as not supporting NULL search.[hashutil.c#_hash_convert_tuple](../../../../raw/postgres-12/src/backend/access/hash/hashutil.c#L312-L343) [hashsearch.c#_hash_first](../../../../raw/postgres-12/src/backend/access/hash/hashsearch.c#L325-L330) [bloom.sql#bloom-basic-tests](../../../../raw/postgres-12/contrib/bloom/sql/bloom.sql#L1-L30) [bloom.out#bloom-basic-plans](../../../../raw/postgres-12/contrib/bloom/expected/bloom.out#L33-L60) [bloom.sgml#limitations](../../../../raw/postgres-12/doc/src/sgml/bloom.sgml#L228-L259)

## Context Reviewed

- `wiki/versions.md`, `wiki/index.md`, `wiki/log.md`, and `wiki/v12/index.md` for navigation and pinned version context.
- `raw/postgres-12/src/include/catalog/pg_am.dat` and `raw/postgres-12/doc/src/sgml/ref/create_index.sgml` for PostgreSQL 12 index access-method inventory.
- Shared index executor, catalog, tuple, planner, and scan-key code: `src/backend/catalog/index.c`, `src/backend/executor/execIndexing.c`, `src/backend/access/index/indexam.c`, `src/backend/access/common/indextuple.c`, `src/include/access/itup.h`, `src/include/access/skey.h`, `src/include/access/amapi.h`, and `src/backend/optimizer/path/indxpath.c`.
- B-tree source, docs, and tests: `src/backend/access/nbtree/*`, `doc/src/sgml/indices.sgml`, `doc/src/sgml/ref/create_table.sgml`, `doc/src/sgml/ref/create_index.sgml`, and `src/test/regress/sql|expected/create_index.*`.
- Hash source: `src/backend/access/hash/*`.
- GiST source, docs, and tests: `src/backend/access/gist/*`, `doc/src/sgml/gist.sgml`, and `src/test/regress/sql|expected/create_index.*`.
- SP-GiST source, docs, and tests: `src/backend/access/spgist/*`, `src/include/access/spgist_private.h`, `doc/src/sgml/spgist.sgml`, and `src/test/regress/sql|expected/create_index_spgist.*`.
- GIN source, docs, and tests: `src/backend/access/gin/*`, `src/include/access/ginblock.h`, `doc/src/sgml/gin.sgml`, and `src/test/regress/sql|expected/create_index.*`.
- BRIN source, docs, and tests: `src/backend/access/brin/*`, `src/include/access/brin_tuple.h`, `doc/src/sgml/brin.sgml`, and `src/test/regress/sql|expected/brin.*`.
- Contrib Bloom source, docs, and tests: `contrib/bloom/*` and `doc/src/sgml/bloom.sgml`.

## Evidence Map

| Claim | Primary evidence |
| --- | --- |
| The executor passes values and NULL flags to each index access method. | [index.c#FormIndexDatum](../../../../raw/postgres-12/src/backend/catalog/index.c#L2578-L2648), [execIndexing.c#ExecInsertIndexTuples](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L314-L400), [indexam.c#index_insert](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L165-L189) |
| Generic `IS NULL` index matching requires `amsearchnulls`. | [amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L163-L199), [skey.h#ScanKey-flags](../../../../raw/postgres-12/src/include/access/skey.h#L43-L51), [indxpath.c#match_clause_to_indexcol](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2408-L2444) |
| B-tree stores NULLs, can search them, orders them, and treats them as distinct for uniqueness. | [nbtree.c#bthandler](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L102-L130), [nbtutils.c#_bt_mkscankey](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L95-L154), [nbtsearch.c#_bt_compare](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L545-L625), [nbtinsert.c#btinsert](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L90-L116) |
| Hash skips NULL entries and cannot search NULLs. | [hash.c#hashhandler](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L54-L83), [hash.c#hashinsert](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L239-L269), [hashutil.c#_hash_convert_tuple](../../../../raw/postgres-12/src/backend/access/hash/hashutil.c#L312-L343), [hashsearch.c#_hash_first](../../../../raw/postgres-12/src/backend/access/hash/hashsearch.c#L325-L330) |
| GiST stores NULL index attributes and supports NULL tests with page-level caveats. | [gist.c#gisthandler](../../../../raw/postgres-12/src/backend/access/gist/gist.c#L55-L82), [gistutil.c#gistFormTuple](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L576-L624), [gistget.c#gistindex_keytest](../../../../raw/postgres-12/src/backend/access/gist/gistget.c#L173-L191) |
| SP-GiST stores NULLs in a separate NULL tree and supports NULL tests. | [spgutils.c#spghandler](../../../../raw/postgres-12/src/backend/access/spgist/spgutils.c#L36-L62), [spgist_private.h#SPGIST-layout](../../../../raw/postgres-12/src/include/access/spgist_private.h#L24-L62), [spgdoinsert.c#spgdoinsert-null-root](../../../../raw/postgres-12/src/backend/access/spgist/spgdoinsert.c#L1963-L2058), [spgscan.c#spgPrepareScanKeys](../../../../raw/postgres-12/src/backend/access/spgist/spgscan.c#L192-L297), [spgscan.c#resetSpGistScanOpaque](../../../../raw/postgres-12/src/backend/access/spgist/spgscan.c#L145-L168) |
| GIN stores NULL categories for GIN key semantics but does not expose generic `IS NULL` matching. | [ginutil.c#ginhandler](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L33-L58), [ginblock.h#GinNullCategory](../../../../raw/postgres-12/src/include/access/ginblock.h#L199-L216), [ginutil.c#ginExtractEntries](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L484-L600), [ginscan.c#startScanKey](../../../../raw/postgres-12/src/backend/access/gin/ginscan.c#L296-L365) |
| BRIN summarizes NULLs with `hasnulls` and `allnulls`, and can search NULL tests at range granularity. | [brin.c#brinhandler](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L81-L107), [brin_tuple.c#tuple-layout](../../../../raw/postgres-12/src/backend/access/brin/brin_tuple.c#L15-L24), [brin_minmax.c#brin_minmax_consistent](../../../../raw/postgres-12/src/backend/access/brin/brin_minmax.c#L154-L188), [brin_inclusion.c#brin_inclusion_consistent](../../../../raw/postgres-12/src/backend/access/brin/brin_inclusion.c#L266-L300) |
| Contrib Bloom skips NULL columns and does not support NULL search. | [blutils.c#blhandler](../../../../raw/postgres-12/contrib/bloom/blutils.c#L101-L122), [blutils.c#BloomFormTuple](../../../../raw/postgres-12/contrib/bloom/blutils.c#L286-L302), [blscan.c#blgetbitmap](../../../../raw/postgres-12/contrib/bloom/blscan.c#L89-L113), [bloom.sgml#limitations](../../../../raw/postgres-12/doc/src/sgml/bloom.sgml#L228-L259) |

## Open Questions

None for source behavior at the pinned PostgreSQL 12 commit. The reviewed regression suite has direct NULL-predicate coverage for B-tree, GiST, SP-GiST, and BRIN, plus GIN array NULL operator semantics. Hash and contrib Bloom NULL behavior is source-backed; Bloom is also documentation-backed.

## Source References

- [pg_am.dat#built-in-index-ams](../../../../raw/postgres-12/src/include/catalog/pg_am.dat#L18-L35)
- [create_index.sgml#access-method](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L230-L239)
- [amapi.h#IndexAmRoutine](../../../../raw/postgres-12/src/include/access/amapi.h#L163-L199)
- [skey.h#ScanKey-flags](../../../../raw/postgres-12/src/include/access/skey.h#L43-L51)
- [skey.h#ScanKey-flags-definitions](../../../../raw/postgres-12/src/include/access/skey.h#L115-L122)
- [indxpath.c#match_clause_to_indexcol](../../../../raw/postgres-12/src/backend/optimizer/path/indxpath.c#L2408-L2444)
- [index.c#FormIndexDatum](../../../../raw/postgres-12/src/backend/catalog/index.c#L2578-L2648)
- [execIndexing.c#ExecInsertIndexTuples](../../../../raw/postgres-12/src/backend/executor/execIndexing.c#L314-L400)
- [indexam.c#index_insert](../../../../raw/postgres-12/src/backend/access/index/indexam.c#L165-L189)
- [itup.h#IndexTupleHasNulls](../../../../raw/postgres-12/src/include/access/itup.h#L65-L89)
- [itup.h#index_getattr](../../../../raw/postgres-12/src/include/access/itup.h#L100-L127)
- [indextuple.c#index_form_tuple](../../../../raw/postgres-12/src/backend/access/common/indextuple.c#L112-L188)
- [nbtree.c#bthandler](../../../../raw/postgres-12/src/backend/access/nbtree/nbtree.c#L102-L130)
- [nbtutils.c#_bt_mkscankey](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L95-L154)
- [nbtutils.c#_bt_preprocess_keys](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1182-L1222)
- [nbtutils.c#_bt_checkkeys](../../../../raw/postgres-12/src/backend/access/nbtree/nbtutils.c#L1400-L1435)
- [nbtsearch.c#_bt_compare](../../../../raw/postgres-12/src/backend/access/nbtree/nbtsearch.c#L545-L625)
- [nbtinsert.c#btinsert](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L90-L116)
- [nbtinsert.c#_bt_check_unique](../../../../raw/postgres-12/src/backend/access/nbtree/nbtinsert.c#L338-L380)
- [indices.sgml#indexes-is-null](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L149-L152)
- [indices.sgml#indexes-ordering](../../../../raw/postgres-12/doc/src/sgml/indices.sgml#L505-L529)
- [create_index.sgml#NULLS-FIRST-LAST](../../../../raw/postgres-12/doc/src/sgml/ref/create_index.sgml#L304-L320)
- [create_table.sgml#unique-constraints](../../../../raw/postgres-12/doc/src/sgml/ref/create_table.sgml#L878-L899)
- [hash.c#hashhandler](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L54-L83)
- [hash.c#hashinsert](../../../../raw/postgres-12/src/backend/access/hash/hash.c#L239-L269)
- [hashutil.c#_hash_convert_tuple](../../../../raw/postgres-12/src/backend/access/hash/hashutil.c#L312-L343)
- [hashsearch.c#_hash_first](../../../../raw/postgres-12/src/backend/access/hash/hashsearch.c#L325-L330)
- [gist.c#gisthandler](../../../../raw/postgres-12/src/backend/access/gist/gist.c#L55-L82)
- [gist.c#gistinsert](../../../../raw/postgres-12/src/backend/access/gist/gist.c#L146-L183)
- [gistutil.c#gistMakeUnionItVec](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L151-L210)
- [gistutil.c#gistMakeUnionKey](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L234-L276)
- [gistutil.c#gistFormTuple](../../../../raw/postgres-12/src/backend/access/gist/gistutil.c#L576-L624)
- [gistscan.c#gistrescan](../../../../raw/postgres-12/src/backend/access/gist/gistscan.c#L242-L272)
- [gistget.c#gistindex_keytest](../../../../raw/postgres-12/src/backend/access/gist/gistget.c#L173-L191)
- [spgutils.c#spghandler](../../../../raw/postgres-12/src/backend/access/spgist/spgutils.c#L36-L62)
- [spgist_private.h#SPGIST-layout](../../../../raw/postgres-12/src/include/access/spgist_private.h#L24-L62)
- [spginsert.c#spgbuildempty](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L84-L110)
- [spginsert.c#spginsert](../../../../raw/postgres-12/src/backend/access/spgist/spginsert.c#L207-L232)
- [spgdoinsert.c#spgdoinsert-null-opclass-boundary](../../../../raw/postgres-12/src/backend/access/spgist/spgdoinsert.c#L1890-L1925)
- [spgdoinsert.c#spgdoinsert-null-root](../../../../raw/postgres-12/src/backend/access/spgist/spgdoinsert.c#L1963-L2058)
- [spgscan.c#spgAddStartItem](../../../../raw/postgres-12/src/backend/access/spgist/spgscan.c#L121-L133)
- [spgscan.c#spgPrepareScanKeys](../../../../raw/postgres-12/src/backend/access/spgist/spgscan.c#L192-L297)
- [spgscan.c#resetSpGistScanOpaque](../../../../raw/postgres-12/src/backend/access/spgist/spgscan.c#L145-L168)
- [spgscan.c#spgLeafTest](../../../../raw/postgres-12/src/backend/access/spgist/spgscan.c#L470-L555)
- [spgscan.c#spgWalk](../../../../raw/postgres-12/src/backend/access/spgist/spgscan.c#L769-L879)
- [spgist.sgml#null-values](../../../../raw/postgres-12/doc/src/sgml/spgist.sgml#L272-L280)
- [gin.sgml#intro](../../../../raw/postgres-12/doc/src/sgml/gin.sgml#L14-L36)
- [ginutil.c#ginhandler](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L33-L58)
- [ginblock.h#GinNullCategory](../../../../raw/postgres-12/src/include/access/ginblock.h#L199-L216)
- [ginutil.c#ginExtractEntries](../../../../raw/postgres-12/src/backend/access/gin/ginutil.c#L484-L600)
- [gininsert.c#ginEntryInsert](../../../../raw/postgres-12/src/backend/access/gin/gininsert.c#L468-L532)
- [ginscan.c#startScanKey](../../../../raw/postgres-12/src/backend/access/gin/ginscan.c#L296-L365)
- [ginarrayproc.c#ginarrayextract](../../../../raw/postgres-12/src/backend/access/gin/ginarrayproc.c#L30-L58)
- [ginarrayproc.c#ginqueryarrayextract](../../../../raw/postgres-12/src/backend/access/gin/ginarrayproc.c#L82-L112)
- [ginarrayproc.c#ginarrayconsistent](../../../../raw/postgres-12/src/backend/access/gin/ginarrayproc.c#L154-L185)
- [ginarrayproc.c#ginarraytriconsistent](../../../../raw/postgres-12/src/backend/access/gin/ginarrayproc.c#L230-L270)
- [brin.c#brinhandler](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L81-L107)
- [brin.c#brinbuildCallback](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L645-L655)
- [brin.c#brinbuild](../../../../raw/postgres-12/src/backend/access/brin/brin.c#L723-L724)
- [brin_tuple.c#tuple-layout](../../../../raw/postgres-12/src/backend/access/brin/brin_tuple.c#L15-L24)
- [brin_tuple.c#brin_form_tuple](../../../../raw/postgres-12/src/backend/access/brin/brin_tuple.c#L135-L160)
- [brin_tuple.c#brin_deform_tuple](../../../../raw/postgres-12/src/backend/access/brin/brin_tuple.c#L507-L538)
- [brin_tuple.h#BrinValues](../../../../raw/postgres-12/src/include/access/brin_tuple.h#L23-L45)
- [README#BRIN-tuples](../../../../raw/postgres-12/src/backend/access/brin/README#L50-L62)
- [brin_minmax.c#brin_minmax_add_value](../../../../raw/postgres-12/src/backend/access/brin/brin_minmax.c#L75-L106)
- [brin_minmax.c#brin_minmax_consistent](../../../../raw/postgres-12/src/backend/access/brin/brin_minmax.c#L154-L188)
- [brin_inclusion.c#brin_inclusion_add_value](../../../../raw/postgres-12/src/backend/access/brin/brin_inclusion.c#L148-L177)
- [brin_inclusion.c#brin_inclusion_consistent](../../../../raw/postgres-12/src/backend/access/brin/brin_inclusion.c#L266-L300)
- [brin.sgml#intro](../../../../raw/postgres-12/doc/src/sgml/brin.sgml#L14-L40)
- [brin.sgml#maintenance](../../../../raw/postgres-12/doc/src/sgml/brin.sgml#L62-L82)
- [bloom.sgml#operator-classes](../../../../raw/postgres-12/doc/src/sgml/bloom.sgml#L214-L225)
- [bloom.sgml#limitations](../../../../raw/postgres-12/doc/src/sgml/bloom.sgml#L228-L259)
- [blutils.c#blhandler](../../../../raw/postgres-12/contrib/bloom/blutils.c#L101-L122)
- [blutils.c#BloomFormTuple](../../../../raw/postgres-12/contrib/bloom/blutils.c#L286-L302)
- [blscan.c#blgetbitmap](../../../../raw/postgres-12/contrib/bloom/blscan.c#L89-L113)
- [create_index.sql#btree-null-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L603-L676)
- [create_index.out#btree-null-tests](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1566-L1724)
- [create_index.sql#unique-expression-null-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L393-L423)
- [create_index.out#unique-expression-null-tests](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L1274-L1315)
- [create_index.sql#gist-null-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L80-L149)
- [create_index.out#gist-null-results](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L196-L205)
- [create_index.out#gist-null-plans](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L538-L559)
- [create_index_spgist.sql#spgist-null-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index_spgist.sql#L1-L40)
- [create_index_spgist.out#spgist-null-plans](../../../../raw/postgres-12/src/test/regress/expected/create_index_spgist.out#L181-L205)
- [create_index.sql#gin-array-index-tests](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L250-L287)
- [create_index.out#gin-array-index-plan](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L672-L690)
- [create_index.sql#array-null-semantics](../../../../raw/postgres-12/src/test/regress/sql/create_index.sql#L288-L301)
- [create_index.out#array-null-semantics](../../../../raw/postgres-12/src/test/regress/expected/create_index.out#L903-L920)
- [brin.sql#brin-null-test-data](../../../../raw/postgres-12/src/test/regress/sql/brin.sql#L101-L130)
- [brin.sql#brin-null-operators](../../../../raw/postgres-12/src/test/regress/sql/brin.sql#L276-L282)
- [brin.sql#brin-test-loop](../../../../raw/postgres-12/src/test/regress/sql/brin.sql#L292-L366)
- [brin.out#brin-null-operators](../../../../raw/postgres-12/src/test/regress/expected/brin.out#L276-L324)
- [bloom.sql#bloom-basic-tests](../../../../raw/postgres-12/contrib/bloom/sql/bloom.sql#L1-L30)
- [bloom.out#bloom-basic-plans](../../../../raw/postgres-12/contrib/bloom/expected/bloom.out#L33-L60)

## Navigation

- [PostgreSQL 12 index](../../index.md)
- [PostgreSQL 12 codebase navigation guide](../../codebase-navigation-guide.md)
- [Wiki index](../../../index.md)
- [Versions](../../../versions.md)
