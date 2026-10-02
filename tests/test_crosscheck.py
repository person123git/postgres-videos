import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pgvideo.cli import NEEDS_REVIEW, parser, prepare, resume
from pgvideo.crosscheck import RESOLUTIONS, _guc_data, _guc_table, _number, _same, _sentence_facts, check_glossary
from pgvideo.document import parse_document
from pgvideo.glossary import _plain, match_glossary
from pgvideo.snapshot import snapshot_sources
from test_sources import DOCUMENT, PIN, POSTGRES, PROJECT_ROOT, RAW, WIKI, WIKI_COMMIT, FakeGitHub, \
    install_project_files, postgres_files, wiki_files

# Ordinary English words for these tests, in place of Kokoro's lexicon.
ENGLISH = frozenset({"row", "path", "cost"})
GUC_PATH = "src/backend/utils/misc/guc_tables.c"
STATUS_PATH = "src/backend/status.c"
VIEWS_PATH = "src/backend/catalog/system_views.sql"

GUC = """/* guc_tables.c */
struct config_bool ConfigureNamesBool[] =
{
\t{
\t\t{"example_flag", PGC_SUSET, STATS,
\t\t\tgettext_noop("Reports slot activity."),
\t\t\tNULL
\t\t},
\t\t&example_flag,
\t\ttrue,
\t\tNULL, NULL, NULL
\t},
};

struct config_int ConfigureNamesInt[] =
{
\t{
\t\t{"example_size", PGC_POSTMASTER, STATS,
\t\t\tgettext_noop("Sets the size reserved for pg_stat_activity.query, in bytes."),
\t\t\tNULL,
\t\t\tGUC_UNIT_BYTE
\t\t},
\t\t&pgstat_example_size,
\t\t1024, 100, 1048576,
\t\tNULL, NULL, NULL
\t},
\t{
\t\t{"example_timeout", PGC_USERSET, STATS,
\t\t\tgettext_noop("Sets the wait limit."),
\t\t\tNULL,
\t\t\tGUC_UNIT_MS
\t\t},
\t\t&example_timeout,
\t\t1000, 0, INT_MAX,
\t\tNULL, NULL, NULL
\t},
\t{
\t\t{"example_buffers", PGC_POSTMASTER, STATS,
\t\t\tgettext_noop("Sets the number of slot buffers."),
\t\t\tNULL,
\t\t\tGUC_UNIT_BLOCKS
\t\t},
\t\t&example_buffers,
\t\t16384, 16, INT_MAX / 2,
\t\tNULL, NULL, NULL
\t},
};

static const struct config_enum_entry example_mode_options[] = {
\t{"auto", EXAMPLE_MODE_AUTO, false},
\t{"on", EXAMPLE_MODE_ON, false},
\t{"off", EXAMPLE_MODE_OFF, false},
\t{NULL, 0, false}
};

struct config_enum ConfigureNamesEnum[] =
{
\t{
\t\t{"example_mode", PGC_SUSET, STATS,
\t\t\tgettext_noop("Chooses the slot mode."),
\t\t\tNULL
\t\t},
\t\t&example_mode,
\t\tEXAMPLE_MODE_AUTO, example_mode_options,
\t\tNULL, NULL, NULL
\t},
};
"""
STATUS = """/* status.c: the widget cache and its slots */
void
SlotScannerMain(void)
{
\texample_widget = 0;\t/* example_widget holds the slots; pg_subtrans records parents */
\texample_size = 0;
}
"""
VIEWS = """CREATE VIEW pg_stat_activity AS
    SELECT S.query FROM pg_stat_get_activity(NULL) AS S;
"""


def line_of(text: str, needle: str) -> int:
    return next(number for number, line in enumerate(text.split("\n"), 1) if needle in line)


def guc(name: str) -> str:
    """Cite a parameter's GUC table entry, from its name through its values."""
    first = line_of(GUC, f'{{"{name}"')
    return f"[guc_tables.c#{name}]({RAW}/{GUC_PATH}#L{first}-L{first + 8})"


