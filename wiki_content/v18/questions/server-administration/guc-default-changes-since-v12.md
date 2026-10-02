---
type: question
version: 18
pinned_commit: baa7b142aace6821ce085906f314a75bcc4d95c8
verified: false
verified_by_agent: not yet
---

# GUC Default-Value Changes Since PostgreSQL 12 (unverified)

## Question

In PostgreSQL 18, summarize all GUC default-value changes since PostgreSQL 12.

## Answer Up Front

Eight server settings that already existed in PostgreSQL 12 have a different
semantic built-in default in PostgreSQL 18. One more setting,
`log_connections`, changed from a boolean default display of `off` to a string
default display of `''`, but both defaults disable connection logging. Each row
shows the PostgreSQL 12 default, the PostgreSQL 18 default, the major version
that introduced the change, and how a change to the setting takes effect.

| Setting | Old default (v12) | New default (v18) | First in | Apply scope |
|---|---|---|---|---|
| `ssl_min_protocol_version` | `TLSv1` | `TLSv1.2` | 13 | Reload (`PGC_SIGHUP`) |
| `password_encryption` | `md5` | `scram-sha-256` | 14 | Session (`PGC_USERSET`) |
| `vacuum_cost_page_miss` | `10` | `2` | 14 | Session (`PGC_USERSET`) |
| `checkpoint_completion_target` | `0.5` | `0.9` | 14 | Reload (`PGC_SIGHUP`) |
| `shared_buffers` built-in default | `8MB` (1024 blocks) | `128MB` (16384 blocks) | 15 | Restart (`PGC_POSTMASTER`) |
| `log_checkpoints` | `off` | `on` | 15 | Reload (`PGC_SIGHUP`) |
| `log_autovacuum_min_duration` | `-1` (off) | `10min` | 15 | Reload (`PGC_SIGHUP`) |
| `effective_io_concurrency` | `1` on prefetch builds, `0` otherwise | `16` | 18 | Session (`PGC_USERSET`) |
| `log_connections` default spelling/type | `off` | `''` (disabled) | 18 | New session (`PGC_SU_BACKEND`) |

The PostgreSQL 18 value and apply scope come from the v18 GUC table
([guc_tables.c](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c))
and the v18 configuration docs
([config.sgml](../../../../raw/postgres-18/doc/src/sgml/config.sgml)). The old
values and introducing major versions come from the same `raw/postgres-18/`
checkout's Git history and were cross-checked against the pinned PostgreSQL 12
GUC table. Per this wiki's version rule, this v18 page cites only
`raw/postgres-18/` files.

