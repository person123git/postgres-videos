---
type: question
version: 12
pinned_commit: 45b88269a353ad93744772791feb6d01bc7e1e42
verified: false
verified_by_agent: not yet
---

# psql Environment Variables and Timeout Settings in PostgreSQL 12 (unverified)

## Question

> In PostgreSQL 12, what environment variables does psql read, and how would setting statement_timeout and/or lock_timeout impact the user session in psql?

## Short Answer

`psql` reads two classes of environment variables. First, it reads `psql`-specific user-interface variables such as `COLUMNS`, `PSQL_EDITOR`/`EDITOR`/`VISUAL`, `PSQL_EDITOR_LINENUMBER_ARG`, `PSQL_HISTORY`, `PSQL_PAGER`/`PAGER`, `PSQLRC`, `SHELL`, and `TMPDIR`; the shared frontend logging code also reads `PG_COLOR` and, when color is active, `PG_COLORS` [psql-ref.sgml#environment](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4340-L4486) [startup.c#COLUMNS-and-connect](../../../../raw/postgres-12/src/bin/psql/startup.c#L150-L267) [command.c#editor-and-tempfile](../../../../raw/postgres-12/src/bin/psql/command.c#L3378-L3475) [print.c#PageOutput](../../../../raw/postgres-12/src/fe_utils/print.c#L2990-L3032) [logging.c#PG_COLOR](../../../../raw/postgres-12/src/common/logging.c#L35-L92). Second, because `psql` connects through libpq with `PQconnectdbParams()`, it also honors libpq environment variables such as `PGHOST`, `PGHOSTADDR`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGPASSFILE`, `PGSERVICE`, `PGSERVICEFILE`, `PGOPTIONS`, `PGAPPNAME`, SSL/GSS variables, `PGCONNECT_TIMEOUT`, `PGCLIENTENCODING`, and `PGTARGETSESSIONATTRS` [startup.c#PQconnectdbParams](../../../../raw/postgres-12/src/bin/psql/startup.c#L238-L267) [fe-connect.c#PQconninfoOptions](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L157-L345) [libpq.sgml#libpq-envars](../../../../raw/postgres-12/doc/src/sgml/libpq.sgml#L7297-L7665).

There is no dedicated `PGSTATEMENTTIMEOUT` or `PGLOCKTIMEOUT` variable in v12. To set these for a `psql` session from the environment, use `PGOPTIONS='-c statement_timeout=... -c lock_timeout=...'`; libpq documents that `PGOPTIONS` settings become defaults for the life of that session and do not affect other sessions [config.sgml#PGOPTIONS-example](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L338-L356). Inside `psql`, `SET statement_timeout` and `SET lock_timeout` are ordinary server-side GUC changes. Both are `PGC_USERSET`, so any user can set them for the current session or transaction without restart or reload [guc.c#statement-and-lock-timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2378-L2398) [catalogs.sgml#context-user](../../../../raw/postgres-12/doc/src/sgml/catalogs.sgml#L10505-L10614).

`statement_timeout` aborts a statement that runs longer than its limit; `lock_timeout` aborts a statement only while it waits too long to acquire a table, index, row, or other lock, and the lock limit is applied separately to each lock acquisition attempt [config.sgml#statement_timeout](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7669-L7699) [config.sgml#lock_timeout](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7701-L7738). If both are set, the earlier timeout is what the user sees; setting `lock_timeout` equal to or larger than a nonzero `statement_timeout` is usually not useful because the statement timeout will fire first [postgres.c#timeout-reporting](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L3058-L3095) [timeouts.out#combined-timeouts](../../../../raw/postgres-12/src/test/isolation/expected/timeouts.out#L31-L73).

## Environment Variables Read By psql

### psql-specific and frontend variables

| Variable | Effect in psql |
|---|---|
| `COLUMNS` | Captured at startup before readline can change it; when `\pset columns` is zero, it helps decide wrapped output width, pager use, and expanded-auto vertical output [startup.c#COLUMNS](../../../../raw/postgres-12/src/bin/psql/startup.c#L150-L181) [psql-ref.sgml#COLUMNS](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4352-L4364). |
| `PG_COLOR`, `PG_COLORS` | `PG_COLOR` enables colored diagnostic messages for frontend tools; when color is enabled, `PG_COLORS` can customize the SGR sequences for error, warning, and locus output [logging.c#PG_COLOR](../../../../raw/postgres-12/src/common/logging.c#L35-L92) [psql-ref.sgml#PG_COLOR](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4378-L4387). |
| `PGCLIENTENCODING` | libpq uses it as the default `client_encoding`; `psql` also checks it and only injects `client_encoding=auto` for an interactive terminal when `PGCLIENTENCODING` is not already set [startup.c#PGCLIENTENCODING](../../../../raw/postgres-12/src/bin/psql/startup.c#L238-L267) [fe-connect.c#PQconninfoOptions](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L217-L247) [libpq.sgml#PGCLIENTENCODING](../../../../raw/postgres-12/doc/src/sgml/libpq.sgml#L7557-L7575). |
| `PSQL_EDITOR`, `EDITOR`, `VISUAL` | Editor for `\e`, `\ef`, and `\ev`; `psql` checks them in that order, then falls back to the compiled default editor [command.c#editor-selection](../../../../raw/postgres-12/src/bin/psql/command.c#L3378-L3406) [psql-ref.sgml#editor-env](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4389-L4404). |
| `PSQL_EDITOR_LINENUMBER_ARG` | Argument prefix used when opening an editor at a requested line number; on Unix the compiled default can supply `+`, while Windows has no default [command.c#line-number-arg](../../../../raw/postgres-12/src/bin/psql/command.c#L3396-L3406) [psql-ref.sgml#line-number-arg](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4406-L4431). |
| `PSQL_HISTORY` | Alternative command history file when the `HISTFILE` psql variable is not set; tilde expansion is applied [input.c#PSQL_HISTORY](../../../../raw/postgres-12/src/bin/psql/input.c#L350-L392) [psql-ref.sgml#PSQL_HISTORY](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4434-L4442). |
| `PSQL_PAGER`, `PAGER` | Pager command for query and help output; `PSQL_PAGER` wins over `PAGER`, and an empty or all-whitespace value disables the pager path [print.c#PageOutput](../../../../raw/postgres-12/src/fe_utils/print.c#L2990-L3032) [psql-ref.sgml#pager-env](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4444-L4458). |
| `PSQLRC` | Alternative user startup file. `psql` always tries the system `psqlrc` first, then `PSQLRC` if set and nonempty, otherwise the default user file [startup.c#process_psqlrc](../../../../raw/postgres-12/src/bin/psql/startup.c#L754-L789) [psql-ref.sgml#PSQLRC](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4465-L4471). |
| `SHELL` and Windows `COMSPEC` | Shell used by the `\!` command when no command argument is supplied; on Windows `COMSPEC` is the fallback if `SHELL` is unset [command.c#shell-selection](../../../../raw/postgres-12/src/bin/psql/command.c#L4376-L4395) [psql-ref.sgml#SHELL](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4477-L4485). |
| `TMPDIR` | Directory for temporary edit files used by `\e` without an explicit file name; Unix defaults to `/tmp` when `TMPDIR` is not set [command.c#TMPDIR](../../../../raw/postgres-12/src/bin/psql/command.c#L3454-L3475) [psql-ref.sgml#TMPDIR](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4487-L4497). |
| Windows `APPDATA` | On Windows, the shared path helper uses `APPDATA` to locate the PostgreSQL application-data directory used for default `psqlrc` and history paths; on Unix it uses the password database, not `HOME` [path.c#get_home_path](../../../../raw/postgres-12/src/port/path.c#L801-L835) [psql-ref.sgml#files](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4510-L4564). |

The `psql` reference names only `PGDATABASE`, `PGHOST`, `PGPORT`, and `PGUSER` in its own environment section, but then states that `psql`, like most PostgreSQL utilities, also uses the libpq environment variables [psql-ref.sgml#libpq-env-note](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4366-L4376) [psql-ref.sgml#libpq-env-note-2](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4499-L4505).

### libpq connection and session variables used by psql

`psql` passes command-line host, port, user, password, dbname, fallback application name, and sometimes `client_encoding=auto` into `PQconnectdbParams()` [startup.c#PQconnectdbParams](../../../../raw/postgres-12/src/bin/psql/startup.c#L238-L267). libpq then fills missing values from service definitions, environment variables, and compiled defaults in that order: `parseServiceInfo()` checks `PGSERVICE`, `PGSERVICEFILE`, and the system service file directory; `conninfo_add_defaults()` skips explicit and service-provided values, then copies each option's `envvar` fallback, and only then uses compiled defaults [fe-connect.c#service-info](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L4957-L5012) [fe-connect.c#conninfo_add_defaults](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L5663-L5725).

| Group | Variables |
|---|---|
| Connection identity and password defaults | `PGHOST`, `PGHOSTADDR`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGPASSFILE`, `PGSERVICE`, `PGSERVICEFILE`; `PGPASSWORD` works but the docs warn against it because process environments can be visible to other OS users on some systems [fe-connect.c#PQconninfoOptions](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L189-L231) [libpq.sgml#connection-envars](../../../../raw/postgres-12/doc/src/sgml/libpq.sgml#L7304-L7410). |
| Startup options and client behavior | `PGOPTIONS`, `PGAPPNAME`, `PGCLIENTENCODING`, `PGTARGETSESSIONATTRS` [fe-connect.c#PQconninfoOptions](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L237-L345) [libpq.sgml#startup-envars](../../../../raw/postgres-12/doc/src/sgml/libpq.sgml#L7414-L7575). |
| SSL and GSS options | `PGSSLMODE`, deprecated `PGREQUIRESSL`, `PGSSLCOMPRESSION`, `PGSSLCERT`, `PGSSLKEY`, `PGSSLROOTCERT`, `PGSSLCRL`, `PGREQUIREPEER`, `PGGSSENCMODE`, `PGKRBSRVNAME`, `PGGSSLIB`; `PGSSLMODE` takes precedence over deprecated `PGREQUIRESSL` [fe-connect.c#ssl-gss-options](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L257-L331) [fe-connect.c#PGREQUIRESSL](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L5688-L5725) [libpq.sgml#ssl-gss-envars](../../../../raw/postgres-12/doc/src/sgml/libpq.sgml#L7434-L7554). |
| Connection timeout | `PGCONNECT_TIMEOUT` [fe-connect.c#connect-timeout-env](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L209-L216) [libpq.sgml#PGCONNECT_TIMEOUT](../../../../raw/postgres-12/doc/src/sgml/libpq.sgml#L7547-L7554). |
| Session-default GUC shorthands | `PGDATESTYLE`, `PGTZ`, and `PGGEQO`; libpq maps these to `datestyle`, `timezone`, and `geqo` startup options [fe-connect.c#EnvironmentOptions](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L345-L359) [libpq.sgml#session-envars](../../../../raw/postgres-12/doc/src/sgml/libpq.sgml#L7577-L7621). |
| Internal libpq behavior | `PGSYSCONFDIR` selects the directory for `pg_service.conf`, and `PGLOCALEDIR` selects locale files for message localization [fe-connect.c#system-service-file](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L4998-L5012) [fe-misc.c#PGLOCALEDIR](../../../../raw/postgres-12/src/interfaces/libpq/fe-misc.c#L1233-L1275) [libpq.sgml#internal-envars](../../../../raw/postgres-12/doc/src/sgml/libpq.sgml#L7623-L7654). |
| Legacy accepted fields | Source still defines `PGAUTHTYPE` and `PGTTY` environment fallbacks, but comments mark `authtype` and `tty` as no longer used and kept only for old connection strings [fe-connect.c#legacy-options](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L189-L247). |

## Setting statement_timeout and lock_timeout in psql

Use `SET` for the current `psql` session:

```sql
SET /* wiki_psql_timeout_session */ statement_timeout = '5min';
SET /* wiki_psql_timeout_session */ lock_timeout = '5s';
```

Use `SET LOCAL` for only the current transaction:

```sql
BEGIN /* wiki_psql_timeout_tx */;
SET /* wiki_psql_timeout_local */ LOCAL statement_timeout = '30s';
SET /* wiki_psql_timeout_local */ LOCAL lock_timeout = '2s';
COMMIT /* wiki_psql_timeout_tx */;
```

Use `PGOPTIONS` to set startup defaults before `psql` connects:

```sh
PGOPTIONS='-c statement_timeout=5min -c lock_timeout=5s' psql
```

`SET` affects only the current session. If `SET` is issued inside a transaction that later aborts, the setting is rolled back; after a committed transaction, it lasts until session end unless another `SET` overrides it. `SET LOCAL` lasts only until the end of the current transaction, and outside a transaction block it has no effect beyond a warning [set.sgml#description](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L24-L75) [set.sgml#SESSION-LOCAL](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L89-L104). `PGOPTIONS` settings are defaults for the life of that libpq session and do not affect other sessions [config.sgml#PGOPTIONS-example](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L338-L356).

The `postgresql.conf.sample` defaults for both timeouts are zero, meaning disabled [postgresql.conf.sample#timeouts](../../../../raw/postgres-12/src/backend/utils/misc/postgresql.conf.sample#L626-L635). The v12 docs recommend against setting either timeout globally in `postgresql.conf` because that affects all sessions, so for an interactive `psql` user the usual safer choices are `SET`, `SET LOCAL`, `PGOPTIONS`, or a personal `.psqlrc` command that runs after connection [config.sgml#statement_timeout](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7669-L7699) [config.sgml#lock_timeout](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7701-L7738) [psql-ref.sgml#psqlrc-files](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4510-L4549).

## Session Impact

### statement_timeout

`statement_timeout` is stored in the backend variable `StatementTimeout`, defaults to zero, has unit milliseconds, and a zero value disables it [guc.c#statement_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2378-L2387). When nonzero, the backend arms the `STATEMENT_TIMEOUT` timer while a statement is active and disables it after the statement path is done [postgres.c#enable_statement_timeout](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L4685-L4716). If it fires, the backend reports `ERROR: canceling statement due to statement timeout` with SQLSTATE class `query_canceled`; because the ereport level is `ERROR`, it cancels the statement rather than closing the `psql` process [postgres.c#timeout-reporting](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L3058-L3095).

The user-visible effect is a cap on total statement duration. The docs define the measurement window as the time from command arrival at the server until server completion; for extended query protocol, it starts on query-related messages and is canceled by Execute or Sync completion [config.sgml#statement_timeout](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7669-L7699). Long CPU work, long I/O, and time spent waiting for locks all count toward `statement_timeout` because the setting limits the statement as a whole.

### lock_timeout

`lock_timeout` is stored in `LockTimeout`, defaults to zero, has unit milliseconds, and a zero value disables it [guc.c#lock_timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2389-L2398). When a backend has to sleep waiting for a lock, `ProcSleep()` arms both the deadlock timeout and, if `LockTimeout > 0`, the `LOCK_TIMEOUT` timer; when the wait ends or is cleaned up, PostgreSQL disables the lock/deadlock timers while preserving the indicator that a lock timeout fired [proc.c#enable-lock-timeout](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1240-L1315) [proc.c#disable-lock-timeout](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1528-L1555) [proc.c#LockErrorCleanup](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L720-L742). If it fires, the backend reports `ERROR: canceling statement due to lock timeout` with SQLSTATE class `lock_not_available` [postgres.c#timeout-reporting](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L3058-L3095).

The user-visible effect is narrower than `statement_timeout`: `lock_timeout` only applies while waiting for locks, and the time limit applies separately to each lock acquisition attempt [config.sgml#lock_timeout](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7701-L7738). It covers explicit lock requests such as `LOCK TABLE` and `SELECT FOR UPDATE` without `NOWAIT`, and it also covers implicit locks that ordinary DML or DDL must acquire [config.sgml#lock_timeout](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7701-L7738).

### Using both together

When both indicators are set, the interrupt handler fetches and clears both indicators, then reports whichever timeout finished earlier; ties are broken in favor of lock timeout [postgres.c#timeout-reporting](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L3058-L3095). The docs therefore say that when `statement_timeout` is nonzero, setting `lock_timeout` to the same or a larger value is rather pointless because `statement_timeout` would always trigger first [config.sgml#lock_timeout](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7721-L7728).

The isolation tests cover both table-level and row-level lock waits: a session with only `statement_timeout` gets statement-timeout errors, a session with only `lock_timeout` gets lock-timeout errors, `lock_timeout = 5000` with `statement_timeout = 6000` reports lock timeout, and `lock_timeout = 6000` with `statement_timeout = 5000` reports statement timeout [timeouts.spec#permutations](../../../../raw/postgres-12/src/test/isolation/specs/timeouts.spec#L1-L38) [timeouts.out#results](../../../../raw/postgres-12/src/test/isolation/expected/timeouts.out#L1-L73).

Practical patterns in `psql`:

| Goal | Setting pattern | Expected effect |
|---|---|---|
| Cap all ad hoc statements in one interactive session | `SET statement_timeout = '5min';` | Any statement in that `psql` session that exceeds five minutes is canceled with statement-timeout ERROR [config.sgml#statement_timeout](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7669-L7699). |
| Fail quickly when blocked by locks, but allow normal long work | `SET lock_timeout = '5s';` and leave `statement_timeout = 0` or much larger | Statements can run longer than five seconds if they are not waiting on locks, but any single lock wait over five seconds aborts the statement with lock-timeout ERROR [config.sgml#lock_timeout](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7701-L7738). |
| Put a short lock-wait guard inside a larger statement budget | `SET statement_timeout = '10min'; SET lock_timeout = '5s';` | Lock waits fail quickly; non-lock execution can continue up to ten minutes [postgres.c#timeout-reporting](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L3058-L3095) [timeouts.out#combined-timeouts](../../../../raw/postgres-12/src/test/isolation/expected/timeouts.out#L31-L73). |
| Limit only one transaction | `SET LOCAL statement_timeout = '30s'; SET LOCAL lock_timeout = '2s';` inside `BEGIN` | The timeout values disappear at transaction end; after commit or rollback, the session-level values apply again [set.sgml#LOCAL](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L43-L56) [set.sgml#SESSION-LOCAL](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L89-L104). |

## Context Reviewed

- [psql-ref.sgml#environment-and-files](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4340-L4564)
- [startup.c#connection-startup-and-psqlrc](../../../../raw/postgres-12/src/bin/psql/startup.c#L150-L280)
- [startup.c#process_psqlrc](../../../../raw/postgres-12/src/bin/psql/startup.c#L754-L789)
- [command.c#editor-tempdir-shell](../../../../raw/postgres-12/src/bin/psql/command.c#L3378-L3475)
- [command.c#shell-selection](../../../../raw/postgres-12/src/bin/psql/command.c#L4376-L4395)
- [input.c#history-file](../../../../raw/postgres-12/src/bin/psql/input.c#L350-L392)
- [print.c#pager](../../../../raw/postgres-12/src/fe_utils/print.c#L2990-L3032)
- [logging.c#color-env](../../../../raw/postgres-12/src/common/logging.c#L35-L92)
- [path.c#home-path](../../../../raw/postgres-12/src/port/path.c#L801-L835)
- [fe-connect.c#connection-options](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L157-L370)
- [fe-connect.c#service-and-defaults](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L4957-L5012)
- [fe-connect.c#conninfo-defaults](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L5663-L5725)
- [libpq.sgml#environment-variables](../../../../raw/postgres-12/doc/src/sgml/libpq.sgml#L7297-L7665)
- [guc.c#statement-and-lock-timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2378-L2398)
- [config.sgml#PGOPTIONS-and-timeouts](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L338-L356)
- [config.sgml#timeout-docs](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7669-L7738)
- [postgres.c#timeout-reporting](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L3058-L3095)
- [postgres.c#statement-timeout-timer](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L4685-L4716)
- [proc.c#lock-wait-timers](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1240-L1315)
- [timeouts.spec](../../../../raw/postgres-12/src/test/isolation/specs/timeouts.spec#L1-L38)
- [timeouts.out](../../../../raw/postgres-12/src/test/isolation/expected/timeouts.out#L1-L73)

## Evidence Map

| Claim | Source |
|---|---|
| `psql` has its own documented environment section and also uses libpq environment variables | [psql-ref.sgml#environment](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml#L4340-L4505) |
| `psql` supplies explicit connection parameters and calls `PQconnectdbParams()` | [startup.c#PQconnectdbParams](../../../../raw/postgres-12/src/bin/psql/startup.c#L238-L267) |
| libpq maps connection option names to environment-variable fallbacks | [fe-connect.c#PQconninfoOptions](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L157-L345) |
| Service files are read before ordinary environment defaults; environment comes before compiled defaults | [fe-connect.c#service-info](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L4957-L5012) [fe-connect.c#conninfo_add_defaults](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c#L5663-L5725) |
| `PGOPTIONS` can set session GUC defaults for the life of one libpq session | [config.sgml#PGOPTIONS-example](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L338-L356) |
| `statement_timeout` and `lock_timeout` are user-context millisecond GUCs with zero disabled | [guc.c#statement-and-lock-timeout](../../../../raw/postgres-12/src/backend/utils/misc/guc.c#L2378-L2398) |
| `SET` and `SET LOCAL` scope session and transaction-local changes | [set.sgml#description](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L24-L75) [set.sgml#SESSION-LOCAL](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml#L89-L104) |
| `statement_timeout` measures whole statement duration and aborts on timeout | [config.sgml#statement_timeout](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7669-L7699) [postgres.c#enable_statement_timeout](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L4685-L4716) |
| `lock_timeout` applies only to lock waits, separately per lock acquisition | [config.sgml#lock_timeout](../../../../raw/postgres-12/doc/src/sgml/config.sgml#L7701-L7738) [proc.c#enable-lock-timeout](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c#L1240-L1315) |
| If both fire, PostgreSQL reports the one whose finish time came first | [postgres.c#timeout-reporting](../../../../raw/postgres-12/src/backend/tcop/postgres.c#L3058-L3095) |
| Same-checkout tests cover table-level and row-level lock waits with both timeout orderings | [timeouts.spec#permutations](../../../../raw/postgres-12/src/test/isolation/specs/timeouts.spec#L1-L38) [timeouts.out#results](../../../../raw/postgres-12/src/test/isolation/expected/timeouts.out#L1-L73) |

## Source References

- [psql-ref.sgml](../../../../raw/postgres-12/doc/src/sgml/ref/psql-ref.sgml) - psql environment and startup-file documentation.
- [startup.c](../../../../raw/postgres-12/src/bin/psql/startup.c), [command.c](../../../../raw/postgres-12/src/bin/psql/command.c), [input.c](../../../../raw/postgres-12/src/bin/psql/input.c), and [print.c](../../../../raw/postgres-12/src/fe_utils/print.c) - psql startup, connection, editor, history, shell, temp-file, and pager behavior.
- [fe-connect.c](../../../../raw/postgres-12/src/interfaces/libpq/fe-connect.c), [fe-misc.c](../../../../raw/postgres-12/src/interfaces/libpq/fe-misc.c), and [libpq.sgml](../../../../raw/postgres-12/doc/src/sgml/libpq.sgml) - libpq connection and internal environment variables.
- [guc.c](../../../../raw/postgres-12/src/backend/utils/misc/guc.c), [config.sgml](../../../../raw/postgres-12/doc/src/sgml/config.sgml), and [set.sgml](../../../../raw/postgres-12/doc/src/sgml/ref/set.sgml) - timeout GUC definitions, documentation, and SQL scope.
- [postgres.c](../../../../raw/postgres-12/src/backend/tcop/postgres.c), [proc.c](../../../../raw/postgres-12/src/backend/storage/lmgr/proc.c), [timeouts.spec](../../../../raw/postgres-12/src/test/isolation/specs/timeouts.spec), and [timeouts.out](../../../../raw/postgres-12/src/test/isolation/expected/timeouts.out) - runtime timeout timers, error reporting, and test coverage.

## Open Questions

- No unresolved factual questions remain in this pass. The page is marked `(unverified)` because `verified:` is human-only and `verified_by_agent` has not been advanced after a separate full-page re-check.

## Related Pages

- [How pg_stat_statements Works and Which Settings Affect It in PostgreSQL 12 (unverified)](../observability/pg-stat-statements.md)
- [EXPLAIN ANALYZE BUFFERS Output in PostgreSQL 12 (unverified)](../observability/explain-analyze-buffers-output.md)