STATUS_CITE = f"[status.c#widget]({RAW}/{STATUS_PATH}#L1-L7)"
VIEWS_CITE = f"[system_views.sql#pg_stat_activity]({RAW}/{VIEWS_PATH}#L1-L2)"

GLOSSARY = f"""---
type: glossary
verified: false
---

# Wiki Glossary (unverified)

## Source Pins

| Version | Checkout | Branch | Pinned commit |
|---|---|---|---|
| 17 | `raw/postgres-17/` | `REL_17_STABLE` | `{"c" * 40}` |
| 18 | `raw/postgres-18/` | `REL_18_STABLE` | `{PIN}` |

## Terms

### example_size

**Aliases:** `pgstat_example_size`. **Checked on:** PostgreSQL 17, 18.

`example_size` is the [GUC](#guc) that sets the byte size of each slot. The default is 1024. It accepts 100 to 1048576 bytes. The GUC has context `postmaster`, so a change needs a restart ([guc_tables.c#example_size](../raw/postgres-17/{GUC_PATH}#L10-L20)).

**Version notes:**
- PostgreSQL 18: Holds ([guc_tables.c#example_size](../raw/postgres-18/{GUC_PATH}#L10-L20)).

Related: [GUC](#guc), [pg_stat_activity](#pg_stat_activity)

### example_timeout

**Checked on:** PostgreSQL 18.

`example_timeout` is the GUC that limits each wait. The default is 2000 ms ([guc_tables.c#example_timeout](../raw/postgres-18/{GUC_PATH}#L27-L35)).

### example_flag

**Checked on:** PostgreSQL 18.

`example_flag` is the GUC that turns slot reporting on. It is enabled by default ([guc_tables.c#example_flag](../raw/postgres-18/{GUC_PATH}#L3-L12)).

### example_buffers

**Checked on:** PostgreSQL 18.

`example_buffers` sets how many slot buffers exist. The built-in default is 16384 blocks, which is 128 MB ([guc_tables.c#example_buffers](../raw/postgres-18/{GUC_PATH}#L37-L45)).

### GUC

**Aliases:** configuration parameter. **Checked on:** PostgreSQL 18.

A GUC is one server configuration setting ([guc_tables.c:1](../raw/postgres-18/{GUC_PATH}#L1)).

### pg_stat_activity

**Aliases:** `pg_stat_get_activity()`. **Checked on:** PostgreSQL 18.

`pg_stat_activity` is the view with one row per server process ([system_views.sql:1](../raw/postgres-18/{VIEWS_PATH}#L1)).

### Write-ahead log

**Aliases:** WAL. **Checked on:** PostgreSQL 18.

The write-ahead log records every change before it reaches the data files ([xlog.c:1](../raw/postgres-18/src/backend/access/transam/xlog.c#L1)).

### Slot scanner

**Aliases:** `SlotScannerMain`. **Checked on:** PostgreSQL 17, 18.

The slot scanner walks every slot ([scanner.c:1](../raw/postgres-17/src/backend/scanner.c#L1)).

**Version notes:**
- PostgreSQL 18: Not present in PostgreSQL 18 ([Makefile:1](../raw/postgres-18/src/backend/Makefile#L1)).

### Slot cleaner

**Aliases:** slot sweeper (PostgreSQL 12 and 14). **Checked on:** PostgreSQL 18.

The slot cleaner frees idle slots ([status.c:1](../raw/postgres-18/{STATUS_PATH}#L1)).

### Tuple

**Aliases:** row. **Checked on:** PostgreSQL 18.

A tuple is one row version ([htup.h:1](../raw/postgres-18/src/include/access/htup.h#L1)).

### SLRU

**Aliases:** `pg_subtrans`. **Checked on:** PostgreSQL 18.

An SLRU is a small buffer pool ([slru.c:1](../raw/postgres-18/src/backend/access/transam/slru.c#L1)).

### Subtransaction

**Aliases:** `pg_subtrans`. **Checked on:** PostgreSQL 18.

A subtransaction is a transaction inside another ([xact.c:1](../raw/postgres-18/src/backend/access/transam/xact.c#L1)).

### Widget cache

**Checked on:** PostgreSQL 17.

A widget cache keeps widgets ([widget.c:1](../raw/postgres-17/src/backend/widget.c#L1)).
"""