Settings added after v12 are not counted even when their own defaults later
changed. For example, `maintenance_io_concurrency` also defaults to `16` in
v18, but it did not exist in v12; it is therefore out of this inventory
([guc_tables.c#maintenance_io_concurrency](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3263-L3273),
[release-18.sgml#io-concurrency-defaults](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L9620-L9632)).

The 18.4 and 18.6 minor releases did not change this answer. No GUC present in
both v12 and PostgreSQL 18 changed its built-in default anywhere in that range:
`src/backend/utils/misc/guc_tables.c` has exactly one commit between the
previous pin `6cb307251c5c6261286c1566496920976640108e` (18.3 line) and this
page's pin `baa7b142aace6821ce085906f314a75bcc4d95c8`, and that commit
(`2a29b607dbb`) only adds a new entry rather than editing an existing boot value
([guc_tables.c#output_plugin_libraries](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L4986-L4996)).
The new parameter is covered under
[Not Default-Value Changes](#not-default-value-changes).

## Changed In PostgreSQL 13

### `ssl_min_protocol_version`: `TLSv1` -> `TLSv1.2`

PostgreSQL 18 boots with `PG_TLS1_2_VERSION` for the minimum SSL/TLS protocol
version
([guc_tables.c#ssl_min_protocol_version](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5397-L5406)).
The docs state that the default is `TLSv1.2`, and the sample file shows the
same value
([config.sgml#ssl_min_protocol_version](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L1592-L1594),
[postgresql.conf.sample#ssl_min_protocol_version](../../../../raw/postgres-18/src/backend/utils/misc/postgresql.conf.sample#L115-L120)).
The change was made by commit `b1abfec8` (2019-12-04, "Update minimum SSL
version"), whose in-tree version string was `13devel`. The setting is
`PGC_SIGHUP`, so a configuration-file change takes effect on reload.

## Changed In PostgreSQL 14

### `password_encryption`: `md5` -> `scram-sha-256`

New passwords set by role DDL now default to SCRAM-SHA-256 storage. The v18
boot value is `PASSWORD_TYPE_SCRAM_SHA_256`
([guc_tables.c#password_encryption](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5374-L5381)),
and the docs say the default is `scram-sha-256`
([config.sgml#password_encryption](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L1114-L1121)).
The sample file agrees
([postgresql.conf.sample#password_encryption](../../../../raw/postgres-18/src/backend/utils/misc/postgresql.conf.sample#L94-L99)).
Commit `c7eab0e9` (2020-06-10, "Change default of password_encryption to
scram-sha-256") introduced the change in `14devel`. This is `PGC_USERSET`, so
it can be changed for a session or transaction; changing the cluster default in
the configuration file takes effect on reload for future sessions.

### `vacuum_cost_page_miss`: `10` -> `2`

Cost-based vacuum delay now charges a lower cost for a page miss. PostgreSQL 18
uses the boot value `2`
([guc_tables.c#vacuum_cost_page_miss](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2653-L2660)),
and the docs describe `2` as the default
([config.sgml#vacuum_cost_page_miss](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L9402-L9415)).
The sample file shows the same value
([postgresql.conf.sample#vacuum_cost_page_miss](../../../../raw/postgres-18/src/backend/utils/misc/postgresql.conf.sample#L717-L723)).
Commit `e19594c5` (2021-01-27, "Reduce the default value of
vacuum_cost_page_miss") introduced the change in `14devel`. This is
`PGC_USERSET`.

### `checkpoint_completion_target`: `0.5` -> `0.9`

Checkpoints now spread writes over 90% of the checkpoint interval by default.
The v18 boot value is `0.9`
([guc_tables.c#checkpoint_completion_target](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L4123-L4130)),
and the docs explain the same default
([config.sgml#checkpoint_completion_target](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L3712-L3724)).
The sample file also uses `0.9`
([postgresql.conf.sample#checkpoint_completion_target](../../../../raw/postgres-18/src/backend/utils/misc/postgresql.conf.sample#L265-L270)).
Commit `bbcc4eb2` (2021-03-24, "Change checkpoint_completion_target default to
0.9") introduced the change in `14devel`. This is `PGC_SIGHUP`, so reload is
enough.

## Changed In PostgreSQL 15

### `shared_buffers` built-in default: `8MB` -> `128MB`

The compiled boot value rose from 1024 blocks to 16384 blocks, which is 128MB
with the default 8kB `BLCKSZ`. PostgreSQL 18 stores `16384` in the GUC table
([guc_tables.c#shared_buffers](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2378-L2386)),
and the docs describe the default as typically 128MB
([config.sgml#shared_buffers](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L1731-L1739)).
The sample file shows `128MB`
([postgresql.conf.sample#shared_buffers](../../../../raw/postgres-18/src/backend/utils/misc/postgresql.conf.sample#L131-L133)).

This is mainly a built-in-default and `pg_settings.boot_val` correction. Commit
`f7bda63a` (2021-08-23, "Improve defaults shown in postgresql.conf.sample and
pg_settings") noted that `initdb` had already selected a practical default of
128MB in ordinary clusters. `shared_buffers` is `PGC_POSTMASTER`, so changing it
requires restart.

### `log_checkpoints`: `off` -> `on`

Checkpoint and restartpoint logging is enabled by default. The v18 GUC table
sets `log_checkpoints` to `true`
([guc_tables.c#log_checkpoints](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L1239-L1247)),
and the docs state that the default is on
([config.sgml#log_checkpoints](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L7584-L7597)).
The sample file agrees
([postgresql.conf.sample#log_checkpoints](../../../../raw/postgres-18/src/backend/utils/misc/postgresql.conf.sample#L592-L601)).

### `log_autovacuum_min_duration`: `-1` -> `10min`

Autovacuum and autoanalyze actions running at least 10 minutes are now logged by
default. PostgreSQL 18 stores `600000` milliseconds as the boot value
([guc_tables.c#log_autovacuum_min_duration](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3181-L3190)),
and the docs state the human-readable default as `10min`
([config.sgml#log_autovacuum_min_duration](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L7564-L7580)).
The sample file shows `10min`
([postgresql.conf.sample#log_autovacuum_min_duration](../../../../raw/postgres-18/src/backend/utils/misc/postgresql.conf.sample#L592-L596)).

Both logging defaults changed in commit `64da07c4` (2021-12-13, "Default to
log_checkpoints=on, log_autovacuum_min_duration=10m"), whose in-tree version
was `15devel`. Both are `PGC_SIGHUP`, so reload applies configuration-file
changes.

## Changed In PostgreSQL 18

### `effective_io_concurrency`: `1` -> `16`

PostgreSQL 18 now defaults the number of concurrent storage I/O operations to
`16`. The GUC table reads the value from `DEFAULT_EFFECTIVE_IO_CONCURRENCY`
([guc_tables.c#effective_io_concurrency](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3249-L3260)),
and that macro is `16`
([bufmgr.h#DEFAULT_EFFECTIVE_IO_CONCURRENCY](../../../../raw/postgres-18/src/include/storage/bufmgr.h#L155-L164)).
The docs and sample file both show `16`
([config.sgml#effective_io_concurrency](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L2688-L2704),
[postgresql.conf.sample#effective_io_concurrency](../../../../raw/postgres-18/src/backend/utils/misc/postgresql.conf.sample#L202-L206)).
The v18 release notes identify commit `ff79b5b2` as the default increase and
say the new value better reflects modern hardware
([release-18.sgml#effective_io_concurrency](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L9613-L9632)).
This is `PGC_USERSET`, so a session or transaction can override it; changing
the cluster default takes effect for later settings loads.

### `log_connections`: `off` -> `''` with disabled behavior preserved

`log_connections` changed from a boolean to a string/list setting in
PostgreSQL 18. The v18 GUC table gives it an empty-string boot value
([guc_tables.c#log_connections](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L4998-L5006)).
The docs say the empty string disables all connection logging, and they retain
boolean spellings such as `on` and `off` for compatibility
([config.sgml#log_connections-default](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L7601-L7612),
[config.sgml#log_connections-compat](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L7687-L7700)).
The check hook maps an empty list and compatibility values like `off` to zero
logging flags, while positive compatibility values map to the pre-v18 logging
aspects
([backend_startup.c#validate_log_connections_options](../../../../raw/postgres-18/src/backend/tcop/backend_startup.c#L990-L1042),
[backend_startup.h#LogConnectionOption](../../../../raw/postgres-18/src/include/tcop/backend_startup.h#L72-L89)).
The release notes identify commit `9219093c` as the modularization that made
`log_connections` non-boolean while retaining boolean input compatibility
([release-18.sgml#log_connections](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L9644-L9661)).

This is `PGC_SU_BACKEND`. A configuration reload changes the value inherited by
subsequently-started backends, but existing backends ignore reload changes for
`PGC_BACKEND` and `PGC_SU_BACKEND` settings
([guc.c#PGC_SU_BACKEND](../../../../raw/postgres-18/src/backend/utils/misc/guc.c#L3523-L3584)).
At connection start, only superusers and users with the needed `SET` privilege
can set it; after connection start, it cannot be changed
([config.sgml#log_connections-scope](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L7697-L7700)).

## Not Default-Value Changes

These differences can look like default changes when comparing files, but they
are out of scope for this page:

- **Settings added after v12**: examples include `summarize_wal`,
  `vacuum_buffer_usage_limit`, `maintenance_io_concurrency`,
  `compute_query_id`, `default_toast_compression`, and `io_method`. They have
  v18 defaults, but they were not settings present in both v12 and v18
  ([guc_tables.c#summarize_wal](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L1885-L1892),
  [guc_tables.c#vacuum_buffer_usage_limit](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2389-L2398),
  [guc_tables.c#maintenance_io_concurrency](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3263-L3273),
  [guc_tables.c#compute_query_id](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5050-L5057),
  [guc_tables.c#default_toast_compression](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5072-L5080),
  [guc_tables.c#io_method](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5443-L5450)).
- **`lc_messages`**: the built-in default is still the empty string, which means
  use the operating-system setting. The sample-file spelling changed, but the
  v18 boot value remains `""`
  ([guc_tables.c#lc_messages](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L4435-L4442),
  [postgresql.conf.sample#lc_messages](../../../../raw/postgres-18/src/backend/utils/misc/postgresql.conf.sample#L796-L798)).
- **`krb_server_keyfile`**: the boot value is still the `PG_KRB_SRVTAB` macro,
  whose in-source fallback is the empty string. Packaged builds can pass a
  system-dependent value from the build system, so sample-file spelling is not
  the same thing as a GUC boot-value change
  ([guc_tables.c#PG_KRB_SRVTAB](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L111-L114),
  [guc_tables.c#krb_server_keyfile](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L4414-L4422)).
- **`wal_compression`**: the setting changed from boolean to enum before v18,
  but the default remains off (`WAL_COMPRESSION_NONE`). The sample file's
  comment now spells the choices as `# off, pglz (or "on"), lz4, or zstd`
  (commit `6a6cf80e550`, "Document wal_compression=on", in the 18.4/18.6 range),
  and `config.sgml` states that "The value `on` is a historical spelling of
  `pglz`." This is comment and documentation wording only; the boot value is
  unchanged
  ([guc_tables.c#wal_compression](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5239-L5246),
  [postgresql.conf.sample#wal_compression](../../../../raw/postgres-18/src/backend/utils/misc/postgresql.conf.sample#L252-L253),
  [config.sgml:3473](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L3473)).
- **`output_plugin_libraries`**: 18.6 introduced this brand-new GUC
  (`2a29b607dbb`, CVE-2026-6471). It is `PGC_SUSET` in the
  `REPLICATION_SENDING` group with flags
  `GUC_LIST_INPUT | GUC_LIST_QUOTE | GUC_SUPERUSER_ONLY` and boot value
  `'pgoutput, test_decoding'`. It is out of scope here because the parameter
  does not exist in v12, but it is worth naming as a behavior-changing new
  default shipped in a minor release: a server whose administrator narrows the
  list refuses logical decoding requests for any other plugin. Apply scope:
  `PGC_SUSET` means a `postgresql.conf` change takes effect on reload (no
  restart), a superuser can change it for a session with `SET`, and
  `GUC_SUPERUSER_ONLY` restricts who may read or set it; a superuser can also
  override it per connection with `options=-coutput_plugin_libraries=...`
  ([guc_tables.c#output_plugin_libraries](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L4986-L4996),
  [postgresql.conf.sample:821](../../../../raw/postgres-18/src/backend/utils/misc/postgresql.conf.sample#L821),
  [config.sgml#output_plugin_libraries](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L4615-L4670)).
- **Allowed-range changes**: `maintenance_work_mem` and `autovacuum_work_mem`
  keep defaults of `64MB` and `-1` while allowing smaller explicit values;
  explicit `autovacuum_work_mem` values below `64kB` are clamped to `64kB`.
  `max_files_per_process` still defaults to `1000`, and
  `track_activity_query_size` still defaults to `1024`
  ([guc_tables.c#maintenance_work_mem](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2593-L2601),
  [guc_tables.c#autovacuum_work_mem](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3649-L3657),
  [autovacuum.c#check_autovacuum_work_mem](../../../../raw/postgres-18/src/backend/postmaster/autovacuum.c#L3420-L3443),
  [guc_tables.c#max_files_per_process](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2693-L2700),
  [guc_tables.c#track_activity_query_size](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3772-L3780)).

## Context Reviewed

- **Current PostgreSQL 18 defaults and apply scope**: read from
  `src/backend/utils/misc/guc_tables.c`, with docs and sample-file checks in
  the same pinned `raw/postgres-18/` checkout at
  `baa7b142aace6821ce085906f314a75bcc4d95c8` (`REL_18_6-10-gbaa7b142aac`).
- **18.4/18.6 range re-check (2026-08-17 repin)**: `git log` over
  `src/backend/utils/misc/guc_tables.c` for
  `6cb307251c5c6261286c1566496920976640108e..baa7b142aace6821ce085906f314a75bcc4d95c8`
  returns exactly one commit, `2a29b607dbb`, which adds the new
  `output_plugin_libraries` entry. The same range touches
  `src/backend/utils/misc/postgresql.conf.sample` twice: `2a29b607dbb` for the
  same new entry and `6a6cf80e550` for the `wal_compression` comment wording.
  No existing boot value changed, so the eight-plus-one inventory above stands
  unchanged.
- **Enumeration method**: extracted common `name -> boot_val` entries from
  PostgreSQL 18 `guc_tables.c` and PostgreSQL 12 `guc.c`. The comparison found
  the eight semantic changes listed above plus the v18 `log_connections`
  type/default-spelling change. It filtered macro renames, preprocessor
  normalizations, range-only changes, settings added after v12, and type changes
  that preserve the same default behavior.
- **Old values and introducing versions**: derived from the `raw/postgres-18/`
  Git history. The introducing major version was read from the in-tree
  `AC_INIT([PostgreSQL], [NNdevel], ...)` string at the relevant commit.
- **Scope rule applied**: `postmaster` -> restart; `sighup` -> reload;
  `user`/`superuser` -> session or transaction. For `PGC_SU_BACKEND`, the value
  is fixed at connection start for a backend.

## Test Coverage

I did not find a single PostgreSQL 18 test that enumerates this v12-to-v18
default-change inventory. Same-checkout tests cover individual settings and
adjacent behavior: `password_encryption` accepted values and password storage
paths
([password.sql#password_encryption](../../../../raw/postgres-18/src/test/regress/sql/password.sql#L5-L19)),
SSL protocol bounds using `ssl_min_protocol_version`
([001_ssltests.pl#ssl_min_protocol_version](../../../../raw/postgres-18/src/test/ssl/t/001_ssltests.pl#L103-L118)),
the `64kB` `maintenance_work_mem` minimum
([vacuum.sql#maintenance_work_mem-minimum](../../../../raw/postgres-18/src/test/regress/sql/vacuum.sql#L137-L143)),
regression harness logging overrides for `log_autovacuum_min_duration` and
`log_checkpoints`
([pg_regress.c#test-cluster-logging-gucs](../../../../raw/postgres-18/src/test/regress/pg_regress.c#L2398-L2406)),
`log_connections` compatibility and aspect-list logging
([001_password.pl#log_connections](../../../../raw/postgres-18/src/test/authentication/t/001_password.pl#L73-L122)),
and explicit `effective_io_concurrency` settings in planner/tablespace tests
([select_parallel.sql#effective_io_concurrency](../../../../raw/postgres-18/src/test/regress/sql/select_parallel.sql#L217-L261),
[tablespace.sql#effective_io_concurrency](../../../../raw/postgres-18/src/test/regress/sql/tablespace.sql#L32)).

## Evidence Map

| Claim | Evidence |
|---|---|
| `ssl_min_protocol_version` default is `TLSv1.2`, reload scope | [guc_tables.c#L5397-L5406](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5397-L5406), [config.sgml#L1592-L1594](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L1592-L1594) |
| `password_encryption` default is `scram-sha-256`, session scope | [guc_tables.c#L5374-L5381](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5374-L5381), [config.sgml#L1114-L1121](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L1114-L1121) |
| `vacuum_cost_page_miss` default is `2`, session scope | [guc_tables.c#L2653-L2660](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2653-L2660), [config.sgml#L9402-L9415](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L9402-L9415) |
| `checkpoint_completion_target` default is `0.9`, reload scope | [guc_tables.c#L4123-L4130](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L4123-L4130), [config.sgml#L3712-L3724](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L3712-L3724) |
| `shared_buffers` built-in default is `16384` blocks (128MB), restart scope | [guc_tables.c#L2378-L2386](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2378-L2386), [config.sgml#L1731-L1739](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L1731-L1739) |
| `log_checkpoints` default is `on`, reload scope | [guc_tables.c#L1239-L1247](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L1239-L1247), [config.sgml#L7584-L7597](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L7584-L7597) |
| `log_autovacuum_min_duration` default is `10min`, reload scope | [guc_tables.c#L3181-L3190](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3181-L3190), [config.sgml#L7564-L7580](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L7564-L7580) |
| `effective_io_concurrency` default is `16`, session scope | [guc_tables.c#L3249-L3260](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3249-L3260), [bufmgr.h#L155-L164](../../../../raw/postgres-18/src/include/storage/bufmgr.h#L155-L164), [release-18.sgml#L9613-L9632](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml#L9613-L9632) |
| `log_connections` default is `''`, disabled behavior preserved, new-session scope | [guc_tables.c#L4998-L5006](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L4998-L5006), [config.sgml#L7601-L7612](../../../../raw/postgres-18/doc/src/sgml/config.sgml#L7601-L7612), [backend_startup.c#L990-L1042](../../../../raw/postgres-18/src/backend/tcop/backend_startup.c#L990-L1042), [guc.c#L3523-L3584](../../../../raw/postgres-18/src/backend/utils/misc/guc.c#L3523-L3584) |
| Added-after-v12 settings are out of scope | [guc_tables.c#L1885-L1892](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L1885-L1892), [guc_tables.c#L2389-L2398](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2389-L2398), [guc_tables.c#L3263-L3273](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3263-L3273), [guc_tables.c#L5050-L5057](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5050-L5057), [guc_tables.c#L5072-L5080](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5072-L5080), [guc_tables.c#L5443-L5450](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5443-L5450) |
| Type/range/sample-only differences excluded from semantic default changes | [guc_tables.c#L4435-L4442](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L4435-L4442), [guc_tables.c#L4414-L4422](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L4414-L4422), [guc_tables.c#L5239-L5246](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L5239-L5246), [guc_tables.c#L2593-L2601](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L2593-L2601), [guc_tables.c#L3649-L3657](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c#L3649-L3657) |
| Tests cover individual settings, not the whole inventory | [password.sql#L5-L19](../../../../raw/postgres-18/src/test/regress/sql/password.sql#L5-L19), [001_ssltests.pl#L103-L118](../../../../raw/postgres-18/src/test/ssl/t/001_ssltests.pl#L103-L118), [001_password.pl#L73-L122](../../../../raw/postgres-18/src/test/authentication/t/001_password.pl#L73-L122), [select_parallel.sql#L217-L261](../../../../raw/postgres-18/src/test/regress/sql/select_parallel.sql#L217-L261) |
| Old values / introducing major versions | `raw/postgres-18/` Git history: commits `b1abfec8` (13), `c7eab0e9`/`e19594c5`/`bbcc4eb2` (14), `f7bda63a`/`64da07c4` (15), `ff79b5b2`/`9219093c` (18), with the in-tree `AC_INIT` dev version at each commit |

## Source References

- [guc_tables.c](../../../../raw/postgres-18/src/backend/utils/misc/guc_tables.c) -
  GUC boot values and `PGC_*` apply-scope flags.
- [config.sgml](../../../../raw/postgres-18/doc/src/sgml/config.sgml) -
  configuration documentation for current defaults, setting effects, and
  `log_connections` compatibility.
- [postgresql.conf.sample](../../../../raw/postgres-18/src/backend/utils/misc/postgresql.conf.sample) -
  shipped sample configuration defaults.
- [release-18.sgml](../../../../raw/postgres-18/doc/src/sgml/release-18.sgml) -
  v18 release-note entries for `effective_io_concurrency`,
  `maintenance_io_concurrency`, and `log_connections`.
- [backend_startup.c](../../../../raw/postgres-18/src/backend/tcop/backend_startup.c),
  [backend_startup.h](../../../../raw/postgres-18/src/include/tcop/backend_startup.h),
  and [guc.c](../../../../raw/postgres-18/src/backend/utils/misc/guc.c) -
  `log_connections` option parsing and `PGC_SU_BACKEND` application rules.
- [password.sql](../../../../raw/postgres-18/src/test/regress/sql/password.sql),
  [001_ssltests.pl](../../../../raw/postgres-18/src/test/ssl/t/001_ssltests.pl),
  [001_password.pl](../../../../raw/postgres-18/src/test/authentication/t/001_password.pl),
  [select_parallel.sql](../../../../raw/postgres-18/src/test/regress/sql/select_parallel.sql),
  [tablespace.sql](../../../../raw/postgres-18/src/test/regress/sql/tablespace.sql),
  [vacuum.sql](../../../../raw/postgres-18/src/test/regress/sql/vacuum.sql), and
  [pg_regress.c](../../../../raw/postgres-18/src/test/regress/pg_regress.c) -
  individual GUC behavior tests and harness settings.

## Open Questions

- This page scopes "default changes" to settings present in both v12 and v18.
  A full v12-to-v18 settings inventory would also enumerate settings added and
  removed across v13-v18, not just changed defaults for common settings.
- Old values and introducing versions are derived from this checkout's own Git
  history and in-tree version strings, with the PostgreSQL 12 checkout used as a
  cross-check. A reviewer wanting independent confirmation of PostgreSQL 12
  values can read `src/backend/utils/misc/guc.c` in that pinned checkout.

## Related Pages

- [v18/index](../../index.md)
- [versions](../../../versions.md)
