---
type: question
version: 18
pinned_commit: baa7b142aace6821ce085906f314a75bcc4d95c8
verified: false
verified_by_agent: not yet
---

# Limiting Query Text Size in pg_stat_statements in PostgreSQL 18 (unverified)

## Question

> Follow AGENTS.md.
> In PostgreSQL 18, is there a way to limit the size of query texts in `pg_stat_statements`?

## Short Answer

No. PostgreSQL 18's `pg_stat_statements` has no setting that limits or truncates the length of an individual representative query text. The extension defines exactly five GUCs — `max`, `track`, `track_utility`, `track_planning`, and `save` — and none of them caps text length [pg_stat_statements.c#custom-GUCs](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L407-L463). Each statement's text is written to the external file at its full length; the only ceiling is the whole file's theoretical maximum, not a per-statement limit [pg_stat_statements.c#qtext_store](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L2230-L2296).

`track_activity_query_size` does **not** apply here. It caps `pg_stat_activity.query`, not `pg_stat_statements.query`; see [How track_activity_query_size Is Used in PostgreSQL 18 (unverified)](track-activity-query-size.md).

What you can control is *how much total* text accumulates, not the size of any one text:

- Lower `pg_stat_statements.max` to bound the number of stored texts. This is the lever the documentation explicitly recommends when the text file grows too large [pgstatstatements.sgml#representative-query-texts](../../../../raw/postgres-18/doc/src/sgml/pgstatstatements.sgml#L719-L731).
- The extension may discard **all** query texts (set every `query` field to NULL) as a last-resort recovery when the file becomes unmanageable; it never truncates a text to a configured length [pgstatstatements.sgml#representative-query-texts](../../../../raw/postgres-18/doc/src/sgml/pgstatstatements.sgml#L719-L731) [pg_stat_statements.c#gc_qtexts-drop](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L2532-L2539).

## Why There Is No Per-Text Length Cap

The full GUC set is defined once in `_PG_init()`. There is no length, byte-limit, or truncation parameter among them [pg_stat_statements.c#custom-GUCs](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L407-L463):

| GUC | What it limits |
|---|---|
| `pg_stat_statements.max` | Number of tracked entries (rows), not text length [pg_stat_statements.c#max](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L407-L418). |
| `pg_stat_statements.track` | Which statements are tracked (`top`/`all`/`none`) [pg_stat_statements.c#track](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L420-L430). |
| `pg_stat_statements.track_utility` | Whether utility commands are tracked [pg_stat_statements.c#track_utility](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L432-L441). |
| `pg_stat_statements.track_planning` | Whether planning duration is tracked [pg_stat_statements.c#track_planning](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L443-L452). |
| `pg_stat_statements.save` | Whether stats persist across shutdown [pg_stat_statements.c#save](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L454-L463). |

The text-handling code confirms there is no truncation step:

- `CleanQuerytext()` only applies the statement's start offset and trims leading/trailing whitespace; it does not cap length [queryjumblefuncs.c#CleanQuerytext](../../../../raw/postgres-18/src/backend/nodes/queryjumblefuncs.c#L86-L128).
- `qtext_store()` writes exactly `query_len` bytes plus a `\0`. The only guard rejects a write that would exceed `MaxAllocHugeSize` for the whole file (a 32-bit overflow safeguard), which fails the store rather than truncating the text [pg_stat_statements.c#qtext_store](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L2240-L2296).

Normalization can *shorten* a stored text by replacing constants with `$n` and squashing constant lists into one placeholder, but that is identity-driven normalization, not a configurable size limit [pg_stat_statements.c#generate_normalized_query](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L2792-L2895).

PostgreSQL 18.6 changed how that normalized text is buffered, and it is worth being precise that this is **not** a new length cap. `generate_normalized_query()` used to write into a fixed `palloc(query_len + clocations_count * 10 + 1)` allocation. That arithmetic did not account for the ` /*, ... */` comment appended for each squashed list, so a query with many squashable lists could write past the allocation. `8a31ffc2d4c` ("pg_stat_statements: Fix buffer overflow with query normalization", CVE-2026-14676, back-patched through 18) replaced the fixed buffer with an expansible `StringInfo`: `initStringInfoExt(&norm_query, query_len + jstate->clocations_count * 10)` reserves the same amount as a *hint*, and the body then appends with `appendBinaryStringInfo()` and `appendStringInfo()`, enlarging the buffer whenever the reserve is not enough [pg_stat_statements.c#generate_normalized_query](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L2792-L2895) [pg_stat_statements.c#initStringInfoExt-reserve](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L2823-L2828) [release-18.sgml#CVE-2026-14676](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L989-L1012). The final `*query_len_p = norm_query.len` is whatever the normalized text actually needs, so the answer above is unchanged: no per-statement length limit exists, and the reserve is now a hint rather than a limit.

## Edge Path: The File Can Grow, Then Texts Are Dropped Wholesale

The external file `pgss_query_texts.stat` holds all representative texts; the shared hash entry stores only an offset, length, and encoding [pg_stat_statements.c#pgssEntry](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L231-L246). Two functions manage its size, and neither truncates individual texts:

- `need_gc_qtexts()` triggers garbage collection only when the file exceeds both `512 * pg_stat_statements.max` bytes and ~50% bloat versus `mean_query_len * max * 2`. It deliberately does nothing when the size is due to genuinely long texts: "Nothing can or should be done in the event of unusually large query texts accounting for file's large size." [pg_stat_statements.c#need_gc_qtexts](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L2425-L2456).
- `gc_qtexts()` compacts out orphaned (already-evicted) texts. If it cannot load the file (for example, OOM), it drops **all** texts by setting `query_offset = 0` and `query_len = -1` per entry, keeping the statistics; it does not shorten any text [pg_stat_statements.c#gc_qtexts](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L2474-L2539).

The documentation states the same: very lengthy texts can be stored, but if many long texts accumulate the file "might grow unmanageably large," and as a recovery method the extension "may choose to discard the query texts," after which `query` fields read NULL while statistics are preserved — and it suggests reducing `pg_stat_statements.max` to prevent recurrences [pgstatstatements.sgml#representative-query-texts](../../../../raw/postgres-18/doc/src/sgml/pgstatstatements.sgml#L719-L731).

## Practical Options If You Want Shorter Texts

These are workarounds, not built-in length controls:

- Lower `pg_stat_statements.max` (`PGC_POSTMASTER`; restart required) to bound the number of stored texts and the file size [pg_stat_statements.c#max](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L407-L418).
- Read `pg_stat_statements(showtext => false)` so the heavy text column is skipped at read time; this avoids loading the text file for the call but does not change what is stored on disk [pg_stat_statements.c#showtext-load](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L1761-L1799).
- Use SQL `left(query, N)` (or `substr`) in your monitoring query if you only need a truncated view of an otherwise full stored text.
- Shorten queries at the application layer (the only place a true length limit can be imposed in v18).

## GUC Change Scope

- `pg_stat_statements.max` is `PGC_POSTMASTER`: a change requires a **server restart** [pg_stat_statements.c#max](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L407-L418) [system-views.sgml#context-postmaster](../../../../raw/postgres-18/doc/src/sgml/system-views.sgml#L3700-L3712).

## Context Reviewed

- [pg_stat_statements.c#custom-GUCs](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L405-L463) - the complete GUC set; no length parameter.
- [pg_stat_statements.c#qtext_store](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L2230-L2296) - full-length text write and whole-file ceiling.
- [pg_stat_statements.c#gc-paths](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L2421-L2589) - `need_gc_qtexts`/`gc_qtexts` size management and wholesale text drop.
- [pg_stat_statements.c#pgssEntry](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L231-L246) - entry stores only offset/length/encoding.
- [pg_stat_statements.c#showtext-load](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L1745-L1799) - read-time `showtext` handling.
- [queryjumblefuncs.c#CleanQuerytext](../../../../raw/postgres-18/src/backend/nodes/queryjumblefuncs.c#L86-L128) - no truncation at clean step.
- [pgstatstatements.sgml#representative-query-texts](../../../../raw/postgres-18/doc/src/sgml/pgstatstatements.sgml#L719-L731) - external file growth and discard behavior.
- [How track_activity_query_size Is Used in PostgreSQL 18 (unverified)](track-activity-query-size.md) and [How pg_stat_statements Works (unverified)](pg-stat-statements.md) - adjacent pages for the related size GUC and overall mechanics.

## Evidence Map

| Claim | Source |
|---|---|
| There is no GUC to limit query-text length; only five GUCs exist | [pg_stat_statements.c#custom-GUCs](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L407-L463) |
| Texts are stored at full length; only a whole-file ceiling guards `qtext_store` | [pg_stat_statements.c#qtext_store](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L2240-L2296) |
| `CleanQuerytext` trims whitespace/offset only, no length cap | [queryjumblefuncs.c#CleanQuerytext](../../../../raw/postgres-18/src/backend/nodes/queryjumblefuncs.c#L86-L128) |
| GC won't shrink the file when long texts dominate; on failure it drops all texts (not truncate) | [pg_stat_statements.c#need_gc_qtexts](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L2425-L2456) [pg_stat_statements.c#gc_qtexts-drop](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L2532-L2539) |
| Docs: long texts allowed; discard is the recovery; reduce `max` | [pgstatstatements.sgml#representative-query-texts](../../../../raw/postgres-18/doc/src/sgml/pgstatstatements.sgml#L719-L731) |
| `max` is `PGC_POSTMASTER` (restart) | [pg_stat_statements.c#max](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c#L407-L418) [system-views.sgml#context-postmaster](../../../../raw/postgres-18/doc/src/sgml/system-views.sgml#L3700-L3712) |

## Source References

- [pg_stat_statements.c](../../../../raw/postgres-18/contrib/pg_stat_statements/pg_stat_statements.c) - GUC definitions, query-text storage, garbage collection, and read path.
- [pgstatstatements.sgml](../../../../raw/postgres-18/doc/src/sgml/pgstatstatements.sgml) - same-version documentation on representative query texts and file growth.
- [release-18.sgml](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml) - 18.6 release note for the normalization buffer-overrun fix.
- [queryjumblefuncs.c](../../../../raw/postgres-18/src/backend/nodes/queryjumblefuncs.c) - `CleanQuerytext` normalization input handling.
- [system-views.sgml](../../../../raw/postgres-18/doc/src/sgml/system-views.sgml) - `pg_settings` context meanings for GUC change scope.

## Open Questions

- No unresolved factual question remains for the "is there a length limit?" answer as of the 2026-08-17 repin to `baa7b142aace6821ce085906f314a75bcc4d95c8`. The one in-range change to `contrib/pg_stat_statements/pg_stat_statements.c` is `8a31ffc2d4c`, described above; it makes the normalization output buffer expansible and adds no cap, so the "No" answer stands. Nothing on this page was re-measured on a running server for that repin. The page is marked `(unverified)` because `verified:` is human-only and `verified_by_agent` has not been advanced after a separate full-page re-check.