# Consistent terms and facts, pinned-source corrections, allowed exceptions, and waived names.
PASSING = f"""---
type: question
version: 18
pinned_commit: {PIN}
verified: false
---

# How `example_size` Is Used in PostgreSQL 18 (unverified)

## Question

In PostgreSQL 18, how is `example_size` used, and should `my_ratio` change?

## Short Answer

`example_size` sets the byte size of each slot behind `pg_stat_activity` {guc("example_size")}. It defaults to `1024` bytes, has a minimum of `100` and a maximum of `1048576`, and is stored in `pgstat_example_size` {guc("example_size")}.

The setting is `PGC_POSTMASTER`, so a change needs a restart {guc("example_size")}. `example_widget` holds the slots {STATUS_CITE}. `my_ratio` is the asker's own number.

## Details

`example_timeout` defaults to 1000 ms {guc("example_timeout")}.

`example_flag` is off by default {guc("example_flag")}.

`example_mode` is `auto` (the default) {guc("example_mode")}.

`example_buffers` defaults to 128MB {guc("example_buffers")}.

`pg_stat_activity` is a SQL view over `pg_stat_get_activity()` {VIEWS_CITE}.

The write-ahead log (WAL) is not involved {STATUS_CITE}.

PostgreSQL 18 has no `widget_hook` and no slot scanner {STATUS_CITE}.

The widget cache keeps the slots {STATUS_CITE}.

`example_size` and `example_timeout` keep defaults of `1024` and `1000` {guc("example_size")}.

The slot sweeper is gone; the slot cleaner frees idle slots {STATUS_CITE}.

The values are:

| Parameter | Default |
|---|---|
| `example_size` | `1024` |
"""

# No GUC table is cited, so the example_size fact can be checked only against the glossary.
BLOCKING = f"""---
type: question
version: 18
pinned_commit: {PIN}
---

# How Slots Work in PostgreSQL 18

## Question

How do slots work in PostgreSQL 18?

## Short Answer

The `example_size` setting defaults to `2048` bytes {STATUS_CITE}. `missing_widget` stores every slot {STATUS_CITE}. `pg_subtrans` records parents {STATUS_CITE}. Each row is a slot {STATUS_CITE}.

## Details

The slot scanner walks every slot {STATUS_CITE}.

`pg_stat_activity` is a function that reports slots {VIEWS_CITE}.

The WAL (write-ahead lock) guards slots {STATUS_CITE}.

The slot sweeper runs every minute {STATUS_CITE}.
"""


def postgres_snapshot() -> dict[str, bytes]:
    return postgres_files() | {GUC_PATH: GUC.encode(), STATUS_PATH: STATUS.encode(), VIEWS_PATH: VIEWS.encode()}


class CheckTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-test-", dir=PROJECT_ROOT / ".runtime" / "tmp")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve() / "project"
        self.workspace.mkdir()
        self.github = FakeGitHub()
        self.github.add(POSTGRES, PIN, postgres_snapshot())
        self.enterContext(patch("pgvideo.sources._http_get", side_effect=self.github))
        self.enterContext(patch("pgvideo.glossary.english_words", return_value=ENGLISH))
        self.runs = 0

    def check(self, document=PASSING, glossary=GLOSSARY):
        """Run Steps 3 to 6 on a document and return the manifest record, the check record, and the run."""
        self.runs += 1
        self.github.add(WIKI, f"{self.runs:040x}", wiki_files(document=document, glossary=glossary), refs=["master"])
        run_dir = self.workspace / "runs" / f"request-{self.runs}"
        run_dir.mkdir(parents=True)
        request = {"request_id": run_dir.name, "repository": WIKI, "document": {"path": DOCUMENT, "ref": "master"}}
        self.assertEqual(snapshot_sources(self.workspace, run_dir, request)["status"], "passed",
                         (run_dir / "source-report.md").read_text())
        self.assertEqual(parse_document(self.workspace, run_dir)["status"], "passed")
        match_glossary(self.workspace, run_dir)
        return self.recheck(run_dir)

    def recheck(self, run_dir):
        result = check_glossary(self.workspace, run_dir)
        return result, json.loads((run_dir / "glossary-check.json").read_text(encoding="utf-8")), run_dir

    @staticmethod
    def results(record):
        return {result["id"]: result for result in record["results"]}

    @staticmethod
    def blocking(record):
        return {issue["ids"][0] for issue in record["issues"] if issue["severity"] == "blocking"}

    @staticmethod
    def resolve(run_dir, *resolutions):
        (run_dir / RESOLUTIONS).write_text(json.dumps({"resolutions": list(resolutions)}), encoding="utf-8")

    def test_passing_document_records_consistent_results_corrections_and_exceptions(self):
        result, record, run_dir = self.check()
        self.assertEqual(result["status"], "passed", self.blocking(record))
        results = self.results(record)
        size = results["entry:example_size"]
        self.assertEqual((size["result"], size["tier"], size["glossary"]["version_status"]),
                         ("consistent", "central", "holds"))
        self.assertEqual(size["definition"]["use"], "introduce")
        self.assertIn("shared evidence: " + GUC_PATH, size["basis"])
        focus = {term["term"]: term for term in record["subject"]["focus_terms"]}
        self.assertEqual(focus["example_size"]["result"], "consistent")
        self.assertEqual(record["method"]["semantic_comparison"]["used"], False)

        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["status"], manifest["glossary_check"]["record"]),
                         ("glossary_checked", "glossary-check.json"))
        self.assertIsNone(manifest["glossary_check"]["resolutions"]["file"])
        self.assertTrue((run_dir / "glossary-check.md").is_file())

    def test_parameter_facts_are_compared_with_the_glossary_and_the_pinned_source(self):
        _result, record, _run_dir = self.check()
        facts = {(r["setting"], r["attribute"]): r for r in record["results"] if r["check"].startswith("fact:")}
        for key in (("example_size", "default"), ("example_size", "min"), ("example_size", "max"),
                    ("example_size", "context"), ("example_mode", "default"), ("example_buffers", "default")):
            with self.subTest(fact=key):
                self.assertEqual(facts[key]["result"], "consistent")
                self.assertEqual(facts[key]["evidence"][0]["path"], GUC_PATH)
        # The glossary's 16384 blocks and the document's 128MB are the same amount.
        self.assertEqual(facts["example_buffers", "default"]["glossary_values"][0]["same"], True)
        # "The setting is `PGC_POSTMASTER`" refers back to the subject's own parameter.
        self.assertEqual(facts["example_size", "context"]["document_value"]["value"], "postmaster")

        # The pinned source supports the document over the glossary's 2000 ms.
        timeout = facts["example_timeout", "default"]
        self.assertEqual((timeout["result"], timeout["resolution"]["winner"]), ("conflict", "document"))
        self.assertEqual(self.results(record)["entry:example_timeout"]["definition"]["use"], "name_only")
        # The document is wrong about example_flag; the correction goes to the script, not the snapshot.
        flag = facts["example_flag", "default"]
        self.assertEqual((flag["result"], flag["resolution"]["status"], flag["resolution"]["winner"]),
                         ("conflict", "resolved", "glossary"))
        (correction,) = record["corrections"]
        self.assertEqual((correction["setting"], correction["corrected"], correction["source"]),
                         ("example_flag", "on", "pinned_source"))
        codes = {issue["code"] for issue in record["issues"]}
        self.assertTrue({"correction_from_pinned_source", "glossary_corrected_by_source",
                         "definition_contradicted"} <= codes)
        # Values listed for two parameters at once are not paired with either.
        listed = [r for r in facts.values() if r["passages"]["sample"][0]["text"].startswith("`example_size` and")]
        self.assertEqual(listed, [])

    def test_version_scope_availability_aliases_acronyms_and_roles(self):
        _result, record, _run_dir = self.check()
        results = self.results(record)
        # "PostgreSQL 18 has no ... slot scanner" agrees with the Not present note.
        self.assertEqual(results["entry:slot-scanner"]["result"], "consistent")
        alias = results["alias:slot-cleaner:slot sweeper"]
        self.assertEqual((alias["result"], alias["resolution"]["by"], alias["blocking"]),
                         ("version_mismatch", "document_qualifier", False))
        acronym = next(r for r in record["results"] if r["check"] == "acronym")
        self.assertEqual((acronym["result"], acronym["document_expansion"]), ("consistent", "write-ahead log"))
        role = next(r for r in record["results"] if r["check"] == "role")
        self.assertEqual((role["result"], role["document_role"], role["glossary_role"]), ("consistent", "view", "view"))

    def test_concepts_outside_the_glossary_need_matching_version_evidence(self):
        _result, record, _run_dir = self.check()
        results = self.results(record)
        widget = results["term:example_widget"]
        self.assertEqual((widget["result"], widget["tier"], widget["resolution"]["status"]),
                         ("not_in_glossary", "central", "accepted_exception"))
        self.assertEqual(widget["evidence"][0]["path"], STATUS_PATH)
        cache = results["entry:widget-cache"]
        self.assertEqual((cache["gap"], cache["resolution"]["status"]), ("unchecked", "accepted_exception"))
        self.assertEqual(results["term:my_ratio"]["resolution"]["by"], "question")
        self.assertEqual(results["term:widget_hook"]["resolution"]["by"], "negated")
        self.assertLessEqual({"example_widget", "Widget cache"}, {e["term"] for e in record["exceptions"]})

    def test_narrated_claims_are_checked_against_their_citations(self):
        _result, record, _run_dir = self.check()
        claims = {claim["at"]: claim for claim in record["claims"]}
        first = claims["short-answer.1.s2"]
        self.assertEqual((first["status"], first["central"], first["citation_scope"]), ("verified", True, "sentence"))
        found = {item["text"]: item for item in first["items"]}
        self.assertEqual(found["1048576"]["level"], "range")
        self.assertEqual(found["pgstat_example_size"]["line"], line_of(GUC, "&pgstat_example_size"))
        self.assertTrue(any(claim["id"].startswith("claim@details.") and claim["status"] == "verified"
                            for claim in record["claims"]))
        # A lead-in ending in a colon introduces the table; the table's rows are checked instead.
        self.assertFalse(any(claim["text"] == "The values are:" for claim in record["claims"]))
        self.assertTrue(any(claim["at"].endswith(".r1") for claim in record["claims"]))

    def test_unresolved_issues_need_review_with_the_evidence_to_continue(self):
        result, record, run_dir = self.check(BLOCKING)
        self.assertEqual(result["status"], "needs_review")
        blocking = self.blocking(record)
        expected = {"fact:example_size:default@short-answer.1.s1", "term:missing_widget",
                    "claim@short-answer.1.s2", "ambiguous:pg_subtrans:slru+subtransaction", "entry:slot-scanner",
                    "alias:slot-cleaner:slot sweeper"}
        self.assertTrue(expected <= blocking, blocking)
        self.assertTrue(any(i.startswith("role:pg_stat_activity@") for i in blocking))
        self.assertTrue(any(i.startswith("acronym:WAL@") for i in blocking))
        fact = self.results(record)["fact:example_size:default@short-answer.1.s1"]
        self.assertEqual((fact["result"], fact["source_value"]), ("conflict", None))
        self.assertIn(GUC_PATH, fact["resolution"]["evidence_needed"])
        # An ordinary word in a conclusion only keeps its glossary definition out of the script.
        self.assertIn("ambiguous_central_words", {issue["code"] for issue in record["issues"]})
        self.assertNotIn("ambiguous:row", blocking)
        report = (run_dir / "glossary-check.md").read_text(encoding="utf-8")
        self.assertIn("## Blocking Issues", report)
        self.assertIn('- id: "entry:slot-scanner"', report)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["status"], manifest["glossary_check"]["issues"]["blocking"]),
                         ("needs_review", len(blocking)))

    def test_documented_resolutions_let_the_same_request_continue(self):
        _result, record, run_dir = self.check(BLOCKING)
        evidence = f"raw/postgres-18/{STATUS_PATH}#L3-L4"
        decisions = []
        for identifier in sorted(self.blocking(record)):
            if identifier.startswith("fact:"):
                decisions.append({"id": identifier, "decision": "use_glossary", "reason": "The table says 1024.",
                                  "evidence": f"raw/postgres-18/{GUC_PATH}#L20-L25"})
            elif identifier.startswith("ambiguous:"):
                decisions.append({"id": identifier, "decision": "choose_entry", "entry": "slru",
                                  "reason": "pg_subtrans is an SLRU."})
            elif identifier.startswith("entry:"):
                decisions.append({"id": identifier, "decision": "use_document", "reason": "SlotScannerMain exists.",
                                  "evidence": evidence, "reviewer": "a reviewer"})
            else:
                decisions.append({"id": identifier, "decision": "omit", "reason": "Not needed for the video."})
        self.resolve(run_dir, *decisions)
        result, record, run_dir = self.recheck(run_dir)
        self.assertEqual(result["status"], "passed", self.blocking(record))
        self.assertEqual(len(record["resolutions"]["applied"]), len(decisions))
        results = self.results(record)
        scanner = results["entry:slot-scanner"]["resolution"]
        self.assertEqual((scanner["by"], scanner["decision"], scanner["replaces"]["status"]),
                         ("reviewer", "use_document", "unresolved"))
        self.assertEqual(scanner["evidence"][0]["checked"], True)
        self.assertIn("SlotScannerMain", scanner["evidence"][0]["excerpt"])
        self.assertIn("reviewer", {correction["source"] for correction in record["corrections"]})
        self.assertIn("claim@short-answer.1.s2", {omission["id"] for omission in record["omissions"]})
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["glossary_check"]["resolutions"]["file"], RESOLUTIONS)
        self.assertEqual(len(manifest["glossary_check"]["resolutions"]["sha256"]), 64)
        self.assertIn("## Resolutions Applied", (run_dir / "glossary-check.md").read_text(encoding="utf-8"))

    def test_invalid_resolutions_fail_clearly(self):
        _result, _record, run_dir = self.check(BLOCKING)
        claim = "claim@short-answer.1.s2"
        cases = [
            ({"id": "nope", "decision": "omit", "reason": "x"}, "is not a result or claim"),
            ({"id": claim, "decision": "use_glossary", "reason": "x"}, "must be one of use_document, omit"),
            ({"id": claim, "decision": "omit"}, "needs a nonempty reason"),
            ({"id": claim, "decision": "use_document", "reason": "x"}, "needs PostgreSQL 18 evidence"),
            ({"id": claim, "decision": "use_document", "reason": "x", "evidence": "raw/postgres-17/src/a.c#L1"},
             "not from the document's PostgreSQL 18 source tree"),
            ({"id": claim, "decision": "use_document", "reason": "x",
              "evidence": f"raw/postgres-18/{STATUS_PATH}#L1-L99"}, "outside the file"),
            ({"id": claim, "decision": "use_document", "reason": "x", "evidence": "../../etc/passwd"},
             "is not raw/postgres-NN/path"),
            ({"id": "ambiguous:pg_subtrans:slru+subtransaction", "decision": "choose_entry", "reason": "x",
              "entry": "tuple"}, "needs entry: one of slru, subtransaction"),
            ({"id": "entry:example_size", "decision": "omit", "reason": "x"}, "has nothing to resolve"),
            ({"id": claim, "decision": "omit", "reason": "x", "extra": 1}, "unknown keys: extra"),
        ]
        for resolution, message in cases:
            with self.subTest(message=message):
                self.resolve(run_dir, resolution)
                with self.assertRaisesRegex(ValueError, message):
                    check_glossary(self.workspace, run_dir)
        self.resolve(run_dir, {"id": claim, "decision": "omit", "reason": "x"},
                     {"id": claim, "decision": "omit", "reason": "y"})
        with self.assertRaisesRegex(ValueError, "resolved more than once"):
            check_glossary(self.workspace, run_dir)
        (run_dir / RESOLUTIONS).write_text("resolutions: &a\n  - *a\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "must not use YAML aliases"):
            check_glossary(self.workspace, run_dir)
        (run_dir / RESOLUTIONS).unlink()
        outside = self.workspace.parent / "resolutions.yaml"
        outside.write_text("resolutions: []\n", encoding="utf-8")
        (run_dir / RESOLUTIONS).symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "not a symlink"):
            check_glossary(self.workspace, run_dir)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["status"], manifest["glossary_check"]["status"]), ("failed", "failed"))

    def test_altered_inputs_fail_and_are_recorded(self):
        _result, _record, run_dir = self.check()
        matches = run_dir / "glossary-matches.json"
        matches.write_text(matches.read_text(encoding="utf-8").replace("example_size", "example_sizes"),
                           encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "glossary-matches.json does not match"):
            check_glossary(self.workspace, run_dir)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["status"], manifest["glossary_check"]["status"]), ("failed", "failed"))

    def test_prepare_needs_review_and_resume_continues_the_same_request(self):
        self.github.add(WIKI, WIKI_COMMIT, wiki_files(document=BLOCKING, glossary=GLOSSARY), refs=["main"])
        self.enterContext(patch("pgvideo.cli.project_root", return_value=self.workspace))
        self.enterContext(patch("pgvideo.cli.local_selection"))
        self.enterContext(patch("pgvideo.cli._narrate", return_value=0))
        self.enterContext(patch("pgvideo.sources._github_contents",
                                side_effect=lambda path, ref: {"type": "file", "path": path}))

        def run(*argv):
            args = parser().parse_args(list(argv))
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = (prepare if argv[0] == "prepare" else resume)(args, self.workspace)
            return status, stdout.getvalue(), stderr.getvalue()

        install_project_files(self.workspace)
        status, stdout, stderr = run("prepare", "--document", DOCUMENT)
        self.assertEqual(status, NEEDS_REVIEW, stderr)
        self.assertIn("Glossary check:", stdout)
        (run_dir,) = (self.workspace / "runs").iterdir()
        self.assertIn(f"scripts/pgvideo resume --request {run_dir.name}", stderr)

        status, _stdout, stderr = run("resume", "--request", run_dir.name)
        self.assertEqual(status, NEEDS_REVIEW)
        record = json.loads((run_dir / "glossary-check.json").read_text(encoding="utf-8"))
        self.resolve(run_dir, *({"id": identifier, "decision": "omit", "reason": "Left out of the video."}
                                for identifier in self.blocking(record)))
        status, stdout, stderr = run("resume", "--request", run_dir.name)
        self.assertEqual(status, 0, stderr)
        self.assertIn(f"Resuming request: {run_dir}", stdout)
        self.assertIn("Evidence packet:", stdout)
        self.assertIn("nothing saved yet", stdout)

        for request, message in (("../outside", "one directory name"), ("missing", "No request 'missing'")):
            with self.subTest(request=request):
                status, _stdout, stderr = run("resume", "--request", request)
                self.assertEqual(status, 1)
                self.assertIn(message, stderr)
        manifest_path = run_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["document"]["status"] = "needs_review"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        status, _stdout, stderr = run("resume", "--request", run_dir.name)
        self.assertEqual(status, 1)
        self.assertIn("only the cross-check and later stages can be resumed", stderr)


