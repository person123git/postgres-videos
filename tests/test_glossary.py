import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pgvideo.cli import parser, prepare
from pgvideo.document import parse_document
from pgvideo.glossary import INDEX, build_index, english_words, match_glossary, version_scope
from pgvideo.snapshot import snapshot_sources
from test_sources import DOCUMENT, PIN, POSTGRES, PROJECT_ROOT, RAW, WIKI, WIKI_COMMIT, FakeGitHub, \
    install_project_files, postgres_files, wiki_files

PINS = {17: "c" * 40, 18: PIN, 19: "d" * 40}
# Ordinary English words for these tests, in place of Kokoro's lexicon.
ENGLISH = frozenset({"cost", "path", "auto", "row", "tuple"})

GLOSSARY = f"""---
type: glossary
verified: false
---

# Wiki Glossary (unverified)

## Scope

A glossary link supplies vocabulary, not proof.

## Source Pins

| Version | Checkout | Branch | Pinned commit |
|---|---|---|---|
| 17 | `raw/postgres-17/` | `REL_17_STABLE` | `{PINS[17]}` |
| 18 | `raw/postgres-18/` | `REL_18_STABLE` | `{PINS[18]}` |
| 19 | `raw/postgres-19/` | `REL_19_STABLE` | `{PINS[19]}` |

## Terms

### Access method

**Aliases:** AM, index access method, `pg_am`. **Checked on:** PostgreSQL 17, 18.

An access method is how a relation stores and finds data ([pg_am.h#FormData_pg_am](../raw/postgres-17/src/include/catalog/pg_am.h#L29-L41)). `GetIndexAmRoutine()` calls its handler.

**Version notes:**
- PostgreSQL 18: Holds ([pg_am.h](../raw/postgres-18/src/include/catalog/pg_am.h#L29-L41)).

Related: [B-tree](#b-tree)

### B-tree

**Aliases:** btree, `nbtree`. **Checked on:** PostgreSQL 17, 18, 19.

A B-tree is the default index type ([nbtree.c:1](../raw/postgres-17/src/backend/access/nbtree/nbtree.c#L1)).

**Version notes:**
- PostgreSQL 18: Holds, except that 18 adds skip scan ([nbtree.c:2](../raw/postgres-18/src/backend/access/nbtree/nbtree.c#L2)).
- PostgreSQL 19: Holds, as in 18 ([nbtree.c:2](../raw/postgres-19/src/backend/access/nbtree/nbtree.c#L2)).

Related: [Access method](#access-method)

### Cost

**Aliases:** planner cost. **Checked on:** PostgreSQL 17, 18.

Cost is the planner's estimate of work ([costsize.c:1](../raw/postgres-17/src/backend/optimizer/path/costsize.c#L1)).

**Version notes:**
- PostgreSQL 18: Differs: 18 counts disabled nodes first ([costsize.c:2](../raw/postgres-18/src/backend/optimizer/path/costsize.c#L2)).

Related: [Path](#path)

### Path

**Checked on:** PostgreSQL 17.

A path is one way to scan a relation ([pathnode.c:1](../raw/postgres-17/src/backend/optimizer/util/pathnode.c#L1)). See `add_path()`.

### Asynchronous I/O

**Aliases:** AIO. **Checked on:** PostgreSQL 17, 18.

In PostgreSQL 18, asynchronous I/O issues reads ahead ([aio.c:1](../raw/postgres-18/src/backend/storage/aio/aio.c#L1)).

**Version notes:**
- PostgreSQL 17: Not present in PostgreSQL 17 ([Makefile:1](../raw/postgres-17/src/backend/storage/Makefile#L1)).

### Shared-memory statistics

**Aliases:** stats collector (PostgreSQL 12 and 14), `PgStatShared_*`. **Checked on:** PostgreSQL 18.

Counters live in shared memory ([pgstat.c:1](../raw/postgres-18/src/backend/utils/activity/pgstat.c#L1)).

### Tuple

**Aliases:** row, heap tuple, summarized tuple (contrast), RT index (range-table index). **Checked on:** PostgreSQL 18.

A tuple is one row version ([htup.h:1](../raw/postgres-18/src/include/access/htup.h#L1)).

### Plan cache mode

**Aliases:** `plan_cache_mode`, `auto`. **Checked on:** PostgreSQL 18.

`plan_cache_mode` chooses custom or generic plans ([plancache.c:1](../raw/postgres-18/src/backend/utils/cache/plancache.c#L1)).

### SLRU

**Aliases:** `pg_subtrans`. **Checked on:** PostgreSQL 18.

An SLRU is a small buffer pool for transaction status ([slru.c:1](../raw/postgres-18/src/backend/access/transam/slru.c#L1)).

### Subtransaction

**Aliases:** `pg_subtrans`, savepoint. **Checked on:** PostgreSQL 18.

A subtransaction is a transaction inside another ([xact.c:1](../raw/postgres-18/src/backend/access/transam/xact.c#L1)).

### HOT

**Aliases:** heap-only tuple. **Checked on:** PostgreSQL 18.

HOT keeps a new row version on the same page ([heapam.c:1](../raw/postgres-18/src/backend/access/heap/heapam.c#L1)).

### Orphan

**Checked on:** PostgreSQL 17, 18.

An orphan entry has no notes ([orphan.c:1](../raw/postgres-17/src/orphan.c#L1)).

## Open Questions

- None.
"""

