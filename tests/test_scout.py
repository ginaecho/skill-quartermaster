import json
import sys
from pathlib import Path

import pytest

from qm import scout
from qm.cli import main

from .helpers import make_skill


def make_suite(path):
    path.write_text(
        json.dumps(
            {
                "id": "reviewing",
                "version": "2026-08-25",
                "tasks": [
                    {
                        "id": "find-bug",
                        "prompt": "Review this change for bugs.",
                        "rubric": "Find the seeded correctness bug.",
                        "should_invoke": True,
                        "tags": ["code-review"],
                    },
                    {
                        "id": "write-poem",
                        "prompt": "Write a short poem.",
                        "rubric": "Do not invoke code review.",
                        "should_invoke": False,
                        "tags": ["control"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def make_plan(tmp_path, *, current=True):
    candidate_path = make_skill(
        tmp_path / "skills",
        "candidate-review",
        "Reviews code when a correctness review is requested",
        extra=(
            "license: MIT\n"
            "scout-author: candidate-owner\n"
            "scout-non-goals: prose editing\n"
            "scout-prerequisites: git\n"
            "compatibility: generic agents\n"
            "scout-outputs: review findings"
        ),
    )
    current_path = make_skill(
        tmp_path / "skills",
        "current-review",
        "Current code review workflow",
    )
    suite = scout.load_suite(make_suite(tmp_path / "suite.json"))
    candidate = scout.snapshot_candidate(candidate_path, source="https://example/candidate", version="abc123")
    current_snapshot = scout.snapshot_candidate(current_path, source="https://example/current", version="v1")
    return scout.build_plan(
        candidate,
        suite,
        current_skill=current_snapshot if current else None,
        repetitions=2,
        seed=11,
        created_at=100.0,
    )


def successful_trials(plan):
    out = []
    for job in plan.jobs:
        if job.condition == scout.CANDIDATE_SKILL:
            quality = 0.9
            success = True
            invoked = job.should_invoke
            tokens = 120
        elif job.condition == scout.CURRENT_SKILL:
            quality = 0.6
            success = True
            invoked = job.should_invoke
            tokens = 100
        else:
            quality = 0.4
            success = job.should_invoke is False
            invoked = False
            tokens = 80
        out.append(
            scout.TrialResult(
                plan_id=plan.plan_id,
                job_id=job.job_id,
                success=success,
                quality=quality,
                invoked=invoked,
                latency_ms=float(tokens),
                tokens=tokens,
                cost=tokens / 10000,
                output=f"output for {job.job_id}",
            )
        )
    return tuple(out)


def test_snapshot_is_content_addressed_and_records_manifest(tmp_path):
    skill = make_skill(tmp_path, "alpha", "Alpha review skill")
    first = scout.snapshot_candidate(skill, source="org/repo", version="latest")
    skill.write_text(skill.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8")
    second = scout.snapshot_candidate(skill, source="org/repo", version="latest")

    assert first.skill_id == second.skill_id
    assert first.content_sha256 != second.content_sha256
    assert "purpose_and_triggers" in first.manifest
    assert first.manifest_warnings


def test_suite_requires_positive_and_negative_controls(tmp_path):
    suite_path = make_suite(tmp_path / "suite.json")
    data = json.loads(suite_path.read_text(encoding="utf-8"))
    data["tasks"] = data["tasks"][:1]
    suite_path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(scout.ScoutError, match="positive and negative"):
        scout.load_suite(suite_path)


def test_plan_is_reproducible_randomized_and_paired(tmp_path):
    first = make_plan(tmp_path)
    second = scout.build_plan(
        first.candidate,
        first.suite,
        current_skill=first.current_skill,
        repetitions=2,
        seed=11,
        created_at=200.0,
    )

    assert first.plan_id == second.plan_id
    assert [job.job_id for job in first.jobs] == [job.job_id for job in second.jobs]
    assert len(first.jobs) == 2 * 2 * 5
    assert {job.condition for job in first.jobs} == set(scout.CONDITIONS)
    assert {job.invocation_mode for job in first.jobs} == set(scout.INVOCATION_MODES)
    assert {job.blind_label for job in first.jobs} == {"A", "B", "C", "D", "E"}


def test_evidence_compares_candidate_to_both_baselines_and_blinds_packet(tmp_path):
    plan = make_plan(tmp_path)
    evidence = scout.build_evidence(plan, successful_trials(plan), created_at=200.0)

    assert evidence.automated_recommendation == "send-to-review"
    assert evidence.ranking_score > 0.7
    assert {item.baseline for item in evidence.comparisons} == {
        scout.NO_SKILL,
        scout.CURRENT_SKILL,
    }
    assert all(item.quality_delta > 0 for item in evidence.comparisons)
    packet = evidence.review_packet()
    assert "blind_labels" not in packet
    assert "trials" not in packet
    assert {row["condition"] for row in packet["blinded_outputs"]} == {"A", "B", "C", "D", "E"}
    packet_text = json.dumps(packet)
    assert not any(condition in packet_text for condition in scout.CONDITIONS)
    assert plan.candidate.name not in packet_text
    assert plan.current_skill.name not in packet_text


def test_evidence_rejects_incomplete_or_duplicated_trials(tmp_path):
    plan = make_plan(tmp_path)
    trials = successful_trials(plan)

    with pytest.raises(scout.ScoutError, match="does not match"):
        scout.build_evidence(plan, trials[:-1])
    with pytest.raises(scout.ScoutError, match="duplicates=1"):
        scout.build_evidence(plan, trials + (trials[0],))


def test_safety_flags_prevent_automated_advancement(tmp_path):
    plan = make_plan(tmp_path)
    trials = list(successful_trials(plan))
    candidate_index = next(
        index
        for index, trial in enumerate(trials)
        if next(job for job in plan.jobs if job.job_id == trial.job_id).condition
        == scout.CANDIDATE_SKILL
    )
    original = trials[candidate_index]
    trials[candidate_index] = scout.TrialResult(
        **{**original.as_dict(), "safety_flags": ("secret-exposure",)}
    )

    evidence = scout.build_evidence(plan, trials)
    assert evidence.automated_recommendation == "do-not-advance"
    assert "safety flag" in evidence.recommendation_reasons[0]


def test_review_requires_three_independent_non_author_votes_and_honors_veto():
    evidence_id = "evidence-1"
    votes = [
        scout.ReviewVote(evidence_id, "one", "accept", "Strong evidence."),
        scout.ReviewVote(evidence_id, "two", "accept", "Useful and bounded."),
        scout.ReviewVote(evidence_id, "three", "revise", "Clarify limitations."),
    ]
    assert scout.decide_review(votes, evidence_id=evidence_id, author="author").status == "approved"
    assert scout.decide_review(votes[:2], evidence_id=evidence_id).status == "pending"

    vetoed = votes[:2] + [
        scout.ReviewVote(evidence_id, "three", "reject", "Unsafe permission.", safety_veto=True)
    ]
    assert scout.decide_review(vetoed, evidence_id=evidence_id).status == "blocked"
    with pytest.raises(scout.ScoutError, match="author"):
        scout.decide_review(votes, evidence_id=evidence_id, author="one")
    with pytest.raises(scout.ScoutError, match="evidence"):
        scout.decide_review(
            [scout.ReviewVote("other", "one", "accept", "Wrong pack.")],
            evidence_id=evidence_id,
        )


def test_lifecycle_recommendations_are_non_destructive():
    merged = scout.recommend_lifecycle(
        evidence_age_days=30,
        usage_count=5,
        dominated_by="better",
        semantic_overlap=0.9,
        quality_delta=0.01,
    )
    archived = scout.recommend_lifecycle(
        evidence_age_days=200,
        usage_count=0,
        dominated_by="better",
        semantic_overlap=0.7,
        quality_delta=-0.1,
    )

    assert merged.action == "merge"
    assert merged.superseded_by == "better"
    assert archived.action == "archive"
    assert scout.freshness_weight(90) == pytest.approx(0.5)


def test_json_runner_adapter_executes_every_job(tmp_path):
    plan = make_plan(tmp_path, current=False)
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import json, sys\n"
        "request = json.load(sys.stdin)\n"
        "job = request['job']\n"
        "print(json.dumps({'success': True, 'quality': 0.75, "
        "'invoked': job['should_invoke'], 'tokens': 10, 'cost': 0.01, "
        "'output': job['blind_label']}))\n",
        encoding="utf-8",
    )

    results = scout.run_plan(plan, [sys.executable, str(runner)], timeout_seconds=10)
    assert len(results) == len(plan.jobs)
    assert all(not result.error for result in results)
    assert all(result.quality == 0.75 for result in results)


def test_runner_rejects_changed_candidate_and_records_malformed_output(tmp_path):
    plan = make_plan(tmp_path, current=False)
    candidate_file = Path(plan.candidate.path) / "SKILL.md"
    with candidate_file.open("a", encoding="utf-8") as handle:
        handle.write("\nchanged after planning\n")
    with pytest.raises(scout.ScoutError, match="changed after planning"):
        scout.run_plan(plan, [sys.executable, "-c", "print('{}')"])

    fresh = make_plan(tmp_path / "fresh", current=False)
    runner = tmp_path / "bad-runner.py"
    runner.write_text("print('{\"quality\":\"not-a-number\"}')\n", encoding="utf-8")
    results = scout.run_plan(fresh, [sys.executable, str(runner)])
    assert len(results) == len(fresh.jobs)
    assert all("invalid runner response" in result.error for result in results)

    runner.write_text(
        "print('{\"success\":\"false\",\"invoked\":\"false\",\"quality\":1}')\n",
        encoding="utf-8",
    )
    results = scout.run_plan(fresh, [sys.executable, str(runner)])
    assert all("must be boolean" in result.error for result in results)

    results = scout.run_plan(fresh, [str(tmp_path / "missing-runner")])
    assert len(results) == len(fresh.jobs)
    assert all("could not start" in result.error for result in results)


def test_plan_loader_rejects_tampering(tmp_path):
    plan = make_plan(tmp_path)
    data = plan.as_dict()
    data["seed"] = 999

    with pytest.raises(scout.ScoutError, match="identity"):
        scout.plan_from_dict(data)

    data = plan.as_dict()
    data["jobs"][0]["prompt"] = "tampered"
    with pytest.raises(scout.ScoutError, match="jobs"):
        scout.plan_from_dict(data)


def test_trials_and_evidence_are_bound_to_their_artifacts(tmp_path):
    plan = make_plan(tmp_path)
    trials = successful_trials(plan)
    wrong_plan_trials = tuple(
        scout.TrialResult(**{**trial.as_dict(), "plan_id": "other-plan"})
        for trial in trials
    )
    with pytest.raises(scout.ScoutError, match="reference the plan"):
        scout.build_evidence(plan, wrong_plan_trials)

    evidence = scout.build_evidence(plan, trials)
    raw = evidence.as_dict()
    scout.verify_evidence_dict(raw)
    raw["candidate"]["name"] = "tampered"
    with pytest.raises(scout.ScoutError, match="identity"):
        scout.verify_evidence_dict(raw)

    raw = evidence.as_dict()
    raw["created_at"] += 1
    with pytest.raises(scout.ScoutError, match="identity"):
        scout.verify_evidence_dict(raw)


def test_scout_cli_plan_report_and_review(tmp_path, capsys):
    plan = make_plan(tmp_path)
    plan_path = tmp_path / "plan.json"
    trial_path = tmp_path / "trials.jsonl"
    evidence_path = tmp_path / "evidence.json"
    review_path = tmp_path / "packet.json"
    votes_path = tmp_path / "votes.json"
    decision_path = tmp_path / "decision.json"
    scout.write_json(plan_path, plan.as_dict())
    scout.write_trials(trial_path, successful_trials(plan))

    assert main([
        "scout", "report", str(plan_path), str(trial_path),
        "--out", str(evidence_path), "--review-out", str(review_path),
    ]) == 0
    evidence_id = json.loads(evidence_path.read_text(encoding="utf-8"))["evidence_id"]
    votes_path.write_text(
        json.dumps(
            [
                {
                    "evidence_id": evidence_id,
                    "reviewer": "a",
                    "decision": "accept",
                    "rationale": "Good.",
                },
                {
                    "evidence_id": evidence_id,
                    "reviewer": "b",
                    "decision": "accept",
                    "rationale": "Useful.",
                },
                {
                    "evidence_id": evidence_id,
                    "reviewer": "c",
                    "decision": "revise",
                    "rationale": "Document limits.",
                },
            ]
        ),
        encoding="utf-8",
    )
    assert main([
        "scout", "review", str(evidence_path), str(votes_path),
        "--author", "owner", "--out", str(decision_path),
    ]) == 0

    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision["decision"]["status"] == "approved"
    assert "Review decision: approved" in capsys.readouterr().out


def test_scout_cli_run_preserves_options_before_runner(tmp_path):
    plan = make_plan(tmp_path, current=False)
    plan_path = tmp_path / "plan.json"
    output_path = tmp_path / "custom-trials.jsonl"
    runner = tmp_path / "runner.py"
    scout.write_json(plan_path, plan.as_dict())
    runner.write_text(
        "import json, sys\n"
        "request = json.load(sys.stdin)\n"
        "print(json.dumps({'success': True, 'quality': 0.5, "
        "'invoked': request['job']['should_invoke'], 'output': 'ok'}))\n",
        encoding="utf-8",
    )

    assert main([
        "scout", "run", str(plan_path),
        "--out", str(output_path),
        "--runner", sys.executable,
        "--runner-arg", str(runner),
    ]) == 0
    assert len(output_path.read_text(encoding="utf-8").splitlines()) == len(plan.jobs)


def test_merge_trials_replaces_only_failed_jobs(tmp_path):
    plan = make_plan(tmp_path, current=False)
    trials = list(successful_trials(plan))
    failed = scout.TrialResult(
        **{
            **trials[0].as_dict(),
            "success": False,
            "quality": 0.0,
            "error": "temporary",
        }
    )
    replacement = scout.TrialResult(
        **{
            **trials[0].as_dict(),
            "output": "retried",
        }
    )

    merged = scout.merge_trials(plan, [failed] + trials[1:], [replacement])
    assert len(merged) == len(plan.jobs)
    assert merged[0].output == next(
        trial.output for trial in merged if trial.job_id == merged[0].job_id
    )
    assert next(trial for trial in merged if trial.job_id == replacement.job_id).output == "retried"
