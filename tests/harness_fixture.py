"""Recorded harness responses for deterministic tests.

A real harness writes the plan, storyboard, and review with a model. These tests
stand in for it with files derived from the extractive baseline of the same
request: every baseline sentence becomes a plan claim assessed as supported by its
own sources, the scenes become a version 2 storyboard, and the review judges every
target supported. Tests then mutate one of these files to exercise a gate. None of
this measures a model; it only exercises pgvideo's contracts and gates.
"""

import copy
import json
from pathlib import Path

from pgvideo.orchestration import request_status
from pgvideo.review import targets
from pgvideo.script import create_baseline

PRODUCER = {"harness": {"name": "recorded-test-harness", "version": "1"}, "model": "unavailable"}
DERIVED_SCREEN = {"image": ("path", "alt")}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")
    return path


def authored(root: Path, run_dir: Path, name: str) -> Path:
    """Where the recorded harness keeps a file it writes: in the project, outside runs/."""
    return root / "harness" / run_dir.name / name


def recorded_content(root: Path, run_dir: Path) -> tuple[dict, dict]:
    """Return a recorded plan and a storyboard template (the plan digest is filled in later)."""
    create_baseline(root, run_dir)
    baseline = _load(run_dir / "baseline/storyboard.json")
    packet = _load(run_dir / "evidence-packet.json")
    settings = _load(run_dir / "request.json")["settings"]
    occurrences = {entry["anchor"]: entry["occurrences"] for entry in packet["glossary"]["entries"]}
    claims, outline, scenes = [], [], []
    number = 0
    for scene in baseline["scenes"]:
        item_sources = {s for item in scene["narration"] for s in item["sources"]}
        extra = [s for s in scene["sources"] if s not in item_sources]
        scene_claims, narration = [], []
        for item in scene["narration"]:
            entry = {"text": item["text"], "origin": item["origin"]}
            if item["origin"] != "framing":
                number += 1
                claim_id = f"c{number:03d}"
                sources = list(item["sources"])
                if item["origin"] == "glossary":
                    sources = sources or [at for anchor in item["glossary"] for at in occurrences.get(anchor, [])][:1]
                sources += [s for s in extra if s not in sources]
                extra = []
                claims.append({"id": claim_id, "text": item["text"], "kind": "definition" if item["origin"] ==
                               "glossary" else "caveat" if scene["part"] == "caveat" else "fact",
                               "sources": sources, **({"glossary": item["glossary"]} if item["glossary"] else {}),
                               "assessment": {"source_support": "supported", "evidence": sources[:2],
                                              "justification": "Recorded: the sources state this sentence.",
                                              "glossary": "consistent" if item["glossary"] else "not_applicable"}})
                scene_claims.append(claim_id)
                entry.update(sources=item["sources"], claims=[claim_id], evidence=sources[:2])
                for key in ("glossary", "correction"):
                    if item.get(key):
                        entry[key] = item[key]
            if item["tts_source"] == "manual":
                entry.update(tts=item["tts"], tts_source="manual")
            narration.append(entry)
        if extra and scene["part"] not in ("opening", "credits"):
            number += 1
            claims.append({"id": f"c{number:03d}", "text": scene["title"], "kind": "example", "sources": extra,
                           "assessment": {"source_support": "supported", "evidence": extra[:1],
                                          "justification": "Recorded: shown verbatim.", "glossary": "not_applicable"}})
            scene_claims.append(f"c{number:03d}")
            if settings["detail"] == "full":
                narration.append({"text": scene["title"], "origin": "paraphrase", "claims": [f"c{number:03d}"],
                                  "sources": extra, "evidence": extra[:1]})
        screen = copy.deepcopy(scene["screen"])
        if screen.get("image"):
            screen["image"] = {"link": screen["image"]["link"]}
        for edge in (screen.get("diagram") or {}).get("edges", []):
            edge["claims"] = [n["claims"][0] for n in narration if edge["source"] in n.get("sources", [])][:1]
        if not screen.get("lines"):
            screen.pop("lines", None)
        scenes.append({"id": scene["id"], "part": scene["part"], "title": scene["title"], "screen": screen,
                       "visual": scene["visual"], "narration": narration, "sources": scene["sources"],
                       "glossary": scene["glossary"]})
        outline.append({"id": scene["id"], "part": scene["part"], "title": scene["title"][:120],
                        "purpose": f"Recorded outline for {scene['id']}.", "claims": scene_claims,
                        "budget_seconds": max(scene["estimated_seconds"], 1)})
    answer = next((item["claims"] for item in outline if item["part"] == "answer" and item["claims"]),
                  None) or [claims[0]["id"]]
    selected = set()
    sections = {section["id"]: section for section in packet["sections"]}
    units = {}
    for section in packet["sections"]:
        for block in section["blocks"]:
            units[block["id"]] = section["id"]
            for unit in block.get("sentences", []) + block.get("rows", []):
                units[unit["id"]] = section["id"]
    for claim in claims:
        for source in claim["sources"]:
            section = units.get(source, source if source in sections else None)
            while section:
                selected.add(section)
                section = sections[section]["parent"]
    omissions = [{"section": s["id"], "reason": "Recorded: the baseline leaves it out."}
                 for s in packet["sections"] if s["eligible"] and s["blocks"] and s["id"] not in selected]
    plan = {"schema": "pgvideo/plan/v1", "request_id": run_dir.name,
            "evidence_digest": packet["digests"]["content"], "producer": PRODUCER | {"prompt": "prompts/plan.md"},
            "audience": settings["audience"], "detail": settings["detail"],
            "target_minutes": settings["target_minutes"],
            "main_answer": {"text": "Recorded main answer.", "claims": answer},
            "learning_objectives": ["Recorded objective."], "claims": claims, "outline": outline,
            "required_caveats": [{"claim": c, "reason": "Recorded caveat."}
                                 for item in outline if item["part"] == "caveat" for c in item["claims"]],
            "omissions": omissions, "feasibility": {"status": "feasible"}}
    storyboard = {"schema": "pgvideo/storyboard/v2", "request_id": run_dir.name, "plan_digest": None,
                  "producer": PRODUCER | {"prompt": "prompts/draft.md"}, "scenes": scenes}
    return plan, storyboard