TEXT = f"""---
type: question
version: 18
pinned_commit: {PIN}
verified: false
---

# How B-tree Indexes Use `example_size` in PostgreSQL 18 (unverified)

## Question

How does a [B-tree](../../../glossary.md#b-tree) index use `example_size` in PostgreSQL 18?

## Short Answer

The `pg_am` catalog lists each index access method [nbtree.c]({RAW}/src/backend/access/nbtree/nbtree.c#L1).

## Planning

Each path has a cost [costsize.c]({RAW}/src/backend/optimizer/path/costsize.c#L1).

## Updates

A HOT update keeps the row in place, unlike a hot standby or a HOTEL. The `pg_amop` catalog is unrelated.

## Subtransactions

`pg_subtrans` records parents.

`pg_subtrans` is an SLRU file [slru.c]({RAW}/src/backend/access/transam/slru.c#L1).

## Statistics

The stats collector is gone; `PgStatShared_Backend` holds counters. Asynchronous I/O (AIO) reads ahead.
See the [missing entry](../../../glossary.md#no-such-entry).

## Query IDs

Setting `compute_query_id` to `auto` enables query IDs.

## Plan Cache

With `plan_cache_mode` set to `auto`, the server picks plans. A summarized tuple is different.

## Source References

- [nbtree.c]({RAW}/src/backend/access/nbtree/nbtree.c)
"""


