"""Reproducible A/B scouting for candidate skills.

Scout produces evidence and review decisions; Quartermaster's lifecycle
modules remain responsible for applying any resulting state transition.
External agent execution crosses a JSON-over-stdin seam so runners can use
subscription CLIs inside an appropriately isolated environment.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from . import frontmatter, intake, metadata

NO_SKILL = "no-skill"
CURRENT_SKILL = "current-skill"
CANDIDATE_SKILL = "candidate-skill"
CONDITIONS = (NO_SKILL, CURRENT_SKILL, CANDIDATE_SKILL)
FORCED = "forced"
NATURAL = "natural"
INVOCATION_MODES = (FORCED, NATURAL)
DECISIONS = ("accept", "reject", "revise")
MAX_RUNNER_OUTPUT_CHARS = 1_000_000


class ScoutError(ValueError):
    """Raised when scouting input cannot produce trustworthy evidence."""


@dataclass(frozen=True)
class CandidateSnapshot:
    skill_id: str
    name: str
    source: str
    version: str
    content_sha256: str
    path: str
    description: str
    license: str
    author: str
    manifest: Dict[str, object]
    manifest_warnings: Tuple[str, ...] = ()
    risk_flags: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["manifest_warnings"] = list(self.manifest_warnings)
        data["risk_flags"] = list(self.risk_flags)
        return data


@dataclass(frozen=True)
class BenchmarkTask:
    task_id: str
    prompt: str
    rubric: str
    should_invoke: bool
    tags: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["tags"] = list(self.tags)
        return data


@dataclass(frozen=True)
class BenchmarkSuite:
    suite_id: str
    version: str
    tasks: Tuple[BenchmarkTask, ...]

    def as_dict(self) -> Dict[str, object]:
        return {
            "suite_id": self.suite_id,
            "version": self.version,
            "tasks": [task.as_dict() for task in self.tasks],
        }


@dataclass(frozen=True)
class ScoutJob:
    job_id: str
    task_id: str
    repetition: int
    condition: str
    invocation_mode: str
    blind_label: str
    prompt: str
    rubric: str
    should_invoke: bool
    skill_path: Optional[str]

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ScoutPlan:
    plan_id: str
    created_at: float
    seed: int
    repetitions: int
    candidate: CandidateSnapshot
    current_skill: Optional[CandidateSnapshot]
    suite: BenchmarkSuite
    jobs: Tuple[ScoutJob, ...]

    def as_dict(self) -> Dict[str, object]:
        return {
            "schema_version": 1,
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "seed": self.seed,
            "repetitions": self.repetitions,
            "candidate": self.candidate.as_dict(),
            "current_skill": self.current_skill.as_dict() if self.current_skill else None,
            "suite": self.suite.as_dict(),
            "jobs": [job.as_dict() for job in self.jobs],
        }


@dataclass(frozen=True)
class TrialResult:
    plan_id: str
    job_id: str
    success: bool
    quality: float
    invoked: Optional[bool]
    latency_ms: float
    tokens: int
    cost: float
    output: str
    safety_flags: Tuple[str, ...] = ()
    error: str = ""

    def as_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["safety_flags"] = list(self.safety_flags)
        return data


@dataclass(frozen=True)
class ConditionProfile:
    condition: str
    invocation_mode: str
    trials: int
    completion_rate: float
    quality_mean: float
    quality_stddev: float
    selection_observations: int
    selection_accuracy: Optional[float]
    latency_mean_ms: float
    tokens_mean: float
    cost_mean: float
    safety_flag_count: int

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Comparison:
    baseline: str
    candidate_mode: str
    baseline_mode: str
    pairs: int
    quality_delta: float
    quality_ci95_low: float
    quality_ci95_high: float
    completion_delta: float
    selection_accuracy_delta: Optional[float]
    latency_delta_ms: float
    tokens_delta: float
    cost_delta: float

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ScoutingPolicy:
    minimum_quality_lift: float = 0.0
    minimum_completion_rate: float = 0.8
    maximum_safety_flags: int = 0
    freshness_half_life_days: float = 90.0


@dataclass(frozen=True)
class EvidencePack:
    evidence_id: str
    created_at: float
    plan_id: str
    candidate: CandidateSnapshot
    current_skill: Optional[CandidateSnapshot]
    suite_id: str
    suite_version: str
    profiles: Tuple[ConditionProfile, ...]
    comparisons: Tuple[Comparison, ...]
    ranking_score: float
    freshness_half_life_days: float
    automated_recommendation: str
    recommendation_reasons: Tuple[str, ...]
    limitations: Tuple[str, ...]
    trials: Tuple[TrialResult, ...]
    blind_labels: Dict[str, str]

    def as_dict(self, *, include_condition_map: bool = True) -> Dict[str, object]:
        data = {
            "schema_version": 1,
            "evidence_id": self.evidence_id,
            "created_at": self.created_at,
            "plan_id": self.plan_id,
            "candidate": self.candidate.as_dict(),
            "current_skill": self.current_skill.as_dict() if self.current_skill else None,
            "suite_id": self.suite_id,
            "suite_version": self.suite_version,
            "profiles": [profile.as_dict() for profile in self.profiles],
            "comparisons": [comparison.as_dict() for comparison in self.comparisons],
            "ranking_score": self.ranking_score,
            "freshness_half_life_days": self.freshness_half_life_days,
            "automated_recommendation": self.automated_recommendation,
            "recommendation_reasons": list(self.recommendation_reasons),
            "limitations": list(self.limitations),
            "trials": [trial.as_dict() for trial in self.trials],
        }
        if include_condition_map:
            data["blind_labels"] = dict(self.blind_labels)
        return data

    def review_packet(self) -> Dict[str, object]:
        outputs = []
        for trial in sorted(self.trials, key=lambda item: item.job_id):
            outputs.append(
                {
                    "job_id": trial.job_id,
                    "condition": self.blind_labels[trial.job_id],
                    "success": trial.success,
                    "quality": trial.quality,
                    "invoked": trial.invoked,
                    "latency_ms": trial.latency_ms,
                    "tokens": trial.tokens,
                    "cost": trial.cost,
                    "output": trial.output,
                    "safety_flags": list(trial.safety_flags),
                    "error": trial.error,
                }
            )
        return {
            "schema_version": 1,
            "evidence_id": self.evidence_id,
            "suite_id": self.suite_id,
            "suite_version": self.suite_version,
            "limitations": list(self.limitations),
            "blinded_outputs": outputs,
        }

    def ranking_score_at(self, now: float) -> float:
        age_days = max(0.0, (now - self.created_at) / 86400.0)
        return self.ranking_score * freshness_weight(
            age_days,
            self.freshness_half_life_days,
        )


@dataclass(frozen=True)
class ReviewVote:
    evidence_id: str
    reviewer: str
    decision: str
    rationale: str
    safety_veto: bool = False


@dataclass(frozen=True)
class ReviewDecision:
    status: str
    accept_count: int
    reject_count: int
    revise_count: int
    safety_vetoes: int
    reasons: Tuple[str, ...]

    def as_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class LifecycleRecommendation:
    action: str
    reason: str
    superseded_by: str = ""


def snapshot_candidate(
    skill_path: Path,
    *,
    source: str = "",
    version: str = "latest",
) -> CandidateSnapshot:
    """Resolve a mutable skill reference to an immutable content snapshot."""
    skill_path = Path(skill_path)
    skill_md = skill_path / "SKILL.md" if skill_path.is_dir() else skill_path
    if not skill_md.is_file():
        raise ScoutError(f"candidate has no SKILL.md: {skill_path}")

    root = skill_md.parent
    text = skill_md.read_text(encoding="utf-8", errors="replace")
    fm = frontmatter.parse(text)
    name = (fm.get("name") or root.name).strip()
    description = (fm.get("description") or "").strip()
    if not name or not description:
        raise ScoutError("candidate SKILL.md requires name and description")

    parsed = metadata.parse(fm, name=name, description=description)
    manifest = {
        "purpose_and_triggers": description,
        "non_goals": fm.get("scout-non-goals") or "",
        "prerequisites": metadata.parse_list(fm.get("scout-prerequisites") or ""),
        "compatibility": fm.get("compatibility") or fm.get("scout-compatible") or "",
        "expected_outputs": metadata.parse_list(fm.get("scout-outputs") or ""),
        "known_risks": metadata.parse_list(fm.get("scout-risks") or "") or parsed.risk,
        "allowed_tools": metadata.parse_list(fm.get("allowed-tools") or ""),
    }
    author = (fm.get("scout-author") or fm.get("author") or "").strip()
    warnings = []
    for key in ("non_goals", "prerequisites", "compatibility", "expected_outputs"):
        if not manifest[key]:
            warnings.append(f"manifest field {key!r} is missing")
    if not author:
        warnings.append("manifest field 'author' is missing")

    digest = _content_digest(root)
    identity_source = source or str(root.resolve())
    skill_id = hashlib.sha256(f"{identity_source}\0{name}".encode("utf-8")).hexdigest()[:20]
    return CandidateSnapshot(
        skill_id=skill_id,
        name=name,
        source=identity_source,
        version=version,
        content_sha256=digest,
        path=str(root.resolve()),
        description=description,
        license=(fm.get("license") or "").strip(),
        author=author,
        manifest=manifest,
        manifest_warnings=tuple(warnings),
        risk_flags=tuple(intake.risk_flags(text)),
    )


def load_suite(path: Path) -> BenchmarkSuite:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    try:
        suite_id = str(data["id"]).strip()
        version = str(data["version"]).strip()
        raw_tasks = data["tasks"]
    except (KeyError, TypeError) as exc:
        raise ScoutError(f"invalid benchmark suite: missing {exc}") from exc
    if not suite_id or not version or not isinstance(raw_tasks, list) or not raw_tasks:
        raise ScoutError("benchmark suite requires non-empty id, version, and tasks")

    tasks = []
    seen = set()
    for raw in raw_tasks:
        try:
            task_id = str(raw["id"]).strip()
            prompt = str(raw["prompt"]).strip()
            rubric = str(raw["rubric"]).strip()
            should_invoke = raw["should_invoke"]
        except (KeyError, TypeError) as exc:
            raise ScoutError(f"invalid benchmark task: missing {exc}") from exc
        if not task_id or task_id in seen or not prompt or not rubric:
            raise ScoutError(f"benchmark task IDs must be unique and fields non-empty: {task_id!r}")
        if not isinstance(should_invoke, bool):
            raise ScoutError(f"task {task_id!r} should_invoke must be boolean")
        seen.add(task_id)
        tasks.append(
            BenchmarkTask(
                task_id=task_id,
                prompt=prompt,
                rubric=rubric,
                should_invoke=should_invoke,
                tags=tuple(str(tag) for tag in raw.get("tags", [])),
            )
        )
    if not any(task.should_invoke for task in tasks) or all(task.should_invoke for task in tasks):
        raise ScoutError("suite must contain both positive and negative-control tasks")
    return BenchmarkSuite(suite_id=suite_id, version=version, tasks=tuple(tasks))


def build_plan(
    candidate: CandidateSnapshot,
    suite: BenchmarkSuite,
    *,
    current_skill: Optional[CandidateSnapshot] = None,
    repetitions: int = 5,
    seed: int = 7,
    created_at: Optional[float] = None,
) -> ScoutPlan:
    if repetitions < 2:
        raise ScoutError("paired scouting requires at least two repetitions")
    arms = [(NO_SKILL, NATURAL)]
    if current_skill:
        arms.extend(((CURRENT_SKILL, FORCED), (CURRENT_SKILL, NATURAL)))
    arms.extend(((CANDIDATE_SKILL, FORCED), (CANDIDATE_SKILL, NATURAL)))
    labels = dict(zip(arms, ("A", "B", "C", "D", "E")))
    rng = random.Random(seed)
    shuffled_labels = list(labels.values())
    rng.shuffle(shuffled_labels)
    labels = dict(zip(arms, shuffled_labels))

    jobs = []
    plan_id = _plan_id(candidate, current_skill, suite, repetitions, seed)
    for task in suite.tasks:
        for repetition in range(1, repetitions + 1):
            for condition, invocation_mode in arms:
                raw_id = (
                    f"{plan_id}:"
                    f"{task.task_id}:{repetition}:{condition}:{invocation_mode}:{seed}"
                )
                skill_path = None
                if condition == CANDIDATE_SKILL:
                    skill_path = candidate.path
                elif condition == CURRENT_SKILL and current_skill:
                    skill_path = current_skill.path
                jobs.append(
                    ScoutJob(
                        job_id=hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:24],
                        task_id=task.task_id,
                        repetition=repetition,
                        condition=condition,
                        invocation_mode=invocation_mode,
                        blind_label=labels[(condition, invocation_mode)],
                        prompt=task.prompt,
                        rubric=task.rubric,
                        should_invoke=task.should_invoke,
                        skill_path=skill_path,
                    )
                )
    rng.shuffle(jobs)
    created = created_at if created_at is not None else time.time()
    return ScoutPlan(
        plan_id=plan_id,
        created_at=created,
        seed=seed,
        repetitions=repetitions,
        candidate=candidate,
        current_skill=current_skill,
        suite=suite,
        jobs=tuple(jobs),
    )


def run_plan(
    plan: ScoutPlan,
    runner_command: Sequence[str],
    *,
    timeout_seconds: float = 600.0,
    job_ids: Optional[Iterable[str]] = None,
) -> Tuple[TrialResult, ...]:
    """Execute plan jobs through a JSON stdin/stdout runner adapter."""
    if not runner_command:
        raise ScoutError("runner command cannot be empty")
    _verify_snapshot(plan.candidate)
    if plan.current_skill:
        _verify_snapshot(plan.current_skill)
    selected_ids = set(job_ids) if job_ids is not None else None
    results = []
    for job in plan.jobs:
        if selected_ids is not None and job.job_id not in selected_ids:
            continue
        request = {
            "schema_version": 1,
            "plan_id": plan.plan_id,
            "candidate": plan.candidate.as_dict(),
            "current_skill": plan.current_skill.as_dict() if plan.current_skill else None,
            "job": job.as_dict(),
        }
        started = time.monotonic()
        try:
            completed = subprocess.run(
                list(runner_command),
                input=json.dumps(request),
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            elapsed_ms = (time.monotonic() - started) * 1000
            results.append(
                TrialResult(
                    plan_id=plan.plan_id,
                    job_id=job.job_id,
                    success=False,
                    quality=0.0,
                    invoked=False,
                    latency_ms=elapsed_ms,
                    tokens=0,
                    cost=0.0,
                    output=_timeout_text(exc.stdout),
                    error=f"runner timed out after {timeout_seconds:g}s",
                )
            )
            continue
        except OSError as exc:
            elapsed_ms = (time.monotonic() - started) * 1000
            results.append(
                TrialResult(
                    plan_id=plan.plan_id,
                    job_id=job.job_id,
                    success=False,
                    quality=0.0,
                    invoked=False,
                    latency_ms=elapsed_ms,
                    tokens=0,
                    cost=0.0,
                    output="",
                    error=f"runner could not start: {exc}",
                )
            )
            continue
        elapsed_ms = (time.monotonic() - started) * 1000
        if completed.returncode != 0:
            results.append(
                TrialResult(
                    plan_id=plan.plan_id,
                    job_id=job.job_id,
                    success=False,
                    quality=0.0,
                    invoked=False,
                    latency_ms=elapsed_ms,
                    tokens=0,
                    cost=0.0,
                    output=completed.stdout,
                    error=completed.stderr.strip() or f"runner exited {completed.returncode}",
                )
            )
            continue
        if len(completed.stdout) > MAX_RUNNER_OUTPUT_CHARS:
            results.append(
                TrialResult(
                    plan_id=plan.plan_id,
                    job_id=job.job_id,
                    success=False,
                    quality=0.0,
                    invoked=False,
                    latency_ms=elapsed_ms,
                    tokens=0,
                    cost=0.0,
                    output=completed.stdout[:MAX_RUNNER_OUTPUT_CHARS],
                    error=f"runner output exceeded {MAX_RUNNER_OUTPUT_CHARS} characters",
                )
            )
            continue
        try:
            raw = json.loads(completed.stdout)
            results.append(_parse_trial(plan.plan_id, job.job_id, raw, elapsed_ms=elapsed_ms))
        except (json.JSONDecodeError, ScoutError, TypeError, ValueError) as exc:
            results.append(
                TrialResult(
                    plan_id=plan.plan_id,
                    job_id=job.job_id,
                    success=False,
                    quality=0.0,
                    invoked=False,
                    latency_ms=elapsed_ms,
                    tokens=0,
                    cost=0.0,
                    output=completed.stdout,
                    error=f"invalid runner response: {exc}",
                )
            )
    return tuple(results)


def load_trials(path: Path) -> Tuple[TrialResult, ...]:
    path = Path(path)
    raw_text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        rows = [json.loads(line) for line in raw_text.splitlines() if line.strip()]
    else:
        payload = json.loads(raw_text)
        rows = payload["trials"] if isinstance(payload, dict) else payload
    return tuple(
        _parse_trial(str(row.get("plan_id", "")), str(row.get("job_id", "")), row)
        for row in rows
    )


def build_evidence(
    plan: ScoutPlan,
    trials: Iterable[TrialResult],
    *,
    policy: ScoutingPolicy = ScoutingPolicy(),
    created_at: Optional[float] = None,
) -> EvidencePack:
    results = tuple(trials)
    if any(trial.plan_id != plan.plan_id for trial in results):
        raise ScoutError("every trial must reference the plan being evaluated")
    jobs = {job.job_id: job for job in plan.jobs}
    by_id = {trial.job_id: trial for trial in results}
    missing = sorted(set(jobs) - set(by_id))
    extra = sorted(set(by_id) - set(jobs))
    if missing or extra or len(by_id) != len(results):
        raise ScoutError(
            f"trial set does not match plan: missing={len(missing)}, "
            f"extra={len(extra)}, duplicates={len(results) - len(by_id)}"
        )

    grouped: Dict[Tuple[str, str], List[Tuple[ScoutJob, TrialResult]]] = {}
    for job_id, job in jobs.items():
        grouped.setdefault((job.condition, job.invocation_mode), []).append((job, by_id[job_id]))
    profiles = tuple(
        _profile(condition, mode, grouped[(condition, mode)])
        for condition, mode in (
            (NO_SKILL, NATURAL),
            (CURRENT_SKILL, FORCED),
            (CURRENT_SKILL, NATURAL),
            (CANDIDATE_SKILL, FORCED),
            (CANDIDATE_SKILL, NATURAL),
        )
        if (condition, mode) in grouped
    )
    comparison_arms = [
        (NO_SKILL, FORCED, NATURAL),
        (NO_SKILL, NATURAL, NATURAL),
    ]
    if plan.current_skill:
        comparison_arms.extend(
            (
                (CURRENT_SKILL, FORCED, FORCED),
                (CURRENT_SKILL, NATURAL, NATURAL),
            )
        )
    comparisons = tuple(
        _comparison(
            baseline,
            candidate_mode,
            baseline_mode,
            grouped[(CANDIDATE_SKILL, candidate_mode)],
            grouped[(baseline, baseline_mode)],
        )
        for baseline, candidate_mode, baseline_mode in comparison_arms
    )
    candidate_forced = next(
        p for p in profiles
        if p.condition == CANDIDATE_SKILL and p.invocation_mode == FORCED
    )
    candidate_natural = next(
        p for p in profiles
        if p.condition == CANDIDATE_SKILL and p.invocation_mode == NATURAL
    )
    safety_flags = candidate_forced.safety_flag_count + candidate_natural.safety_flag_count
    reasons = []
    if safety_flags > policy.maximum_safety_flags:
        reasons.append(f"candidate emitted {safety_flags} safety flag(s)")
    if candidate_forced.completion_rate < policy.minimum_completion_rate:
        reasons.append(
            f"completion rate {candidate_forced.completion_rate:.3f} is below "
            f"{policy.minimum_completion_rate:.3f}"
        )
    if any(
        comparison.quality_ci95_low < policy.minimum_quality_lift
        for comparison in comparisons
    ):
        reasons.append(
            "candidate quality confidence interval did not clear the required lift "
            "against every baseline"
        )
    recommendation = "do-not-advance" if reasons else "send-to-review"

    baseline_profile = next(
        p for p in profiles
        if p.condition == NO_SKILL and p.invocation_mode == NATURAL
    )
    quality = max(0.0, min(1.0, candidate_forced.quality_mean))
    reliability = max(0.0, 1.0 - min(1.0, candidate_forced.quality_stddev))
    efficiency_baseline = next(
        (
            profile for profile in profiles
            if profile.condition == CURRENT_SKILL and profile.invocation_mode == FORCED
        ),
        baseline_profile,
    )
    efficiency = _efficiency(candidate_forced, efficiency_baseline)
    safety = 1.0 if safety_flags == 0 else 0.0
    score = (
        quality * 0.40
        + candidate_forced.completion_rate * 0.20
        + (
            candidate_natural.selection_accuracy
            if candidate_natural.selection_accuracy is not None
            else 0.5
        ) * 0.15
        + reliability * 0.10
        + efficiency * 0.10
        + safety * 0.05
    )
    created = created_at if created_at is not None else time.time()
    limitations = [
        "Automated evidence supports discovery and review; it does not establish field adoption.",
        "Results apply only to the recorded skill, suite, model, runner, and environment versions.",
    ]
    if plan.candidate.manifest_warnings:
        limitations.append("Candidate manifest is incomplete: " + "; ".join(plan.candidate.manifest_warnings))
    evidence_payload = {
        "created_at": created,
        "plan_id": plan.plan_id,
        "candidate": plan.candidate.as_dict(),
        "current_skill": plan.current_skill.as_dict() if plan.current_skill else None,
        "suite_id": plan.suite.suite_id,
        "suite_version": plan.suite.version,
        "profiles": [profile.as_dict() for profile in profiles],
        "comparisons": [comparison.as_dict() for comparison in comparisons],
        "ranking_score": score,
        "freshness_half_life_days": policy.freshness_half_life_days,
        "automated_recommendation": recommendation,
        "recommendation_reasons": reasons,
        "limitations": limitations,
        "trials": [trial.as_dict() for trial in results],
        "blind_labels": {job.job_id: job.blind_label for job in plan.jobs},
    }
    return EvidencePack(
        evidence_id=_artifact_id(evidence_payload),
        created_at=created,
        plan_id=plan.plan_id,
        candidate=plan.candidate,
        current_skill=plan.current_skill,
        suite_id=plan.suite.suite_id,
        suite_version=plan.suite.version,
        profiles=profiles,
        comparisons=comparisons,
        ranking_score=score,
        freshness_half_life_days=policy.freshness_half_life_days,
        automated_recommendation=recommendation,
        recommendation_reasons=tuple(reasons),
        limitations=tuple(limitations),
        trials=results,
        blind_labels={job.job_id: job.blind_label for job in plan.jobs},
    )


def decide_review(
    votes: Iterable[ReviewVote],
    *,
    evidence_id: str,
    author: str = "",
    required_reviewers: int = 3,
) -> ReviewDecision:
    submitted = tuple(votes)
    reviewers = [vote.reviewer.strip().lower() for vote in submitted]
    if any(not reviewer for reviewer in reviewers) or len(set(reviewers)) != len(reviewers):
        raise ScoutError("reviewers must be non-empty and independent")
    if any(vote.evidence_id != evidence_id for vote in submitted):
        raise ScoutError("every vote must reference the evidence being reviewed")
    if len(submitted) > required_reviewers:
        raise ScoutError(f"review accepts at most {required_reviewers} votes")
    if len(submitted) < required_reviewers:
        return ReviewDecision(
            "pending", 0, 0, 0, 0,
            (f"requires exactly {required_reviewers} independent reviewer votes",),
        )
    if author and author.strip().lower() in reviewers:
        raise ScoutError("candidate author cannot review their own skill")
    for vote in submitted:
        if vote.decision not in DECISIONS:
            raise ScoutError(f"unknown review decision: {vote.decision!r}")
        if not vote.rationale.strip():
            raise ScoutError("every review vote requires a rationale")

    accepts = sum(vote.decision == "accept" for vote in submitted)
    rejects = sum(vote.decision == "reject" for vote in submitted)
    revises = sum(vote.decision == "revise" for vote in submitted)
    vetoes = sum(vote.safety_veto for vote in submitted)
    reasons = tuple(f"{vote.reviewer}: {vote.rationale}" for vote in submitted)
    if vetoes:
        status = "blocked"
    elif accepts >= 2:
        status = "approved"
    elif rejects >= 2:
        status = "rejected"
    else:
        status = "revise"
    return ReviewDecision(status, accepts, rejects, revises, vetoes, reasons)


def recommend_lifecycle(
    *,
    evidence_age_days: float,
    usage_count: int,
    dominated_by: str = "",
    semantic_overlap: float = 0.0,
    quality_delta: float = 0.0,
) -> LifecycleRecommendation:
    """Suggest reversible cleanup without changing lifecycle state."""
    if dominated_by and semantic_overlap >= 0.85 and abs(quality_delta) < 0.03:
        return LifecycleRecommendation(
            "merge",
            "high-overlap skills have no meaningful measured quality difference",
            superseded_by=dominated_by,
        )
    if dominated_by and evidence_age_days >= 180 and usage_count == 0 and quality_delta <= -0.03:
        return LifecycleRecommendation(
            "archive",
            "unused, stale evidence, and consistently dominated by an approved alternative",
            superseded_by=dominated_by,
        )
    if evidence_age_days >= 180:
        return LifecycleRecommendation("re-evaluate", "evidence is stale")
    return LifecycleRecommendation("retain", "evidence and usage do not justify retirement")


def freshness_weight(age_days: float, half_life_days: float = 90.0) -> float:
    if age_days < 0 or half_life_days <= 0:
        raise ScoutError("freshness ages must be non-negative and half-life positive")
    return 2.0 ** (-age_days / half_life_days)


def write_json(path: Path, data: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_trials(path: Path, trials: Iterable[TrialResult]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for trial in trials:
            handle.write(json.dumps(trial.as_dict(), sort_keys=True) + "\n")


def merge_trials(
    plan: ScoutPlan,
    existing: Iterable[TrialResult],
    replacements: Iterable[TrialResult],
) -> Tuple[TrialResult, ...]:
    """Replace selected trial rows while preserving canonical plan order."""
    merged = {trial.job_id: trial for trial in existing}
    merged.update({trial.job_id: trial for trial in replacements})
    return tuple(merged[job.job_id] for job in plan.jobs if job.job_id in merged)


def plan_from_dict(data: Mapping[str, object]) -> ScoutPlan:
    if data.get("schema_version") != 1:
        raise ScoutError("unsupported scout plan schema_version")
    candidate = _snapshot_from_dict(data["candidate"])
    current_raw = data.get("current_skill")
    if current_raw is not None and not isinstance(current_raw, Mapping):
        raise ScoutError("plan current_skill must be an object or null")
    current = _snapshot_from_dict(current_raw) if current_raw is not None else None
    suite_raw = data["suite"]
    if not isinstance(suite_raw, Mapping):
        raise ScoutError("plan suite must be an object")
    suite = BenchmarkSuite(
        suite_id=str(suite_raw["suite_id"]),
        version=str(suite_raw["version"]),
        tasks=tuple(
            BenchmarkTask(
                task_id=str(task["task_id"]),
                prompt=str(task["prompt"]),
                rubric=str(task["rubric"]),
                should_invoke=bool(task["should_invoke"]),
                tags=tuple(task.get("tags", [])),
            )
            for task in suite_raw["tasks"]
        ),
    )
    jobs = tuple(
        ScoutJob(
            job_id=str(job["job_id"]),
            task_id=str(job["task_id"]),
            repetition=int(job["repetition"]),
            condition=str(job["condition"]),
            invocation_mode=str(job["invocation_mode"]),
            blind_label=str(job["blind_label"]),
            prompt=str(job["prompt"]),
            rubric=str(job["rubric"]),
            should_invoke=bool(job["should_invoke"]),
            skill_path=str(job["skill_path"]) if job.get("skill_path") else None,
        )
        for job in data["jobs"]
    )
    plan = ScoutPlan(
        plan_id=str(data["plan_id"]),
        created_at=float(data["created_at"]),
        seed=int(data["seed"]),
        repetitions=int(data["repetitions"]),
        candidate=candidate,
        current_skill=current,
        suite=suite,
        jobs=jobs,
    )
    expected_id = _plan_id(candidate, current, suite, plan.repetitions, plan.seed)
    if plan.plan_id != expected_id:
        raise ScoutError("scout plan identity does not match its pinned inputs")
    canonical = build_plan(
        candidate,
        suite,
        current_skill=current,
        repetitions=plan.repetitions,
        seed=plan.seed,
        created_at=plan.created_at,
    )
    if plan.jobs != canonical.jobs:
        raise ScoutError("scout plan jobs do not match its pinned inputs")
    return plan


def load_plan(path: Path) -> ScoutPlan:
    return plan_from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def verify_evidence_dict(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != 1:
        raise ScoutError("unsupported evidence schema_version")
    evidence_id = str(data.get("evidence_id", ""))
    payload = {
        key: value
        for key, value in data.items()
        if key not in ("schema_version", "evidence_id")
    }
    if not evidence_id or evidence_id != _artifact_id(payload):
        raise ScoutError("evidence identity does not match its contents")


def _content_digest(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        path for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts and "__pycache__" not in path.parts
    )
    for path in files:
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _plan_id(
    candidate: CandidateSnapshot,
    current_skill: Optional[CandidateSnapshot],
    suite: BenchmarkSuite,
    repetitions: int,
    seed: int,
) -> str:
    material = json.dumps(
        {
            "candidate": candidate.as_dict(),
            "current": current_skill.as_dict() if current_skill else None,
            "suite": suite.as_dict(),
            "repetitions": repetitions,
            "seed": seed,
        },
        sort_keys=True,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _verify_snapshot(snapshot: CandidateSnapshot) -> None:
    actual = _content_digest(Path(snapshot.path))
    if actual != snapshot.content_sha256:
        raise ScoutError(
            f"skill content changed after planning: {snapshot.name} "
            f"expected {snapshot.content_sha256[:12]}, found {actual[:12]}"
        )


def _timeout_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _parse_trial(
    plan_id: str,
    job_id: str,
    raw: Mapping[str, object],
    *,
    elapsed_ms: float = 0.0,
) -> TrialResult:
    if not plan_id or not job_id:
        raise ScoutError("trial result requires plan_id and job_id")
    success = raw.get("success", False)
    invoked = raw.get("invoked")
    if not isinstance(success, bool) or (invoked is not None and not isinstance(invoked, bool)):
        raise ScoutError("trial success must be boolean and invoked must be boolean or null")
    quality = float(raw.get("quality", 0.0))
    if not 0.0 <= quality <= 1.0:
        raise ScoutError(f"trial quality must be between 0 and 1: {quality}")
    tokens = int(raw.get("tokens", 0))
    cost = float(raw.get("cost", 0.0))
    flags = raw.get("safety_flags", [])
    if tokens < 0 or cost < 0:
        raise ScoutError("trial tokens and cost must be non-negative")
    if not isinstance(flags, list):
        raise ScoutError("trial safety_flags must be an array")
    return TrialResult(
        plan_id=plan_id,
        job_id=job_id,
        success=success,
        quality=quality if success else 0.0,
        invoked=invoked,
        latency_ms=elapsed_ms if elapsed_ms > 0 else float(raw.get("latency_ms", 0.0)),
        tokens=tokens,
        cost=cost,
        output=str(raw.get("output", "")),
        safety_flags=tuple(str(flag) for flag in flags),
        error=str(raw.get("error", "")),
    )


def _profile(
    condition: str,
    invocation_mode: str,
    pairs: Sequence[Tuple[ScoutJob, TrialResult]],
) -> ConditionProfile:
    results = [trial for _, trial in pairs]
    qualities = [trial.quality for trial in results]
    observed_invocations = [
        trial.invoked == job.should_invoke
        for job, trial in pairs
        if invocation_mode == NATURAL and trial.invoked is not None
    ]
    return ConditionProfile(
        condition=condition,
        invocation_mode=invocation_mode,
        trials=len(results),
        completion_rate=_mean(float(trial.success) for trial in results),
        quality_mean=_mean(qualities),
        quality_stddev=_within_task_stddev(pairs),
        selection_observations=len(observed_invocations),
        selection_accuracy=(
            _mean(float(correct) for correct in observed_invocations)
            if observed_invocations
            else None
        ),
        latency_mean_ms=_mean(trial.latency_ms for trial in results),
        tokens_mean=_mean(float(trial.tokens) for trial in results),
        cost_mean=_mean(trial.cost for trial in results),
        safety_flag_count=sum(len(trial.safety_flags) for trial in results),
    )


def _within_task_stddev(pairs: Sequence[Tuple[ScoutJob, TrialResult]]) -> float:
    grouped: Dict[str, List[float]] = {}
    for job, trial in pairs:
        grouped.setdefault(job.task_id, []).append(trial.quality)
    spreads = [
        statistics.pstdev(values)
        for values in grouped.values()
        if len(values) > 1
    ]
    return _mean(spreads)


def _comparison(
    baseline: str,
    candidate_mode: str,
    baseline_mode: str,
    candidate_pairs: Sequence[Tuple[ScoutJob, TrialResult]],
    baseline_pairs: Sequence[Tuple[ScoutJob, TrialResult]],
) -> Comparison:
    candidate = {
        (job.task_id, job.repetition): (job, trial)
        for job, trial in candidate_pairs
    }
    baseline_map = {
        (job.task_id, job.repetition): (job, trial)
        for job, trial in baseline_pairs
    }
    keys = sorted(set(candidate) & set(baseline_map))
    if len(keys) != len(candidate) or len(keys) != len(baseline_map):
        raise ScoutError(f"unpaired candidate and {baseline} trials")
    quality_deltas = [candidate[key][1].quality - baseline_map[key][1].quality for key in keys]
    task_deltas: Dict[str, List[float]] = {}
    for key, delta in zip(keys, quality_deltas):
        task_deltas.setdefault(key[0], []).append(delta)
    independent_deltas = [_mean(values) for values in task_deltas.values()]
    low, high = _ci95(independent_deltas)
    return Comparison(
        baseline=baseline,
        candidate_mode=candidate_mode,
        baseline_mode=baseline_mode,
        pairs=len(keys),
        quality_delta=_mean(quality_deltas),
        quality_ci95_low=low,
        quality_ci95_high=high,
        completion_delta=_mean(
            float(candidate[key][1].success) - float(baseline_map[key][1].success)
            for key in keys
        ),
        selection_accuracy_delta=_selection_delta(
            candidate_mode,
            baseline_mode,
            [candidate[key] for key in keys],
            [baseline_map[key] for key in keys],
        ),
        latency_delta_ms=_mean(
            candidate[key][1].latency_ms - baseline_map[key][1].latency_ms
            for key in keys
        ),
        tokens_delta=_mean(
            float(candidate[key][1].tokens - baseline_map[key][1].tokens)
            for key in keys
        ),
        cost_delta=_mean(
            candidate[key][1].cost - baseline_map[key][1].cost
            for key in keys
        ),
    )


def _ci95(values: Sequence[float]) -> Tuple[float, float]:
    center = _mean(values)
    if len(values) < 2:
        return center, center
    standard_error = statistics.stdev(values) / math.sqrt(len(values))
    margin = _t95(len(values) - 1) * standard_error
    return center - margin, center + margin


def _selection_delta(
    candidate_mode: str,
    baseline_mode: str,
    candidate: Sequence[Tuple[ScoutJob, TrialResult]],
    baseline: Sequence[Tuple[ScoutJob, TrialResult]],
) -> Optional[float]:
    if candidate_mode != NATURAL or baseline_mode != NATURAL:
        return None
    deltas = []
    for (candidate_job, candidate_trial), (baseline_job, baseline_trial) in zip(candidate, baseline):
        if candidate_trial.invoked is None or baseline_trial.invoked is None:
            continue
        deltas.append(
            float(candidate_trial.invoked == candidate_job.should_invoke)
            - float(baseline_trial.invoked == baseline_job.should_invoke)
        )
    return _mean(deltas) if deltas else None


def _t95(degrees_of_freedom: int) -> float:
    """Two-sided 95% Student-t critical value, conservative for small suites."""
    table = {
        1: 12.706,
        2: 4.303,
        3: 3.182,
        4: 2.776,
        5: 2.571,
        6: 2.447,
        7: 2.365,
        8: 2.306,
        9: 2.262,
        10: 2.228,
        11: 2.201,
        12: 2.179,
        13: 2.160,
        14: 2.145,
        15: 2.131,
        16: 2.120,
        17: 2.110,
        18: 2.101,
        19: 2.093,
        20: 2.086,
        21: 2.080,
        22: 2.074,
        23: 2.069,
        24: 2.064,
        25: 2.060,
        26: 2.056,
        27: 2.052,
        28: 2.048,
        29: 2.045,
        30: 2.042,
    }
    if degrees_of_freedom <= 0:
        return 0.0
    if degrees_of_freedom <= 30:
        return table[degrees_of_freedom]
    if degrees_of_freedom <= 60:
        return 2.000
    if degrees_of_freedom <= 120:
        return 1.980
    return 1.960


def _efficiency(candidate: ConditionProfile, baseline: ConditionProfile) -> float:
    ratios = []
    for current, base in (
        (candidate.latency_mean_ms, baseline.latency_mean_ms),
        (candidate.tokens_mean, baseline.tokens_mean),
        (candidate.cost_mean, baseline.cost_mean),
    ):
        if base > 0:
            ratios.append(min(1.0, base / max(current, 1e-12)))
    return _mean(ratios) if ratios else 1.0


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def _artifact_id(payload: Mapping[str, object]) -> str:
    material = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def _snapshot_from_dict(raw: object) -> CandidateSnapshot:
    if not isinstance(raw, Mapping):
        raise ScoutError("candidate snapshot must be an object")
    return CandidateSnapshot(
        skill_id=str(raw["skill_id"]),
        name=str(raw["name"]),
        source=str(raw["source"]),
        version=str(raw["version"]),
        content_sha256=str(raw["content_sha256"]),
        path=str(raw["path"]),
        description=str(raw["description"]),
        license=str(raw.get("license", "")),
        author=str(raw.get("author", "")),
        manifest=dict(raw.get("manifest", {})),
        manifest_warnings=tuple(raw.get("manifest_warnings", [])),
        risk_flags=tuple(raw.get("risk_flags", [])),
    )
