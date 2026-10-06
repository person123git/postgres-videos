"""The harness workflow: prepare, the plan, storyboard, and review contracts, and the content gate.

A recorded harness (harness_fixture.py) supplies the files a model would write. The
tests exercise what pgvideo enforces in code: schema and ID checks, plan coverage and
budgets, claims and evidence on every factual sentence, diagram direction, a separate
review of every target, repair budgets, resume and replay without inference, and the
gate in front of every media stage. They include the two semantic mutations from the
proposal: a changed verb that lexical checks still call verified, and a reversed
diagram edge.
"""

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness_fixture import accept_content, authored, recorded_content, recorded_review, write
from pgvideo import cli
from pgvideo.narration import create_narration
from pgvideo.orchestration import (MAX_PLAN_IMPORTS, MAX_REPAIR_ROUNDS, MAX_SAME_BLOCKER, check_instructions,
                                   duration_check, instructions, require_content_gate, require_duration)
from pgvideo.planning import import_plan
from pgvideo.review import import_review
from pgvideo.script import create_script
from test_crosscheck import ENGLISH, GLOSSARY, postgres_snapshot
from test_script import PAGE
from test_sources import DOCUMENT, PIN, POSTGRES, PROJECT_ROOT, WIKI, WIKI_COMMIT, FakeGitHub, install_project_files, \
    wiki_files

ERASED = "`pg_stat_get_activity()` then uses `example_widget` to erase the slots."


class HarnessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="pgvideo-harness-", dir=PROJECT_ROOT / ".runtime" / "tmp")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve() / "project"
        self.workspace.mkdir()
        install_project_files(self.workspace)
        self.github = FakeGitHub()
        self.github.add(WIKI, WIKI_COMMIT, wiki_files(document=PAGE, glossary=GLOSSARY), refs=["main"])
        self.github.add(POSTGRES, PIN, postgres_snapshot())
        self.enterContext(patch("pgvideo.sources._http_get", side_effect=self.github))
        self.enterContext(patch("pgvideo.sources._github_contents",
                                side_effect=lambda path, ref: {"type": "file", "path": path}))
        self.enterContext(patch("pgvideo.glossary.english_words", return_value=ENGLISH))
        self.enterContext(patch("pgvideo.cli.project_root", return_value=self.workspace))
        self.enterContext(patch("pgvideo.cli.local_selection"))

    def command(self, *argv) -> tuple[int, dict | None, str]:
        """Run a harness command with --json; return its exit status, parsed result, and progress output."""
        args = cli.parser().parse_args([*argv, "--json"])
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = cli.COMMANDS[argv[0]](args, self.workspace)
        return status, json.loads(stdout.getvalue()) if stdout.getvalue().strip() else None, stderr.getvalue()

    def prepare(self, *options) -> tuple[dict, Path]:
        status, result, stderr = self.command("prepare", "--document", DOCUMENT, *options)
        self.assertEqual(status, 0, (result, stderr))
        return result, self.workspace / "runs" / result["request_id"]

    @staticmethod
    def load(run_dir: Path, name: str) -> dict:
        return json.loads((run_dir / name).read_text(encoding="utf-8"))

    def blocking(self, record: dict) -> set[str]:
        return {issue["code"] for issue in record["issues"] if issue["severity"] == "blocking"}

    def content(self, run_dir: Path) -> tuple[dict, dict]:
        """Accept the recorded plan and return it with a storyboard template bound to it."""
        plan, storyboard = recorded_content(self.workspace, run_dir)
        record = import_plan(self.workspace, run_dir, write(authored(self.workspace, run_dir, "plan.json"),
                                                            plan))
        self.assertEqual(record["status"], "passed", self.load(run_dir, "plan.json")["issues"])
        storyboard["plan_digest"] = record["digest"]
        return plan, storyboard

    def storyboard(self, run_dir: Path, storyboard: dict, **options) -> tuple[dict, dict]:
        path = write(authored(self.workspace, run_dir, "story.json"), storyboard)
        record = create_script(self.workspace, run_dir, storyboard=path, **options)
        return record, self.load(run_dir, "storyboard.json")

    def review(self, run_dir: Path, **options) -> dict:
        return import_review(self.workspace, run_dir, write(authored(self.workspace, run_dir, "review.json"),
                                                            recorded_review(self.workspace, run_dir, **options)))

    # Prepare -----------------------------------------------------------------------------------

    def test_prepare_stops_at_the_evidence_packet_and_names_the_next_step(self):
        result, run_dir = self.prepare("--detail", "summary", "--audience", "PostgreSQL administrators")
        self.assertEqual((result["stage"], result["status"]), ("evidence", "passed"))
        self.assertEqual(result["next_actions"][0]["phase"], "plan")
        self.assertEqual(self.load(run_dir, "last-result.json"), result)
        request = self.load(run_dir, "request.json")
        self.assertEqual(request["workflow"]["kind"], "harness")
        self.assertEqual(request["workflow"]["instructions"], instructions(self.workspace))
        self.assertEqual((request["settings"]["audience"], request["settings"]["target_minutes"]),
                         ("PostgreSQL administrators", 3.0))
        manifest = self.load(run_dir, "manifest.json")
        self.assertEqual(manifest["evidence"]["status"], "passed")
        self.assertFalse({"plan", "script", "content_review", "narration"} & set(manifest))
        orchestration = self.load(run_dir, "orchestration.json")
        self.assertEqual(orchestration["instructions"]["file"], "AGENTS.md")
        self.assertTrue(all(orchestration["prompts"].values()))

        # Extraction is separate from selection: every section is eligible, and the summary map is kept aside.
        document = self.load(run_dir, "document.json")
        self.assertEqual(document["coverage"]["mode"], "eligibility")
        self.assertEqual(document["static_coverage"]["detail"], "summary")
        packet = self.load(run_dir, "evidence-packet.json")
        eligible = {s["id"] for s in packet["sections"] if s["eligible"]}
        self.assertLessEqual({"question", "short-answer", "read-path", "details", "known-limitations"}, eligible)
        self.assertEqual(packet["digests"]["content"], manifest["evidence"]["digest"])
        excerpt = packet["evidence"]["excerpts"][0]
        self.assertTrue(excerpt["id"].startswith("pg:") and excerpt["text"] and len(excerpt["sha256"]) == 64)
        self.assertIn("guc:example_size", {fact["id"] for fact in packet["evidence"]["settings"]})
        read = next(s for s in packet["sections"] if s["id"] == "read-path")
        uses = next(s for b in read["blocks"] for s in b.get("sentences", []) if "example_widget" in s["text"])
        self.assertEqual(uses["lexical"]["status"], "verified")
        self.assertIn("does not establish", packet["lexical_notice"])

        # The same evidence gives the same digest in another request; request IDs and times are excluded.
        _again, other = self.prepare("--detail", "summary", "--audience", "PostgreSQL administrators")
        self.assertEqual(self.load(other, "manifest.json")["evidence"]["digest"], manifest["evidence"]["digest"])

        # There is no extractive fallback for a harness request.
        status, result, _stderr = self.command("script", "--request", run_dir.name)
        self.assertEqual(status, 1)
        self.assertIn("orchestrated by an LLM harness", result["message"])

    def test_request_constraints_are_validated(self):
        status, result, _stderr = self.command("prepare", "--document", DOCUMENT, "--detail", "full",
                                               "--target-minutes", "5")
        self.assertEqual(status, 1)
        self.assertIn("no duration target", result["message"])
        _result, run_dir = self.prepare("--detail", "full")
        self.assertIsNone(self.load(run_dir, "request.json")["settings"]["target_minutes"])

    def test_excerpt_reads_only_the_snapshot(self):
        _result, run_dir = self.prepare()
        packet = self.load(run_dir, "evidence-packet.json")
        path = packet["evidence"]["excerpts"][0]["path"]
        status, result, _stderr = self.command("excerpt", "--request", run_dir.name, "--path", path, "--lines", "1-3")
        self.assertEqual(status, 0)
        self.assertEqual(result["excerpt"]["id"], f"pg:{path}#L1-L3")
        status, result, _stderr = self.command("excerpt", "--request", run_dir.name, "--path", "src/absent.c",
                                               "--lines", "1-3")
        self.assertEqual(status, 1)
        self.assertIn("never substitutes", result["message"])

    def test_packet_is_served_in_bounded_pieces(self):
        _result, run_dir = self.prepare()
        packet = self.load(run_dir, "evidence-packet.json")

        def view(*options) -> dict:
            status, result, _stderr = self.command("packet", "--request", run_dir.name, *options)
            self.assertEqual((status, result["status"]), (0, "passed"), result)
            return result["packet"]

        # The index names every section without its blocks and carries what the plan copies.
        index = view()
        self.assertEqual([row["id"] for row in index["sections"]], [s["id"] for s in packet["sections"]])
        self.assertEqual([row["blocks"] for row in index["sections"]], [len(s["blocks"]) for s in packet["sections"]])
        self.assertEqual((index["digests"], index["request"], index["page"], index["pages"]),
                         (packet["digests"], packet["request"], 1, 1))

        # A section is returned unchanged, with the evidence its own units cite and nothing else.
        read = next(s for s in packet["sections"] if s["id"] == "read-path")
        section = view("--section", "read-path")
        self.assertEqual(section["blocks"], read["blocks"])
        cited = sorted(e["id"] for e in packet["evidence"]["excerpts"]
                       if any(unit.split(".")[0] == "read-path" for unit in e["cited_by"]))
        self.assertTrue(cited)
        self.assertEqual(section["section"]["evidence"], cited)

        # Evidence and glossary entries are fetched by ID or term, exactly as the packet holds them.
        fetched = view("--evidence", cited[0], "guc:example_size")["evidence"]
        self.assertEqual(fetched[0], next(e for e in packet["evidence"]["excerpts"] if e["id"] == cited[0]))
        self.assertEqual(fetched[1]["id"], "guc:example_size")
        self.assertEqual(view("--settings")["settings"], packet["evidence"]["settings"])
        entry = packet["glossary"]["entries"][0]
        listed = [item["entry"] for item in view("--glossary")["glossary"] if "entry" in item]
        self.assertEqual([e["id"] for e in listed], [e["id"] for e in packet["glossary"]["entries"]])
        self.assertNotIn("occurrences", listed[0])
        full = view("--glossary", entry["term"].upper())["glossary"][0]["entry"]
        self.assertEqual((full["definition"], full["occurrences"]), (entry["definition"], len(entry["occurrences"])))

        # Pages hold whole items in order, and together they are the whole list.
        with patch("pgvideo.packet.MAX_BYTES", 600):
            first = view("--section", "read-path")
            self.assertGreater(first["pages"], 1)
            blocks = [b for page in range(1, first["pages"] + 1)
                      for b in view("--section", "read-path", "--page", str(page))["blocks"]]
        self.assertEqual(blocks, read["blocks"])

        # An unknown section, evidence ID, term, or page fails; nothing is guessed.
        for options in (("--section", "absent"), ("--evidence", "pg:src/absent.c#L1-L3"), ("--glossary", "absent"),
                        ("--page", "9")):
            status, result, _stderr = self.command("packet", "--request", run_dir.name, *options)
            self.assertEqual((status, result["status"]), (1, "failed"), options)

    # Plan --------------------------------------------------------------------------------------

    def test_plan_contract(self):
        _result, run_dir = self.prepare()
        plan, _storyboard = recorded_content(self.workspace, run_dir)

        def imported(change):
            changed = copy.deepcopy(plan)
            change(changed)
            path = write(authored(self.workspace, run_dir, "plan.json"), changed)
            # Each case is a different plan, not a repair of the last one, so the repair limit is left out.
            record = import_plan(self.workspace, run_dir, path, limited=False)
            return record, self.load(run_dir, "plan.json")

        record, _plan = imported(lambda p: None)
        self.assertEqual(record["status"], "passed")
        self.assertEqual(self.load(run_dir, "manifest.json")["plan"]["authored"]["file"], "authored/plan.json")

        def contradicted(p):
            p["claims"][1]["assessment"].update(source_support="contradicted", justification="The source says no.")

        def unknown_evidence(p):
            p["claims"][1]["assessment"]["evidence"] = ["pg:src/absent.c#L1-L2", "missing-unit"]

        cases = {
            "unknown_source": lambda p: p["claims"][0]["sources"].append("no-such-sentence"),
            "claim_contradicted": contradicted,
            "unresolved_evidence": unknown_evidence,
            "constraint_changed": lambda p: p.update(audience="Kernel developers"),
            "infeasible_plan": lambda p: p.update(feasibility={"status": "infeasible", "note": "Caveats need 12 min."}),
            "over_budget": lambda p: p["outline"][0].update(budget_seconds=3000),
            "section_unaccounted": lambda p: p.update(
                claims=[c for c in p["claims"] if not any(s.startswith("details") for s in c["sources"])]),
            "essential_omitted": lambda p: p["omissions"].append({"section": "question", "reason": "Too long."}),
            "correction_not_applied": lambda p: [c.update(text=c["text"].replace("on by", "off by"))
                                                 for c in p["claims"] if "example_flag" in c["text"]],
        }
        for code, change in cases.items():
            with self.subTest(code=code):
                record, accepted = imported(change)
                self.assertEqual(record["status"], "needs_review")
                self.assertIn(code, self.blocking(accepted))
        caveat, accepted = imported(lambda p: p["omissions"].append({"section": "known-limitations",
                                                                      "reason": "Short video."}))
        self.assertIn("caveat_omitted", {i["code"] for i in accepted["issues"] if i["severity"] == "warning"})

        for change, message in (
                (lambda p: p.update(status="passed"), "does not match schemas/plan.schema.json"),
                (lambda p: p.update(evidence_digest="0" * 64), "made from other evidence"),
                (lambda p: p.update(request_id="another"), "is for request another")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                imported(change)
        self.assertEqual(self.load(run_dir, "manifest.json")["plan"]["status"], "failed")

    def test_the_question_is_selected_by_a_claim_and_never_omitted(self):
        _result, run_dir = self.prepare()
        plan, _storyboard = recorded_content(self.workspace, run_dir)
        asks = {c["id"] for c in plan["claims"] if any(s.startswith("question.") for s in c["sources"])}
        self.assertTrue(asks)

        def unselect(p):
            """Leave the outline's question item in place, with no claim that cites the question."""
            p["claims"] = [c for c in p["claims"] if c["id"] not in asks]
            for item in p["outline"]:
                item["claims"] = [c for c in item["claims"] if c not in asks]
            p["main_answer"]["claims"] = [c for c in p["main_answer"]["claims"] if c not in asks] or \
                [p["claims"][0]["id"]]
            p["required_caveats"] = [c for c in p["required_caveats"] if c["claim"] not in asks]

        def omit(p):
            p["omissions"].append({"section": "question", "reason": "Too long."})

        def reported(*changes) -> dict:
            changed = copy.deepcopy(plan)
            for change in changes:
                change(changed)
            import_plan(self.workspace, run_dir, write(authored(self.workspace, run_dir, "plan.json"), changed),
                        limited=False)
            blocking = [i for i in self.load(run_dir, "plan.json")["issues"]
                        if i["section"] == "question" and i["severity"] == "blocking"]
            self.assertEqual([i["code"] for i in blocking], ["essential_omitted"], blocking)
            return blocking[0]

        # Not omitted and not cited, or omitted, or both: one issue, whose action names the fix for that state.
        self.assertTrue(any(item["part"] == "question" for item in plan["outline"]))
        issue = reported(unselect)
        self.assertIn("No claim cites one of its units.", issue["message"])
        self.assertRegex(issue["action"], r"^Cite one of its unit IDs, such as `question\.1\.s1`, in the `sources`")
        self.assertIn("an outline item's `part` or title does not", issue["action"])
        self.assertNotIn("omissions", issue["action"])
        issue = reported(unselect, omit)
        self.assertIn("It is listed in `omissions`.", issue["message"])
        self.assertIn("such as `question.1.s1`", issue["action"])
        self.assertIn("and remove it from `omissions`", issue["action"])
        issue = reported(omit)
        self.assertEqual(issue["action"], "Remove it from `omissions`; a claim already cites it.")
        self.assertIn("Remove it from `omissions`", (run_dir / "plan-report.md").read_text(encoding="utf-8"))

    def test_a_plan_repair_that_does_not_converge_is_stopped(self):
        _result, run_dir = self.prepare()
        plan, _storyboard = recorded_content(self.workspace, run_dir)
        rid, folder = run_dir.name, authored(self.workspace, run_dir, "x").parent
        attempts = iter(range(1, 100))

        def attempt(change, *options) -> tuple[int, dict]:
            changed = copy.deepcopy(plan)
            change(changed)
            file = write(folder / f"plan.v{next(attempts)}.json", changed)
            status, result, _stderr = self.command("plan", "--request", rid, "--file", str(file), *options)
            return status, result

        def omit(p):
            p["omissions"].append({"section": "question", "reason": "Too long."})

        def over(p):
            p["outline"][0].update(budget_seconds=3000)

        def used() -> dict:
            return self.command("status", "--request", rid)[1]["repairs"]

        # Blocking issues that change from one import to the next do not stop a repair.
        for change in (omit, over, omit, over):
            status, result = attempt(change)
            self.assertEqual((status, result["next_actions"][0]["action"]), (3, "author"), result)
        self.assertEqual((used()["plan_imports"], used()["max_plan_imports"]), (4, MAX_PLAN_IMPORTS))

        # One blocking issue may survive two fixes. The import that reports it a third time ends the repair.
        for _fix in range(MAX_SAME_BLOCKER - 1):
            status, result = attempt(omit)
            self.assertEqual((status, result["next_actions"][0]["action"]), (3, "author"), result)
        status, result = attempt(omit)
        self.assertEqual((status, result["status"]), (3, "needs_review"))
        action = result["next_actions"][0]
        self.assertEqual(action["action"], "escalate")
        self.assertIn(f"the last {MAX_SAME_BLOCKER} plan imports report the same blocking issue: "
                      "essential_omitted (question)", action["reason"])
        self.assertIn("--human-revision", action["reason"])

        # A further import is refused and changes nothing, even one that would pass. Status says the same.
        before = (self.load(run_dir, "manifest.json"), used()["plan_imports"])
        status, result = attempt(lambda p: None)
        self.assertEqual((status, result["status"], result["issues"][0]["code"]), (1, "failed", "repair_stopped"))
        self.assertIn("not converging", result["message"])
        self.assertEqual(result["next_actions"][0]["action"], "escalate")
        self.assertEqual((self.load(run_dir, "manifest.json"), used()["plan_imports"]), before)
        self.assertEqual(self.command("status", "--request", rid)[1]["next_actions"][0]["action"], "escalate")

        # Checking saved content again is not a repair: it is neither refused nor counted.
        status, result, _stderr = self.command("resume", "--request", rid)
        self.assertEqual((status, result["status"]), (3, "needs_review"), result)
        self.assertEqual(used()["plan_imports"], before[1])

        # A person's revision is imported and recorded. A plan that passes clears the limit.
        status, result = attempt(omit, "--human-revision")
        self.assertEqual((status, result["next_actions"][0]["action"]), (3, "escalate"))
        status, result = attempt(lambda p: None, "--human-revision")
        self.assertEqual((status, result["status"]), (0, "passed"), result)
        record = self.load(run_dir, "orchestration.json")
        self.assertEqual(record["events"][-1].get("revised_by"), "human")
        self.assertEqual((record["repairs"]["plan_imports"], record.get("plan_stopped")), (0, None))

        # Imports that fail before the checks count too: the repair ends after MAX_PLAN_IMPORTS misses in a row.
        for _miss in range(MAX_PLAN_IMPORTS - 1):
            status, result = attempt(lambda p: p.update(status="passed"))
            self.assertEqual((status, result["status"], result["next_actions"][0]["action"]), (1, "failed", "author"))
        status, result = attempt(lambda p: p.update(status="passed"))
        self.assertEqual(result["next_actions"][0]["action"], "escalate")
        self.assertIn(f"{MAX_PLAN_IMPORTS} plan imports in a row have not passed", result["next_actions"][0]["reason"])
        status, result = attempt(lambda p: None)
        self.assertEqual((status, result["issues"][0]["code"]), (1, "repair_stopped"))

    def test_a_repair_reads_a_compact_result_and_patches_a_new_revision(self):
        _result, run_dir = self.prepare()
        plan, _storyboard = recorded_content(self.workspace, run_dir)
        rid, folder = run_dir.name, authored(self.workspace, run_dir, "x").parent

        # One mistake in every claim is one schema line, with the rule's own explanation.
        dotted = copy.deepcopy(plan)
        for claim in dotted["claims"]:
            claim["id"] = claim["id"].replace("c", "c.")
        status, result, _stderr = self.command("plan", "--request", rid, "--file",
                                               str(write(folder / "dotted.json", dotted)))
        self.assertEqual(status, 1)
        self.assertIn(f"claims/*/id ({len(plan['claims'])} places, first claims/0/id)", result["message"])
        self.assertIn("keep their dots", result["message"])

        # Unit IDs renamed to look like claim IDs, and no omissions: the result folds each code into one issue.
        broken = copy.deepcopy(plan)
        for claim in broken["claims"]:
            claim["sources"] = [source.replace(".", "_") for source in claim["sources"]]
        broken["omissions"] = []
        source = write(folder / "plan.v1.json", broken)
        before = source.read_bytes()
        status, result, _stderr = self.command("plan", "--request", rid, "--file", str(source))
        self.assertEqual((status, result["status"]), (3, "needs_review"))
        # The question and the summary are never omitted: each keeps its own issue, with a unit to cite.
        essential = {issue["section"]: issue["action"] for issue in result["issues"]
                     if issue["code"] == "essential_omitted"}
        self.assertEqual(set(essential), {"question", "short-answer"})
        self.assertIn("such as `question.1.s1`", essential["question"])
        codes = [issue["code"] for issue in result["issues"] if issue["code"] != "essential_omitted"]
        self.assertEqual(len(codes), len(set(codes)), codes)
        unknown = next(issue for issue in result["issues"] if issue["code"] == "unknown_source")
        renamed = sum(1 for c in plan["claims"] for s in c["sources"] if "." in s)
        self.assertEqual((unknown["count"], len(unknown["examples"])), (renamed, 3))
        self.assertLessEqual(set(unknown["claims"]), {claim["id"] for claim in plan["claims"]})
        self.assertRegex(unknown["action"], r"^Cite \S+\.\S+\. Only a claim's own `id` is hyphenated")
        self.assertIn("plan-report.md", unknown["message"])
        # The record keeps every issue.
        self.assertEqual(sum(1 for i in self.load(run_dir, "plan.json")["issues"] if i["code"] == "unknown_source"),
                         renamed)

        # The template omits what the plan leaves unaccounted; the question cannot be omitted.
        status, result, _stderr = self.command("packet", "--request", rid, "--omissions-template", "--plan",
                                               str(source))
        self.assertEqual(status, 0, result)
        template = result["packet"]
        packet = self.load(run_dir, "evidence-packet.json")
        eligible = {s["id"] for s in packet["sections"] if s["eligible"] and s["blocks"]}
        offered = {value["section"] for value in template["patch"][0]["values"]}
        self.assertEqual(offered | set(template["essential"]), eligible)
        self.assertIn("question", template["essential"])
        self.assertIn("known-limitations", template["caveats"])
        self.assertTrue(all(value["reason"] == "" for value in template["patch"][0]["values"]))
        status, result, _stderr = self.command("packet", "--request", rid, "--omissions-template", "--plan",
                                               str(write(folder / "good.json", plan)))
        self.assertEqual((result["packet"]["patch"], result["packet"]["essential"]), ([], []))

        def revise(operations, out: str, origin: Path = source) -> tuple[int, dict]:
            patch_file = write(folder / f"patch-{out}", operations)
            status, result, _stderr = self.command("revise", "--from", str(origin), "--patch", str(patch_file),
                                                   "--out", str(folder / out))
            return status, result

        # A few operations repair every claim; the source file is untouched and the revision imports.
        wanted = ["known-limitations", "details"]
        status, result = revise([
            {"op": "replace", "path": "claims[*].sources[*]", "find": "_", "with": "."},
            {"op": "add", "path": "omissions", "values": [{"section": s, "reason": ""} for s in wanted]},
            {"op": "set", "path": "omissions[reason=].reason", "value": "Left out of this video."},
        ], "plan.v2.json")
        self.assertEqual((status, result["status"]), (0, "passed"), result)
        self.assertEqual([change["matched"] for change in result["changes"]][1:], [1, len(wanted)])
        self.assertEqual(source.read_bytes(), before)
        revised = json.loads((folder / "plan.v2.json").read_text(encoding="utf-8"))
        self.assertEqual([c["sources"] for c in revised["claims"]], [c["sources"] for c in plan["claims"]])
        status, result, _stderr = self.command("plan", "--request", rid, "--file", str(folder / "plan.v2.json"))
        self.assertEqual((status, result["status"]), (0, "passed"), result)

        # Nothing is guessed or overwritten: an existing revision, a pgvideo-owned path, a path that matches
        # nothing, and a malformed operation all fail and write no file.
        one = [{"op": "set", "path": "claims[0].kind", "value": "fact"}]
        failures = (
            (one, "plan.v2.json", "already exists"),
            (one, f"../../runs/{rid}/plan.v9.json", "pgvideo owns runs/"),
            ([{"op": "remove", "path": "claims[id=absent]"}], "plan.v3.json", "matches nothing"),
            ([*one, {"op": "set", "path": "claims[*].assessment.absent.key", "value": 1}], "plan.v3.json",
             "matches nothing"),
            ([{"op": "rename", "path": "claims"}], "plan.v3.json", "needs an `op`"),
            ([{"op": "add", "path": "claims[0].id", "value": "x"}], "plan.v3.json", "is not a list"),
        )
        for operations, out, message in failures:
            with self.subTest(message=message, out=out):
                status, result = revise(operations, out)
                self.assertEqual((status, result["status"]), (1, "failed"))
                self.assertIn(message, result["message"])
        self.assertFalse((folder / "plan.v3.json").exists() or (run_dir / "plan.v9.json").exists())

        # Selectors: a position, a key's value containing dots, and a plain value in a list of strings.
        first = plan["claims"][0]
        status, result = revise([
            {"op": "remove", "path": f"claims[id={first['id']}].sources[={first['sources'][0]}]"},
            {"op": "set", "path": "outline[-1].purpose", "value": "Close."},
            {"op": "set", "path": "claims[1].note", "value": {"new": True}},
        ], "plan.v4.json", folder / "good.json")
        self.assertEqual(status, 0, result)
        selected = json.loads((folder / "plan.v4.json").read_text(encoding="utf-8"))
        self.assertEqual(selected["claims"][0]["sources"], first["sources"][1:])
        self.assertEqual((selected["outline"][-1]["purpose"], selected["claims"][1]["note"]), ("Close.", {"new": True}))

    # Storyboard --------------------------------------------------------------------------------

    def test_storyboard_contract(self):
        _result, run_dir = self.prepare()
        _plan, storyboard = self.content(run_dir)
        record, accepted = self.storyboard(run_dir, storyboard)
        self.assertEqual(record["status"], "passed", self.blocking(accepted))
        self.assertEqual((accepted["schema"], accepted["workflow"], accepted["semantic_review"]),
                         (2, "harness", "pending"))
        self.assertIn("lexical verified", (run_dir / "script.md").read_text(encoding="utf-8"))
        # Importing a storyboard never starts narration.
        self.assertNotIn("narration", self.load(run_dir, "manifest.json"))

        def item(board, text):
            return next(n for s in board["scenes"] for n in s["narration"] if text in n["text"])

        def paraphrase(board):
            sentence = item(board, "defaults to `1024` bytes")
            sentence.update(origin="paraphrase", text="It defaults to `4096` bytes and lives in `pgstat_example_size`.")

        def outside(board):
            board["scenes"][1]["narration"][0]["sources"] = ["open-questions.1.1.1.s1"]

        cases = {
            "missing_claims": lambda b: item(b, "defaults to `1024`").pop("claims"),
            "unknown_claim": lambda b: item(b, "defaults to `1024`").update(claims=["c999"]),
            "unresolved_evidence": lambda b: item(b, "defaults to `1024`").update(evidence=["guc:no_such_setting"]),
            "framing_with_claims": lambda b: b["scenes"][0]["narration"][0].update(claims=["c001"]),
            "unsupported_edit": paraphrase,
        }
        for code, change in cases.items():
            with self.subTest(code=code):
                changed = copy.deepcopy(storyboard)
                change(changed)
                record, accepted = self.storyboard(run_dir, changed)
                self.assertEqual(record["status"], "needs_review")
                self.assertIn(code, self.blocking(accepted))

        # A plan that drops a section leaves its scenes outside the plan.
        plan, storyboard = recorded_content(self.workspace, run_dir)
        dropped = {c["id"] for c in plan["claims"] if any(s.startswith("open-questions") for s in c["sources"])}
        plan["claims"] = [c for c in plan["claims"] if c["id"] not in dropped]
        for entry in plan["outline"]:
            entry["claims"] = [c for c in entry["claims"] if c not in dropped]
        plan["omissions"].append({"section": "open-questions", "reason": "Out of scope."})
        plan_record = import_plan(self.workspace, run_dir, write(authored(self.workspace, run_dir, "plan.json"), plan))
        storyboard["plan_digest"] = plan_record["digest"]
        record, accepted = self.storyboard(run_dir, storyboard)
        self.assertLessEqual({"not_in_plan", "unknown_claim"}, self.blocking(accepted))

        for change, message in ((lambda b: b.update(status="passed"), "storyboard.schema.json"),
                                (lambda b: b["scenes"][0]["narration"][0].update(check={"status": "unchanged"}),
                                 "storyboard.schema.json"),
                                (lambda b: b.update(plan_digest="0" * 64), "written from another plan")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                changed = copy.deepcopy(storyboard)
                change(changed)
                self.storyboard(run_dir, changed)

    # Semantic mutations and the gate -----------------------------------------------------------

    def test_a_changed_verb_passes_lexical_checks_but_not_the_content_gate(self):
        _result, run_dir = self.prepare()
        _plan, storyboard = self.content(run_dir)
        sentence = next(n for s in storyboard["scenes"] for n in s["narration"] if "to read the slots" in n["text"])
        sentence["text"] = ERASED
        record, accepted = self.storyboard(run_dir, storyboard)
        # The identifiers are all in the cited lines, so the lexical recheck still says verified.
        self.assertEqual(record["status"], "passed", self.blocking(accepted))
        mutated = next(n for s in accepted["scenes"] for n in s["narration"] if n["text"] == ERASED)
        self.assertEqual((mutated["check"]["status"], mutated["check"]["claim"]), ("rechecked", "verified"))
        manifest = self.load(run_dir, "manifest.json")
        with self.assertRaisesRegex(ValueError, "Content gate: the semantic content review has status 'None'"):
            require_content_gate(run_dir, manifest)

        target = f"narration:{mutated['id']}"
        review = self.review(run_dir, verdicts={target: {
            "verdict": "contradicted", "justification": "The function reads the slots; it does not erase them.",
            "issues": [{"code": "contradiction", "severity": "material", "message": "reads became erases"}]}})
        self.assertEqual(review["status"], "needs_review")
        report = (run_dir / "content-report.md").read_text(encoding="utf-8")
        self.assertIn(f"`{target}`: **contradicted**; lexical verified", report)
        manifest = self.load(run_dir, "manifest.json")
        with self.assertRaisesRegex(ValueError, "Content gate"):
            require_content_gate(run_dir, manifest)
        # A media command run directly is refused as well.
        with self.assertRaisesRegex(ValueError, "Content gate"):
            create_narration(self.workspace, run_dir)
        status, result, _stderr = self.command("build", "--request", run_dir.name)
        self.assertEqual(status, 1)
        self.assertIn("Content gate", result["message"])
        self.assertEqual(result["next_actions"][0]["phase"], "repair")

    def test_a_reversed_diagram_edge_is_rejected(self):
        _result, run_dir = self.prepare()
        _plan, storyboard = self.content(run_dir)
        scene = next(s for s in storyboard["scenes"] if s["screen"]["layout"] == "diagram")
        edge = scene["screen"]["diagram"]["edges"][0]
        edge["from"], edge["to"] = edge["to"], edge["from"]
        record, accepted = self.storyboard(run_dir, storyboard)
        self.assertEqual(record["status"], "needs_review")
        self.assertIn("diagram_direction", self.blocking(accepted))

        edge["from"], edge["to"] = edge["to"], edge["from"]
        # A claim from another sentence cannot justify the edge; an edge without claims fails the schema.
        question = next(s for s in storyboard["scenes"] if s["part"] == "question")
        edge["claims"] = question["narration"][0]["claims"]
        _record, accepted = self.storyboard(run_dir, storyboard)
        self.assertIn("diagram_unjustified", self.blocking(accepted))
        edge["claims"] = []
        with self.assertRaisesRegex(ValueError, "storyboard.schema.json"):
            self.storyboard(run_dir, storyboard)

    def test_review_contract_and_gate(self):
        _result, run_dir = self.prepare()
        _plan, storyboard = self.content(run_dir)
        self.storyboard(run_dir, storyboard)
        review = recorded_review(self.workspace, run_dir)

        def imported(change):
            changed = copy.deepcopy(review)
            change(changed)
            return import_review(self.workspace, run_dir, write(authored(self.workspace, run_dir, "review.json"),
                                                                changed))

        for change, message in (
                (lambda r: r["findings"].pop(), "leaves 1 target"),
                (lambda r: r["reviewer"].update(writer_context_shared=True), "does not count as its own review"),
                (lambda r: r.update(storyboard_digest="0" * 64), "reviews another storyboard"),
                (lambda r: r["findings"].append(dict(r["findings"][0])), "judges .* twice"),
                (lambda r: r.update(confidence=0.99), "review.schema.json")):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                imported(change)
        factual = next(f for f in review["findings"] if f["factual"])

        def insufficient(r):
            next(f for f in r["findings"] if f["target"] == factual["target"]).update(
                verdict="insufficient_evidence", evidence=[])

        def material(r):
            r["editorial"].append({"scene": "*", "code": "missing_caveat", "severity": "material",
                                   "message": "The restart requirement is dropped."})

        def unsupported(r):
            next(f for f in r["findings"] if f["target"] == factual["target"]).update(evidence=[])

        for change, code in ((insufficient, "insufficient_evidence"), (material, "editorial_missing_caveat"),
                             (unsupported, "unsupported_verdict")):
            with self.subTest(code=code):
                record = imported(change)
                self.assertEqual(record["status"], "needs_review")
                self.assertIn(code, self.blocking(self.load(run_dir, "content-review.json")))

        record = imported(lambda r: None)
        self.assertEqual(record["status"], "passed")
        require_content_gate(run_dir, self.load(run_dir, "manifest.json"))
        status, result, _stderr = self.command("status", "--request", run_dir.name)
        self.assertEqual(result["next_actions"][0]["command"], f"scripts/pgvideo build --request {run_dir.name}")
        self.assertEqual(len(result["review_targets"]), len(review["findings"]))
        # A storyboard imported after the review needs a review of its own.
        self.storyboard(run_dir, storyboard)
        with self.assertRaisesRegex(ValueError, "semantic content review has status 'None'"):
            require_content_gate(run_dir, self.load(run_dir, "manifest.json"))

    def test_repairs_after_a_failed_review_are_bounded(self):
        _result, run_dir = self.prepare()
        _plan, storyboard = self.content(run_dir)
        self.storyboard(run_dir, storyboard)
        target = recorded_review(self.workspace, run_dir)["findings"][1]["target"]
        failing = {target: {"issues": [{"code": "other", "severity": "material",
                                        "message": "Recorded material finding."}]}}
        for round_ in range(1, MAX_REPAIR_ROUNDS + 1):
            self.assertEqual(self.review(run_dir, verdicts=failing)["status"], "needs_review")
            record, _accepted = self.storyboard(run_dir, storyboard)
            self.assertEqual(record["status"], "passed")
            self.assertEqual(self.load(run_dir, "orchestration.json")["repairs"]["storyboard"], round_)
        self.assertEqual(self.review(run_dir, verdicts=failing)["status"], "needs_review")
        status, result, _stderr = self.command("status", "--request", run_dir.name)
        self.assertEqual(result["next_actions"][0]["action"], "escalate")
        with self.assertRaisesRegex(ValueError, "after 2 repair rounds"):
            self.storyboard(run_dir, storyboard)
        # The refused import changed nothing; a person's revision is accepted and recorded.
        self.assertEqual(self.load(run_dir, "manifest.json")["content_review"]["status"], "needs_review")
        record, _accepted = self.storyboard(run_dir, storyboard, revision="human")
        self.assertEqual(record["status"], "passed")
        events = self.load(run_dir, "orchestration.json")["events"]
        self.assertEqual(events[-1].get("revised_by"), "human")

    # Recovery ----------------------------------------------------------------------------------

    def test_resume_and_replay_revalidate_saved_content_without_inference(self):
        _result, first = self.prepare()
        results = accept_content(self.workspace, first)
        self.assertEqual(results["review"]["status"], "passed")
        digests = {stage: self.load(first, "manifest.json")[stage]["digest"] for stage in ("plan", "script")}

        status, result, stderr = self.command("resume", "--request", first.name)
        self.assertEqual(status, 0, (result, stderr))
        self.assertIn("plan passed, script passed, content_review passed", result["message"])
        manifest = self.load(first, "manifest.json")
        self.assertEqual({stage: manifest[stage]["digest"] for stage in digests}, digests)
        require_content_gate(first, manifest)

        result, second = self.prepare()
        self.assertEqual(result["replay_available"], [first.name])
        status, result, stderr = self.command("replay", "--request", second.name, "--from", first.name)
        self.assertEqual(status, 0, (result, stderr))
        manifest = self.load(second, "manifest.json")
        require_content_gate(second, manifest)
        self.assertEqual(manifest["script"]["digest"], digests["script"])
        replays = [e for e in self.load(second, "orchestration.json")["events"] if e["stage"] == "replay"]
        self.assertEqual([(e["status"], e["inference"]) for e in replays], [("started", "none"), ("passed", "none")])
        # The replayed request resumes from its own saved copies.
        status, result, _stderr = self.command("resume", "--request", second.name)
        self.assertEqual(status, 0, result)

    def test_a_new_instruction_version_reopens_the_content_stages(self):
        _result, run_dir = self.prepare()
        accept_content(self.workspace, run_dir)
        current_version = instructions(self.workspace)["version"]
        next_version = current_version + 1
        agents = self.workspace / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8") + "\nOne more rule.\n", encoding="utf-8")
        self.assertEqual(len(check_instructions(self.workspace, run_dir)), 1)
        self.assertIn("content_review", self.load(run_dir, "manifest.json"))
        agents.write_text(agents.read_text(encoding="utf-8").replace(
            f"<!-- instructions-version: {current_version} -->",
            f"<!-- instructions-version: {next_version} -->"), encoding="utf-8")
        messages = check_instructions(self.workspace, run_dir)
        self.assertIn("resume", messages[-1])
        manifest = self.load(run_dir, "manifest.json")
        self.assertFalse({"plan", "script", "content_review"} & set(manifest))
        history = self.load(run_dir, "orchestration.json")["instructions"]["history"]
        self.assertEqual([change["to"]["version"] for change in history], [current_version, next_version])
        status, result, _stderr = self.command("resume", "--request", run_dir.name)
        self.assertEqual(status, 0, result)
        require_content_gate(run_dir, self.load(run_dir, "manifest.json"))

    def test_measured_duration_is_checked_against_the_target(self):
        _result, run_dir = self.prepare("--detail", "summary", "--target-minutes", "2")
        self.assertEqual(duration_check(run_dir, 118)["status"], "passed")
        check = duration_check(run_dir, 150)
        self.assertEqual((check["status"], check["range_seconds"]), ("needs_review", [102.0, 138.0]))
        with self.assertRaisesRegex(ValueError, "--duration-rewrite"):
            require_duration(run_dir, {"narration": {"duration_check": check}})
        with self.assertRaisesRegex(ValueError, "no such result"):
            create_script(self.workspace, run_dir, storyboard=Path("x.json"), duration_rewrite=True)

    def test_an_older_request_is_not_gated(self):
        run_dir = self.workspace / "runs" / "older"
        run_dir.mkdir(parents=True)
        (run_dir / "request.json").write_text(json.dumps({"request_id": "older", "settings": {}}), encoding="utf-8")
        require_content_gate(run_dir, {})
        self.assertIsNone(duration_check(run_dir, 999))


if __name__ == "__main__":
    unittest.main()
