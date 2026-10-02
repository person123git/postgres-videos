---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# EXPLAIN ANALYZE BUFFERS Output in PostgreSQL 12 (unverified)

## Contents

- [Question](#question)
- [Short Answer](#short-answer)
- [What Each Field Means](#what-each-field-means)
- [How The Counters Are Collected](#how-the-counters-are-collected)
- [Where It Appears In The Plan](#where-it-appears-in-the-plan)
- [I/O Timing And `track_io_timing`](#io-timing-and-track_io_timing)
- [Reading Common Patterns](#reading-common-patterns)
- [Tests And Examples](#tests-and-examples)
- [Context Reviewed](#context-reviewed)
- [Evidence Map](#evidence-map)
- [Source References](#source-references)
- [Open Questions](#open-questions)
- [Related Pages](#related-pages)

## Question

In PostgreSQL 12, when a query uses `EXPLAIN (ANALYZE, BUFFERS)`, describe in detail all buffer information in the output.

## Short Answer

In PostgreSQL 12, `EXPLAIN (ANALYZE, BUFFERS)` executes the statement and adds buffer-use counters to the plan-node instrumentation. `BUFFERS` is rejected unless `ANALYZE` is also set, and `ExplainOnePlan` turns the option into `INSTRUMENT_BUFFERS` before it builds the `QueryDesc` and runs the executor [explain.c#ExplainQuery](../../../../raw/postgres-12/src/backend/commands/explain.c#L143) [explain.c#ExplainOnePlan](../../../../raw/postgres-12/src/backend/commands/explain.c#L466).

The text output prints lines like:

```text
Buffers: shared hit=15 read=4 dirtied=1 written=1, local hit=2 read=1 dirtied=1 written=1, temp read=12 written=12
I/O Timings: read=3.217 write=0.812
```

Those fields come directly from `BufferUsage`: shared blocks, local blocks, temp blocks, and optional read/write time [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19) [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2867). Text format prints only positive counters; non-text formats emit every buffer counter property and emit I/O time properties when `track_io_timing` is enabled [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2867).

## What Each Field Means

`shared` means blocks for ordinary relations and indexes in the shared buffer pool. `local` means blocks for temporary relations and indexes in the backend-local buffer pool. `temp` means short-lived working files used by operations such as sorts, hashes, materialization, and similar executor work [ref/explain.sgml#BUFFERS-def](../../../../raw/postgres-12/doc/src/sgml/ref/explain.sgml#L168-L192).

The counters are block counters, not tuple counters. A PostgreSQL data block is `BLCKSZ` bytes, typically 8kB in a normal build [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19) [config.sgml#BLCKSZ](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L1504).

| Output field | Meaning in PostgreSQL 12 |
|---|---|
| `shared hit=N` | The executor asked for a non-temporary relation block and found it already in the shared buffer pool. `ReadBuffer_common` increments `shared_blks_hit` when `BufferAlloc` reports `found` for a non-local buffer [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704). |
| `shared read=N` | The executor asked for a non-temporary relation block that was not already valid in shared buffers, and the buffer manager read it from the relation storage path. `ReadBuffer_common` increments `shared_blks_read` for normal read modes when the buffer was not found and the request is not an extension [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704). |
| `shared dirtied=N` | The query changed a previously clean shared buffer. `MarkBufferDirty` increments `shared_blks_dirtied` only when the buffer did not already have `BM_DIRTY` set [bufmgr.c#MarkBufferDirty](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1457). |
| `shared written=N` | This backend wrote shared relation data. PostgreSQL 12 increments this counter when relation extension allocates a new shared block in `ReadBuffer_common`, and also after `FlushBuffer` writes a shared dirty buffer with `smgrwrite` [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704) [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2672). |
| `local hit=N` | The executor asked for a temporary-relation block and found it in backend-local buffers. `ReadBuffer_common` increments `local_blks_hit` when `LocalBufferAlloc` reports `found` [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704). |
| `local read=N` | The executor asked for a temporary-relation block that had to be read into a backend-local buffer. `ReadBuffer_common` increments `local_blks_read` for normal read modes when the local buffer was not found and the request is not an extension [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704). |
| `local dirtied=N` | The query changed a previously clean backend-local buffer. `MarkLocalBufferDirty` increments `local_blks_dirtied` only when the local buffer did not already have `BM_DIRTY` set [localbuf.c#MarkLocalBufferDirty](../../../../raw/postgres-12/src/backend/storage/buffer/localbuf.c#L280). |
| `local written=N` | This backend wrote temporary-relation data. PostgreSQL 12 increments this counter for local relation extension in `ReadBuffer_common` and when `LocalBufferAlloc` writes out a dirty local buffer before reuse [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704) [localbuf.c#LocalBufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/localbuf.c#L103). |
| `temp read=N` | The executor read from a temporary work file through `BufFile`. `BufFileLoadBuffer` increments `temp_blks_read` when a `FileRead` loads bytes into the `BufFile` buffer [buffile.c#BufFileLoadBuffer](../../../../raw/postgres-12/src/backend/storage/file/buffile.c#L413). |
| `temp written=N` | The executor wrote to a temporary work file through `BufFile`. `BufFileDumpBuffer` increments `temp_blks_written` after successful `FileWrite` calls [buffile.c#BufFileDumpBuffer](../../../../raw/postgres-12/src/backend/storage/file/buffile.c#L452). |
| `I/O Timings: read=... write=...` | Optional elapsed time for database block reads and writes. `ReadBuffer_common` adds read time around `smgrread`; `FlushBuffer` adds write time around `smgrwrite`; `show_buffer_usage` prints the timing fields when they are present in text output [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704) [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2672) [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2867). |

## How The Counters Are Collected

`pgBufferUsage` is the backend-wide buffer-use accumulator. Plan nodes do not own separate counters while they run. Instead, instrumentation snapshots `pgBufferUsage` at node entry and adds the difference between the current value and the saved value at node exit [instrument.h#pgBufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L73) [instrument.c#InstrStartNode](../../../../raw/postgres-12/src/backend/executor/instrument.c#L63) [instrument.c#InstrStopNode](../../../../raw/postgres-12/src/backend/executor/instrument.c#L76).

Executor nodes get an `Instrumentation` object when `estate->es_instrument` is set, and the executor wrapper calls `InstrStartNode` before the node callback and `InstrStopNode` after it returns a slot [execProcnode.c#ExecInitNode](../../../../raw/postgres-12/src/backend/executor/execProcnode.c#L139) [execProcnode.c#ExecProcNodeInstr](../../../../raw/postgres-12/src/backend/executor/execProcnode.c#L455). Because a parent node is instrumented while it calls its children, an upper-level node includes the buffer use of its child nodes. The PostgreSQL 12 `EXPLAIN` reference states the same rule explicitly [ref/explain.sgml#BUFFERS-def](../../../../raw/postgres-12/doc/src/sgml/ref/explain.sgml#L168-L192).

Do not add every `Buffers:` line in the text plan to get a query total. A parent already includes its descendants, so summing parent and child lines double-counts the same work [ref/explain.sgml#BUFFERS-def](../../../../raw/postgres-12/doc/src/sgml/ref/explain.sgml#L168-L192).

The counters are event counters, not distinct-page counters. `ReadBuffer_common` increments a hit, read, or extension-written counter each time a buffer request follows that path, so repeated requests for the same block can increase the count more than once [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704).

## Where It Appears In The Plan

`ExplainNode` prints buffer usage for a plan node after the node-specific details, and only when `es->buffers` is true and the node has instrumentation [explain.c#ExplainNode](../../../../raw/postgres-12/src/backend/commands/explain.c#L1062). In text format, `show_buffer_usage` suppresses a `Buffers:` line when all shared, local, and temp counters are zero, and suppresses an `I/O Timings:` line when both timing fields are zero [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2867).

In parallel query, PostgreSQL 12 allocates per-worker `BufferUsage` slots in dynamic shared memory. A worker stores the delta from its parallel execution with `InstrEndParallelQuery`, and the leader later accumulates those worker values into its own `pgBufferUsage` with `InstrAccumParallelQuery` [execParallel.c#ExecInitParallelPlan](../../../../raw/postgres-12/src/backend/executor/execParallel.c#L561) [execParallel.c#ParallelQueryMain](../../../../raw/postgres-12/src/backend/executor/execParallel.c#L1330) [execParallel.c#ExecParallelFinish](../../../../raw/postgres-12/src/backend/executor/execParallel.c#L1073). `EXPLAIN (ANALYZE, VERBOSE, BUFFERS)` can print per-worker buffer detail because `ExplainNode` walks `worker_instrument` and calls `show_buffer_usage` for each worker [explain.c#ExplainNode](../../../../raw/postgres-12/src/backend/commands/explain.c#L1062).

Trigger functions are instrumented when trigger instrumentation is allocated, but the trigger report in PostgreSQL 12 prints trigger time and calls only. `report_triggers` does not call `show_buffer_usage`, so the separate `Trigger ...` summary does not display buffer fields [execMain.c#InitResultRelInfo](../../../../raw/postgres-12/src/backend/executor/execMain.c#L1277) [trigger.c#ExecCallTriggerFunc](../../../../raw/postgres-12/src/backend/commands/trigger.c#L2373) [explain.c#report_triggers](../../../../raw/postgres-12/src/backend/commands/explain.c#L907).

## I/O Timing And `track_io_timing`

`I/O Timings` depends on the `track_io_timing` GUC. PostgreSQL 12 defines `track_io_timing` as `PGC_SUSET`, off by default, and backed by the `track_io_timing` variable [guc.c#track_io_timing](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1402). By the wiki GUC context mapping, `PGC_SUSET` is a superuser-settable session/transaction-scope setting, so enabling it for a session does not require restart or reload. A superuser can use:

```sql
SET /* wiki_enable_track_io_timing */ track_io_timing = on;
```

The PostgreSQL 12 documentation says this setting repeatedly queries the operating system clock and may add overhead on some platforms [config.sgml#track_io_timing](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6854).

## Reading Common Patterns

High `shared hit` and low `shared read` means the plan mostly found ordinary table or index blocks already in the shared buffer pool. That still represents buffer traffic, not free work, because the executor still requested those blocks through the buffer manager [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704).

High `shared read` means the plan had to load ordinary table or index blocks that were not already in shared buffers. PostgreSQL 12 records the read counter before the `smgrread` path that fills the buffer [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704).

High `temp read` or `temp written` points to executor work files rather than table or index pages. In PostgreSQL 12 those counters are updated by `BufFile`, the file abstraction used for temporary buffered files [buffile.c#BufFileLoadBuffer](../../../../raw/postgres-12/src/backend/storage/file/buffile.c#L413) [buffile.c#BufFileDumpBuffer](../../../../raw/postgres-12/src/backend/storage/file/buffile.c#L452).

High `dirtied` means the query turned clean buffers dirty. High `written` means the backend wrote relation data during the query, either by relation extension or by flushing/reusing dirty buffers on the source paths above [bufmgr.c#MarkBufferDirty](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1457) [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704) [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2672) [localbuf.c#LocalBufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/localbuf.c#L103).

## Tests And Examples

The same-checkout documentation includes a worked `EXPLAIN (ANALYZE, BUFFERS)` example that shows parent and child `Buffers:` lines for a bitmap heap scan with bitmap index scan children [perform.sgml#EXPLAIN-BUFFERS-example](../../../../raw/postgres-12/doc/src/sgml/perform.sgml#L694-L718).

The regression suite has some `EXPLAIN ANALYZE` coverage, but no `EXPLAIN (ANALYZE, BUFFERS)` case and no expected output containing literal `Buffers:`. Specific findings:

- `select_parallel.sql:399` exercises `EXPLAIN (analyze, timing off, summary off, costs off)` but does not include `BUFFERS`.
- `tidscan.sql:71-82` exercises `EXPLAIN (ANALYZE, COSTS OFF, SUMMARY OFF, TIMING OFF)` for cursor-based updates but does not include `BUFFERS`.
- Other regression EXPLAIN tests also omit `BUFFERS`; most are plan-shape checks with costs disabled, sometimes with verbose/timing option variants.
- No file in `src/test/regress/expected/*.out` contains the literal string `Buffers:` as EXPLAIN output (only `rules.out` references `buffers_*` column names in `pg_stat_bgwriter` queries).
- `src/test/isolation/`: no isolation test spec contains `Buffers:` output.
- `contrib/auto_explain.c` sets `INSTRUMENT_BUFFERS` internally but has no `Buffers:` output assertion; `src/bin/psql/tab-complete.c` only lists `BUFFERS` in psql tab-completion hints.

This is a test-coverage gap for literal `Buffers:` output formatting, though the behavior source in `explain.c#show_buffer_usage` is fully documented [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2867).

## Context Reviewed

- [explain.c#ExplainQuery](../../../../raw/postgres-12/src/backend/commands/explain.c#L143)
- [explain.c#ExplainOnePlan](../../../../raw/postgres-12/src/backend/commands/explain.c#L466)
- [explain.c#ExplainNode](../../../../raw/postgres-12/src/backend/commands/explain.c#L1062)
- [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2867)
- [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19)
- [instrument.c#InstrStartNode](../../../../raw/postgres-12/src/backend/executor/instrument.c#L63)
- [instrument.c#InstrStopNode](../../../../raw/postgres-12/src/backend/executor/instrument.c#L76)
- [execProcnode.c#ExecProcNodeInstr](../../../../raw/postgres-12/src/backend/executor/execProcnode.c#L455)
- [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704)
- [bufmgr.c#MarkBufferDirty](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1457)
- [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2672)
- [localbuf.c#LocalBufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/localbuf.c#L103)
- [localbuf.c#MarkLocalBufferDirty](../../../../raw/postgres-12/src/backend/storage/buffer/localbuf.c#L280)
- [buffile.c#BufFileLoadBuffer](../../../../raw/postgres-12/src/backend/storage/file/buffile.c#L413)
- [buffile.c#BufFileDumpBuffer](../../../../raw/postgres-12/src/backend/storage/file/buffile.c#L452)
- [execParallel.c#ParallelQueryMain](../../../../raw/postgres-12/src/backend/executor/execParallel.c#L1330)
- [ref/explain.sgml#BUFFERS](../../../../raw/postgres-12/doc/src/sgml/ref/explain.sgml#L43)
- [ref/explain.sgml#BUFFERS-def](../../../../raw/postgres-12/doc/src/sgml/ref/explain.sgml#L168-L192)
- [perform.sgml#EXPLAIN-BUFFERS-example](../../../../raw/postgres-12/doc/src/sgml/perform.sgml#L694-L718)
- [auto_explain.c#INSTRUMENT_BUFFERS](../../../../raw/postgres-12/contrib/auto_explain/auto_explain.c#L282)
- [select_parallel.sql:399](../../../../raw/postgres-12/src/test/regress/sql/select_parallel.sql#L399)
- [tidscan.sql:71-82](../../../../raw/postgres-12/src/test/regress/sql/tidscan.sql#L71-L82)

## Evidence Map

| Claim | Source |
|---|---|
| `BUFFERS` requires `ANALYZE` | [explain.c#ExplainQuery](../../../../raw/postgres-12/src/backend/commands/explain.c#L143) |
| `BUFFERS` maps to `INSTRUMENT_BUFFERS` | [explain.c#ExplainOnePlan](../../../../raw/postgres-12/src/backend/commands/explain.c#L466) |
| Buffer counters are stored in `BufferUsage` | [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19) |
| Plan nodes capture deltas from `pgBufferUsage` | [instrument.c#InstrStartNode](../../../../raw/postgres-12/src/backend/executor/instrument.c#L63) [instrument.c#InstrStopNode](../../../../raw/postgres-12/src/backend/executor/instrument.c#L76) |
| Text format prints only positive buffer counters | [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2867) |
| Non-text formats emit explicit buffer properties | [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2867) |
| Upper nodes include child-node buffer use | [ref/explain.sgml#BUFFERS-def](../../../../raw/postgres-12/doc/src/sgml/ref/explain.sgml#L168-L192) |
| Shared/local hit/read/written counters are updated by `ReadBuffer_common` | [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704) |
| Shared dirty/write counters are updated by dirty/flush paths | [bufmgr.c#MarkBufferDirty](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1457) [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2672) |
| Local dirty/write counters are updated by local buffer paths | [localbuf.c#MarkLocalBufferDirty](../../../../raw/postgres-12/src/backend/storage/buffer/localbuf.c#L280) [localbuf.c#LocalBufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/localbuf.c#L103) |
| Temp read/write counters are updated by `BufFile` | [buffile.c#BufFileLoadBuffer](../../../../raw/postgres-12/src/backend/storage/file/buffile.c#L413) [buffile.c#BufFileDumpBuffer](../../../../raw/postgres-12/src/backend/storage/file/buffile.c#L452) |
| Parallel workers report buffer usage through DSM and leader accumulation | [execParallel.c#ParallelQueryMain](../../../../raw/postgres-12/src/backend/executor/execParallel.c#L1330) [execParallel.c#ExecParallelFinish](../../../../raw/postgres-12/src/backend/executor/execParallel.c#L1073) |
| `track_io_timing` is superuser-settable and off by default | [guc.c#track_io_timing](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1402) |
| Same-version documentation includes a `BUFFERS` example | [perform.sgml#EXPLAIN-BUFFERS-example](../../../../raw/postgres-12/doc/src/sgml/perform.sgml#L694-L718) |
| Regression suite has `EXPLAIN ANALYZE` but no `BUFFERS` case | `select_parallel.sql:399` and `tidscan.sql:71-82` use `EXPLAIN (ANALYZE, ...)` without `BUFFERS`; no expected output contains literal `Buffers:` |

## Source References

- [explain.c#ExplainQuery](../../../../raw/postgres-12/src/backend/commands/explain.c#L143) - parses `EXPLAIN` options and rejects `BUFFERS` without `ANALYZE`.
- [explain.c#ExplainOnePlan](../../../../raw/postgres-12/src/backend/commands/explain.c#L466) - maps `BUFFERS` to executor instrumentation and runs the plan.
- [explain.c#ExplainNode](../../../../raw/postgres-12/src/backend/commands/explain.c#L1062) - decides where buffer usage is printed for each node and worker.
- [explain.c#show_buffer_usage](../../../../raw/postgres-12/src/backend/commands/explain.c#L2867) - formats text, JSON, XML, and YAML buffer output.
- [instrument.h#BufferUsage](../../../../raw/postgres-12/src/include/executor/instrument.h#L19) - defines all buffer counters and I/O timing fields.
- [instrument.c#InstrStartNode](../../../../raw/postgres-12/src/backend/executor/instrument.c#L63) and [instrument.c#InstrStopNode](../../../../raw/postgres-12/src/backend/executor/instrument.c#L76) - snapshot and accumulate per-node buffer deltas.
- [execProcnode.c#ExecProcNodeInstr](../../../../raw/postgres-12/src/backend/executor/execProcnode.c#L455) - wraps node execution with instrumentation.
- [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704) - shared/local hit/read/extension-write accounting and read timing.
- [bufmgr.c#MarkBufferDirty](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L1457) - shared dirty accounting.
- [bufmgr.c#FlushBuffer](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L2672) - shared write accounting and write timing.
- [localbuf.c#LocalBufferAlloc](../../../../raw/postgres-12/src/backend/storage/buffer/localbuf.c#L103) - local dirty-buffer write accounting.
- [localbuf.c#MarkLocalBufferDirty](../../../../raw/postgres-12/src/backend/storage/buffer/localbuf.c#L280) - local dirty accounting.
- [buffile.c#BufFileLoadBuffer](../../../../raw/postgres-12/src/backend/storage/file/buffile.c#L413) and [buffile.c#BufFileDumpBuffer](../../../../raw/postgres-12/src/backend/storage/file/buffile.c#L452) - temp file read/write accounting.
- [execParallel.c#ExecInitParallelPlan](../../../../raw/postgres-12/src/backend/executor/execParallel.c#L561), [execParallel.c#ParallelQueryMain](../../../../raw/postgres-12/src/backend/executor/execParallel.c#L1330), and [execParallel.c#ExecParallelFinish](../../../../raw/postgres-12/src/backend/executor/execParallel.c#L1073) - parallel worker buffer accounting.
- [guc.c#track_io_timing](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L1402) - `track_io_timing` GUC definition.
- [ref/explain.sgml#BUFFERS-def](../../../../raw/postgres-12/doc/src/sgml/ref/explain.sgml#L168-L192) - user-facing definition of `BUFFERS` fields.
- [config.sgml#track_io_timing](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L6854) - user-facing `track_io_timing` behavior and overhead note.
- [perform.sgml#EXPLAIN-BUFFERS-example](../../../../raw/postgres-12/doc/src/sgml/perform.sgml#L694-L718) - same-version documentation example with `Buffers:` lines.

## Open Questions

- The documentation describes `written` as previously dirty blocks evicted from cache, while the PostgreSQL 12 source also increments `shared_blks_written` and `local_blks_written` during relation extension in `ReadBuffer_common`. This page follows the implementation source for the detailed field definition [ref/explain.sgml#BUFFERS-def](../../../../raw/postgres-12/doc/src/sgml/ref/explain.sgml#L168-L192) [bufmgr.c#ReadBuffer_common](../../../../raw/postgres-12/src/backend/storage/buffer/bufmgr.c#L704).

## Related Pages

- [v12/index](../../index.md)
- [versions](../../../versions.md)
