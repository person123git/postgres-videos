---
type: question
version: 17
pinned_commit: 786db8dcf168bd9df8f55047337525ac19118b1c
verified: false
verified_by_agent: not yet
---

# PostgreSQL 17 Contrib Extensions (unverified)

## Question

In PostgreSQL 17, list all contrib extensions with a comprehensive explanation of each extension.

## Answer Up Front

PostgreSQL 17 ships **53 contrib extensions** in the pinned `raw/postgres-17/`
checkout. This page counts a contrib component as an extension when it has a
`*.control` file and is meant to be registered in a database with
`CREATE EXTENSION`. The PostgreSQL documentation describes contrib components as
optional modules outside the core system, says many of them package SQL objects
as extensions, and explains that `CREATE EXTENSION extension_name` registers
those objects in the current database
([contrib.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/contrib.sgml#L10-L31),
[contrib.sgml#CREATE-EXTENSION](../../../../raw/postgres-17/doc/src/sgml/contrib.sgml#L63-L82)).

Some neighboring contrib components are not `CREATE EXTENSION` extensions. The
same documentation says some contrib components are loaded into the server in
other ways, such as `shared_preload_libraries`, and it separates utility
programs into a different appendix
([contrib.sgml#non-extension-components](../../../../raw/postgres-17/doc/src/sgml/contrib.sgml#L107-L111),
[contrib.sgml#contrib-programs](../../../../raw/postgres-17/doc/src/sgml/contrib.sgml#L160-L174)).

## Quick Install Notes

After the contrib code is installed on the server, most entries below are made
available in a database with `CREATE EXTENSION name;`. A trusted extension can be
installed by a non-superuser that has `CREATE` privilege on the database; other
extensions need superuser privileges unless privileges are delegated by the
installation. PostgreSQL documents the default trusted-extension rule and lists
the trusted contrib extensions in the contrib chapter
([contrib.sgml#trusted-extensions](../../../../raw/postgres-17/doc/src/sgml/contrib.sgml#L86-L104)).

## Complete Extension List

| Extension | What it adds | Operational notes |
|---|---|---|
| `amcheck` | Consistency-checking functions for relations. Its B-tree checks verify access-method invariants such as logical item ordering; `verify_heapam` reports heap corruptions as rows where possible. | Use it for corruption checks and incident triage. It can reveal structural information through error or corruption reports, so granting execution needs care. [amcheck.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/amcheck.sgml#L10-L56) |
| `autoinc` | A trigger function that writes the next sequence value into one or more integer columns. | It predates modern identity/serial patterns and can override user-supplied values on insert, with optional update behavior. [contrib-spi.sgml#autoinc](../../../../raw/postgres-17/doc/src/sgml/contrib-spi.sgml#L125-L150), [autoinc--1.0.sql#function](../../../../raw/postgres-17/contrib/spi/autoinc--1.0.sql#L6-L9) |
| `bloom` | A Bloom-filter index access method. It stores lossy signatures for indexed attributes, supports equality searches, and can cover many queried column combinations with one index. | False positives require heap recheck. It is most useful for wide tables queried by arbitrary equality combinations; btree is faster for simple equality/range cases. [bloom.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/bloom.sgml#L10-L39) |
| `bool_plperl` | A transform between SQL `bool` and trusted PL/Perl. It fixes the default PL/Perl behavior where SQL `false` reaches Perl as the true string `'f'`. | Requires `plperl`; use the `TRANSFORM` function attribute on PL/Perl functions that accept or return `bool`. [plperl.sgml#bool-transform](../../../../raw/postgres-17/doc/src/sgml/plperl.sgml#L195-L210), [bool_plperl--1.0.sql#transform](../../../../raw/postgres-17/contrib/bool_plperl/bool_plperl--1.0.sql#L14-L19) |
| `bool_plperlu` | The same SQL `bool` transform for untrusted PL/PerlU. | Requires `plperlu`; it creates `CREATE TRANSFORM FOR bool LANGUAGE plperlu`. [plperl.sgml#bool-transform](../../../../raw/postgres-17/doc/src/sgml/plperl.sgml#L195-L210), [bool_plperlu--1.0.sql#transform](../../../../raw/postgres-17/contrib/bool_plperl/bool_plperlu--1.0.sql#L14-L19) |
| `btree_gin` | GIN operator classes with B-tree-equivalent behavior for common scalar types, `bytea`, network types, UUIDs, booleans, and enum types. | It usually does not beat normal btree indexes and cannot enforce uniqueness, but it is useful when a multicolumn GIN index should combine GIN-searchable and scalar columns. [btree-gin.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/btree-gin.sgml#L10-L39) |
| `btree_gist` | GiST operator classes with B-tree-equivalent behavior for common scalar types and enum types. | It cannot enforce uniqueness, but it supports GiST features that btree lacks, including `<>` support for exclusion constraints and distance operators for nearest-neighbor searches on supported types. [btree-gist.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/btree-gist.sgml#L10-L59) |
| `citext` | A case-insensitive string type, `citext`, that compares by internally applying `lower()` while otherwise behaving much like `text`. | It can simplify case-insensitive equality and uniqueness, but the docs suggest considering nondeterministic collations for broader Unicode/case/accent behavior. [citext.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/citext.sgml#L10-L23), [citext.sgml#comparison](../../../../raw/postgres-17/doc/src/sgml/citext.sgml#L115-L130) |
| `cube` | A multidimensional `cube` type for points and intervals in N-dimensional space. | Cube values use 64-bit floating-point storage and provide specialized operators/functions; `earthdistance` depends on this extension for one of its two approaches. [cube.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/cube.sgml#L10-L20), [cube.sgml#syntax-precision](../../../../raw/postgres-17/doc/src/sgml/cube.sgml#L22-L108) |
| `dblink` | Functions for connecting from one PostgreSQL database session to other PostgreSQL databases. | It supports persistent remote connections and reports extension wait events; `postgres_fdw` is the more modern, standards-compliant alternative for remote table access. [dblink.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/dblink.sgml#L10-L54), [dblink.sgml#connect](../../../../raw/postgres-17/doc/src/sgml/dblink.sgml#L56-L80) |
| `dict_int` | A full-text-search dictionary template and default dictionary for integer tokens. | It can limit indexed integer token growth with options such as `maxlen`, `rejectlong`, and `absval`. [dict-int.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/dict-int.sgml#L11-L23), [dict-int.sgml#configuration](../../../../raw/postgres-17/doc/src/sgml/dict-int.sgml#L25-L77) |
| `dict_xsyn` | An extended-synonym full-text-search dictionary template. It can replace words with synonym groups so any synonym can match. | It reads synonym rules from a `$SHAREDIR/tsearch_data/*.rules` file and has options controlling whether originals and synonyms match or are emitted. [dict-xsyn.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/dict-xsyn.sgml#L10-L15), [dict-xsyn.sgml#configuration](../../../../raw/postgres-17/doc/src/sgml/dict-xsyn.sgml#L17-L80) |
| `earthdistance` | Great-circle distance functions with two models: a cube-based 3D representation and a point-based longitude/latitude representation. | It assumes a spherical Earth. The cube-based path requires `cube`, and the docs warn to install `earthdistance` and `cube` in a trusted schema/search-path setup. [earthdistance.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/earthdistance.sgml#L10-L30), [earthdistance.sgml#security](../../../../raw/postgres-17/doc/src/sgml/earthdistance.sgml#L32-L45) |
| `file_fdw` | A foreign-data wrapper for reading server-side files or program output through foreign tables. | Inputs must be readable by `COPY FROM`; the foreign data is read-only. [file-fdw.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/file-fdw.sgml#L10-L18), [file-fdw.sgml#options](../../../../raw/postgres-17/doc/src/sgml/file-fdw.sgml#L20-L40) |
| `fuzzystrmatch` | String-similarity and string-distance functions, including Soundex, Daitch-Mokotoff Soundex, Levenshtein, Metaphone, and Double Metaphone. | Some phonetic functions do not work well with multibyte encodings; the docs recommend Daitch-Mokotoff or Levenshtein for such data. [fuzzystrmatch.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/fuzzystrmatch.sgml#L10-L23), [fuzzystrmatch.sgml#levenshtein](../../../../raw/postgres-17/doc/src/sgml/fuzzystrmatch.sgml#L247-L284) |
| `hstore` | An `hstore` key/value type for storing text key/value pairs in one PostgreSQL value. | Keys are unique, values can be SQL `NULL`, and PL transform extensions are available separately. [hstore.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/hstore.sgml#L10-L22), [hstore.sgml#external-representation](../../../../raw/postgres-17/doc/src/sgml/hstore.sgml#L24-L68) |
| `hstore_plperl` | A transform that maps `hstore` values to Perl hashes for trusted PL/Perl functions. | Requires `hstore` and `plperl`; the docs recommend installing transform extensions in the same schema as `hstore`. [hstore.sgml#transforms](../../../../raw/postgres-17/doc/src/sgml/hstore.sgml#L936-L955), [hstore_plperl--1.0.sql#transform](../../../../raw/postgres-17/contrib/hstore_plperl/hstore_plperl--1.0.sql#L14-L17) |
| `hstore_plperlu` | A transform that maps `hstore` values to Perl hashes for untrusted PL/PerlU functions. | Requires `hstore` and `plperlu`; it creates `CREATE TRANSFORM FOR hstore LANGUAGE plperlu`. [hstore.sgml#transforms](../../../../raw/postgres-17/doc/src/sgml/hstore.sgml#L936-L955), [hstore_plperlu--1.0.sql#transform](../../../../raw/postgres-17/contrib/hstore_plperl/hstore_plperlu--1.0.sql#L14-L17) |
| `hstore_plpython3u` | A transform that maps `hstore` values to Python dictionaries for PL/Python 3U functions. | Requires `hstore` and `plpython3u`; install it with `hstore` in a trusted schema. [hstore.sgml#transforms](../../../../raw/postgres-17/doc/src/sgml/hstore.sgml#L936-L955), [hstore_plpython3u--1.0.sql#transform](../../../../raw/postgres-17/contrib/hstore_plpython/hstore_plpython3u--1.0.sql#L14-L19) |
| `insert_username` | A trigger function that stores the current database user's name into a text column. | Use it as a `BEFORE INSERT` and/or `BEFORE UPDATE` trigger to track who changed a row. [contrib-spi.sgml#insert-username](../../../../raw/postgres-17/doc/src/sgml/contrib-spi.sgml#L152-L171), [insert_username--1.0.sql#function](../../../../raw/postgres-17/contrib/spi/insert_username--1.0.sql#L6-L9) |
| `intagg` | Compatibility wrappers for integer-array aggregation and enumeration. | It is obsolete because built-in functions provide a superset: `int_array_aggregate(integer)` wraps `array_agg`, and `int_array_enum(integer[])` wraps `unnest`. [intagg.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/intagg.sgml#L10-L16), [intagg.sgml#functions](../../../../raw/postgres-17/doc/src/sgml/intagg.sgml#L18-L49) |
| `intarray` | Functions, operators, and index support for null-free one-dimensional integer arrays. | Operations error on arrays containing `NULL`; many operations treat multidimensional arrays as linear storage-order arrays. [intarray.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/intarray.sgml#L10-L31), [intarray.sgml#functions](../../../../raw/postgres-17/doc/src/sgml/intarray.sgml#L33-L90) |
| `isn` | Data types for international standard numbers such as EAN13, UPC, ISBN, ISMN, and ISSN. | Input is validated and output hyphenated using a hard-coded prefix list that can become outdated. [isn.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/isn.sgml#L10-L27), [isn.sgml#data-types](../../../../raw/postgres-17/doc/src/sgml/isn.sgml#L30-L90) |
| `jsonb_plperl` | A transform that maps `jsonb` values to Perl arrays, hashes, and scalars for trusted PL/Perl. | This is the trusted PL/Perl variant among the `jsonb` transform extensions. [json.sgml#jsonb-transforms](../../../../raw/postgres-17/doc/src/sgml/json.sgml#L719-L739), [jsonb_plperl--1.0.sql#transform](../../../../raw/postgres-17/contrib/jsonb_plperl/jsonb_plperl--1.0.sql#L14-L19) |
| `jsonb_plperlu` | A transform that maps `jsonb` values to Perl arrays, hashes, and scalars for untrusted PL/PerlU. | Requires `plperlu`; the docs say the non-`jsonb_plperl` JSONB transform extensions require superuser privilege to install. [json.sgml#jsonb-transforms](../../../../raw/postgres-17/doc/src/sgml/json.sgml#L719-L739), [jsonb_plperlu--1.0.sql#transform](../../../../raw/postgres-17/contrib/jsonb_plperl/jsonb_plperlu--1.0.sql#L14-L19) |
| `jsonb_plpython3u` | A transform that maps `jsonb` values to Python dictionaries, lists, and scalars for PL/Python 3U. | Requires `plpython3u`; it creates `CREATE TRANSFORM FOR jsonb LANGUAGE plpython3u`. [json.sgml#jsonb-transforms](../../../../raw/postgres-17/doc/src/sgml/json.sgml#L719-L739), [jsonb_plpython3u--1.0.sql#transform](../../../../raw/postgres-17/contrib/jsonb_plpython/jsonb_plpython3u--1.0.sql#L14-L19) |
| `lo` | Large-object maintenance helpers: a domain-like `lo` type over `oid` and an `lo_manage` trigger. | The trigger unlinks large objects when trigger-controlled reference columns are deleted or modified, assuming only one database reference to each managed large object. [lo.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/lo.sgml#L10-L20), [lo.sgml#rationale](../../../../raw/postgres-17/doc/src/sgml/lo.sgml#L47-L63) |
| `ltree` | Data types and operators for hierarchical label paths. `ltree` stores a path, `lquery` represents path patterns, and `ltxtquery` supports full-text-like matching. | Labels and paths have length rules, and the module provides extensive searching facilities for tree-shaped labels. [ltree.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/ltree.sgml#L10-L40), [ltree.sgml#lquery](../../../../raw/postgres-17/doc/src/sgml/ltree.sgml#L41-L120) |
| `ltree_plpython3u` | A transform from SQL `ltree` values to Python lists for PL/Python 3U. | The reverse Python-to-`ltree` transform is not supported. [ltree.sgml#transforms](../../../../raw/postgres-17/doc/src/sgml/ltree.sgml#L839-L848), [ltree_plpython3u--1.0.sql#transform](../../../../raw/postgres-17/contrib/ltree_plpython/ltree_plpython3u--1.0.sql#L10-L12) |
| `moddatetime` | A trigger function that stores the current time into a timestamp column on update. | Use it as a `BEFORE UPDATE` trigger; the target column must be `timestamp` or `timestamp with time zone`. [contrib-spi.sgml#moddatetime](../../../../raw/postgres-17/doc/src/sgml/contrib-spi.sgml#L173-L194), [moddatetime--1.0.sql#function](../../../../raw/postgres-17/contrib/spi/moddatetime--1.0.sql#L6-L9) |
| `pageinspect` | Low-level page-inspection functions for heap and index pages. | It is for debugging, and all functions are superuser-only. [pageinspect.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pageinspect.sgml#L10-L14), [pageinspect.sgml#general-functions](../../../../raw/postgres-17/doc/src/sgml/pageinspect.sgml#L17-L90) |
| `pg_buffercache` | Views/functions that inspect shared-buffer-cache state in real time, plus a low-level buffer eviction function for testing. | Read functions are restricted to superusers and `pg_monitor` by default; eviction is superuser-only. [pgbuffercache.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgbuffercache.sgml#L11-L66) |
| `pg_freespacemap` | Functions that expose the free space map (FSM) value for one page or all pages of a relation. | FSM values are rounded and not fully up-to-date; for indexes the tracked signal is whether pages are entirely unused, not in-page free bytes. [pgfreespacemap.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgfreespacemap.sgml#L10-L21), [pgfreespacemap.sgml#caveats](../../../../raw/postgres-17/doc/src/sgml/pgfreespacemap.sgml#L61-L70) |
| `pg_prewarm` | Manual and automatic prewarming of relation blocks into the OS buffer cache or PostgreSQL shared buffers. | Manual modes are `prefetch`, `read`, and `buffer`; automatic prewarm needs `shared_preload_libraries` and records/reloads shared-buffer contents around restart. [pgprewarm.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgprewarm.sgml#L10-L20), [pgprewarm.sgml#methods](../../../../raw/postgres-17/doc/src/sgml/pgprewarm.sgml#L42-L62) |
| `pg_stat_statements` | Server-wide tracking of planning and execution statistics for SQL statements. | It must be loaded in `shared_preload_libraries` because it needs shared memory; a database still needs `CREATE EXTENSION pg_stat_statements` to expose its views/functions there. [pgstatstatements.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgstatstatements.sgml#L10-L37), [pgstatstatements.sgml#view](../../../../raw/postgres-17/doc/src/sgml/pgstatstatements.sgml#L39-L49) |
| `pg_surgery` | Low-level functions for changing tuple visibility state in damaged relations. | It is unsafe by design and can corrupt or further corrupt a database; use only as a last resort. [pgsurgery.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgsurgery.sgml#L10-L19), [pgsurgery.sgml#functions](../../../../raw/postgres-17/doc/src/sgml/pgsurgery.sgml#L21-L60) |
| `pg_trgm` | Trigram-based text similarity functions, operators, and GiST/GIN index operator classes for fast similar-string search. | Trigrams are groups of three consecutive characters after ignoring non-word characters; similarity ranges from 0 to 1. [pgtrgm.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgtrgm.sgml#L11-L23), [pgtrgm.sgml#concepts-functions](../../../../raw/postgres-17/doc/src/sgml/pgtrgm.sgml#L25-L98) |
| `pg_visibility` | Functions for examining a table's visibility map and page-level visibility bits, checking VM integrity, and rebuilding the VM. | Functions that inspect data-page `PD_ALL_VISIBLE` bits are more expensive than VM-only functions because they must read data blocks. [pgvisibility.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgvisibility.sgml#L10-L42), [pgvisibility.sgml#functions](../../../../raw/postgres-17/doc/src/sgml/pgvisibility.sgml#L44-L100) |
| `pg_walinspect` | SQL functions for low-level inspection of WAL records in the current timeline. | It is similar to `pg_waldump` but SQL-accessible; default access is restricted to superusers and `pg_read_server_files`. [pgwalinspect.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgwalinspect.sgml#L10-L57), [pgwalinspect.sgml#functions](../../../../raw/postgres-17/doc/src/sgml/pgwalinspect.sgml#L59-L94) |
| `pgcrypto` | Cryptographic functions: hashing, HMAC, password hashing, symmetric encryption, public-key encryption, random data, and related helpers. | It requires OpenSSL support at build time; `digest()` and `hmac()` are the basic hash/MAC entry points. [pgcrypto.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgcrypto.sgml#L15-L29), [pgcrypto.sgml#hashing](../../../../raw/postgres-17/doc/src/sgml/pgcrypto.sgml#L31-L88). 17.11 documents a decrypt-side option `ignore-cipher-failure` (values 0/1, default 0, applies to `pgp_sym_decrypt` / `pgp_pub_decrypt`) that restores the behavior from before the CVE-2026-14663 fix by ignoring OpenSSL cipher failures, for recovering incorrectly encrypted messages only; commits `b05cfc69375` (the encryption error-handling fix) and `7eed42aa880` (the option). [pgcrypto.sgml#ignore-cipher-failure](../../../../raw/postgres-17/doc/src/sgml/pgcrypto.sgml#L927-L956) |
| `pgrowlocks` | A function that reports row-level locking information for a table. | It takes `AccessShareLock` and scans rows one by one, so it can be slow for large tables. [pgrowlocks.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgrowlocks.sgml#L10-L19), [pgrowlocks.sgml#scan-cost](../../../../raw/postgres-17/doc/src/sgml/pgrowlocks.sgml#L29-L100) |
| `pgstattuple` | Functions that return tuple-level and page-level statistics, including relation length, dead tuple percentage, free space, and index stats. | Detailed page-level access is restricted by default to `pg_stat_scan_tables`; superusers bypass that restriction. [pgstattuple.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L10-L23), [pgstattuple.sgml#functions](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L26-L42) |
| `postgres_fdw` | A foreign-data wrapper for external PostgreSQL servers. | It uses foreign servers, user mappings, and foreign tables; it supports selecting and modifying remote tables, but some `ON CONFLICT` and remote partition-row-movement cases are limited. [postgres-fdw.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/postgres-fdw.sgml#L12-L24), [postgres-fdw.sgml#usage-limits](../../../../raw/postgres-17/doc/src/sgml/postgres-fdw.sgml#L26-L90) |
| `refint` | SPI trigger functions for referential integrity examples: `check_primary_key()` and `check_foreign_key()`. | Built-in foreign keys supersede it; keep it mainly as an SPI/trigger example. **The module will be removed in PostgreSQL 20** [contrib-spi.sgml:33-35](../../../../raw/postgres-17/doc/src/sgml/contrib-spi.sgml#L33-L35). It requires a secure schema usage pattern and data types whose equality operator is named `=` [contrib-spi.sgml#refint-secure-schema](../../../../raw/postgres-17/doc/src/sgml/contrib-spi.sgml#L38-L44). The *referenced* table and column arguments of `check_primary_key()` [contrib-spi.sgml#check_primary_key-quoting](../../../../raw/postgres-17/doc/src/sgml/contrib-spi.sgml#L56-L79) and the *referencing* table and column arguments of `check_foreign_key()` [contrib-spi.sgml#check_foreign_key-quoting](../../../../raw/postgres-17/doc/src/sgml/contrib-spi.sgml#L88-L118) are copied as-is into internally generated SQL, so the user must double-quote them in `CREATE TRIGGER`, while the other side's column arguments must not be quoted. In 17.11 the removal note came from `e1885a875cb`, the usage guidance from `c0392783c54`, the per-invocation plan cache was dropped by `66a5146dc73`, and a `check_foreign_key()` segfault was fixed by `6b4de201e82`. [contrib-spi.sgml#refint](../../../../raw/postgres-17/doc/src/sgml/contrib-spi.sgml#L27-L123), [refint--1.0.sql#functions](../../../../raw/postgres-17/contrib/spi/refint--1.0.sql#L6-L14) |
| `seg` | A `seg` data type for line segments or floating-point intervals, including fuzzy endpoint precision. | It is useful for measurements where endpoint uncertainty matters and supports interval-style input syntax. [seg.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/seg.sgml#L10-L20), [seg.sgml#rationale-syntax](../../../../raw/postgres-17/doc/src/sgml/seg.sgml#L23-L90) |
| `sslinfo` | Functions that expose SSL connection and client-certificate information for the current client connection. | Most functions return `NULL` when the current connection does not use SSL, and the extension only builds with OpenSSL support. [sslinfo.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/sslinfo.sgml#L10-L26), [sslinfo.sgml#functions](../../../../raw/postgres-17/doc/src/sgml/sslinfo.sgml#L28-L90) |
| `tablefunc` | Set-returning table utilities, most notably `crosstab`, plus helpers such as `normal_rand`. | It is useful for pivot-style output and as examples of C functions returning multiple rows. [tablefunc.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/tablefunc.sgml#L10-L20), [tablefunc.sgml#functions](../../../../raw/postgres-17/doc/src/sgml/tablefunc.sgml#L23-L90) |
| `tcn` | A trigger function that sends notifications when attached table rows change. | It must be an `AFTER` `FOR EACH ROW` trigger; payloads include table name, operation letter, and primary-key column/value pairs. [tcn.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/tcn.sgml#L14-L40) |
| `tsm_system_rows` | A `TABLESAMPLE` method named `SYSTEM_ROWS` that reads up to a requested row count. | It performs block-level sampling, so small samples can show clustering effects, and it does not support `REPEATABLE`. [tsm-system-rows.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/tsm-system-rows.sgml#L11-L40) |
| `tsm_system_time` | A `TABLESAMPLE` method named `SYSTEM_TIME` that samples for a requested maximum number of milliseconds. | It gives time control rather than predictable sample size, uses block-level sampling, and does not support `REPEATABLE`. [tsm-system-time.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/tsm-system-time.sgml#L11-L42) |
| `unaccent` | A filtering text-search dictionary that removes accents/diacritics from lexemes before passing output to the next dictionary. | It is not usable as a normalizing dictionary for the thesaurus dictionary; its rules come from `$SHAREDIR/tsearch_data/*.rules`. [unaccent.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/unaccent.sgml#L10-L28), [unaccent.sgml#configuration](../../../../raw/postgres-17/doc/src/sgml/unaccent.sgml#L30-L84) |
| `uuid-ossp` | UUID generation functions for several standard algorithms plus functions for special UUID constants. | Core PostgreSQL has built-in UUID generation for common needs; this extension remains for special requirements such as version 1, 3, and 5 UUIDs. [uuid-ossp.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/uuid-ossp.sgml#L10-L23), [uuid-ossp.sgml#functions](../../../../raw/postgres-17/doc/src/sgml/uuid-ossp.sgml#L25-L90) |
| `xml2` | XPath querying and XSLT functionality. | The docs mark it as deprecated in favor of newer core SQL/XML functionality, though the APIs are not compatible. [xml2.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/xml2.sgml#L10-L30), [xml2.sgml#functions](../../../../raw/postgres-17/doc/src/sgml/xml2.sgml#L33-L59) |

## Grouped Reading Guide

- **Integrity, storage, and diagnostics:** `amcheck`, `pageinspect`,
  `pg_buffercache`, `pg_freespacemap`, `pg_prewarm`, `pg_surgery`,
  `pg_visibility`, `pg_walinspect`, `pgrowlocks`, and `pgstattuple` expose
  internal state or help inspect corruption, cache contents, storage maps, WAL,
  row locks, and tuple/index statistics
  ([amcheck.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/amcheck.sgml#L10-L56),
  [pageinspect.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pageinspect.sgml#L10-L14),
  [pgstattuple.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml#L10-L23)).
- **Indexing and search helpers:** `bloom`, `btree_gin`, `btree_gist`,
  `dict_int`, `dict_xsyn`, `pg_trgm`, `unaccent`, `tsm_system_rows`, and
  `tsm_system_time` add index access/operator classes, text-search dictionary
  pieces, similarity search, and table-sampling methods
  ([bloom.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/bloom.sgml#L10-L39),
  [pgtrgm.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgtrgm.sgml#L11-L23),
  [tsm-system-rows.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/tsm-system-rows.sgml#L11-L40)).
- **Data types and domain utilities:** `citext`, `cube`, `earthdistance`,
  `hstore`, `intagg`, `intarray`, `isn`, `lo`, `ltree`, `seg`, and `uuid-ossp`
  add types or functions for case-insensitive text, multidimensional cubes,
  spherical distances, key/value data, integer arrays, product numbers, large
  objects, hierarchical labels, measurement intervals, and UUID generation
  ([citext.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/citext.sgml#L10-L23),
  [hstore.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/hstore.sgml#L10-L22),
  [ltree.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/ltree.sgml#L10-L40)).
- **Remote access, table output, crypto, and XML:** `dblink`, `file_fdw`,
  `postgres_fdw`, `tablefunc`, `tcn`, `pgcrypto`, `sslinfo`, and `xml2` cover
  remote PostgreSQL access, server-side file foreign tables, pivot/table-returning
  functions, triggered notifications, cryptography, SSL inspection, and legacy XML
  helpers
  ([dblink.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/dblink.sgml#L10-L54),
  [postgres-fdw.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/postgres-fdw.sgml#L12-L24),
  [pgcrypto.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/pgcrypto.sgml#L15-L29)).
- **Procedural-language transforms and SPI examples:** `bool_plperl`,
  `bool_plperlu`, `hstore_plperl`, `hstore_plperlu`, `hstore_plpython3u`,
  `jsonb_plperl`, `jsonb_plperlu`, `jsonb_plpython3u`, and
  `ltree_plpython3u` adapt SQL values to PL-language runtime values, while
  `autoinc`, `insert_username`, `moddatetime`, and `refint` are separately
  installable SPI trigger examples
  ([create_transform.sgml#description](../../../../raw/postgres-17/doc/src/sgml/ref/create_transform.sgml#L35-L55),
  [contrib-spi.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/contrib-spi.sgml#L10-L24)).

## Context Reviewed

- [contrib.sgml#contrib](../../../../raw/postgres-17/doc/src/sgml/contrib.sgml#L1-L174)
- [contrib-spi.sgml#spi](../../../../raw/postgres-17/doc/src/sgml/contrib-spi.sgml#L1-L196)
- [create_transform.sgml#description](../../../../raw/postgres-17/doc/src/sgml/ref/create_transform.sgml#L35-L55)
- `raw/postgres-17/contrib/*/*.control` and `raw/postgres-17/contrib/spi/*.control` for the extension inventory.
- Pinned checkout `raw/postgres-17/` at commit
  `786db8dcf168bd9df8f55047337525ac19118b1c` (PostgreSQL 17.11,
  `REL_17_11-7-g786db8dcf16`); repinned from
  `54eeefaedbee0385529f3edf321bb99e49232aaa` (17.10) on 2026-08-17.
- 2026-08-17 repin review: the count of **53** control-file-backed contrib
  extensions was re-counted at the new pin, and no `contrib/*/*.control` file was
  added, removed, or changed in the `54eeefaed..786db8dcf16` range. Two entries
  gained notes: `refint` (`e1885a875cb`, `c0392783c54`, `66a5146dc73`,
  `6b4de201e82`) and `pgcrypto` (`b05cfc69375`, `7eed42aa880`).
- Same-checkout SGML chapters for each documented extension named in the table above.
- SQL install scripts for transform and SPI extensions where the installable object is clearest in SQL.

## Evidence Map

| Claim | Evidence |
|---|---|
| Contrib contains optional modules and extensions outside the core system | [contrib.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/contrib.sgml#L10-L31) |
| Extension-style contrib modules are registered per database with `CREATE EXTENSION` | [contrib.sgml#CREATE-EXTENSION](../../../../raw/postgres-17/doc/src/sgml/contrib.sgml#L63-L82) |
| Trusted extensions can be installed by users with database `CREATE` privilege; untrusted ones require superuser | [contrib.sgml#trusted-extensions](../../../../raw/postgres-17/doc/src/sgml/contrib.sgml#L86-L104) |
| Some contrib modules are loaded in other ways and some contrib entries are utility programs, not SQL extensions | [contrib.sgml#non-extension-components](../../../../raw/postgres-17/doc/src/sgml/contrib.sgml#L107-L111), [contrib.sgml#contrib-programs](../../../../raw/postgres-17/doc/src/sgml/contrib.sgml#L160-L174) |
| The SPI contrib directory contains several separately installable extensions | [contrib-spi.sgml#overview](../../../../raw/postgres-17/doc/src/sgml/contrib-spi.sgml#L10-L24) |
| Transform extensions adapt SQL data types to procedural languages | [create_transform.sgml#description](../../../../raw/postgres-17/doc/src/sgml/ref/create_transform.sgml#L35-L55) |

## Source References

- [amcheck.sgml](../../../../raw/postgres-17/doc/src/sgml/amcheck.sgml) - `amcheck` behavior and security notes.
- [bloom.sgml](../../../../raw/postgres-17/doc/src/sgml/bloom.sgml) - Bloom index access method behavior and false-positive model.
- [btree-gin.sgml](../../../../raw/postgres-17/doc/src/sgml/btree-gin.sgml) and [btree-gist.sgml](../../../../raw/postgres-17/doc/src/sgml/btree-gist.sgml) - B-tree-equivalent GIN/GiST operator classes.
- [citext.sgml](../../../../raw/postgres-17/doc/src/sgml/citext.sgml), [cube.sgml](../../../../raw/postgres-17/doc/src/sgml/cube.sgml), [hstore.sgml](../../../../raw/postgres-17/doc/src/sgml/hstore.sgml), [ltree.sgml](../../../../raw/postgres-17/doc/src/sgml/ltree.sgml), and [seg.sgml](../../../../raw/postgres-17/doc/src/sgml/seg.sgml) - contrib data types and their transform notes.
- [dblink.sgml](../../../../raw/postgres-17/doc/src/sgml/dblink.sgml), [file-fdw.sgml](../../../../raw/postgres-17/doc/src/sgml/file-fdw.sgml), and [postgres-fdw.sgml](../../../../raw/postgres-17/doc/src/sgml/postgres-fdw.sgml) - local-to-remote data access extensions.
- [dict-int.sgml](../../../../raw/postgres-17/doc/src/sgml/dict-int.sgml), [dict-xsyn.sgml](../../../../raw/postgres-17/doc/src/sgml/dict-xsyn.sgml), [pgtrgm.sgml](../../../../raw/postgres-17/doc/src/sgml/pgtrgm.sgml), and [unaccent.sgml](../../../../raw/postgres-17/doc/src/sgml/unaccent.sgml) - text-search and string-matching extensions.
- [earthdistance.sgml](../../../../raw/postgres-17/doc/src/sgml/earthdistance.sgml), [fuzzystrmatch.sgml](../../../../raw/postgres-17/doc/src/sgml/fuzzystrmatch.sgml), [intagg.sgml](../../../../raw/postgres-17/doc/src/sgml/intagg.sgml), [intarray.sgml](../../../../raw/postgres-17/doc/src/sgml/intarray.sgml), [isn.sgml](../../../../raw/postgres-17/doc/src/sgml/isn.sgml), [lo.sgml](../../../../raw/postgres-17/doc/src/sgml/lo.sgml), and [uuid-ossp.sgml](../../../../raw/postgres-17/doc/src/sgml/uuid-ossp.sgml) - domain-specific utility extensions.
- [pageinspect.sgml](../../../../raw/postgres-17/doc/src/sgml/pageinspect.sgml), [pgbuffercache.sgml](../../../../raw/postgres-17/doc/src/sgml/pgbuffercache.sgml), [pgfreespacemap.sgml](../../../../raw/postgres-17/doc/src/sgml/pgfreespacemap.sgml), [pgprewarm.sgml](../../../../raw/postgres-17/doc/src/sgml/pgprewarm.sgml), [pgsurgery.sgml](../../../../raw/postgres-17/doc/src/sgml/pgsurgery.sgml), [pgvisibility.sgml](../../../../raw/postgres-17/doc/src/sgml/pgvisibility.sgml), [pgwalinspect.sgml](../../../../raw/postgres-17/doc/src/sgml/pgwalinspect.sgml), [pgrowlocks.sgml](../../../../raw/postgres-17/doc/src/sgml/pgrowlocks.sgml), and [pgstattuple.sgml](../../../../raw/postgres-17/doc/src/sgml/pgstattuple.sgml) - storage, cache, WAL, lock, and tuple-inspection extensions.
- [pgstatstatements.sgml](../../../../raw/postgres-17/doc/src/sgml/pgstatstatements.sgml) - `pg_stat_statements` preload and per-database extension behavior.
- [pgcrypto.sgml](../../../../raw/postgres-17/doc/src/sgml/pgcrypto.sgml), [sslinfo.sgml](../../../../raw/postgres-17/doc/src/sgml/sslinfo.sgml), [tablefunc.sgml](../../../../raw/postgres-17/doc/src/sgml/tablefunc.sgml), [tcn.sgml](../../../../raw/postgres-17/doc/src/sgml/tcn.sgml), [tsm-system-rows.sgml](../../../../raw/postgres-17/doc/src/sgml/tsm-system-rows.sgml), [tsm-system-time.sgml](../../../../raw/postgres-17/doc/src/sgml/tsm-system-time.sgml), and [xml2.sgml](../../../../raw/postgres-17/doc/src/sgml/xml2.sgml) - remaining documented contrib extensions.
- [plperl.sgml#bool-transform](../../../../raw/postgres-17/doc/src/sgml/plperl.sgml#L195-L210), [json.sgml#jsonb-transforms](../../../../raw/postgres-17/doc/src/sgml/json.sgml#L719-L739), and the transform SQL scripts under `raw/postgres-17/contrib/*_pl*/` - procedural-language transform extensions.

## Open Questions

- This page lists control-file-backed contrib extensions. It does not list contrib
  plug-in modules that are loaded by `shared_preload_libraries`, output plugin
  mechanisms, or other non-`CREATE EXTENSION` paths.
- Packaging names can differ by operating-system distribution. The inventory here
  is from the pinned PostgreSQL 17 source checkout, not from a vendor package.

## Related Pages

- [v17/index](../../index.md)
- [versions](../../../versions.md)