class ParameterTests(unittest.TestCase):
    def test_guc_tables_give_context_defaults_limits_units_and_enum_spellings(self):
        settings = _guc_table(GUC_PATH, GUC)
        size = settings["example_size"]
        self.assertEqual((size["type"], size["context"]["value"], size["line"]),
                         ("int", "postmaster", line_of(GUC, '{"example_size"')))
        self.assertEqual([size[key]["value"] for key in ("default", "min", "max")], [1024, 100, 1048576])
        self.assertEqual(size["default"]["unit"], "bytes")
        self.assertEqual(settings["example_timeout"]["max"]["value"], 2147483647)
        self.assertEqual(settings["example_buffers"]["max"]["value"], 1073741823)
        self.assertEqual(settings["example_flag"]["default"]["value"], "on")
        mode = settings["example_mode"]["default"]
        self.assertEqual((mode["kind"], mode["value"], mode["names"]), ("enum", "EXAMPLE_MODE_AUTO", ["auto"]))

    def test_guc_parameters_dat_records_are_read(self):
        text = """[
{ name => 'example_size', type => 'int', context => 'PGC_POSTMASTER', group => 'STATS',
  short_desc => 'Sets the size.', flags => 'GUC_UNIT_BYTE', variable => 'pgstat_example_size',
  boot_val => '1024', min => '100', max => '1048576' },
]
"""
        size = _guc_data("src/backend/utils/misc/guc_parameters.dat", text)["example_size"]
        self.assertEqual((size["context"]["value"], size["default"]["value"], size["max"]["value"], size["line"]),
                         ("postmaster", 1024, 1048576, 2))

    def test_values_compare_across_units_and_spellings(self):
        blocks = _guc_table(GUC_PATH, GUC)["example_buffers"]["default"]
        self.assertTrue(_same(_number("128", "MB", "128MB"), blocks))
        self.assertFalse(_same(_number("64", "MB", "64MB"), blocks))
        self.assertTrue(_same(_number("1", "s", "1s"), _number("1000", "ms", "1000 ms")))
        self.assertIsNone(_same(_number("1", "s", "1s"), _number("1", "MB", "1MB")))
        mode = _guc_table(GUC_PATH, GUC)["example_mode"]["default"]
        self.assertTrue(_same({"kind": "word", "value": "auto", "raw": "auto"}, mode))
        self.assertFalse(_same({"kind": "bool", "value": "off", "raw": "off"}, mode))

    def test_sentence_facts_need_a_keyword_and_a_value(self):
        def facts(text):
            return {(f["attribute"], f["value"].get("value")) for f in _sentence_facts(*_plain(text))}

        self.assertEqual(facts("It defaults to `1024` bytes, has a minimum of `100` and a maximum of `1048576`."),
                         {("default", 1024), ("min", 100), ("max", 1048576)})
        self.assertEqual(facts("It accepts 100 to 1048576 bytes."), {("min", 100), ("max", 1048576)})
        self.assertEqual(facts("`compute_query_id` is `auto` (the default)."), {("default", "auto")})
        self.assertEqual(facts("Its context is `postmaster`; `work_mem` is `PGC_USERSET`."),
                         {("context", "postmaster"), ("context", "user")})
        self.assertEqual(facts("`track_activities` is enabled by default."), {("default", "on")})
        # Measurements and ordinary words are not parameter facts.
        self.assertEqual(facts("Each command was cancelled between 2018 and 2024 ms."), set())
        self.assertEqual(facts("The default is the value of the other setting."), set())
        self.assertEqual(facts("The `postmaster` process starts first."), set())


if __name__ == "__main__":
    unittest.main()
