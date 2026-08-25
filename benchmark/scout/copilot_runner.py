"""Live Skill Scout runner for GitHub Copilot CLI subscriptions.

The runner creates an ephemeral workspace for each job, exposes only the
assigned candidate skill, invokes Copilot non-interactively, and applies a
deterministic task rubric. Natural skill activation is reported as unobserved
because Copilot CLI currently reports loaded skills but no distinct activation
event for these prompt-only tasks.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List


def _sentences(text: str) -> List[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part.strip()]


def _contains(text: str, term: str) -> bool:
    return re.search(r"\b" + re.escape(term.lower()) + r"\b", text.lower()) is not None


def _score(output: str, rubric: Dict[str, object]) -> float:
    checks: List[bool] = []
    required_groups = rubric.get("required_groups", [])
    for group in required_groups:
        checks.append(any(_contains(output, str(term)) for term in group))
    for term in rubric.get("forbidden_terms", []):
        checks.append(not _contains(output, str(term)))

    max_words = int(rubric.get("max_sentence_words", 0) or 0)
    if max_words:
        checks.append(all(len(sentence.split()) <= max_words for sentence in _sentences(output)))
    if rubric.get("no_semicolon"):
        checks.append(";" not in output)
    if rubric.get("output_only"):
        lower = output.lstrip().lower()
        checks.append(not lower.startswith(("here is", "here's", "mode:", "rewritten")))

    minimum_uncertainty = int(rubric.get("minimum_uncertainty_markers", 0) or 0)
    if minimum_uncertainty:
        markers = ("may", "might", "could", "possible", "possibly", "sometimes", "likely")
        count = sum(len(re.findall(r"\b" + marker + r"\b", output.lower())) for marker in markers)
        checks.append(count >= minimum_uncertainty)

    if not checks:
        return 0.0
    return sum(checks) / len(checks)


def _usage_tokens(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return 0

    input_tokens = data.get("lastCallInputTokens", 0)
    output_tokens = data.get("lastCallOutputTokens", 0)
    if isinstance(input_tokens, (int, float)) and isinstance(output_tokens, (int, float)):
        return int(input_tokens) + int(output_tokens)
    return 0


def _copy_skill(source: Path, workspace: Path, name: str) -> None:
    target = workspace / ".github" / "skills" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"),
    )


def _extract_response(events: str) -> str:
    messages = []
    for line in events.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant.message":
            content = event.get("data", {}).get("content")
            if isinstance(content, str):
                messages.append(content)
    return messages[-1].strip() if messages else ""


def main() -> int:
    request = json.load(sys.stdin)
    job = request["job"]
    candidate = request["candidate"]
    condition = job["condition"]
    invocation_mode = job["invocation_mode"]
    skill_path = job.get("skill_path")

    copilot = shutil.which(os.environ.get("SCOUT_COPILOT_COMMAND", "copilot"))
    if not copilot:
        raise SystemExit("copilot executable was not found")

    with tempfile.TemporaryDirectory(prefix="qm-scout-copilot-") as temp:
        workspace = Path(temp)
        if skill_path:
            _copy_skill(Path(skill_path), workspace, candidate["name"])

        request_path = workspace / "request.md"
        request_path.write_text(str(job["prompt"]), encoding="utf-8")
        prompt = "Complete the request in @request.md. Follow its output instructions exactly."
        if condition == "candidate-skill" and invocation_mode == "forced":
            prompt = (
                f"Use the installed {candidate['name']} skill. "
                "Follow its applicability boundaries and output contract. "
                + prompt
            )

        usage_path = workspace / "usage.json"
        command = [
            copilot,
            "-C",
            str(workspace),
            "-p",
            prompt,
            "--allow-all-tools",
            "--disable-builtin-mcps",
            "--model",
            os.environ.get("SCOUT_MODEL", "gpt-5-mini"),
            "--effort",
            os.environ.get("SCOUT_EFFORT", "low"),
            "--output-format",
            "json",
            "--stream",
            "off",
            "--usage-output-file",
            str(usage_path),
        ]
        completed = subprocess.run(
            command,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=float(os.environ.get("SCOUT_AGENT_TIMEOUT", "180")),
            check=False,
        )
        output = _extract_response(completed.stdout or "")
        try:
            rubric = json.loads(job["rubric"])
        except json.JSONDecodeError as exc:
            raise SystemExit(f"rubric must be a JSON object string: {exc}") from exc

        result = {
            "success": completed.returncode == 0 and bool(output),
            "quality": _score(output, rubric) if completed.returncode == 0 else 0.0,
            "invoked": (
                True
                if condition == "candidate-skill" and invocation_mode == "forced"
                else False if condition == "no-skill" else None
            ),
            "tokens": _usage_tokens(usage_path),
            "cost": 0.0,
            "output": output,
            "safety_flags": [],
            "error": completed.stderr.strip() if completed.returncode != 0 else "",
        }
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
