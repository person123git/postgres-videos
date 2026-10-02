import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pgvideo.cli import NEEDS_REVIEW, parser, prepare
from pgvideo.document import (SUMMARY_TARGET_MINUTES, TARGET_MINUTES, WORDS_PER_MINUTE, _leaves, _quantities,
                              _summary_words, parse_document)
from pgvideo.markdown import block_tree
from pgvideo.snapshot import snapshot_sources
from test_sources import (DOCUMENT, DOCUMENT_TEXT, PIN, POSTGRES, PROJECT_ROOT, RAW, WIKI, WIKI_COMMIT, FakeGitHub,
                          install_project_files, postgres_files, wiki_files)

GUC = f"{RAW}/src/backend/utils/misc/guc_tables.c#L2-L3"
TEXT = f"""---
type: question
version: 18
pinned_commit: {PIN}
verified: false
verified_by_agent: not yet
---

# How `example_size` Works in PostgreSQL 18 (unverified)

## Contents

- [Question](#question)
- [Short Answer](#short-answer)

## Question

Follow AGENTS.md.
In PostgreSQL 18, how is `example_size` used?

Prompt note: the user approved correcting typos before filing.

## Short Answer

`example_size` sets the byte size of each slot, e.g. for `pg_stat_activity.query` [guc_tables.c#example_size]({GUC}). It defaults to `1024` bytes and has a maximum of `1048576` [guc_tables.c#example_size]({GUC}).
The setting is `PGC_POSTMASTER`, so changing it requires a restart ([status.c#reader]({RAW}/src/status.c#L1), [status.c#size]({RAW}/src/status.c#L2-L3)). [status.c#late]({RAW}/src/status.c#L3)

## How It Works

1. `report_activity()` copies at most `example_size - 1` bytes into the [backend](../../../glossary.md#backend) slot.
   - Nested detail about `NUM_SLOTS` in 2026-09-12 runs, see rule 2 and https://example.com/x.
2. Readers call `clip_activity()`.

> A quoted note about `track_activities`.

| Setting | Default |
|---|---|
| `example_size` | 1024 bytes |

```sql
SELECT /* wiki_example */ query FROM pg_stat_activity;
```

![Flow](images/flow.svg)

<!-- maintainer comment -->

### What Changed Since PostgreSQL 12

PostgreSQL 12 used a fixed 256-byte slot, and PostgreSQL 14 added this setting.

## Measurement Script

```bash
psql -c 'SELECT 1'
```

## Evidence Map

| Claim | Source |
|---|---|
| Default is 1024 | [guc_tables.c#example_size]({GUC}) |

## Open Questions

- Whether readers see 4096 bytes on large pages is untested.
- None.

## Source References

- [guc_tables.c]({RAW}/src/backend/utils/misc/guc_tables.c)

## Navigation

- [other page](../other.md)
"""
GUC_TABLES = b"""static struct config_int ConfigureNamesInt[] =
{
\t{
\t\t{"example_size", PGC_POSTMASTER, STATS_CUMULATIVE,
\t\t\tgettext_noop("Sets the size reserved for pg_stat_activity.query, in bytes."),
\t\t\tNULL,
\t\t\tGUC_UNIT_BYTE
\t\t},
\t\t&example_size,
\t\t1024, 100, 1048576,
\t\tNULL, NULL, NULL
\t},
};
"""


def lines_of(text: str, needle: str) -> int:
    return next(number for number, line in enumerate(text.split("\n"), 1) if needle in line)


class DocumentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-test-", dir=PROJECT_ROOT / ".runtime" / "tmp")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve() / "project"
        self.workspace.mkdir()
        self.github = FakeGitHub()
        files = postgres_files() | {"src/backend/utils/misc/guc_tables.c": GUC_TABLES}
        self.github.add(POSTGRES, PIN, files)
        self.enterContext(patch("pgvideo.sources._http_get", side_effect=self.github))
        self.runs = 0

    def parse(self, document=TEXT, detail=None):
        self.runs += 1
        self.github.add(WIKI, f"{self.runs:040x}", wiki_files(document=document), refs=["master"])
        run_dir = self.workspace / "runs" / f"request-{self.runs}"
        run_dir.mkdir(parents=True)
        request = {"request_id": run_dir.name, "repository": WIKI, "document": {"path": DOCUMENT, "ref": "master"}}
        if detail:
            (run_dir / "request.json").write_text(json.dumps(request | {"settings": {"detail": detail}}),
                                                  encoding="utf-8")
        sources = snapshot_sources(self.workspace, run_dir, request)
        self.assertEqual(sources["status"], "passed", (run_dir / "source-report.md").read_text())
        result = parse_document(self.workspace, run_dir)
        record = json.loads((run_dir / "document.json").read_text(encoding="utf-8"))
        return result, record, run_dir

    @staticmethod
    def blocks(record):
        return {block["id"]: block for section in record["sections"] for block in _walk(section["blocks"])}

    @staticmethod
    def sentences(record):
        return {sentence["id"]: sentence for section in record["sections"] for block in _leaves(section["blocks"])
                for sentence in block.get("sentences", [])}

    def test_sections_have_anchor_ids_roles_and_original_lines(self):
        _result, record, _run_dir = self.parse()
        sections = {section["id"]: section for section in record["sections"]}
        self.assertEqual([(s["id"], s["role"]) for s in record["sections"]], [
            ("how-example_size-works-in-postgresql-18-unverified", "title"), ("contents", "navigation"),
            ("question", "question"), ("short-answer", "summary"), ("how-it-works", "content"),
            ("what-changed-since-postgresql-12", "content"), ("measurement-script", "measurement"),
            ("evidence-map", "reference"), ("open-questions", "open_questions"),
            ("source-references", "reference"), ("navigation", "navigation"),
        ])
        body = TEXT
        self.assertEqual(sections["question"]["lines"], [lines_of(body, "## Question"), lines_of(body, "Prompt note")])
        self.assertEqual(sections["how-it-works"]["subtree_lines"],
                         [lines_of(body, "## How It Works"), lines_of(body, "PostgreSQL 12 used")])
        self.assertEqual(sections["what-changed-since-postgresql-12"]["parent"], "how-it-works")
        self.assertEqual(sections["short-answer"]["url"],
                         f"https://github.com/{WIKI}/blob/{record['document']['wiki_commit']}/{DOCUMENT}#short-answer")
        self.assertEqual(sections["how-example_size-works-in-postgresql-18-unverified"]["text"],
                         "How `example_size` Works in PostgreSQL 18 (unverified)")
        first = min(block["lines"][0] for section in record["sections"] for block in section["blocks"])
        self.assertGreater(first, lines_of(body, "verified_by_agent"), "front matter must not become blocks")

    def test_blocks_record_structure_types_and_uses(self):
        _result, record, _run_dir = self.parse()
        blocks = self.blocks(record)
        self.assertEqual(blocks["how-it-works.1"]["type"], "list")
        self.assertTrue(blocks["how-it-works.1"]["ordered"])
        self.assertEqual(blocks["how-it-works.1.1.2"]["type"], "list")
        self.assertEqual(blocks["how-it-works.1.1.2.1.1"]["lines"], [lines_of(TEXT, "Nested detail")] * 2)
        self.assertEqual(blocks["how-it-works.2"]["type"], "blockquote")
        table = blocks["how-it-works.3"]
        self.assertEqual((table["type"], table["use"]), ("table", "display"))
        self.assertEqual([cell["text"] for cell in table["header"]], ["Setting", "Default"])
        self.assertEqual([cell["text"] for cell in table["rows"][0]["cells"]], ["`example_size`", "1024 bytes"])
        self.assertEqual(table["rows"][0]["id"], "how-it-works.3.r1")
        code = blocks["how-it-works.4"]
        self.assertEqual((code["type"], code["language"], code["kind"], code["use"]), ("code", "sql", "sql", "display"))
        self.assertEqual(code["lines"], [lines_of(TEXT, "```sql"), lines_of(TEXT, "```sql") + 2])
        image = blocks["how-it-works.5"]
        self.assertEqual((image["type"], image["use"]), ("image", "display"))
        self.assertEqual(record["links"][image["images"][0]]["target"],
                         "wiki/v18/questions/observability/images/flow.svg")
        self.assertEqual((blocks["how-it-works.6"]["type"], blocks["how-it-works.6"]["use"]), ("html", "exclude"))
        self.assertEqual(blocks["contents.1.1.1"]["use"], "exclude")
        self.assertEqual(blocks["evidence-map.1"]["use"], "reference")
        self.assertIsNone(blocks["evidence-map.1"]["rows"][0]["cells"][0]["spoken"])

    def test_sentences_drop_citations_and_keep_code_for_display(self):
        _result, record, _run_dir = self.parse()
        sentences = self.sentences(record)
        line = lines_of(TEXT, "sets the byte size")
        first, second, third = (sentences[f"short-answer.1.s{n}"] for n in (1, 2, 3))
        self.assertEqual(first["text"],
                         "`example_size` sets the byte size of each slot, e.g. for `pg_stat_activity.query`.")
        self.assertEqual(first["spoken"],
                         "example_size sets the byte size of each slot, e.g. for pg_stat_activity.query.")
        self.assertEqual((first["lines"], second["lines"], third["lines"]), ([line, line], [line, line],
                                                                              [line + 1, line + 1]))
        self.assertEqual(second["text"], "It defaults to `1024` bytes and has a maximum of `1048576`.")
        self.assertEqual(third["text"], "The setting is `PGC_POSTMASTER`, so changing it requires a restart.")
        self.assertEqual(len(third["citations"]), 3, "the citation after the period belongs to this sentence")
        citation = record["links"][first["citations"][0]]
        self.assertEqual((citation["kind"], citation["at"], citation["lines"]), ("citation", first["id"], [2, 3]))
        self.assertEqual(citation["url"], f"https://github.com/{POSTGRES}/blob/{PIN}/"
                                          "src/backend/utils/misc/guc_tables.c#L2-L3")
        for sentence in sentences.values():
            for text in (sentence["text"], sentence["spoken"] or ""):
                self.assertNotIn("raw/postgres", text)
                self.assertNotIn("](", text)
        nested = sentences["how-it-works.1.1.2.1.1.s1"]
        self.assertNotIn("https://", nested["spoken"])
        self.assertIn("https://example.com/x", nested["text"])
        self.assertEqual(sentences["how-it-works.1.1.1.s1"]["spoken"],
                         "report_activity() copies at most example_size - 1 bytes into the backend slot.")

    def test_maintenance_navigation_and_references_are_not_spoken(self):
        _result, record, _run_dir = self.parse()
        sentences, blocks = self.sentences(record), self.blocks(record)
        follow = sentences["question.1.s1"]
        self.assertEqual((follow["text"], follow["maintenance"], follow["spoken"]), ("Follow AGENTS.md.", True, None))
        self.assertEqual(sentences["question.1.s2"]["spoken"], "In PostgreSQL 18, how is example_size used?")
        self.assertEqual((blocks["question.2"]["use"], blocks["question.2"]["reason"]), ("exclude", "maintenance"))
        for identifier in ("navigation.1.1.1.s1", "source-references.1.1.1.s1"):
            self.assertIsNone(sentences.get(identifier, {"spoken": None})["spoken"])
        self.assertEqual(blocks["navigation.1.1.1"]["reason"], "navigation")
        self.assertEqual((blocks["source-references.1.1.1"]["use"], blocks["source-references.1.1.1"]["sentences"]),
                         ("reference", []))
        self.assertEqual(len(blocks["source-references.1.1.1"]["citations"]), 1)
        issues = {issue["code"]: issue for issue in record["issues"]}
        self.assertEqual(issues["maintenance_excluded"]["lines"],
                         [lines_of(TEXT, "Follow AGENTS"), lines_of(TEXT, "Prompt note")])
        coverage = (_run_dir / "coverage.md").read_text(encoding="utf-8")
        self.assertIn("## Maintenance Text Excluded From Narration", coverage)
        self.assertIn("Follow AGENTS.md.", coverage)

    def test_extracts_subject_conclusions_terms_numbers_versions_examples_and_open_questions(self):
        _result, record, _run_dir = self.parse()
        subject = record["subject"]
        self.assertEqual(subject["display_title"], "How `example_size` Works in PostgreSQL 18")
        self.assertEqual(subject["spoken_title"], "How example_size Works in PostgreSQL 18")
        self.assertTrue(subject["unverified"])
        self.assertEqual(subject["question"]["text"], "In PostgreSQL 18, how is `example_size` used?")
        self.assertEqual(subject["focus_terms"], ["example_size"])
        self.assertEqual(record["conclusions"]["source"], "summary")
        self.assertEqual([s["id"] for s in record["conclusions"]["sentences"]],
                         ["short-answer.1.s1", "short-answer.1.s2", "short-answer.1.s3"])

        terms = {term["term"]: term for term in record["terms"]}
        self.assertEqual((terms["example_size"]["kind"], terms["example_size"]["setting_source"]),
                         ("setting", "pinned_source"))
        self.assertEqual(terms["report_activity"]["kind"], "function")
        self.assertEqual(terms["NUM_SLOTS"]["kind"], "constant")
        self.assertEqual(terms["PGC_POSTMASTER"]["kind"], "constant")
        self.assertEqual(terms["pg_stat_activity.query"]["kind"], "qualified_name")
        self.assertEqual((terms["backend"]["kind"], terms["backend"]["glossary_anchors"]),
                         ("glossary_link", ["backend"]))
        self.assertEqual(terms["track_activities"]["kind"], "identifier", "not defined in the cited GUC table")
        self.assertIn({"at": "short-answer.1.s1", "line": lines_of(TEXT, "sets the byte size")},
                      terms["example_size"]["occurrences"])

        numbers = {claim["id"]: claim["values"] for claim in record["numbers"]}
        self.assertEqual(numbers["short-answer.1.s2"], [
            {"raw": "1024 bytes", "value": 1024, "unit": "bytes"}, {"raw": "1048576", "value": 1048576, "unit": None}])
        self.assertEqual(numbers["how-it-works.3.r1"], [{"raw": "1024 bytes", "value": 1024, "unit": "bytes"}])
        self.assertEqual(numbers["what-changed-since-postgresql-12.1.s1"],
                         [{"raw": "256-byte", "value": 256, "unit": "bytes"}])
        self.assertNotIn("how-it-works.1.1.2.1.1.s1", numbers, "dates and labels are not quantities")
        self.assertNotIn("evidence-map.1.r1", numbers)

        versions = {entry["id"]: entry for entry in record["version_restrictions"]}
        changed = versions["what-changed-since-postgresql-12.1.s1"]
        self.assertEqual((changed["versions"], changed["other_versions"]), (["12", "14"], ["12", "14"]))
        self.assertIn("added", changed["qualifiers"])
        self.assertEqual(versions["what-changed-since-postgresql-12"]["kind"], "heading")
        self.assertEqual(versions["question.1.s2"]["other_versions"], [])
        self.assertEqual(record["version_scope"]["other_versions_mentioned"], ["12", "14"])

        examples = {example["id"]: example for example in record["examples"]}
        self.assertEqual((examples["how-it-works.4"]["role"], examples["how-it-works.4"]["kind"]), ("example", "sql"))
        self.assertEqual((examples["measurement-script.1"]["role"], examples["measurement-script.1"]["kind"]),
                         ("measurement", "shell"))
        self.assertEqual([item["text"] for item in record["open_questions"]],
                         ["Whether readers see 4096 bytes on large pages is untested."])
        self.assertEqual([page["target"] for page in record["related_pages"]], ["wiki/v18/questions/other.md"])

    def test_short_document_coverage_explains_content_and_excludes_lists(self):
        result, record, run_dir = self.parse()
        coverage = record["coverage"]
        decisions = {entry["section"]: entry["decision"] for entry in coverage["sections"]}
        self.assertFalse(coverage["long_document"])
        self.assertEqual(decisions, {
            "how-example_size-works-in-postgresql-18-unverified": "explain", "contents": "exclude",
            "question": "explain", "short-answer": "explain", "how-it-works": "explain",
            "what-changed-since-postgresql-12": "explain", "measurement-script": "omit", "evidence-map": "exclude",
            "open-questions": "explain", "source-references": "exclude", "navigation": "exclude",
        })
        self.assertEqual(result["status"], "passed")
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "document_ready")
        self.assertEqual(manifest["document"]["record"], "document.json")
        self.assertEqual(manifest["document"]["coverage"]["file"], "coverage.md")
        self.assertEqual(manifest["document"]["input"]["path"], DOCUMENT)
        self.assertEqual(manifest["sources"]["wiki"]["commit"], record["document"]["wiki_commit"])
        report = (run_dir / "coverage.md").read_text(encoding="utf-8")
        self.assertIn("| [Question](", report)
        self.assertIn("## Linked Wiki Pages Not Included", report)

    def test_long_document_is_condensed_around_the_subject_and_keeps_caveats(self):
        filler = " ".join(f"Sentence {n} explains another detail of the mechanism." for n in range(40))
        sections = [
            "## Tests\n\n`example_size` has a test. " + filler,
            "## Known Limitations\n\n" + filler,
            *(f"## Background Part {n}\n\n" + filler for n in range(1, 17)),
            "## Uses Of `example_size`\n\n`example_size` matters here. " + filler,
        ]
        document = TEXT.replace("## Measurement Script", "\n\n".join(sections) + "\n\n## Measurement Script")
        _result, record, _run_dir = self.parse(document)
        coverage = record["coverage"]
        entries = {entry["section"]: entry for entry in coverage["sections"]}
        self.assertTrue(coverage["long_document"])
        self.assertLessEqual(coverage["planned_words"], TARGET_MINUTES[1] * WORDS_PER_MINUTE)
        self.assertGreater(coverage["full_minutes"], TARGET_MINUTES[1])
        self.assertEqual(entries["uses-of-example_size"]["decision"], "explain")
        self.assertEqual(entries["uses-of-example_size"]["focus_terms"], ["example_size"])
        self.assertIn(entries["known-limitations"]["decision"], ("explain", "summarize"))
        self.assertEqual(entries["tests"]["decision"], "omit")
        self.assertTrue(any(entry["decision"] == "omit" for entry in coverage["sections"]
                            if entry["section"].startswith("background-part")))
        self.assertIn("long_document", {issue["code"] for issue in record["issues"]})

    @staticmethod
    def long_text():
        """TEXT with tests, a caveat, sixteen background sections with long lead sentences, and a subject section."""
        filler = " ".join(f"Sentence {n} explains another detail of the mechanism." for n in range(40))
        lead = "describes one more piece of the mechanism, " * 4
        sections = [
            "## Tests\n\n`example_size` has a test. " + filler,
            "## Known Limitations\n\n`example_size` cannot shrink below `100` bytes. " + filler,
            *(f"## Background Part {n}\n\nPart {n} {lead}in detail. " + filler for n in range(1, 17)),
            "## Uses Of `example_size`\n\n`example_size` matters to every reader. " + filler,
        ]
        return TEXT.replace("## Measurement Script", "\n\n".join(sections) + "\n\n## Measurement Script")

    def test_tables_are_planned_at_their_rows_and_condensed_to_their_first_rows(self):
        listing = "".join(f"| Case {n} | Explains another case of the mechanism |\n" for n in range(1, 41))
        issues = "".join(f"| Case {n} | Fails with error {n} |\n" for n in range(1, 21))
        tables = ("## Complete List\n\n| Name | Description |\n|---|---|\n" + listing + "\n"
                  "## Known Issues\n\n| Case | Behavior |\n|---|---|\n" + issues + "\n")
        _result, record, run_dir = self.parse(self.long_text().replace("## Tests\n\n", tables + "## Tests\n\n"))
        entries = {entry["section"]: entry for entry in record["coverage"]["sections"]}
        # Each row is read as "Case 1: description Explains another case of the mechanism."
        self.assertEqual((entries["complete-list"]["words"], entries["known-issues"]["words"]), (9 * 40, 7 * 20))
        self.assertTrue(record["coverage"]["long_document"])
        # A table alone has no sentence to condense, so a condensed section reads its first rows.
        for section, rows, row_words in (("complete-list", 40, 9), ("known-issues", 20, 7)):
            entry = entries[section]
            self.assertEqual(entry["decision"], "summarize", section)
            kept = len(entry["keep"])
            self.assertTrue(0 < kept < rows, section)
            self.assertEqual(entry["keep"], [f"{section}.1.r{n}" for n in range(1, kept + 1)])
            self.assertEqual(entry["planned_words"], row_words * kept)
            self.assertLessEqual(entry["planned_words"], _summary_words(entry["words"]))
            self.assertTrue(entry["reason"].endswith("Only the first rows of its table are read."), section)
        self.assertTrue(entries["known-issues"]["reason"].startswith("Caveat:"))
        report = (run_dir / "coverage.md").read_text(encoding="utf-8")
        self.assertIn("(`complete-list.1.r1`): Case 1 | Explains another case of the mechanism", report)

    def test_summary_keeps_the_key_points_within_its_budget(self):
        result, record, run_dir = self.parse(self.long_text(), detail="summary")
        coverage = record["coverage"]
        entries = {entry["section"]: entry for entry in coverage["sections"]}
        sentences = self.sentences(record)
        self.assertEqual((coverage["detail"], coverage["target_minutes"]), ("summary", list(SUMMARY_TARGET_MINUTES)))
        # The question, the page's own summary, and short open questions are narrated in full.
        for section in ("question", "short-answer", "open-questions"):
            self.assertEqual(entries[section]["decision"], "explain", section)
            self.assertNotIn("keep", entries[section])
        self.assertEqual((entries["tests"]["decision"], entries["measurement-script"]["decision"]), ("omit", "omit"))
        # Every other section keeps its lead sentence, or is left out when the budget is spent.
        caveat = entries["known-limitations"]
        self.assertEqual((caveat["decision"], sentences[caveat["keep"][0]]["text"]),
                         ("summarize", "`example_size` cannot shrink below `100` bytes."))
        self.assertEqual(sentences[entries["how-it-works"]["keep"][0]]["text"],
                         "`report_activity()` copies at most `example_size - 1` bytes into the backend slot.")
        self.assertEqual(entries["uses-of-example_size"]["decision"], "summarize")
        background = [entries[f"background-part-{n}"] for n in range(1, 17)]
        kept = [entry for entry in background if entry["decision"] == "summarize"]
        self.assertTrue(kept and len(kept) < len(background))
        self.assertEqual(kept, background[:len(kept)], "sections of equal rank are kept in page order")
        for entry in kept:
            (sentence,) = entry["keep"]
            self.assertTrue(sentences[sentence]["text"].startswith("Part "))
            self.assertEqual(entry["planned_words"], len(sentences[sentence]["spoken"].split()))
        self.assertEqual({entry["reason"] for entry in background if entry["decision"] == "omit"},
                         {"Beyond the summary's length; kept in the references."})
        self.assertLessEqual(coverage["planned_words"], SUMMARY_TARGET_MINUTES[1] * WORDS_PER_MINUTE)
        self.assertGreater(coverage["full_minutes"], TARGET_MINUTES[1])
        codes = {issue["code"] for issue in record["issues"]}
        self.assertIn("summary", codes)
        self.assertNotIn("long_document", codes)
        self.assertEqual(result["coverage"]["detail"], "summary")
        report = (run_dir / "coverage.md").read_text(encoding="utf-8")
        self.assertIn("- Level of detail: summary", report)
        self.assertIn("## Kept Sentences And Table Rows", report)
        self.assertIn("(`known-limitations.1.s1`): `example_size` cannot shrink below `100` bytes.", report)

    def test_summary_keeps_the_answer_lead_and_the_prose_of_a_nested_short_answer(self):
        table = "| Case | Result |\n|---|---|\n| Default | `1024` bytes |\n\n"
        page = TEXT.replace("## Short Answer", "## Answer").replace(
            "## How It Works", "### Short answer\n\n" + table + "## How It Works")
        _result, record, _run_dir = self.parse(page, detail="summary")
        entries = {entry["section"]: entry for entry in record["coverage"]["sections"]}
        conclusions = record["conclusions"]
        self.assertEqual(conclusions["source"], "answer_lead")
        self.assertEqual((entries["answer"]["decision"], entries["answer"]["keep"]),
                         ("summarize", [sentence["id"] for sentence in conclusions["sentences"]]))
        # A summary that is only a table is left out; the conclusions are narrated instead.
        self.assertEqual(entries["short-answer"]["decision"], "omit")

        prose = page.replace("### Short answer\n\n", "### Short answer\n\nReaders see at most 1023 bytes.\n\n")
        _result, record, _run_dir = self.parse(prose, detail="summary")
        entry = {entry["section"]: entry for entry in record["coverage"]["sections"]}["short-answer"]
        self.assertEqual((entry["decision"], entry["keep"]), ("summarize", ["short-answer.1.s1"]))
        self.assertEqual(entry["reason"], "The document's own summary, without its tables and code.")

    def test_full_detail_narrates_every_section_without_a_length_target(self):
        page = self.long_text().replace("## Question\n\n", "## Question\n\n" + "A long prompt goes on. " * 60)
        _result, record, run_dir = self.parse(page, detail="full")
        coverage = record["coverage"]
        self.assertEqual((coverage["detail"], coverage["target_minutes"], coverage["long_document"]),
                         ("full", None, False))
        for entry in coverage["sections"]:
            expected = {"navigation": "exclude", "reference": "exclude", "measurement": "omit"}.get(entry["role"],
                                                                                                    "explain")
            self.assertEqual(entry["decision"], expected, entry["section"])
            self.assertNotIn("keep", entry)
        self.assertGreater(coverage["decisions"]["explain"], 20)
        self.assertEqual(coverage["planned_words"], coverage["full_words"])
        self.assertIn("full_detail", {issue["code"] for issue in record["issues"]})
        self.assertIn("minutes planned (no length target at 150 words per minute)",
                      (run_dir / "coverage.md").read_text(encoding="utf-8"))

    def test_unknown_level_of_detail_fails(self):
        with self.assertRaisesRegex(ValueError, "unknown level of detail 'short'"):
            self.parse(detail="short")

    def test_ids_of_unchanged_sections_are_stable_across_edits_elsewhere(self):
        _result, before, _run_dir = self.parse()
        edited = TEXT.replace("## How It Works\n\n", "## How It Works\n\nA new opening paragraph.\n\n")
        _result, after, _run_dir = self.parse(edited)
        short = [s for s in self.sentences(before) if s.startswith("short-answer")]
        self.assertEqual(short, [s for s in self.sentences(after) if s.startswith("short-answer")])
        self.assertEqual(self.blocks(after)["how-it-works.2"]["type"], "list")
        self.assertEqual([s["id"] for s in before["sections"]], [s["id"] for s in after["sections"]])

    def test_document_without_narratable_prose_needs_review(self):
        document = DOCUMENT_TEXT.split("# How Example")[0] + (
            "# Only Code (unverified)\n\n## Question\n\nFollow AGENTS.md.\n\n## Answer\n\n```sql\nSELECT 1;\n```\n\n"
            f"## Source References\n\n- [guc.c]({RAW}/src/backend/guc.c)\n")
        result, record, run_dir = self.parse(document)
        self.assertEqual((result["status"], record["status"]), ("needs_review", "needs_review"))
        self.assertIn("no_narration", {issue["code"] for issue in record["issues"] if issue["severity"] == "blocking"})
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["status"], "needs_review")

    def test_altered_snapshot_copy_fails_and_is_recorded(self):
        _result, _record, run_dir = self.parse()
        copy = run_dir / "inputs" / "wiki" / DOCUMENT
        copy.chmod(0o644)
        copy.write_text(TEXT + "\nInjected text.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "does not match its recorded SHA-256"):
            parse_document(self.workspace, run_dir)
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((manifest["status"], manifest["document"]["status"]), ("failed", "failed"))

    def test_sources_that_need_review_are_not_parsed(self):
        self.github.add(WIKI, "f" * 40, wiki_files(document=TEXT.replace("version: 18", "version: 17")),
                        refs=["master"])
        run_dir = self.workspace / "runs" / "request-x"
        run_dir.mkdir(parents=True)
        request = {"request_id": "request-x", "repository": WIKI, "document": {"path": DOCUMENT, "ref": "master"}}
        self.assertEqual(snapshot_sources(self.workspace, run_dir, request)["status"], "needs_review")
        with self.assertRaisesRegex(ValueError, "resolve source-report.md"):
            parse_document(self.workspace, run_dir)
        self.assertFalse((run_dir / "document.json").exists())

    def test_prepare_command_writes_the_coverage_map(self):
        self.github.add(WIKI, WIKI_COMMIT, wiki_files(document=TEXT), refs=["main"])
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
        self.assertIn("Coverage map:", stdout.getvalue())
        self.assertIn("Evidence packet:", stdout.getvalue())
        (run_dir,) = (self.workspace / "runs").iterdir()
        self.assertTrue((run_dir / "document.json").is_file())

        self.github.add(WIKI, "e" * 40, wiki_files(document=TEXT.split("## Short Answer")[0].replace(
            "In PostgreSQL 18, how is `example_size` used?", "") + f"## Source References\n\n- [g]({GUC})\n"),
            refs=["main"])
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(prepare(args, self.workspace), NEEDS_REVIEW)
        self.assertRegex(stderr.getvalue(), r"blocking issue\(s\) in .*coverage\.md")


class QuantityTests(unittest.TestCase):
    def test_units_codes_versions_dates_and_labels(self):
        numeric = "\ue004{}\ue005".format
        cases = {
            f"It defaults to {numeric('1024')} bytes, uses 8kB pages and 25% of 1,048,576 rows.": [
                ("1024 bytes", 1024, "bytes"), ("8kB", 8, "kB"), ("25%", 25, "%"), ("1,048,576 rows", 1048576, "rows")],
            f"The minimum is {numeric('-1')} and the ratio is 0.75.": [("-1", -1, None), ("0.75", 0.75, None)],
            "PostgreSQL 12 and 17 differ since 13; see rule 2, test 18, and commit 10b9ca3d on 2026-09-12.": [],
            "It took 12 ms on a 256 GB server in 2024.": [("12 ms", 12, "ms"), ("256 GB", 256, "GB")],
            "A B-tree on 12 B-tree indexes": [("12", 12, None)],
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual([(v["raw"], v["value"], v["unit"]) for v in _quantities(text)], expected)


class BlockTreeTests(unittest.TestCase):
    def test_block_tree_nests_blocks_and_trims_line_ranges(self):
        body = ("# Title\n\nPara `x`\nline two.\n\n- one\n\n  ```c\n  int x;\n  ```\n\n- two\n\n\n> quote\n\n"
                "## Next\n\n| a | b |\n|:-|-:|\n| 1 | [l](u) |\n")
        tree = block_tree(body)
        self.assertEqual([(h["text"], h["line"], h["parent"]) for h in tree["headings"]],
                         [("Title", 1, None), ("Next", 17, 0)])
        paragraph, items, quote, table = tree["blocks"]
        self.assertEqual((paragraph["lines"], paragraph["heading"]), ([3, 4], 0))
        self.assertEqual([run["line"] for run in paragraph["inline"]["runs"]], [3, 3, 3, 4])
        self.assertEqual(items["lines"], [6, 12])
        self.assertEqual(items["items"][0]["blocks"][1]["language"], "c")
        self.assertEqual(quote["type"], "blockquote")
        self.assertEqual((table["align"], table["heading"]), (["left", "right"], 1))
        self.assertEqual(table["rows"][0]["cells"][1]["links"], [{"href": "u", "image": False, "line": 21}])


def _walk(blocks):
    for block in blocks:
        yield block
        if block["type"] == "list":
            for item in block["items"]:
                yield item | {"type": "item"}
                yield from _walk(item["blocks"])
        elif block["type"] == "blockquote":
            yield from _walk(block["blocks"])


if __name__ == "__main__":
    unittest.main()
