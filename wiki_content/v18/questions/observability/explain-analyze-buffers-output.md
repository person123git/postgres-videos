---
type: question
version: 18
pinned_commit: baa7b142aace6821ce085906f314a75bcc4d95c8
verified: false
verified_by_agent: not yet
---

# EXPLAIN ANALYZE BUFFERS Output in PostgreSQL 18 (unverified)

## Question

In PostgreSQL 18, when a query uses `EXPLAIN (ANALYZE, BUFFERS)`, describe in detail all buffer information in the output.

## Short Answer

In PostgreSQL 18, `EXPLAIN (ANALYZE, BUFFERS)` executes the target statement and records buffer activity in `BufferUsage` counters attached to executor instrumentation [explain.c#ExplainOnePlan](../../../../raw/postgres-18/src/backend/commands/explain.c#L494-L682) [instrument.h#BufferUsage](../../../../raw/postgres-18/src/include/executor/instrument.h#L24-L42). If `BUFFERS` is not written explicitly, PostgreSQL 18 turns it on by default when `ANALYZE` is true; `BUFFERS OFF` disables it [explain_state.c#ParseExplainOptionList](../../../../raw/postgres-18/src/backend/commands/explain_state.c#L77-L207).

A typical text fragment looks like this:

```text
Buffers: shared hit=15 read=4 dirtied=1 written=1, local hit=2 read=1 dirtied=1 written=1, temp read=12 written=12
I/O Timings: shared read=3.217 write=0.812, local read=0.044 write=0.021, temp read=1.302 write=0.773
```

`shared` means ordinary table and index blocks in shared buffers, `local` means temporary table and index blocks in backend-local buffers, and `temp` means short-lived executor work files used by sorts, hashes, `Materialize`, and similar nodes [ref/explain.sgml#BUFFERS](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L181-L208). Text format prints only positive buffer and I/O-timing values; JSON, XML, and YAML print every buffer counter property, and print I/O-time properties when `track_io_timing` is enabled [explain.c#show_buffer_usage](../../../../raw/postgres-18/src/backend/commands/explain.c#L4086-L4249).

## Safe Production Shape

`EXPLAIN ANALYZE` runs the statement, so a write statement really writes unless the session wraps it in a transaction that later rolls back [explain.c#ExplainOnePlan](../../../../raw/postgres-18/src/backend/commands/explain.c#L494-L682). Before running a production-bound investigation, use session or transaction scoped limits; PostgreSQL 18 defines both `statement_timeout` and `lock_timeout` as `PGC_USERSET`, so they require no restart or reload and can be set in the current session or transaction [guc_tables.c#statement_timeout](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2740-L2748) [guc_tables.c#lock_timeout](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2751-L2758).

```sql
SET /* wiki_limit_explain_statement */ statement_timeout = '30s';
SET /* wiki_limit_explain_lock_wait */ lock_timeout = '5s';
```

## What Each Field Means

The counts are block-event counters, not tuple counters and not distinct-page counters. `BufferUsage` stores block counts, and PostgreSQL reports the configured disk block size through `block_size`, whose default is 8192 bytes [instrument.h#BufferUsage](../../../../raw/postgres-18/src/include/executor/instrument.h#L24-L42) [config.sgml#block_size](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L11808-L11824).

| Output field | Meaning in PostgreSQL 18 |
|---|---|
| `shared hit=N` | PostgreSQL needed a block from an ordinary table or index and found it already available in shared buffers, avoiding a read into a new buffer [ref/explain.sgml#BUFFERS](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L181-L208). The shared hit counter is incremented when `PinBufferForBlock`, `ReadRecentBuffer`, or the concurrent-read path in `AsyncReadBuffers` finds the shared buffer already valid for this backend [bufmgr.c#PinBufferForBlock](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1101-L1176) [bufmgr.c#ReadRecentBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L682-L751) [bufmgr.c#AsyncReadBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1773-L1987). |
| `shared read=N` | PostgreSQL issued relation-block read I/O for ordinary table or index blocks that were not already available to this backend [bufmgr.c#AsyncReadBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1773-L1987). `AsyncReadBuffers` adds the number of blocks in the I/O batch to `shared_blks_read` for persistent or unlogged relation reads [bufmgr.c#AsyncReadBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1773-L1987). |
| `shared dirtied=N` | The statement made previously clean shared buffers dirty. Normal page changes increment the counter in `MarkBufferDirty`, and hint-bit style changes can increment it in `MarkBufferDirtyHint` when the buffer was not already dirty [bufmgr.c#MarkBufferDirty](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2970-L3016) [bufmgr.c#MarkBufferDirtyHint](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L5453-L5583). |
| `shared written=N` | This backend wrote ordinary relation data while the statement was running. PostgreSQL 18 increments the shared written counter when shared relation extension writes zeroed new blocks and when `FlushBuffer` writes a dirty shared buffer [bufmgr.c#ExtendBufferedRelShared](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2628-L2898) [bufmgr.c#FlushBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L4307-L4436). |
| `local hit=N` | PostgreSQL needed a block from a temporary table or index and found it already available in the backend's local buffer pool [ref/explain.sgml#BUFFERS](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L181-L208). The local hit counter is incremented through the local-buffer paths in `PinBufferForBlock`, `ReadRecentBuffer`, and `AsyncReadBuffers` [bufmgr.c#PinBufferForBlock](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1101-L1176) [bufmgr.c#ReadRecentBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L682-L751) [bufmgr.c#AsyncReadBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1773-L1987). |
| `local read=N` | PostgreSQL read temporary table or index blocks into local buffers. The read path adds the I/O batch length to `local_blks_read` for temporary-relation reads [bufmgr.c#AsyncReadBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1773-L1987). |
| `local dirtied=N` | The statement made previously clean local buffers dirty. `MarkLocalBufferDirty` increments `local_blks_dirtied` only when the local buffer was not already dirty [localbuf.c#MarkLocalBufferDirty](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L497-L523). |
| `local written=N` | This backend wrote temporary table or index data. PostgreSQL 18 increments the local written counter when `FlushLocalBuffer` writes a dirty local buffer, and when local relation extension writes new blocks [localbuf.c#FlushLocalBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L182-L220) [localbuf.c#ExtendBufferedRelLocal](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L353-L490). |
| `temp read=N` | The executor read from a temporary work file through `BufFile`, not from a temporary table's local buffer pool [ref/explain.sgml#BUFFERS](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L181-L208). `BufFileLoadBuffer` increments `temp_blks_read` after a positive `FileRead` into the `BufFile` buffer [buffile.c#BufFileLoadBuffer](../../../../raw/postgres-18/src/backend/storage/file/buffile.c#L434-L484). |
| `temp written=N` | The executor wrote to a temporary work file through `BufFile`, not to a temporary table's local buffer pool [ref/explain.sgml#BUFFERS](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L181-L208). `BufFileDumpBuffer` increments `temp_blks_written` after successful `FileWrite` calls [buffile.c#BufFileDumpBuffer](../../../../raw/postgres-18/src/backend/storage/file/buffile.c#L494-L580). |
| `I/O Timings: shared ... local ... temp ...` | These are elapsed times for shared relation I/O, local temporary-relation I/O, and temporary work-file I/O, printed in milliseconds when timing values are present in text output [explain.c#show_buffer_usage](../../../../raw/postgres-18/src/backend/commands/explain.c#L4086-L4249). Shared and local read/write times are accumulated by `pgstat_count_io_op_time`; temp work-file read/write times are accumulated in `BufFileLoadBuffer` and `BufFileDumpBuffer` [pgstat_io.c#pgstat_count_io_op_time](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_io.c#L122-L160) [buffile.c#BufFileLoadBuffer](../../../../raw/postgres-18/src/backend/storage/file/buffile.c#L434-L484) [buffile.c#BufFileDumpBuffer](../../../../raw/postgres-18/src/backend/storage/file/buffile.c#L494-L580). |

## How The Counters Are Collected

`pgBufferUsage` is the backend-wide accumulator for these counters, and plan nodes collect deltas from it rather than owning independent counters while they run [instrument.h#pgBufferUsage](../../../../raw/postgres-18/src/include/executor/instrument.h#L102) [instrument.c#InstrStartNode](../../../../raw/postgres-18/src/backend/executor/instrument.c#L68-L80) [instrument.c#InstrStopNode](../../../../raw/postgres-18/src/backend/executor/instrument.c#L84-L128). `ExplainOnePlan` passes `INSTRUMENT_BUFFERS` into `CreateQueryDesc` when `BUFFERS` is active, `ExecutorStart` copies that option into `EState`, and `ExecInitNode` allocates `Instrumentation` for each plan node [explain.c#ExplainOnePlan](../../../../raw/postgres-18/src/backend/commands/explain.c#L494-L682) [execMain.c#ExecutorStart](../../../../raw/postgres-18/src/backend/executor/execMain.c#L122-L264) [execProcnode.c#ExecInitNode](../../../../raw/postgres-18/src/backend/executor/execProcnode.c#L142-L420).

`ExecProcNodeInstr` calls `InstrStartNode` before the real node function and `InstrStopNode` after it returns a tuple or end-of-scan marker, so the node stores the difference between the global `pgBufferUsage` value at node entry and node exit [execProcnode.c#ExecProcNodeInstr](../../../../raw/postgres-18/src/backend/executor/execProcnode.c#L479-L490) [instrument.c#BufferUsageAccumDiff](../../../../raw/postgres-18/src/backend/executor/instrument.c#L248-L274).

Upper plan nodes include buffer work done by their children, because the parent node remains active while it calls child nodes; the PostgreSQL 18 `EXPLAIN` reference states that upper-level block counts include child-node counts [ref/explain.sgml#BUFFERS](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L181-L208) [execProcnode.c#ExecProcNodeInstr](../../../../raw/postgres-18/src/backend/executor/execProcnode.c#L479-L490). Do not sum all `Buffers:` lines in a text plan to compute a query total, because parent and child lines can describe the same work [ref/explain.sgml#BUFFERS](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L181-L208).

The counters count buffer events, not distinct block identities. The source increments hit, read, dirty, and write counters at the moment each corresponding path is taken, so repeated requests for the same block can increase the same counter more than once [bufmgr.c#PinBufferForBlock](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1101-L1176) [bufmgr.c#AsyncReadBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1773-L1987) [bufmgr.c#MarkBufferDirty](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2970-L3016) [bufmgr.c#FlushBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L4307-L4436).

## Where It Appears In The Plan

Plan-node buffer lines are printed from `ExplainNode` when `es->buffers` is true and the plan node has instrumentation [explain.c#ExplainNode](../../../../raw/postgres-18/src/backend/commands/explain.c#L2284-L2314). In text format, `show_buffer_usage` suppresses a `Buffers:` line if all shared, local, and temp block counters are zero, and suppresses an `I/O Timings:` line if all shared, local, and temp timing fields are zero [explain.c#show_buffer_usage](../../../../raw/postgres-18/src/backend/commands/explain.c#L4086-L4249).

Planning buffer use is measured separately around `pg_plan_query` and printed under a `Planning:` group when the `BUFFERS` option is active and the planning counters have something to print in text format [explain.c#standard_ExplainOneQuery](../../../../raw/postgres-18/src/backend/commands/explain.c#L318-L375) [explain.c#peek_buffer_usage](../../../../raw/postgres-18/src/backend/commands/explain.c#L4046-L4080) [explain.c#ExplainOnePlan](../../../../raw/postgres-18/src/backend/commands/explain.c#L494-L682). Non-text formats print the planning buffer properties even when the values are zero, because `peek_buffer_usage` returns true for non-text formats when a `BufferUsage` object is present [explain.c#peek_buffer_usage](../../../../raw/postgres-18/src/backend/commands/explain.c#L4046-L4080).

Serialization buffer use is printed only when the `SERIALIZE` option is active. The serialize destination receiver snapshots `pgBufferUsage` for each output tuple when `BUFFERS` is active, stores the deltas in `SerializeMetrics`, and `ExplainPrintSerialize` prints those counters in the `Serialization` section [explain_dr.c#serializeAnalyzeReceive](../../../../raw/postgres-18/src/backend/commands/explain_dr.c#L104-L202) [explain_dr.h#SerializeMetrics](../../../../raw/postgres-18/src/include/commands/explain_dr.h#L21-L27) [explain.c#ExplainPrintSerialize](../../../../raw/postgres-18/src/backend/commands/explain.c#L999-L1048).

In parallel query, PostgreSQL 18 allocates a `BufferUsage` slot for each worker in dynamic shared memory, each worker stores its execution delta with `InstrEndParallelQuery`, and the leader adds worker values back into its own `pgBufferUsage` with `InstrAccumParallelQuery` after workers finish [execParallel.c#ExecInitParallelPlan](../../../../raw/postgres-18/src/backend/executor/execParallel.c#L599-L780) [execParallel.c#ParallelQueryMain](../../../../raw/postgres-18/src/backend/executor/execParallel.c#L1429-L1531) [execParallel.c#ExecParallelFinish](../../../../raw/postgres-18/src/backend/executor/execParallel.c#L1156-L1200) [instrument.c#InstrAccumParallelQuery](../../../../raw/postgres-18/src/backend/executor/instrument.c#L218-L222). `EXPLAIN (ANALYZE, VERBOSE, BUFFERS)` can print per-worker buffer details because `ExplainNode` walks `worker_instrument` and calls `show_buffer_usage` for each worker with loops greater than zero [explain.c#ExplainNode](../../../../raw/postgres-18/src/backend/commands/explain.c#L2284-L2314).

Trigger functions can be instrumented with the same executor instrumentation options, but the trigger summary prints trigger name, time, and calls, not buffer counters [execMain.c#InitResultRelInfo](../../../../raw/postgres-18/src/backend/executor/execMain.c#L1247-L1326) [trigger.c#ExecCallTriggerFunc](../../../../raw/postgres-18/src/backend/commands/trigger.c#L2315-L2404) [explain.c#report_triggers](../../../../raw/postgres-18/src/backend/commands/explain.c#L1092-L1159).

## I/O Timing And `track_io_timing`

`track_io_timing` controls whether PostgreSQL measures database I/O wait time for these buffer timing fields; PostgreSQL 18 defines it as `PGC_SUSET`, off by default, backed by the `track_io_timing` variable [guc_tables.c#track_io_timing](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L1513-L1519). Under the wiki GUC context mapping, this is a superuser or granted-privilege session/transaction-scope setting, so enabling it does not require restart or reload [guc_tables.c#track_io_timing](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L1513-L1519) [config.sgml#track_io_timing](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L8745-L8772).

The PostgreSQL 18 documentation says `track_io_timing` repeatedly queries the operating-system clock and may add significant overhead on some platforms [config.sgml#track_io_timing](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L8745-L8772). A superuser, or a user granted permission to set it, can enable it for the current session:

```sql
SET /* wiki_enable_track_io_timing */ track_io_timing = on;
```

## Reading Common Patterns

High `shared hit` means the plan repeatedly found ordinary table or index blocks already in PostgreSQL shared buffers, so it avoided relation-block read I/O for those requests [ref/explain.sgml#BUFFERS](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L181-L208) [bufmgr.c#PinBufferForBlock](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1101-L1176).

High `shared read` means the plan caused relation-block read I/O for ordinary table or index blocks that were not already available to this backend [bufmgr.c#AsyncReadBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1773-L1987).

High `temp read` or `temp written` points to executor work files handled through `BufFile`, not to blocks of temporary tables or temporary indexes [ref/explain.sgml#BUFFERS](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L181-L208) [buffile.c#BufFileLoadBuffer](../../../../raw/postgres-18/src/backend/storage/file/buffile.c#L434-L484) [buffile.c#BufFileDumpBuffer](../../../../raw/postgres-18/src/backend/storage/file/buffile.c#L494-L580).

High `dirtied` means the statement turned clean buffers dirty. High `written` means the backend wrote relation data during the statement, either by relation extension or by flushing dirty buffers on the source paths above [bufmgr.c#MarkBufferDirty](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2970-L3016) [bufmgr.c#MarkBufferDirtyHint](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L5453-L5583) [bufmgr.c#ExtendBufferedRelShared](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2628-L2898) [bufmgr.c#FlushBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L4307-L4436) [localbuf.c#ExtendBufferedRelLocal](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L353-L490) [localbuf.c#FlushLocalBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L182-L220).

## Tests And Examples

The same-checkout PostgreSQL 18 reference documentation defines the `BUFFERS` fields, states that upper-level nodes include child-node block counts, and shows a worked `EXPLAIN ANALYZE` example with `Buffers: shared hit=4` lines [ref/explain.sgml#BUFFERS](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L181-L208) [ref/explain.sgml#EXPLAIN-EXECUTE-example](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L488-L512).

The PostgreSQL 18 regression tests cover `EXPLAIN (ANALYZE, BUFFERS, FORMAT xml)`, `EXPLAIN (ANALYZE, BUFFERS, FORMAT json)`, `EXPLAIN (ANALYZE, SERIALIZE, BUFFERS, FORMAT yaml)`, `track_io_timing` I/O time fields in JSON, and `EXPLAIN (BUFFERS, FORMAT json)` without `ANALYZE` [explain.sql#EXPLAIN-BUFFERS-tests](../../../../raw/postgres-18/src/test/regress/sql/explain.sql#L58-L82) [explain.out#EXPLAIN-BUFFERS-output](../../../../raw/postgres-18/src/test/regress/expected/explain.out#L145-L338). The same test file deliberately filters text-mode `Buffers:` lines because the counts vary with system state [explain.sql#explain_filter](../../../../raw/postgres-18/src/test/regress/sql/explain.sql#L13-L34).

## Context Reviewed

- [explain_state.c#ParseExplainOptionList](../../../../raw/postgres-18/src/backend/commands/explain_state.c#L77-L207)
- [explain.c#standard_ExplainOneQuery](../../../../raw/postgres-18/src/backend/commands/explain.c#L318-L375)
- [explain.c#ExplainOnePlan](../../../../raw/postgres-18/src/backend/commands/explain.c#L494-L682)
- [explain.c#ExplainNode](../../../../raw/postgres-18/src/backend/commands/explain.c#L2284-L2314)
- [explain.c#peek_buffer_usage](../../../../raw/postgres-18/src/backend/commands/explain.c#L4046-L4080)
- [explain.c#show_buffer_usage](../../../../raw/postgres-18/src/backend/commands/explain.c#L4086-L4249)
- [instrument.h#BufferUsage](../../../../raw/postgres-18/src/include/executor/instrument.h#L24-L42)
- [instrument.c#InstrStartNode](../../../../raw/postgres-18/src/backend/executor/instrument.c#L68-L80)
- [instrument.c#InstrStopNode](../../../../raw/postgres-18/src/backend/executor/instrument.c#L84-L128)
- [instrument.c#BufferUsageAccumDiff](../../../../raw/postgres-18/src/backend/executor/instrument.c#L248-L274)
- [execProcnode.c#ExecProcNodeInstr](../../../../raw/postgres-18/src/backend/executor/execProcnode.c#L479-L490)
- [bufmgr.c#PinBufferForBlock](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1101-L1176)
- [bufmgr.c#AsyncReadBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1773-L1987)
- [bufmgr.c#MarkBufferDirty](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2970-L3016)
- [bufmgr.c#MarkBufferDirtyHint](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L5453-L5583)
- [bufmgr.c#ExtendBufferedRelShared](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2628-L2898)
- [bufmgr.c#FlushBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L4307-L4436)
- [localbuf.c#MarkLocalBufferDirty](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L497-L523)
- [localbuf.c#FlushLocalBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L182-L220)
- [localbuf.c#ExtendBufferedRelLocal](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L353-L490)
- [buffile.c#BufFileLoadBuffer](../../../../raw/postgres-18/src/backend/storage/file/buffile.c#L434-L484)
- [buffile.c#BufFileDumpBuffer](../../../../raw/postgres-18/src/backend/storage/file/buffile.c#L494-L580)
- [pgstat_io.c#pgstat_count_io_op_time](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_io.c#L122-L160)
- [execParallel.c#ExecParallelFinish](../../../../raw/postgres-18/src/backend/executor/execParallel.c#L1156-L1200)
- [explain_dr.c#serializeAnalyzeReceive](../../../../raw/postgres-18/src/backend/commands/explain_dr.c#L104-L202)
- [ref/explain.sgml#BUFFERS](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L181-L208)
- [explain.sql#EXPLAIN-BUFFERS-tests](../../../../raw/postgres-18/src/test/regress/sql/explain.sql#L58-L82)
- [explain.out#EXPLAIN-BUFFERS-output](../../../../raw/postgres-18/src/test/regress/expected/explain.out#L145-L338)

## Evidence Map

| Claim | Source |
|---|---|
| `BUFFERS` defaults to `ANALYZE` when not explicitly set | [explain_state.c#ParseExplainOptionList](../../../../raw/postgres-18/src/backend/commands/explain_state.c#L77-L207) |
| `BUFFERS` maps to `INSTRUMENT_BUFFERS` | [explain.c#ExplainOnePlan](../../../../raw/postgres-18/src/backend/commands/explain.c#L494-L682) |
| Buffer counters live in `BufferUsage` | [instrument.h#BufferUsage](../../../../raw/postgres-18/src/include/executor/instrument.h#L24-L42) |
| Plan nodes accumulate `pgBufferUsage` deltas | [instrument.c#InstrStartNode](../../../../raw/postgres-18/src/backend/executor/instrument.c#L68-L80) [instrument.c#InstrStopNode](../../../../raw/postgres-18/src/backend/executor/instrument.c#L84-L128) |
| Text format prints only positive buffer and timing values | [explain.c#show_buffer_usage](../../../../raw/postgres-18/src/backend/commands/explain.c#L4086-L4249) |
| Non-text formats print all buffer properties | [explain.c#show_buffer_usage](../../../../raw/postgres-18/src/backend/commands/explain.c#L4086-L4249) |
| Shared/local hit and read counters are updated by buffer manager read paths | [bufmgr.c#PinBufferForBlock](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1101-L1176) [bufmgr.c#AsyncReadBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1773-L1987) |
| Shared dirty and write counters are updated by dirty, hint-dirty, extension, and flush paths | [bufmgr.c#MarkBufferDirty](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2970-L3016) [bufmgr.c#MarkBufferDirtyHint](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L5453-L5583) [bufmgr.c#ExtendBufferedRelShared](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2628-L2898) [bufmgr.c#FlushBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L4307-L4436) |
| Local dirty and write counters are updated by local buffer paths | [localbuf.c#MarkLocalBufferDirty](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L497-L523) [localbuf.c#FlushLocalBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L182-L220) [localbuf.c#ExtendBufferedRelLocal](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L353-L490) |
| Temp work-file counters are updated by `BufFile` | [buffile.c#BufFileLoadBuffer](../../../../raw/postgres-18/src/backend/storage/file/buffile.c#L434-L484) [buffile.c#BufFileDumpBuffer](../../../../raw/postgres-18/src/backend/storage/file/buffile.c#L494-L580) |
| Planning buffer use is captured separately | [explain.c#standard_ExplainOneQuery](../../../../raw/postgres-18/src/backend/commands/explain.c#L318-L375) [explain.c#ExplainOnePlan](../../../../raw/postgres-18/src/backend/commands/explain.c#L494-L682) |
| Serialization buffer use is captured only for `SERIALIZE` | [explain_dr.c#serializeAnalyzeReceive](../../../../raw/postgres-18/src/backend/commands/explain_dr.c#L104-L202) [explain.c#ExplainPrintSerialize](../../../../raw/postgres-18/src/backend/commands/explain.c#L999-L1048) |
| Parallel workers report and leader accumulates buffer usage | [execParallel.c#ParallelQueryMain](../../../../raw/postgres-18/src/backend/executor/execParallel.c#L1429-L1531) [execParallel.c#ExecParallelFinish](../../../../raw/postgres-18/src/backend/executor/execParallel.c#L1156-L1200) [instrument.c#InstrAccumParallelQuery](../../../../raw/postgres-18/src/backend/executor/instrument.c#L218-L222) |
| `track_io_timing` is superuser-settable or privilege-settable and off by default | [guc_tables.c#track_io_timing](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L1513-L1519) [config.sgml#track_io_timing](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L8745-L8772) |
| PostgreSQL 18 regression tests cover buffer fields in non-text formats | [explain.sql#EXPLAIN-BUFFERS-tests](../../../../raw/postgres-18/src/test/regress/sql/explain.sql#L58-L82) [explain.out#EXPLAIN-BUFFERS-output](../../../../raw/postgres-18/src/test/regress/expected/explain.out#L145-L338) |

## Source References

- [explain_state.c#ParseExplainOptionList](../../../../raw/postgres-18/src/backend/commands/explain_state.c#L77-L207) - parses `ANALYZE`, `BUFFERS`, `TIMING`, `SERIALIZE`, and related options.
- [explain.c#standard_ExplainOneQuery](../../../../raw/postgres-18/src/backend/commands/explain.c#L318-L375) - captures planning time and planning buffer deltas.
- [explain.c#ExplainOnePlan](../../../../raw/postgres-18/src/backend/commands/explain.c#L494-L682) - maps `BUFFERS` to instrumentation, runs the executor under `ANALYZE`, and prints planning summaries.
- [explain.c#ExplainNode](../../../../raw/postgres-18/src/backend/commands/explain.c#L2284-L2314) - prints plan-node and per-worker buffer usage.
- [explain.c#peek_buffer_usage](../../../../raw/postgres-18/src/backend/commands/explain.c#L4046-L4080) and [explain.c#show_buffer_usage](../../../../raw/postgres-18/src/backend/commands/explain.c#L4086-L4249) - decide whether buffer output appears and format text, JSON, XML, and YAML fields.
- [instrument.h#BufferUsage](../../../../raw/postgres-18/src/include/executor/instrument.h#L24-L42) - defines shared, local, temp, and I/O timing counters.
- [instrument.c#InstrStartNode](../../../../raw/postgres-18/src/backend/executor/instrument.c#L68-L80), [instrument.c#InstrStopNode](../../../../raw/postgres-18/src/backend/executor/instrument.c#L84-L128), and [instrument.c#BufferUsageAccumDiff](../../../../raw/postgres-18/src/backend/executor/instrument.c#L248-L274) - snapshot and accumulate buffer deltas.
- [execMain.c#ExecutorStart](../../../../raw/postgres-18/src/backend/executor/execMain.c#L122-L264) and [execProcnode.c#ExecInitNode](../../../../raw/postgres-18/src/backend/executor/execProcnode.c#L142-L420) - propagate instrumentation options into executor nodes.
- [bufmgr.c#PinBufferForBlock](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1101-L1176), [bufmgr.c#ReadRecentBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L682-L751), and [bufmgr.c#AsyncReadBuffers](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L1773-L1987) - account shared/local hits and reads.
- [bufmgr.c#MarkBufferDirty](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2970-L3016), [bufmgr.c#MarkBufferDirtyHint](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L5453-L5583), [bufmgr.c#ExtendBufferedRelShared](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2628-L2898), and [bufmgr.c#FlushBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L4307-L4436) - account shared dirties and writes.
- [localbuf.c#MarkLocalBufferDirty](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L497-L523), [localbuf.c#FlushLocalBuffer](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L182-L220), and [localbuf.c#ExtendBufferedRelLocal](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L353-L490) - account local dirties and writes.
- [buffile.c#BufFileLoadBuffer](../../../../raw/postgres-18/src/backend/storage/file/buffile.c#L434-L484) and [buffile.c#BufFileDumpBuffer](../../../../raw/postgres-18/src/backend/storage/file/buffile.c#L494-L580) - account temporary work-file reads and writes.
- [pgstat_io.c#pgstat_count_io_op_time](../../../../raw/postgres-18/src/backend/utils/activity/pgstat_io.c#L122-L160) - accumulates shared and local I/O timing into `pgBufferUsage`.
- [execParallel.c#ParallelQueryMain](../../../../raw/postgres-18/src/backend/executor/execParallel.c#L1429-L1531) and [execParallel.c#ExecParallelFinish](../../../../raw/postgres-18/src/backend/executor/execParallel.c#L1156-L1200) - report and accumulate worker buffer usage.
- [explain_dr.c#serializeAnalyzeReceive](../../../../raw/postgres-18/src/backend/commands/explain_dr.c#L104-L202) and [explain_dr.h#SerializeMetrics](../../../../raw/postgres-18/src/include/commands/explain_dr.h#L21-L27) - collect serialization buffer metrics.
- [guc_tables.c#track_io_timing](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L1513-L1519), [guc_tables.c#statement_timeout](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2740-L2748), and [guc_tables.c#lock_timeout](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2751-L2758) - define GUC contexts for settings mentioned in this page.
- [ref/explain.sgml#BUFFERS](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L181-L208) and [ref/explain.sgml#EXPLAIN-EXECUTE-example](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L488-L512) - PostgreSQL 18 user-facing `BUFFERS` definition and example.
- [explain.sql#EXPLAIN-BUFFERS-tests](../../../../raw/postgres-18/src/test/regress/sql/explain.sql#L58-L82) and [explain.out#EXPLAIN-BUFFERS-output](../../../../raw/postgres-18/src/test/regress/expected/explain.out#L145-L338) - same-version regression coverage for buffer output fields.

## Open Questions

- The PostgreSQL 18 documentation describes `written` as previously dirty blocks evicted from cache, while the implementation also increments `shared_blks_written` and `local_blks_written` during relation extension. This page follows the implementation source for the detailed field definition [ref/explain.sgml#BUFFERS](../../../../raw/postgres-18/doc/src/sgml/ref/explain.sgml#L181-L208) [bufmgr.c#ExtendBufferedRelShared](../../../../raw/postgres-18/src/backend/storage/buffer/bufmgr.c#L2628-L2898) [localbuf.c#ExtendBufferedRelLocal](../../../../raw/postgres-18/src/backend/storage/buffer/localbuf.c#L353-L490).

## Related Pages

- [v18/index](../../index.md)
- [versions](../../../versions.md)
