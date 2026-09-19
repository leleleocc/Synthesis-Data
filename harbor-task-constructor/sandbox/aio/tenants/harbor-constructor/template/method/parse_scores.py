#!/usr/bin/env python3
"""Read Harbor trial evidence without writing derived score state.

The parser deliberately treats only a concrete trial's verifier detail as a
score source.  Batch and aggregate result files describe execution, not the
programmatic score used for a round.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
from pathlib import Path
from typing import Any

from harbor.publisher.packager import Packager


COMPLETED = "completed"
TIMED_OUT_SCORED = "timed_out_scored"
TIMED_OUT_UNSCORED = "timed_out_unscored"
PROVIDER_ERROR = "provider_error"
ENVIRONMENT_ERROR = "environment_error"
CANCELLED = "cancelled"
VERIFIER_ERROR = "verifier_error"
UNKNOWN_INVALID = "unknown_invalid"
TARGET_R = 0.2
TARGET_MEAN_LIMIT = 0.7
CRITERION_PREFERRED_MAX = 50


class ReadingError(ValueError):
    """Evidence cannot support the requested reading."""


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadingError(f"cannot read {path}: {exc}") from exc


def _number(value: Any) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _json_scalar(value: Any) -> Any:
    return None if isinstance(value, float) and not math.isfinite(value) else value


def _model_identity(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def harbor_task_digest(task_root: Path) -> str:
    digest, _ = Packager.compute_content_hash(Path(task_root))
    return f"sha256:{digest}"


def latest_numbered(parent: Path, prefix: str) -> Path:
    expression = re.compile(rf"^{re.escape(prefix)}[0-9]{{4}}$")
    candidates = [item for item in Path(parent).iterdir() if item.is_dir() and expression.fullmatch(item.name)] if Path(parent).is_dir() else []
    if not candidates:
        raise ReadingError(f"no numbered {prefix!r} directory under {parent}")
    return max(candidates, key=lambda item: item.name)


def _trial_digest(trial_dir: Path) -> str:
    lock = _read_json(trial_dir / "lock.json")
    digest = lock.get("task", {}).get("digest") if isinstance(lock, dict) else None
    if not isinstance(digest, str) or not digest:
        raise ReadingError(f"trial lock has no task digest: {trial_dir / 'lock.json'}")
    return digest


def _trial_dirs(root: Path) -> list[Path]:
    # A concrete Harbor task trial has the generated task__* directory. Find
    # it independently of its files: a missing result or lock is invalid
    # evidence that must remain visible, while the surrounding job directory
    # (which may also have result.json and lock.json) is not a trial.
    return sorted(
        [path for path in Path(root).rglob("task__*") if path.is_dir()],
        key=str,
    )


def _all_trial_digests(round_dir: Path) -> set[str]:
    return {_trial_digest(trial) for trial in _trial_dirs(round_dir) if (trial / "lock.json").is_file()}


def check_round_task(round_dir: Path, final_task: Path) -> str | None:
    digests = _all_trial_digests(round_dir)
    if not digests:
        return None
    if len(digests) != 1:
        raise ReadingError(f"trial locks disagree in {round_dir}: {sorted(digests)}")
    actual = harbor_task_digest(final_task)
    expected = next(iter(digests))
    if actual != expected:
        raise ReadingError(f"final task digest {actual} does not match trial locks {expected}")
    return expected


def _criteria(items: list[Any], prefix: tuple[str, ...] = ()) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for index, criterion in enumerate(items):
        if not isinstance(criterion, dict):
            continue
        name = str(criterion.get("name", index))
        path = "/".join((*prefix, name))
        found.append({
            "path": path,
            "name": name,
            "value": _number(criterion.get("value")),
            "raw": _json_scalar(criterion.get("raw")),
            "weight": _number(criterion.get("weight")),
            "description": criterion.get("description"),
            "reasoning": criterion.get("reasoning"),
        })
    return found


def _agent_judges(entries: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "score": _number(item.get("score")),
            "criteria": _criteria(item.get("criteria", [])),
            "judge": item.get("judge"),
            "judge_output": item.get("judge_output"),
        }
        for item in entries
        if isinstance(item, dict) and item.get("kind") == "agent"
    ]


def _flat_details(entries: list[Any]) -> tuple[float, list[dict[str, Any]], list[dict[str, Any]]]:
    programmatic = [entry for entry in entries if isinstance(entry, dict) and entry.get("kind") == "programmatic"]
    if len(programmatic) != 1:
        raise ReadingError(f"expected one direct programmatic score, found {len(programmatic)}")
    item = programmatic[0]
    score = _number(item.get("score"))
    if score is None:
        raise ReadingError("programmatic score is not numeric")
    judges = _agent_judges(entries)
    return score, _criteria(item.get("criteria", [])), judges


def _programmatic_group(detail: dict[str, Any], prefix: tuple[str, ...] = ()) -> tuple[bool, list[dict[str, Any]]]:
    """Return whether every scored leaf is programmatic, with qualified criteria."""
    kind = detail.get("kind")
    if kind == "programmatic":
        return _number(detail.get("score")) is not None, _criteria(detail.get("criteria", []), prefix)
    if kind != "group" or _number(detail.get("score")) is None:
        return False, []
    components = detail.get("components")
    if not isinstance(components, list) or not components:
        return False, []
    criteria: list[dict[str, Any]] = []
    for index, component in enumerate(components):
        if not isinstance(component, dict) or not isinstance(component.get("detail"), dict):
            return False, []
        name = str(component.get("name", index))
        all_programmatic, child = _programmatic_group(component["detail"], (*prefix, name))
        if not all_programmatic:
            return False, []
        criteria.extend(child)
    return True, criteria


def _nested_details(value: Any) -> tuple[float, list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(value, dict) and value.get("kind") == "group":
        candidates = [value]
    elif isinstance(value, dict):
        candidates = [entry for entry in value.values() if isinstance(entry, dict) and entry.get("kind") == "group"]
    elif isinstance(value, list):
        candidates = [entry for entry in value if isinstance(entry, dict) and entry.get("kind") == "group"]
    else:
        candidates = []
    eligible: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for candidate in candidates:
        all_programmatic, criteria = _programmatic_group(candidate)
        if all_programmatic:
            eligible.append((candidate, criteria))
    if len(eligible) != 1:
        raise ReadingError(f"expected one all-programmatic scored group, found {len(eligible)}")
    group, criteria = eligible[0]
    score = _number(group.get("score"))
    assert score is not None
    return score, criteria, []


def _programmatic_details(details: Any) -> tuple[float, list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(details, dict):
        raise ReadingError("reward details must be an object")
    reward = details.get("reward", details)
    entries = reward if isinstance(reward, list) else [reward] if isinstance(reward, dict) and reward.get("kind") == "programmatic" else []
    candidate_entries = list(reward.values()) if isinstance(reward, dict) and reward.get("kind") != "group" else entries
    direct = [item for item in entries if isinstance(item, dict) and item.get("kind") == "programmatic"]
    if isinstance(reward, dict) and reward.get("kind") == "group":
        groups = [reward]
    elif isinstance(reward, dict):
        groups = [item for item in reward.values() if isinstance(item, dict) and item.get("kind") == "group"]
    else:
        groups = [item for item in entries if isinstance(item, dict) and item.get("kind") == "group"]
    eligible: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for group in groups:
        all_programmatic, criteria = _programmatic_group(group)
        if all_programmatic:
            eligible.append((group, criteria))
    if len(direct) + len(eligible) != 1:
        raise ReadingError(
            f"expected one unambiguous programmatic score, found {len(direct) + len(eligible)}"
        )
    if direct:
        return _flat_details(entries)
    group, criteria = eligible[0]
    score = _number(group.get("score"))
    assert score is not None
    return score, criteria, _agent_judges(candidate_entries)


def _exception_type(result: Any) -> str | None:
    if not isinstance(result, dict):
        return "malformed result"
    if "exception_info" not in result:
        return "missing exception_info"
    info = result.get("exception_info")
    if info is None:
        return None
    if isinstance(info, str):
        return info.rsplit(".", 1)[-1]
    if isinstance(info, dict):
        value = info.get("exception_type", info.get("type", info.get("name")))
        return value.rsplit(".", 1)[-1] if isinstance(value, str) else "malformed exception"
    return "malformed exception"


def parse_trial(trial_dir: Path) -> dict[str, Any]:
    trial_dir = Path(trial_dir)
    output: dict[str, Any] = {
        "trial": trial_dir.name,
        "path": str(trial_dir),
        "digest": None,
        "resolved_model": None,
        "resolved_reasoning_effort": None,
        "state": UNKNOWN_INVALID,
        "included": False,
        "programmatic_score": None,
        "criteria": [],
        "agent_judges": [],
        "fault": None,
    }
    try:
        lock = _read_json(trial_dir / "lock.json")
        digest = lock.get("task", {}).get("digest") if isinstance(lock, dict) else None
        if not isinstance(digest, str) or not digest:
            raise ReadingError(f"trial lock has no task digest: {trial_dir / 'lock.json'}")
        output["digest"] = digest
        agent = lock.get("agent") if isinstance(lock, dict) else None
        if isinstance(agent, dict):
            output["resolved_model"] = _model_identity(agent.get("model_name"))
            kwargs = agent.get("kwargs") if isinstance(agent.get("kwargs"), dict) else {}
            output["resolved_reasoning_effort"] = _model_identity(kwargs.get("reasoning_effort"))
        result = _read_json(trial_dir / "result.json")
        exception_type = _exception_type(result)
        try:
            score, criteria, judges = _programmatic_details(_read_json(trial_dir / "verifier" / "reward-details.json"))
        except ReadingError as exc:
            score, criteria, judges = None, [], []
            output["fault"] = str(exc)
        output.update({"programmatic_score": score, "criteria": criteria, "agent_judges": judges})
        if exception_type is None:
            if score is not None:
                output.update({"state": COMPLETED, "included": True})
        elif exception_type == "AgentTimeoutError":
            output.update({"state": TIMED_OUT_SCORED if score is not None else TIMED_OUT_UNSCORED, "included": score is not None})
        elif exception_type == "UnknownApiError":
            output["state"] = PROVIDER_ERROR
        elif exception_type == "DaytonaConnectionError":
            output["state"] = ENVIRONMENT_ERROR
        elif exception_type == "CancelledError":
            output["state"] = CANCELLED
        elif exception_type == "RewardFileNotFoundError":
            output["state"] = VERIFIER_ERROR
        else:
            output["fault"] = output["fault"] or f"unclassified exception: {exception_type}"
        if output["included"] and output["resolved_model"] is None:
            output.update({"state": UNKNOWN_INVALID, "included": False, "fault": "trial lock has no resolved model identity"})
    except ReadingError as exc:
        output["fault"] = str(exc)
    return output


def _is_genuine_regrade_config(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    source_jobs = value.get("source_jobs")
    return (
        isinstance(source_jobs, list)
        and bool(source_jobs)
        and all(isinstance(source, dict) and source.get("action") == "regrade" for source in source_jobs)
    )


def _job_configs(arm_run_dir: Path) -> list[dict[str, Any]]:
    configs: list[dict[str, Any]] = []
    for path in sorted((Path(arm_run_dir) / "jobs").rglob("config.json")):
        data = _read_json(path)
        if (
            isinstance(data, dict)
            and isinstance(data.get("tasks"), list)
            and ("agents" in data or _is_genuine_regrade_config(data))
        ):
            configs.append(data)
    if len(configs) != 1:
        raise ReadingError(f"expected one qualifying Harbor job config, found {len(configs)}")
    return configs


def _metadata(configs: list[dict[str, Any]], trials: list[dict[str, Any]]) -> dict[str, Any]:
    if not configs:
        raise ReadingError("no Harbor job config with requested attempts")
    config = configs[0]
    retry = config.get("retry") if isinstance(config.get("retry"), dict) else {}
    if _is_genuine_regrade_config(config):
        models = {trial["resolved_model"] for trial in trials if trial["included"]}
        efforts = {
            trial["resolved_reasoning_effort"]
            for trial in trials
            if trial["included"] and trial["resolved_reasoning_effort"] is not None
        }
        if len(models) != 1:
            raise ReadingError(f"expected one included resolved model, found {sorted(models)}")
        if len(efforts) > 1:
            raise ReadingError(f"expected one resolved reasoning effort, found {sorted(efforts)}")
        return {
            "requested": len(trials),
            "concurrency": config.get("n_concurrent_trials", 4),
            "max_retries": retry.get("max_retries", 0),
            "model": next(iter(models)),
            "reasoning_effort": next(iter(efforts), None),
        }
    agents = [agent for config in configs for agent in (config.get("agents") or [])]
    normalized_agents: list[tuple[str, dict[str, Any]]] = []
    for agent in agents:
        if not isinstance(agent, dict):
            raise ReadingError("Harbor job config has a malformed agent entry")
        model = _model_identity(agent.get("model_name"))
        if model is None:
            raise ReadingError("Harbor job config has an agent without a configured model")
        normalized_agents.append((model, agent))
    models = {model for model, _ in normalized_agents}
    if len(models) != 1:
        raise ReadingError(f"expected one configured model, found {sorted(models)}")
    model = next(iter(models))
    agent = next(agent for normalized, agent in normalized_agents if normalized == model)
    kwargs = agent.get("kwargs") if isinstance(agent.get("kwargs"), dict) else {}
    return {
        "requested": config.get("n_attempts", 1),
        "concurrency": config.get("n_concurrent_trials", 4),
        "max_retries": retry.get("max_retries", 0),
        "model": model,
        "reasoning_effort": kwargs.get("reasoning_effort"),
    }


def parse_arm_run(arm_run_dir: Path) -> dict[str, Any]:
    arm_run_dir = Path(arm_run_dir)
    trials = [parse_trial(path) for path in _trial_dirs(arm_run_dir / "jobs")]
    valid = [trial for trial in trials if trial["included"]]
    metadata = _metadata(_job_configs(arm_run_dir), trials)
    resolved_models = {trial["resolved_model"] for trial in valid if trial["resolved_model"]}
    if len(resolved_models) != 1:
        raise ReadingError(f"expected one included resolved model, found {sorted(resolved_models)}")
    resolved_model = next(iter(resolved_models))
    if metadata["model"] != resolved_model:
        raise ReadingError(
            f"configured model {metadata['model']!r} does not match included resolved model {resolved_model!r}"
        )
    scores = [trial["programmatic_score"] for trial in valid]
    assert all(score is not None for score in scores)
    criteria_by_path: dict[str, dict[str, Any]] = {}
    for index, trial in enumerate(valid):
        for criterion in trial["criteria"]:
            entry = criteria_by_path.setdefault(
                criterion["path"],
                {key: value for key, value in criterion.items() if key not in {"value", "weight"}}
                | {"values": [None] * len(valid), "weights": [None] * len(valid)},
            )
            entry["values"][index] = criterion["value"]
            entry["weights"][index] = criterion["weight"]
    result = {
        "run": arm_run_dir.name,
        **metadata,
        "valid": len(valid),
        "invalid": len(trials) - len(valid),
        "mean": sum(float(score) for score in scores) / len(scores) if scores else None,
        "trials": trials,
        "invalid_trials": [trial for trial in trials if not trial["included"]],
        "criteria": [criteria_by_path[path] for path in sorted(criteria_by_path)],
        "agent_judges": [{"trial": trial["trial"], **judge} for trial in trials for judge in trial["agent_judges"]],
        "resolved_models": sorted(resolved_models),
        "faults": [trial["fault"] for trial in trials if trial["fault"]],
    }
    return result


def _mean_present(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return sum(present) / len(present) if present else None


def _binary_majority(values: list[float | None]) -> bool | None:
    present = [value for value in values if value is not None]
    if not present or any(value not in {0.0, 1.0} for value in present):
        return None
    passed = sum(value == 1.0 for value in present)
    if passed * 2 == len(present):
        return None
    return passed * 2 > len(present)


def _criterion_diagnostics(arms: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    by_arm = {
        arm_name: {criterion["path"]: criterion for criterion in arm["criteria"]}
        for arm_name, arm in arms.items()
    }
    rows: list[dict[str, Any]] = []
    for path in sorted(set(by_arm["target"]) | set(by_arm["solver"])):
        target = by_arm["target"].get(path)
        solver = by_arm["solver"].get(path)
        target_values = target["values"] if target is not None else [None] * arms["target"]["valid"]
        solver_values = solver["values"] if solver is not None else [None] * arms["solver"]["valid"]
        target_mean = _mean_present(target_values)
        solver_mean = _mean_present(solver_values)
        target_weights = sorted({weight for weight in (target or {"weights": []})["weights"] if weight is not None})
        solver_weights = sorted({weight for weight in (solver or {"weights": []})["weights"] if weight is not None})
        weights = {"target": target_weights, "solver": solver_weights}
        unique_weights = set(target_weights) | set(solver_weights)
        source = target or solver
        assert source is not None
        target_pass = _binary_majority(target_values)
        solver_pass = _binary_majority(solver_values)
        if target_pass is None or solver_pass is None:
            quadrant = None
        elif target_pass and solver_pass:
            quadrant = "both_pass"
        elif not target_pass and solver_pass:
            quadrant = "target_fail_solver_pass"
        elif target_pass and not solver_pass:
            quadrant = "target_pass_solver_fail"
        else:
            quadrant = "both_fail"
        rows.append({
            "path": path,
            "name": source["name"],
            "description": source.get("description"),
            "weight": next(iter(unique_weights)) if len(unique_weights) == 1 else None,
            "weights": weights,
            "target_mean": target_mean,
            "solver_mean": solver_mean,
            "delta": solver_mean - target_mean if target_mean is not None and solver_mean is not None else None,
            "target_missing": len(target_values) - sum(value is not None for value in target_values),
            "solver_missing": len(solver_values) - sum(value is not None for value in solver_values),
            "quadrant": quadrant,
        })
    return rows


def _collected_full_workspaces(round_dir: Path) -> list[str]:
    """Find full Harbor workspaces accidentally placed in a compact evidence root."""
    if not (round_dir / "round.json").is_file():
        return []
    evidence_root = round_dir.parent
    found: list[str] = []
    for parent, directories, _files in os.walk(evidence_root):
        parent_path = Path(parent)
        for name in list(directories):
            path = parent_path / name
            if name == "workspace" and parent_path.name == "artifacts":
                found.append(str(path.relative_to(evidence_root)))
                directories.remove(name)
    return sorted(found)


def _quality_scan(
    criteria: list[dict[str, Any]],
    arms: dict[str, dict[str, Any]],
    faults: list[str],
) -> dict[str, Any]:
    quadrants = {
        name: [criterion["path"] for criterion in criteria if criterion["quadrant"] == name]
        for name in (
            "both_pass",
            "target_fail_solver_pass",
            "target_pass_solver_fail",
            "both_fail",
        )
    }
    classified = sum(len(paths) for paths in quadrants.values())
    invalid_trials = sum(arm["invalid"] for arm in arms.values())
    red_flags: list[str] = []
    if quadrants["target_pass_solver_fail"]:
        red_flags.append("direction_reversal")
    if quadrants["both_fail"]:
        red_flags.append("both_fail")
    if classified and len(quadrants["both_pass"]) * 2 > classified:
        red_flags.append("both_pass_dominates")
    if invalid_trials:
        red_flags.append("invalid_trials")
    if faults:
        red_flags.append("faults")
    # collected_full_workspaces check removed: full workspaces are intentional
    # in this tenant (we want workspace evidence for attribution).
    timed_out = sum(
        sum(1 for t in arm["trials"] if t.get("state") == TIMED_OUT_UNSCORED)
        for arm in arms.values()
    )
    valid_total = sum(arm["valid"] for arm in arms.values())
    if valid_total > 0 and timed_out > valid_total:
        red_flags.append("timeouts_dominate")
    advisories = ["criterion_count_high"] if len(criteria) > CRITERION_PREFERRED_MAX else []
    return {
        "criterion_count": len(criteria),
        "criterion_preferred_max": CRITERION_PREFERRED_MAX,
        "criterion_count_high": len(criteria) > CRITERION_PREFERRED_MAX,
        "binary_quadrants": quadrants,
        "unclassified": [criterion["path"] for criterion in criteria if criterion["quadrant"] is None],
        "both_pass_share": len(quadrants["both_pass"]) / classified if classified else None,
        "invalid_trials": invalid_trials,
        "faults": len(faults),
        "timeouts_dominate": timed_out > valid_total if valid_total > 0 else False,
        "red_flags": red_flags,
        "advisories": advisories,
    }


def _next_action(
    *,
    task_matches_final: bool | None,
    clears_all_gates: bool,
    red_flags: list[str],
) -> tuple[str, str]:
    if "collected_full_workspaces" in red_flags:
        return (
            "inspect_red_flags",
            "Stop fresh sampling. Move full mechanical-check Harbor jobs to /home/app/workspace/runtime/harbor-checks, keep only compact diagnostics and the result summary under /home/app/workspace/evidence, then rerun the parser. Reuse the current score round; do not rerun models or checks.",
        )
    if task_matches_final is not True:
        return (
            "verify_final_task",
            "Rerun with --final-task /home/app/workspace/task before deciding; only a matching task digest is current evidence.",
        )
    if not clears_all_gates:
        return (
            "iterate",
            "Select one evidence-backed verifier hypothesis. For tests/solution edits, run nop/oracle and then regrade; use fresh only after rollout inputs change or when no reusable rollout exists.",
        )
    if red_flags:
        return (
            "inspect_red_flags",
            "Stop fresh sampling. Inspect only the listed red flags. A high both-pass share is a looseness or redundancy signal, not an automatic defect; criterion-count advisories do not block delivery. Edit only with concrete contract or counterexample evidence. For tests/solution edits, run nop/oracle and then regrade.",
        )
    return (
        "deliver",
        "Stop fresh sampling. Treat the both-pass share and criterion-count advisory as quick looseness checks; they do not block delivery. With current nop/oracle passing and no concrete defect, record this round and deliver.",
    )


def parse_round(round_dir: Path, final_task: Path | None = None) -> dict[str, Any]:
    round_dir = Path(round_dir)
    arms = {name: parse_arm_run(latest_numbered(round_dir / name, "run-")) for name in ("target", "solver")}
    selected_digests = {trial["digest"] for arm in arms.values() for trial in arm["trials"] if trial["digest"]}
    if len(selected_digests) > 1:
        raise ReadingError(f"selected trial locks disagree in {round_dir}: {sorted(selected_digests)}")
    digest = next(iter(selected_digests), None)
    task_matches_final: bool | None = None
    if final_task is not None:
        task_matches_final = True if check_round_task(round_dir, final_task) is not None else None
    target, solver = arms["target"]["mean"], arms["solver"]["mean"]
    if target is None or solver is None:
        R, R_state, reward, clears = None, "unreadable", 0.0, False
    elif target == 0 and solver > 0:
        R, R_state, reward, clears = None, "infinite", 1.0, True
    elif target == 0 and solver == 0:
        R, R_state, reward, clears = 0.0, "finite", 0.0, False
    elif target is not None:
        R = solver / target - 1.0
        if not math.isfinite(R):
            raise ReadingError("non-finite derived R")
        R_state = "finite"
        clears = R > TARGET_R
        reward = max(0.0, min(1.0, 0.0 if solver <= 0 else 1.0 - target / solver))
        if not math.isfinite(reward):
            raise ReadingError("non-finite derived reward")
    clears_target_mean = target is not None and target < TARGET_MEAN_LIMIT
    clears_all_gates = clears_target_mean and clears
    criteria = _criterion_diagnostics(arms)
    faults = [fault for arm in arms.values() for fault in arm["faults"]]
    quality_scan = _quality_scan(
        criteria,
        arms,
        faults,
    )
    next_action, action_hint = _next_action(
        task_matches_final=task_matches_final,
        clears_all_gates=clears_all_gates,
        red_flags=quality_scan["red_flags"],
    )
    report = {
        "round": round_dir.name,
        "task_digest": digest,
        "task_matches_final": task_matches_final,
        "arms": arms,
        "R": R,
        "R_state": R_state,
        "score_gates": {
            "target_mean_lt_0_7": clears_target_mean,
            "R_gt_0_2": clears,
            "all": clears_all_gates,
        },
        "clears_target_mean": clears_target_mean,
        "clears_R": clears,
        "clears_all_gates": clears_all_gates,
        # Kept for compatibility with existing outer-verifier reports.
        "clears_target_R": clears,
        "reward": reward,
        "criteria": criteria,
        "quality_scan": quality_scan,
        "next_action": next_action,
        "action_hint": action_hint,
        "agent_judges": [
            {"arm": arm_name, **judge}
            for arm_name, arm in arms.items() for judge in arm["agent_judges"]
        ],
        "resolved_models": {name: arm["resolved_models"] for name, arm in arms.items()},
        "faults": faults,
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read Harbor trial verifier details without creating a score cache.",
        epilog=("Only a unique programmatic verifier score is included. Agent timeouts are included "
                "only when that score exists; provider, environment, cancellation, verifier, and "
                "unknown failures remain visible as excluded trials."),
    )
    parser.add_argument("round", nargs="?", type=Path, help="round directory to read")
    parser.add_argument("--last", type=Path, metavar="EVIDENCE_ROOT", help="read the greatest round-NNNN below this evidence root")
    parser.add_argument("--final-task", type=Path, help="require every existing trial lock to match this Harbor-packaged task")
    parser.add_argument("--json", action="store_true", help="print the full stable report schema")
    args = parser.parse_args(argv)
    if (args.round is None) == (args.last is None):
        parser.error("provide exactly one positional ROUND or --last EVIDENCE_ROOT")
    try:
        round_dir = args.round if args.round is not None else latest_numbered(args.last, "round-")
        report = parse_round(round_dir, args.final_task)
    except ReadingError as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    else:
        print(f"{report['round']}  target={report['arms']['target']['mean']}  solver={report['arms']['solver']['mean']}  R={report['R']}  reward={report['reward']}")
        print("criterion                              weight   target   solver   delta   missing(t/s)")
        for criterion in report["criteria"]:
            weight = criterion["weight"] if criterion["weight"] is not None else criterion["weights"]
            target = "-" if criterion["target_mean"] is None else f"{criterion['target_mean']:.4f}"
            solver = "-" if criterion["solver_mean"] is None else f"{criterion['solver_mean']:.4f}"
            delta = "-" if criterion["delta"] is None else f"{criterion['delta']:.4f}"
            print(f"{criterion['path']:<38} {str(weight):<8} {target:>7} {solver:>8} {delta:>7} {criterion['target_missing']}/{criterion['solver_missing']}")
        print("agent judges")
        for judge in report["agent_judges"]:
            reasoning = [criterion["reasoning"] for criterion in judge["criteria"] if criterion.get("reasoning")]
            print(
                f"{judge['arm']}/{judge['trial']}  score={judge['score']}  "
                f"judge_output={judge.get('judge_output')}  reasoning={reasoning}"
            )
        gates = report["score_gates"]
        scan = report["quality_scan"]
        quadrant_counts = {name: len(paths) for name, paths in scan["binary_quadrants"].items()}
        print(
            "score gates  "
            f"target<0.7={'PASS' if gates['target_mean_lt_0_7'] else 'FAIL'}  "
            f"R>0.2={'PASS' if gates['R_gt_0_2'] else 'FAIL'}  "
            f"all={'PASS' if gates['all'] else 'FAIL'}  final-task={report['task_matches_final']}"
        )
        print(
            f"quality scan  criteria={scan['criterion_count']} (preferred<={scan['criterion_preferred_max']})  "
            f"quadrants={quadrant_counts}  both-pass-share={scan['both_pass_share']}  "
            f"unclassified={len(scan['unclassified'])}  invalid={scan['invalid_trials']}  faults={scan['faults']}"
        )
        print(f"red flags  {scan['red_flags'] or 'none'}")
        print(f"advisories  {scan['advisories'] or 'none'}")
        print(f"NEXT_ACTION={report['next_action']}")
        print(report["action_hint"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
