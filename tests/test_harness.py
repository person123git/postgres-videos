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
from pgvideo.orchestration import (MAX_REPAIR_ROUNDS, check_instructions, duration_check, require_content_gate,
                                   require_duration)
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
        self.github.add(WIKI, WIKI_COMMIT, wiki_files(document=PAGE, glossary=GLOSSARY), refs=["master"])
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
        self.assertEqual(request["workflow"]["instructions"]["version"], 2)
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

    # Plan --------------------------------------------------------------------------------------

    def test_plan_contract(self):
        _result, run_dir = self.prepare()
        plan, _storyboard = recorded_content(self.workspace, run_dir)

        def imported(change):
            changed = copy.deepcopy(plan)
            change(changed)
            path = write(authored(self.workspace, run_dir, "plan.json"), changed)
            record = import_plan(self.workspace, run_dir, path)
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
        agents = self.workspace / "AGENTS.md"
        agents.write_text(agents.read_text(encoding="utf-8") + "\nOne more rule.\n", encoding="utf-8")
        self.assertEqual(len(check_instructions(self.workspace, run_dir)), 1)
        self.assertIn("content_review", self.load(run_dir, "manifest.json"))
        agents.write_text(agents.read_text(encoding="utf-8").replace("instructions-version: 2",
                                                                     "instructions-version: 3"), encoding="utf-8")
        messages = check_instructions(self.workspace, run_dir)
        self.assertIn("resume", messages[-1])
        manifest = self.load(run_dir, "manifest.json")
        self.assertFalse({"plan", "script", "content_review"} & set(manifest))
        history = self.load(run_dir, "orchestration.json")["instructions"]["history"]
        self.assertEqual([change["to"]["version"] for change in history], [2, 3])
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