def cited_files():
    return postgres_files() | {path: b"line 1\nline 2\n" for path in (
        "src/backend/optimizer/path/costsize.c", "src/backend/access/transam/slru.c")} | {
        "src/backend/access/nbtree/nbtree.c": b"/* index access methods are listed in pg_am */\nline 2\n"}


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.index = build_index(GLOSSARY, digest="x", english=ENGLISH)
        self.entries = {entry["anchor"]: entry for entry in self.index["entries"]}

    def test_entries_keep_names_aliases_versions_notes_and_evidence(self):
        self.assertEqual(list(self.entries), ["access-method", "b-tree", "cost", "path", "asynchronous-io",
                                              "shared-memory-statistics", "tuple", "plan-cache-mode", "slru",
                                              "subtransaction", "hot", "orphan"])
        self.assertEqual(self.index["source_pins"], {str(version): pin for version, pin in PINS.items()})
        method = self.entries["access-method"]
        self.assertEqual((method["term"], method["checked_on"], method["main_version"], method["main_version_source"]),
                         ("Access method", [17, 18], 17, "notes"))
        self.assertEqual(method["summary"], "An access method is how a relation stores and finds data.")
        self.assertEqual(method["lines"][0], GLOSSARY.split("\n").index("### Access method") + 1)
        citation = method["definition"][0]["citations"][0]
        self.assertEqual((citation["label"], citation["version"], citation["path"], citation["lines"]),
                         ("pg_am.h#FormData_pg_am", 17, "src/include/catalog/pg_am.h", [29, 41]))
        self.assertEqual(citation["url"], f"https://github.com/postgres/postgres/blob/{PINS[17]}/"
                                          "src/include/catalog/pg_am.h#L29-L41")
        self.assertNotIn("raw/postgres", method["definition"][0]["text"])
        self.assertEqual((method["related"], method["neighbors"]), (["b-tree"], ["b-tree"]))
        self.assertIn("GetIndexAmRoutine", method["symbols"])
        forms = {form["text"]: form for form in method["forms"]}
        self.assertEqual({text: (form["kind"], form["needs_context"]) for text, form in forms.items()}, {
            "Access method": ("phrase", False), "AM": ("acronym", True),
            "index access method": ("phrase", False), "pg_am": ("code", False)})

    def test_aliases_record_contrasts_version_limits_expansions_and_patterns(self):
        tuple_forms = {form["text"]: form for form in self.entries["tuple"]["forms"]}
        self.assertEqual(tuple_forms["summarized tuple"]["relation"], "contrast")
        self.assertTrue({"RT index", "range-table index"} <= set(tuple_forms))
        self.assertEqual((tuple_forms["row"]["kind"], tuple_forms["row"]["needs_context"]), ("word", True))
        statistics = {form["text"]: form for form in self.entries["shared-memory-statistics"]["forms"]}
        self.assertEqual(statistics["stats collector"]["versions"], [12, 14])
        self.assertEqual((statistics["PgStatShared_*"]["kind"], statistics["PgStatShared_*"]["needs_context"]),
                         ("pattern", False))
        auto = next(form for form in self.entries["plan-cache-mode"]["forms"] if form["text"] == "auto")
        self.assertTrue(auto["code_only"] and auto["needs_context"])

    def test_notes_record_status_exceptions_and_references(self):
        notes = self.entries["b-tree"]["notes"]
        self.assertEqual((notes["18"]["status"], notes["18"]["exceptions"], notes["18"]["references"]),
                         ("holds", True, []))
        self.assertEqual((notes["19"]["status"], notes["19"]["exceptions"], notes["19"]["references"]),
                         ("holds", False, [18]))
        self.assertEqual(self.entries["cost"]["notes"]["18"]["status"], "differs")
        self.assertEqual(self.entries["asynchronous-io"]["notes"]["17"]["status"], "not_present")
        self.assertEqual((self.entries["asynchronous-io"]["main_version"], self.entries["orphan"]["main_version"],
                          self.entries["orphan"]["main_version_source"]), (18, 17, "citations"))
        self.assertIn("version_note_missing", {issue["code"] for issue in self.entries["orphan"]["issues"]})

    def test_version_scope_resolves_notes_before_using_a_definition(self):
        cases = {
            ("access-method", 17): ("main", True, []),
            ("access-method", 18): ("holds", True, []),
            ("b-tree", 18): ("holds_with_exceptions", True, []),
            ("b-tree", 19): ("holds_with_exceptions", True, [18]),
            ("cost", 18): ("differs", False, []),
            ("asynchronous-io", 17): ("not_present", False, []),
            ("path", 18): ("unchecked", False, []),
            ("orphan", 18): ("unknown", False, []),
        }
        for (anchor, version), (status, applies, references) in cases.items():
            with self.subTest(anchor=anchor, version=version):
                scope = version_scope(self.entries[anchor], version)
                self.assertEqual((scope["status"], scope["definition_applies"],
                                  [ref["version"] for ref in scope["references"]]), (status, applies, references))
        borrowed = version_scope(self.entries["b-tree"], 19)
        self.assertIn("18 adds skip scan", borrowed["references"][0]["text"])
        self.assertIn("borrows from the 18 note", borrowed["explanation"])

    def test_english_lexicon_separates_ordinary_words_from_jargon(self):
        english = english_words()
        self.assertIn("path", english)
        self.assertNotIn("autovacuum", english)


class MatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-test-", dir=PROJECT_ROOT / ".runtime" / "tmp")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve() / "project"
        self.workspace.mkdir()
        self.github = FakeGitHub()
        self.github.add(POSTGRES, PIN, cited_files())
        self.enterContext(patch("pgvideo.sources._http_get", side_effect=self.github))
        self.enterContext(patch("pgvideo.glossary.english_words", return_value=ENGLISH))
        self.runs = 0

    def match(self, document=TEXT, glossary=GLOSSARY):
        self.runs += 1
        self.github.add(WIKI, f"{self.runs:040x}", wiki_files(document=document, glossary=glossary), refs=["master"])
        run_dir = self.workspace / "runs" / f"request-{self.runs}"
        run_dir.mkdir(parents=True)
        request = {"request_id": run_dir.name, "repository": WIKI, "document": {"path": DOCUMENT, "ref": "master"}}
        sources = snapshot_sources(self.workspace, run_dir, request)
        self.assertEqual(sources["status"], "passed", (run_dir / "source-report.md").read_text())
        self.assertEqual(parse_document(self.workspace, run_dir)["status"], "passed")
        result = match_glossary(self.workspace, run_dir)
        record = json.loads((run_dir / "glossary-matches.json").read_text(encoding="utf-8"))
        return result, record, run_dir

    @staticmethod
    def matches(record):
        return {match["anchor"]: match for match in record["matches"]}

    @staticmethod
    def ambiguous(record):
        return {(group["text"], group["reason"]): group for group in record["ambiguous"]}

    def test_candidates_come_from_links_names_aliases_acronyms_and_identifiers(self):
        _result, record, _run_dir = self.match()
        matches = self.matches(record)
        tree = matches["b-tree"]
        self.assertEqual((tree["tier"], tree["rank"], tree["linked"]), ("central", 1, True))
        self.assertEqual(tree["methods"], ["link", "term"])
        self.assertEqual(tree["url"], f"https://github.com/{WIKI}/blob/{1:040x}/wiki/glossary.md#b-tree")
        method = matches["access-method"]
        self.assertEqual((method["tier"], method["forms"]), ("central", ["pg_am", "index access method"]))
        self.assertEqual(method["methods"], ["alias", "identifier"])
        self.assertEqual(matches["asynchronous-io"]["forms"], ["Asynchronous I/O", "AIO"])
        self.assertEqual(matches["asynchronous-io"]["methods"], ["acronym", "term"])
        self.assertEqual(matches["shared-memory-statistics"]["forms"], ["stats collector", "PgStatShared_Backend"])
        self.assertEqual(matches["hot"]["forms"], ["HOT"])
        self.assertEqual([match["tier"] for match in record["matches"]][:2], ["central", "central"])
        focus = {term["term"]: (term["status"], term["anchors"]) for term in record["subject"]["focus_terms"]}
        self.assertEqual(focus, {"B-tree": ("matched", ["b-tree"]), "example_size": ("not_in_glossary", [])})
        self.assertIn("definition", tree)
        self.assertEqual(tree["summary"], "A B-tree is the default index type.")

    def test_word_boundaries_reject_longer_words_and_other_case(self):
        _result, record, _run_dir = self.match()
        forms = [occurrence["text"] for match in record["matches"] for occurrence in match["occurrences"]]
        self.assertNotIn("HOTEL", forms)
        self.assertNotIn("hot", forms)
        self.assertNotIn("pg_amop", forms)
        self.assertIn("pg_amop", {term["term"] for term in record["unmatched"]})

    def test_short_aliases_and_code_words_need_context(self):
        _result, record, _run_dir = self.match()
        matches, ambiguous = self.matches(record), self.ambiguous(record)
        self.assertIn(("row", "needs_context"), ambiguous)
        self.assertEqual(ambiguous["auto", "needs_context"]["occurrences"][0]["section"], "query-ids")
        auto = [o for o in matches["plan-cache-mode"]["occurrences"] if o["text"] == "auto"]
        # `plan_cache_mode` in the same section and block supports it; the query ID section has neither.
        self.assertEqual([(o["section"], o["support"], o["context"]) for o in auto],
                         [("plan-cache", "form", ["symbol:plan_cache_mode"])])
        cost = next(o for o in matches["cost"]["occurrences"])
        self.assertEqual((cost["support"], cost["context"]),
                         ("context", ["file:src/backend/optimizer/path/costsize.c"]))
        path = next(o for o in matches["path"]["occurrences"])
        self.assertEqual((path["support"], path["context"]), ("context", ["entry:cost"]))
        self.assertEqual(matches["tuple"]["relation"], "contrast")

    def test_alias_collisions_stay_ambiguous_unless_context_decides(self):
        _result, record, _run_dir = self.match()
        collision = self.ambiguous(record)["pg_subtrans", "collision"]
        self.assertEqual([c["anchor"] for c in collision["candidates"]], ["slru", "subtransaction"])
        self.assertEqual(collision["count"], 1)
        slru = [o for o in self.matches(record)["slru"]["occurrences"] if o["text"] == "pg_subtrans"]
        self.assertEqual(len(slru), 1)
        self.assertEqual(slru[0]["alternatives"], ["subtransaction"])
        self.assertIn("file:src/backend/access/transam/slru.c", slru[0]["context"])

    def test_version_rules_and_version_limited_aliases_are_reported(self):
        _result, record, _run_dir = self.match()
        matches = self.matches(record)
        self.assertEqual(matches["b-tree"]["version_scope"]["status"], "holds_with_exceptions")
        self.assertEqual(matches["cost"]["version_scope"]["status"], "differs")
        self.assertEqual(matches["path"]["version_scope"]["status"], "unchecked")
        self.assertEqual(matches["asynchronous-io"]["version_scope"]["status"], "main")
        self.assertEqual(matches["b-tree"]["note_statuses"], {"18": "holds", "19": "holds"})
        issues = {issue["code"]: issue for issue in record["issues"]}
        self.assertEqual(issues["definition_unchecked"]["severity"], "warning")
        self.assertIn("Path (#path)", issues["definition_unchecked"]["message"])
        self.assertIn("Cost (#cost)", issues["definition_differs"]["message"])
        self.assertIn("stats collector (12 and 14)", issues["alias_other_version"]["message"])
        self.assertEqual(issues["glossary_unverified"]["severity"], "note")
        stats = next(o for o in matches["shared-memory-statistics"]["occurrences"] if o["text"] == "stats collector")
        self.assertEqual(stats["alias_versions"], [12, 14])

    def test_unmatched_terms_and_missing_links_are_listed(self):
        _result, record, _run_dir = self.match()
        unmatched = {term["term"]: term for term in record["unmatched"]}
        self.assertTrue(unmatched["example_size"]["central"])
        self.assertEqual(unmatched["missing entry"]["reason"], "glossary_anchor_missing")
        self.assertNotIn("pg_subtrans", unmatched)
        self.assertNotIn("PgStatShared_Backend", unmatched)
        issues = {issue["code"]: issue for issue in record["issues"]}
        self.assertIn("#no-such-entry", issues["glossary_anchor_missing"]["message"])
        self.assertIn("`example_size`", issues["central_terms_not_in_glossary"]["message"])

    def test_each_request_builds_its_own_index_from_its_glossary_snapshot(self):
        # Two requests for the same glossary each build an index; neither uses the other's.
        with patch("pgvideo.glossary.build_index", wraps=build_index) as built:
            first, record, first_dir = self.match()
            second, _record, run_dir = self.match()
        self.assertEqual(built.call_count, 2)
        for result, directory in ((first, first_dir), (second, run_dir)):
            data = (directory / INDEX).read_bytes()
            index = json.loads(data)
            self.assertEqual((result["index"]["path"], result["index"]["sha256"], result["index"]["entries"]),
                             (INDEX, hashlib.sha256(data).hexdigest(), len(index["entries"])))
            self.assertEqual(index["glossary_sha256"], record["glossary"]["sha256"])
            self.assertNotIn("reused", result["index"])
        self.assertFalse((self.workspace / "cache" / "glossary").exists())
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "glossary_matched")
        self.assertEqual(manifest["glossary"]["index"], second["index"])
        self.assertEqual(manifest["glossary"]["record"], "glossary-matches.json")

        # A new glossary snapshot changes the definitions the document is matched against.
        _result, record, _run_dir = self.match(glossary=GLOSSARY.replace("default index type", "usual index type"))
        self.assertEqual(self.matches(record)["b-tree"]["summary"], "A B-tree is the usual index type.")

        # The index is built from the run's snapshot copy, which must still match its recorded SHA-256.
        copy = run_dir / "inputs" / "wiki" / "wiki" / "glossary.md"
        copy.chmod(0o644)
        copy.write_text(GLOSSARY.replace("default index type", "usual index type"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "glossary.md does not match its recorded SHA-256"):
            match_glossary(self.workspace, run_dir)

    def test_altered_document_record_fails_and_is_recorded(self):
        _result, _record, run_dir = self.match()
        document = run_dir / "document.json"
        document.write_text(document.read_text(encoding="utf-8").replace("B-tree", "Tree"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "document.json does not match"):
            match_glossary(self.workspace, run_dir)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["status"], manifest["glossary"]["status"]), ("failed", "failed"))

    def test_prepare_command_reports_glossary_matches(self):
        self.github.add(WIKI, WIKI_COMMIT, wiki_files(document=TEXT, glossary=GLOSSARY), refs=["master"])
        self.enterContext(patch("pgvideo.cli.project_root", return_value=self.workspace))
        self.enterContext(patch("pgvideo.cli.local_selection"))
        self.enterContext(patch("pgvideo.cli._narrate", return_value=0))
        self.enterContext(patch("pgvideo.sources._github_contents",
                                side_effect=lambda path, ref: {"type": "file", "path": path}))
        install_project_files(self.workspace)
        args = parser().parse_args(["prepare", "--document", DOCUMENT])
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(prepare(args, self.workspace), 0, stderr.getvalue())
        self.assertRegex(stdout.getvalue(), r"Glossary index: .*glossary-index\.json \(\d+ entries, built from the "
                                            r"glossary downloaded for this request\)")
        self.assertRegex(stdout.getvalue(), r"Glossary matches: .*glossary-matches\.json \(\d+ entries: \d+ central")
        self.assertIn("Evidence packet:", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