def recorded_review(root: Path, run_dir: Path, *, verdicts: dict | None = None) -> dict:
    """A review that judges every target supported by its scene's sources, except the given verdicts."""
    status = request_status(root, run_dir)
    storyboard = _load(run_dir / "storyboard.json")
    packet = _load(run_dir / "evidence-packet.json")
    plan = _load(run_dir / "plan.json")
    omitted = {item["section"] for item in plan["omissions"]}
    scenes = {scene["id"]: scene for scene in storyboard["scenes"]}
    narration = {n["id"]: n for scene in storyboard["scenes"] for n in scene["narration"]}
    findings = []
    for target, info in targets(storyboard).items():
        scene = scenes[info["scene"]]
        item = narration.get(target.split(":", 1)[1]) if info["kind"] in ("narration", "tts") else None
        factual = item["origin"] != "framing" if info["kind"] == "narration" else True
        evidence = (item or {}).get("sources") or scene["sources"]
        if factual and not evidence:
            factual = False
        finding = {"target": target, "factual": factual, "verdict": "supported" if factual else "not_factual",
                   "evidence": evidence[:2] if factual else [], "justification": "Recorded review.", "issues": []}
        finding.update((verdicts or {}).get(target, {}))
        findings.append(finding)
    return {"schema": "pgvideo/review/v1", "request_id": run_dir.name,
            **{key: status["digests"][key] for key in ("storyboard_digest", "plan_digest", "evidence_digest")},
            "reviewer": {"separation": "fresh_context", "writer_context_shared": False,
                         "writer_self_assessment_seen": False},
            "producer": PRODUCER | {"prompt": "prompts/review.md"},
            "findings": findings, "editorial": [],
            "coverage": [{"section": section["id"], "verdict": "allowed_omission" if section["id"] in omitted
                          else "complete", "justification": "Recorded source-to-video coverage check."}
                         for section in packet["sections"] if section["eligible"] and section["blocks"]],
            "summary": "Recorded review of every target."}


def accept_content(root: Path, run_dir: Path, *, plan_change=None, storyboard_change=None) -> dict:
    """Import recorded plan, storyboard, and review files through the ordinary commands' functions."""
    from pgvideo.planning import import_plan
    from pgvideo.review import import_review
    from pgvideo.script import create_script

    plan, storyboard = recorded_content(root, run_dir)
    if plan_change:
        plan_change(plan)
    results = {"plan": import_plan(root, run_dir, write(authored(root, run_dir, "plan.json"), plan))}
    if results["plan"]["status"] != "passed":
        return results
    storyboard["plan_digest"] = results["plan"]["digest"]
    if storyboard_change:
        storyboard_change(storyboard)
    results["script"] = create_script(root, run_dir, storyboard=write(authored(root, run_dir, "storyboard.json"),
                                                                      storyboard))
    if results["script"]["status"] != "passed":
        return results
    results["review"] = import_review(root, run_dir, write(authored(root, run_dir, "review.json"),
                                                           recorded_review(root, run_dir)))
    return results


def recorded_media_review(run_dir: Path) -> dict:
    """Recorded inspection declarations for gate tests, independent of audiovisual quality assessment."""
    manifest = _load(run_dir / "manifest.json")
    storyboard = _load(run_dir / "storyboard.json")
    return {"schema": "pgvideo/media-review/v1", "request_id": run_dir.name,
            "video_sha256": manifest["render"]["draft_sha256"], "storyboard_digest": manifest["script"]["digest"],
            "producer": PRODUCER | {"prompt": "prompts/media-review.md"},
            "scenes": [{"scene": s["id"], "visual": "passed", "listening": "passed", "captions": "passed",
                        "message": "Recorded inspection fixture."} for s in storyboard["scenes"]],
            "checks": {kind: {"verdict": "passed", "message": "Recorded inspection fixture."}
                       for kind in ("playback", "transitions", "pacing", "ending", "caption_sync")},
            "summary": "Recorded review for deterministic gate tests."}
