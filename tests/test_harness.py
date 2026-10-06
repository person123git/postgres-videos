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
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from harness_fixture import accept_content, authored, recorded_content, recorded_review, write
from pgvideo import cli
from pgvideo.evidence import Resolver
from pgvideo.narration import create_narration
from pgvideo.orchestration import (MAX_PLAN_IMPORTS, MAX_REPAIR_ROUNDS, MAX_SAME_BLOCKER, check_instructions,
                                   duration_check, instructions, require_content_gate, require_duration)
from pgvideo.planning import import_plan
from pgvideo.review import import_review
from pgvideo.media_review import import_media_review
from pgvideo.script import create_script
from test_crosscheck import ENGLISH, GLOSSARY, STATUS_PATH, postgres_snapshot
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

    def test_the_evidence_packet_is_read_as_a_file_not_through_a_command(self):
        result, run_dir = self.prepare()
        self.assertNotIn("packet", cli.COMMANDS)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            cli.parser().parse_args(["packet", "--request", run_dir.name])
        self.assertIn(f"runs/{run_dir.name}/evidence-packet.json", result["next_actions"][0]["reason"])
        # The file is indented and in reading order: the page's sections come before the glossary and the evidence.
        text = (run_dir / "evidence-packet.json").read_text(encoding="utf-8")
        self.assertLess(max(len(line) for line in text.splitlines()), 20_000)
        order = ("document", "request", "speech", "sections", "glossary", "evidence", "review_state", "digests")
        self.assertEqual(tuple(key for key in json.loads(text) if key in order), order)
        positions = [text.index(f'\n  "{key}": ') for key in order]
        self.assertEqual(positions, sorted(positions))

    def test_long_citations_and_excerpt_ranges_are_complete(self):
        snapshot = postgres_snapshot()
        lines = snapshot[STATUS_PATH].decode().splitlines()
        lines.extend(f"/* source line {number} */" for number in range(len(lines) + 1, 501))
        snapshot[STATUS_PATH] = "\n".join(lines).encode()
        self.github.add(POSTGRES, PIN, snapshot)
        self.github.add(WIKI, WIKI_COMMIT, wiki_files(document=PAGE.replace("#L1-L7", "#L1-L500"),
                                                    glossary=GLOSSARY), refs=["main"])
        _result, run_dir = self.prepare()
        packet = self.load(run_dir, "evidence-packet.json")
        excerpt = next(e for e in packet["evidence"]["excerpts"] if e["path"] == STATUS_PATH
                       and e["cited_lines"] == [1, 500])
        self.assertEqual(excerpt["lines"], [1, 500])
        self.assertEqual(excerpt["text"], "\n".join(lines))
        self.assertNotIn("truncated", excerpt)
        status, result, _stderr = self.command("excerpt", "--request", run_dir.name,
                                               "--path", STATUS_PATH, "--lines", "1-500")
        self.assertEqual((status, result["status"]), (0, "passed"), result)
        self.assertEqual(result["excerpt"]["text"], excerpt["text"])
        resolver = Resolver(self.workspace, run_dir)
        self.assertIsNone(resolver.problem(excerpt["id"]))
        for invalid in ("0-3", "2-1", "1-501"):
            with self.subTest(lines=invalid):
                status, result, _stderr = self.command("excerpt", "--request", run_dir.name,
                                                       "--path", STATUS_PATH, "--lines", invalid)
                self.assertEqual((status, result["status"]), (1, "failed"), result)
                start, end = invalid.split("-")
                self.assertIsNotNone(resolver.problem(f"pg:{STATUS_PATH}#L{start}-L{end}"))

        # Imports must accept these IDs too, rather than retaining a separate range cap.
        plan, _storyboard = recorded_content(self.workspace, run_dir)
        claim = next(c for c in plan["claims"] if "example_widget" in c["text"])
        claim["assessment"]["evidence"].append(excerpt["id"])
        record = import_plan(self.workspace, run_dir, write(authored(self.workspace, run_dir, "long-plan.json"), plan))
        self.assertEqual(record["status"], "passed", record["issues"])

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
        status, result, _stderr = self.command("omissions-template", "--request", rid, "--plan", str(source))
        self.assertEqual((status, result["stage"], result["status"]), (0, "omissions-template", "passed"), result)
        template = result["template"]
        packet = self.load(run_dir, "evidence-packet.json")
        eligible = {s["id"] for s in packet["sections"] if s["eligible"] and s["blocks"]}
        offered = {value["section"] for value in template["patch"][0]["values"]}
        self.assertEqual(offered | set(template["essential"]), eligible)
        self.assertIn("question", template["essential"])
        self.assertIn("known-limitations", template["caveats"])
        self.assertTrue(all(value["reason"] == "" for value in template["patch"][0]["values"]))
        status, result, _stderr = self.command("omissions-template", "--request", rid, "--plan",
                                               str(write(folder / "good.json", plan)))
        self.assertEqual((result["template"]["patch"], result["template"]["essential"]), ([], []))
        # Without a plan, every eligible section is offered; a missing plan file fails and nothing is guessed.
        status, result, _stderr = self.command("omissions-template", "--request", rid)
        self.assertEqual({value["section"] for value in result["template"]["patch"][0]["values"]}
                         | set(result["template"]["essential"]), eligible)
        status, result, _stderr = self.command("omissions-template", "--request", rid, "--plan",
                                               str(folder / "absent.json"))
        self.assertEqual((status, result["status"]), (1, "failed"))

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

    def review_input(self, run_dir: Path) -> tuple[dict, dict]:
        """Run `review-input`; return its index and the files it wrote, by name."""
        status, result, _stderr = self.command("review-input", "--request", run_dir.name)
        self.assertEqual(status, 0, result)
        index = result["review_input"]
        return index, {name: Path(info["path"]).read_text(encoding="utf-8") for name, info in index["files"].items()}

    def finished(self, run_dir: Path, template: dict) -> dict:
        """A reviewer's finished review: every pending value of the template judged as the recorded review does."""
        recorded = recorded_review(self.workspace, run_dir)
        by_target = {finding["target"]: finding for finding in recorded["findings"]}
        review = copy.deepcopy(template)
        review.update({key: recorded[key] for key in ("reviewer", "producer", "overall", "coverage", "summary")})
        review["findings"] = [by_target[f["target"]] if f["verdict"] == "pending" else f for f in review["findings"]]
        return review

    def test_review_input_hides_writer_assessments_and_expands_screen_targets(self):
        _result, run_dir = self.prepare()
        _plan, storyboard = self.content(run_dir)
        self.storyboard(run_dir, storyboard)
        index, files = self.review_input(run_dir)
        view = json.loads(files["plan"])
        self.assertTrue(view["claims"])
        for claim in view["claims"]:
            self.assertNotIn("assessment", claim)
            self.assertNotIn("lexical", claim)
        # pgvideo's own estimate and section map are not the writer's judgment, so the reviewer gets them.
        self.assertEqual(view["estimate"], self.load(run_dir, "plan.json")["estimate"])
        self.assertTrue(any(row["claims"] for row in view["sections"]))
        expected = self.command("status", "--request", run_dir.name)[1]["review_targets"]
        kinds = {t.split(":", 1)[0] for t in expected}
        self.assertLessEqual({"screen", "node", "table", "code", "term"}, kinds)
        self.assertTrue(all(f"screen:{s['id']}:0" in expected for s in storyboard["scenes"]))
        template = json.loads(files["template"])
        self.assertEqual([f["target"] for f in template["findings"]], expected)
        self.assertEqual((index["counts"]["targets"], index["counts"]["to_judge"]), (len(expected), len(expected)))
        self.assertEqual(index["digests"], {key: template[key] for key in index["digests"]})

    def test_review_input_shows_the_whole_video_and_page_for_reading(self):
        # A summary leaves sections out, so some of the page's units are cited by no scene.
        _result, run_dir = self.prepare("--detail", "summary")
        _plan, storyboard = self.content(run_dir)
        _record, accepted = self.storyboard(run_dir, storyboard)
        index, files = self.review_input(run_dir)
        video, template = files["video"], json.loads(files["template"])
        # Every target appears once, at the element it judges, and the scenes are in playback order.
        for finding in template["findings"]:
            self.assertEqual(video.count(f"`{finding['target']}`"), 1, finding["target"])
        headings = [video.index(f"### {number}. `{scene['id']}`: ")
                    for number, scene in enumerate(accepted["scenes"], 1)]
        self.assertEqual(headings, sorted(headings))
        for scene in accepted["scenes"]:
            for item in scene["narration"]:
                self.assertIn(item["text"], video)
                # What the reviewer reads first has no source lists and no lexical verdicts to lean on.
                self.assertNotIn(item["check"]["status"] + ",", video)
        self.assertIn("## Map", video)
        self.assertIn(self.load(run_dir, "plan.json")["main_answer"]["text"], video)
        # The page is readable in order, and a unit no scene cites is marked there and listed in the coverage file.
        packet = self.load(run_dir, "evidence-packet.json")
        cited = {source for scene in accepted["scenes"] for source in scene["sources"]}
        units = [(section["id"], block["id"], unit["id"], unit["text"])
                 for section in packet["sections"] if section["eligible"]
                 for block in section["blocks"] for unit in block.get("sentences", [])]
        self.assertTrue(units)
        uncited = [unit for section, block, unit, _text in units if not {section, block, unit} & cited]
        self.assertTrue(uncited)
        page = files["document"].splitlines()
        self.assertLess(max(len(line) for line in page), 2000)
        positions = []
        for _section, _block, unit, text in units:
            position = next(k for k, line in enumerate(page) if line.startswith(f"- `{unit}` "))
            positions.append(position)
            self.assertIn(text, page[position])
            self.assertEqual("[no scene cites this]" in page[position], unit in uncited, unit)
        self.assertEqual(positions, sorted(positions))
        # It names the evidence each section's units cite, and the sections the packet holds no content for.
        for excerpt in packet["evidence"]["excerpts"]:
            self.assertIn(f"`{excerpt['id']}`", files["document"])
        left_out = [s["id"] for s in packet["sections"] if not (s["eligible"] and s["blocks"])]
        self.assertTrue(left_out)
        for name in left_out:
            self.assertIn(f"- `{name}` ", files["document"])
        for unit in uncited:
            self.assertIn(f"- `{unit}` ", files["coverage"])
        self.assertEqual(index["counts"]["units"] - index["counts"]["units_cited"],
                         files["document"].count("[no scene cites this]"))
        # Warnings that pgvideo's checks address to the review reach the reviewer in full.
        issues = [issue for name in ("plan.json", "storyboard.json") for issue in self.load(run_dir, name)["issues"]
                  if issue["severity"] in ("warning", "note")]
        self.assertTrue(issues)
        for issue in issues:
            self.assertIn(" ".join(issue["message"].split()), files["checks"])
        # The files are also on disk for a reviewer that reads them in parts.
        self.assertEqual(self.load(run_dir, "review-input/index.json")["files"], index["files"])

    def test_a_template_with_pending_judgments_is_not_a_review(self):
        _result, run_dir = self.prepare()
        _plan, storyboard = self.content(run_dir)
        self.storyboard(run_dir, storyboard)
        _index, files = self.review_input(run_dir)
        template = json.loads(files["template"])
        self.assertTrue(all(f["verdict"] == "pending" for f in template["findings"]))
        path = authored(self.workspace, run_dir, "review.json")
        with self.assertRaisesRegex(ValueError, r"not a finished review.*finding\(s\).*whole-video check"):
            import_review(self.workspace, run_dir, write(path, template))
        # One judgment left pending is enough to refuse it, whichever part it is in.
        for change, message in (
                (lambda r: r["findings"][0].update(verdict="pending"), r"1 finding\(s\)"),
                (lambda r: r["coverage"][0].update(verdict="pending"), r"1 coverage judgment\(s\)"),
                (lambda r: r["overall"]["order"].update(verdict="pending"), "whole-video check.* order"),
                (lambda r: r["reviewer"].update(writer_context_shared=None), "`reviewer` block"),
                (lambda r: r.update(summary="pending"), "the `summary`")):
            review = self.finished(run_dir, template)
            change(review)
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                import_review(self.workspace, run_dir, write(path, review))
        # The reviewer fills the template with patches, including one judgment for many targets.
        patch_file = write(authored(self.workspace, run_dir, "fill.json"), [
            {"op": "set", "path": "findings[target~screen:*:0].justification", "value": "A scene heading."},
            {"op": "set", "path": "findings[verdict=pending].factual", "value": False},
            {"op": "set", "path": "findings[verdict=pending].verdict", "value": "not_factual"}])
        out = authored(self.workspace, run_dir, "review.v1.json")
        status, result, _stderr = self.command("revise", "--from",
                                               f"runs/{run_dir.name}/review-input/review-template.json",
                                               "--patch", str(patch_file), "--out", str(out))
        self.assertEqual((status, result["status"]), (0, "passed"), result)
        filled = json.loads(out.read_text(encoding="utf-8"))
        headings = [f for f in filled["findings"] if f["target"].endswith(":0") and f["target"].startswith("screen:")]
        self.assertEqual(result["changes"][0]["matched"], len(headings))
        self.assertTrue(all(f["justification"] == "A scene heading." for f in headings))
        self.assertFalse([f for f in filled["findings"] if f["verdict"] == "pending"])
        self.assertEqual(self.review(run_dir)["status"], "passed")
        record = import_review(self.workspace, run_dir, write(path, self.finished(run_dir, template)))
        self.assertEqual(record["status"], "passed")

    def test_the_whole_video_checks_gate_the_review(self):
        _result, run_dir = self.prepare()
        _plan, storyboard = self.content(run_dir)
        _record, accepted = self.storyboard(run_dir, storyboard)
        path = authored(self.workspace, run_dir, "review.json")
        review = recorded_review(self.workspace, run_dir)
        del review["overall"]
        with self.assertRaisesRegex(ValueError, "'overall' is a required property"):
            import_review(self.workspace, run_dir, write(path, review))
        review = recorded_review(self.workspace, run_dir)
        del review["overall"]["closing"]
        with self.assertRaisesRegex(ValueError, "'closing' is a required property"):
            import_review(self.workspace, run_dir, write(path, review))
        review = recorded_review(self.workspace, run_dir)
        review["overall"]["order"] = {"verdict": "failed", "message": "A term is used two scenes before it is defined."}
        first, second = accepted["scenes"][1]["id"], accepted["scenes"][2]["id"]
        review["editorial"].append({"scene": second, "related": [first], "code": "ordering", "severity": "minor",
                                    "message": "The definition comes after its first use."})
        record = import_review(self.workspace, run_dir, write(path, review))
        self.assertEqual(record["status"], "needs_review")
        kept = self.load(run_dir, "content-review.json")
        self.assertIn("overall_order", self.blocking(kept))
        self.assertEqual(kept["overall"]["order"]["verdict"], "failed")
        report = (run_dir / "content-report.md").read_text(encoding="utf-8")
        self.assertIn("## Whole-video review", report)
        self.assertIn("**failed** `order`", report)
        self.assertIn(f"({second}, {first})", report)
        review["editorial"][-1]["related"] = ["absent-scene"]
        with self.assertRaisesRegex(ValueError, "unknown scene absent-scene"):
            import_review(self.workspace, run_dir, write(path, review))

    def test_unchanged_findings_are_carried_to_the_review_of_a_revised_storyboard(self):
        _result, run_dir = self.prepare()
        _plan, storyboard = self.content(run_dir)
        self.storyboard(run_dir, storyboard)
        # Nothing is carried into a first review, and a failed review is kept like a passed one.
        index, files = self.review_input(run_dir)
        self.assertEqual((index["counts"]["carried"], index["carried_from_storyboard_digest"]), (0, None))
        self.assertNotIn("carried", json.loads(files["template"]))
        first = recorded_review(self.workspace, run_dir)
        path = authored(self.workspace, run_dir, "review.json")
        scene = next(s for s in storyboard["scenes"] if any(n["origin"] == "framing" for n in s["narration"]))
        position = next(k for k, n in enumerate(scene["narration"], 1) if n["origin"] == "framing")
        changed_target = f"narration:{scene['id']}.n{position}"
        next(f for f in first["findings"] if f["target"] == changed_target)["issues"] = [
            {"code": "other", "severity": "material", "message": "Recorded material finding."}]
        self.assertEqual(import_review(self.workspace, run_dir, write(path, first))["status"], "needs_review")
        earlier = first["storyboard_digest"]
        self.assertTrue((run_dir / "reviews" / f"{earlier}.json").is_file())

        scene["narration"][position - 1]["text"] = scene["narration"][position - 1]["text"].rstrip(".") + " today."
        self.assertEqual(self.storyboard(run_dir, storyboard)[0]["status"], "passed")
        index, files = self.review_input(run_dir)
        template = json.loads(files["template"])
        pending = [f["target"] for f in template["findings"] if f["verdict"] == "pending"]
        self.assertEqual(pending, [changed_target])
        self.assertEqual(template["carried"]["from_storyboard_digest"], earlier)
        self.assertEqual(set(template["carried"]["targets"]),
                         {f["target"] for f in template["findings"]} - set(pending))
        self.assertEqual((index["counts"]["carried"], index["counts"]["to_judge"]), (len(template["findings"]) - 1, 1))
        # The whole-video judgments are never carried, and the reading file marks what is.
        self.assertTrue(all(check["verdict"] == "pending" for check in template["overall"].values()))
        self.assertTrue(all(item["verdict"] == "pending" for item in template["coverage"]))
        self.assertNotIn(f"`{changed_target}` [carried]", files["video"])
        self.assertEqual(files["video"].count("[carried]"), len(template["carried"]["targets"]))

        review = self.finished(run_dir, template)
        record = import_review(self.workspace, run_dir, write(path, review))
        self.assertEqual((record["status"], record["counts"]["carried"]), ("passed", len(template["findings"]) - 1))
        self.assertIn("carried unchanged from the review of storyboard",
                      (run_dir / "content-report.md").read_text(encoding="utf-8"))
        require_content_gate(run_dir, self.load(run_dir, "manifest.json"))

        def refused(change, message):
            altered = copy.deepcopy(review)
            change(altered)
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                import_review(self.workspace, run_dir, write(path, altered))

        carried = review["carried"]["targets"][0]
        refused(lambda r: next(f for f in r["findings"] if f["target"] == carried).update(justification="Rewritten."),
                "carried finding .* differs from the review")
        refused(lambda r: r["carried"]["targets"].append(changed_target), "changed since the review of storyboard")
        refused(lambda r: r["carried"].update(from_storyboard_digest="0" * 64), "does not hold")
        refused(lambda r: r["carried"]["targets"].append("narration:absent.n1"), "not a target of the current")

        # A reviewer may judge a carried target again by taking it out of the list.
        again = copy.deepcopy(review)
        again["carried"]["targets"].remove(carried)
        next(f for f in again["findings"] if f["target"] == carried)["justification"] = "Judged again."
        self.assertEqual(import_review(self.workspace, run_dir, write(path, again))["counts"]["carried"],
                         len(template["findings"]) - 2)
        # Saved content is revalidated with its carried findings.
        status, result, _stderr = self.command("resume", "--request", run_dir.name)
        self.assertEqual((status, result["status"]), (0, "passed"), result)

    def test_verbatim_excerpts_still_require_semantic_review(self):
        _result, run_dir = self.prepare()
        _plan, storyboard = self.content(run_dir)
        self.storyboard(run_dir, storyboard)
        review = recorded_review(self.workspace, run_dir)
        excerpt = next(f for f in review["findings"] if f["target"].startswith("code:"))
        excerpt.update(factual=False, verdict="not_factual", evidence=[])
        record = import_review(self.workspace, run_dir,
                               write(authored(self.workspace, run_dir, "review.json"), review))
        self.assertEqual(record["status"], "needs_review")
        self.assertIn("inconsistent_finding", self.blocking(self.load(run_dir, "content-review.json")))

    def test_review_requires_source_to_video_coverage(self):
        _result, run_dir = self.prepare()
        _plan, storyboard = self.content(run_dir)
        self.storyboard(run_dir, storyboard)
        review = recorded_review(self.workspace, run_dir)
        review["coverage"].pop()
        path = authored(self.workspace, run_dir, "review.json")
        with self.assertRaisesRegex(ValueError, "leaves eligible sections unchecked"):
            import_review(self.workspace, run_dir, write(path, review))
        review = recorded_review(self.workspace, run_dir)
        review["coverage"][0].update(verdict="missing_content", justification="An example is absent from the plan.")
        record = import_review(self.workspace, run_dir, write(path, review))
        self.assertEqual(record["status"], "needs_review")
        self.assertIn("missing_content", self.blocking(self.load(run_dir, "content-review.json")))

    def test_full_detail_rejects_omissions_and_unnarrated_claims(self):
        _result, run_dir = self.prepare("--detail", "full")
        plan, storyboard = recorded_content(self.workspace, run_dir)
        plan["omissions"].append({"section": "details", "reason": "Too much detail."})
        record = import_plan(self.workspace, run_dir, write(authored(self.workspace, run_dir, "plan.json"), plan))
        self.assertEqual(record["status"], "needs_review")
        self.assertIn("full_section_omitted", self.blocking(self.load(run_dir, "plan.json")))
        plan, storyboard = self.content(run_dir)
        dropped = next(n for s in storyboard["scenes"] if s["part"] == "mechanism"
                       for n in s["narration"] if n.get("claims"))
        for s in storyboard["scenes"]:
            s["narration"] = [n for n in s["narration"] if n is not dropped]
        _record, accepted = self.storyboard(run_dir, storyboard)
        self.assertIn("claim_not_narrated", self.blocking(accepted))

    def prepared_media(self, run_dir: Path) -> dict:
        """Recorded renderer output for gate tests; no audiovisual quality claim is made by this fixture."""
        accept_content(self.workspace, run_dir)
        draft = run_dir / "render/draft.mp4"
        draft.parent.mkdir(parents=True, exist_ok=True)
        draft.write_bytes(b"recorded video bytes")
        staged = run_dir / "delivery"
        staged.mkdir()
        files = {}
        for name, data in (("video.mp4", draft.read_bytes()), ("captions.srt", b"recorded captions"),
                           ("captions.vtt", b"recorded web captions"),
                           ("orchestration.json", (run_dir / "orchestration.json").read_bytes())):
            (staged / name).write_bytes(data)
            if name.startswith("captions."):
                (run_dir / name).write_bytes(data)
            files[name] = hashlib.sha256(data).hexdigest()
        manifest = self.load(run_dir, "manifest.json")
        manifest["render"] = {"status": "passed", "draft_sha256": files["video.mp4"]}
        manifest["timing"] = {"status": "passed", "srt_sha256": files["captions.srt"],
                              "vtt_sha256": files["captions.vtt"]}
        manifest["narration"] = {"status": "passed", "duration_check": {"status": "passed"}}
        quality = {"status": "passed", "checks": {}, "delivery": {"directory": str(staged), "files": files}}
        body = (json.dumps(quality, indent=2) + "\n").encode()
        (run_dir / "quality-report.json").write_bytes(body)
        manifest["validation"] = {"status": "passed", "sha256": hashlib.sha256(body).hexdigest(),
                                  "record": "quality-report.json", "output": str(staged.relative_to(self.workspace)),
                                  "video": "video.mp4", "duration_seconds": 120}
        write(run_dir / "manifest.json", manifest)
        return {"schema": "pgvideo/media-review/v1", "request_id": run_dir.name,
                "video_sha256": files["video.mp4"], "storyboard_digest": manifest["script"]["digest"],
                "producer": {"harness": {"name": "recorded-test-reviewer"}, "prompt": "prompts/media-review.md"},
                "scenes": [{"scene": s["id"], "visual": "passed", "listening": "passed", "captions": "passed",
                            "message": "Recorded completed inspection."}
                           for s in self.load(run_dir, "storyboard.json")["scenes"]],
                "checks": {kind: {"verdict": "passed", "message": "Recorded completed inspection."}
                           for kind in ("playback", "transitions", "pacing", "ending", "caption_sync")},
                "summary": "Recorded inspection of the exact video."}

    def test_build_prepares_media_but_does_not_deliver_without_inspection(self):
        _result, run_dir = self.prepare()
        self.prepared_media(run_dir)
        with patch("pgvideo.cli._build", return_value=0):
            status, result, _stderr = self.command("build", "--request", run_dir.name)
        self.assertEqual((status, result["status"]), (0, "passed"))
        self.assertNotIn("delivery", result)
        self.assertEqual(result["next_actions"][0]["phase"], "media_review")
        self.assertFalse((self.workspace / "output" / run_dir.name).exists())
        self.command("note", "--request", run_dir.name, "--kind", "visual", "--text", "A supplementary note.")
        _code, current, _stderr = self.command("status", "--request", run_dir.name)
        self.assertEqual(current["next_actions"][0]["phase"], "media_review")

    def test_media_review_blocks_unavailable_listening_and_failed_playback(self):
        _result, run_dir = self.prepare()
        review = self.prepared_media(run_dir)
        path = authored(self.workspace, run_dir, "media-review.json")
        review["scenes"][0]["listening"] = "unavailable"
        review["checks"]["playback"]["verdict"] = "failed"
        record = import_media_review(self.workspace, run_dir, write(path, review))
        self.assertEqual(record["status"], "needs_review")
        self.assertLessEqual({"media_listening", "media_playback"},
                             self.blocking(self.load(run_dir, "media-review.json")))
        _code, result, _stderr = self.command("status", "--request", run_dir.name)
        self.assertEqual(result["next_actions"][0]["action"], "escalate")
        self.assertFalse((self.workspace / "output" / run_dir.name).exists())

    def test_media_review_rejects_missing_scenes_and_changed_video(self):
        _result, run_dir = self.prepare()
        review = self.prepared_media(run_dir)
        path = authored(self.workspace, run_dir, "media-review.json")
        incomplete = copy.deepcopy(review)
        incomplete["scenes"].pop()
        with self.assertRaisesRegex(ValueError, "leaves scenes unchecked"):
            import_media_review(self.workspace, run_dir, write(path, incomplete))
        (run_dir / "render/draft.mp4").write_bytes(b"different video")
        with self.assertRaisesRegex(ValueError, "video changed"):
            import_media_review(self.workspace, run_dir, write(path, review))

    def test_media_review_delivers_only_the_reviewed_package(self):
        _result, run_dir = self.prepare()
        review = self.prepared_media(run_dir)
        path = authored(self.workspace, run_dir, "media-review.json")
        status, result, _stderr = self.command("media-review", "--request", run_dir.name,
                                               "--file", str(write(path, review)))
        self.assertEqual((status, result["status"]), (0, "completed"), result)
        self.assertEqual(result["next_actions"][0]["action"], "deliver")
        destination = Path(result["delivery"]["directory"])
        self.assertEqual((destination / "video.mp4").read_bytes(), b"recorded video bytes")
        self.assertTrue((destination / "media-review.json").is_file())
        self.assertEqual(self.load(destination, "quality-report.json")["listening_review"], "passed: all scenes")
        self.assertEqual(self.load(destination, "manifest.json")["status"], "completed")

    def test_media_review_rejects_changed_prepared_captions(self):
        _result, run_dir = self.prepare()
        review = self.prepared_media(run_dir)
        (run_dir / "delivery/captions.srt").write_bytes(b"changed captions")
        with self.assertRaisesRegex(ValueError, "member changed"):
            import_media_review(self.workspace, run_dir, write(authored(self.workspace, run_dir, "media-review.json"), review))
        self.assertFalse((self.workspace / "output" / run_dir.name).exists())

    def test_media_review_rejects_inputs_changed_since_automated_validation(self):
        for name in ("plan.json", "captions.srt"):
            with self.subTest(name=name):
                _result, run_dir = self.prepare()
                review = self.prepared_media(run_dir)
                with (run_dir / name).open("ab") as file:
                    file.write(b" ")
                with self.assertRaisesRegex(ValueError, "does not match the SHA-256"):
                    import_media_review(self.workspace, run_dir,
                        write(authored(self.workspace, run_dir, "media-review.json"), review))
                self.assertFalse((self.workspace / "output" / run_dir.name).exists())

    def test_failed_media_content_can_be_repaired_with_the_existing_budget(self):
        _result, run_dir = self.prepare()
        review = self.prepared_media(run_dir)
        review["scenes"][0]["visual"] = "failed"
        import_media_review(self.workspace, run_dir,
                            write(authored(self.workspace, run_dir, "media-review.json"), review))
        _code, result, _stderr = self.command("status", "--request", run_dir.name)
        self.assertEqual((result["next_actions"][0]["action"], result["next_actions"][0]["phase"]),
                         ("author", "repair"))
        storyboard = self.load(run_dir, "authored/storyboard.json")
        self.storyboard(run_dir, storyboard)
        manifest = self.load(run_dir, "manifest.json")
        self.assertNotIn("media_review", manifest)
        self.assertNotIn("validation", manifest)
        self.assertEqual(self.load(run_dir, "orchestration.json")["repairs"]["storyboard"], 1)

    def test_media_review_rejects_a_stale_storyboard_and_duplicate_scene(self):
        _result, run_dir = self.prepare()
        review = self.prepared_media(run_dir)
        path = authored(self.workspace, run_dir, "media-review.json")
        changed = copy.deepcopy(review)
        changed["storyboard_digest"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "another storyboard"):
            import_media_review(self.workspace, run_dir, write(path, changed))
        review["scenes"].append(dict(review["scenes"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate scene"):
            import_media_review(self.workspace, run_dir, write(path, review))

    def test_duration_recovery_distinguishes_short_and_long_videos(self):
        _result, run_dir = self.prepare()
        accept_content(self.workspace, run_dir)
        for seconds, direction, instruction in ((1, "short", "Expand using unused allowed source content"),
                                                 (10000, "long", "Shorten optional detail")):
            check = duration_check(run_dir, seconds)
            self.assertEqual(check["direction"], direction)
            manifest = self.load(run_dir, "manifest.json")
            manifest["narration"] = {"status": "passed", "duration_check": check}
            write(run_dir / "manifest.json", manifest)
            _code, result, _stderr = self.command("status", "--request", run_dir.name)
            self.assertIn(instruction, result["next_actions"][0]["reason"])

    def test_duration_rewrite_survives_a_required_plan_revision(self):
        _result, run_dir = self.prepare()
        accept_content(self.workspace, run_dir)
        manifest = self.load(run_dir, "manifest.json")
        manifest["narration"] = {"status": "passed", "duration_check": duration_check(run_dir, 1)}
        write(run_dir / "manifest.json", manifest)
        plan = self.load(run_dir, "authored/plan.json")
        plan["outline"][0]["budget_seconds"] += 1
        record = import_plan(self.workspace, run_dir, write(authored(self.workspace, run_dir, "plan.json"), plan))
        self.assertEqual(record["status"], "passed")
        self.assertNotIn("narration", self.load(run_dir, "manifest.json"))
        _code, result, _stderr = self.command("status", "--request", run_dir.name)
        self.assertIn("--duration-rewrite", result["next_actions"][0]["command"])
        storyboard = self.load(run_dir, "authored/storyboard.json")
        storyboard["plan_digest"] = record["digest"]
        record, _accepted = self.storyboard(run_dir, storyboard, duration_rewrite=True)
        self.assertEqual(record["status"], "passed")
        self.assertEqual(self.load(run_dir, "orchestration.json")["repairs"]["duration"], 1)

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
