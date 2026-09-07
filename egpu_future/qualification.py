"""Build T0-T3 commissioning qualification reports from measured evidence."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from egpu_future.stage_gate import GateStatus, InterferenceLimits, evaluate_interference_gate


@dataclass(frozen=True)
class PhaseResult:
  phase: str
  description: str
  status: GateStatus
  reasons: tuple[str, ...]
  active_stats: dict | None
  gate: dict | None = None
  tap_probe: dict | None = None


@dataclass(frozen=True)
class QualificationReport:
  overall_status: GateStatus
  phases: tuple[PhaseResult, ...]
  notes: tuple[str, ...]


def _gate_dict(decision) -> dict:
  return {
    "status": decision.status.value,
    "reasons": list(decision.reasons),
    "checks": decision.checks,
    "deltas": decision.deltas,
  }


def _tap_checks(summary: dict | None) -> tuple[GateStatus, list[str]]:
  if summary is None:
    return GateStatus.HOLD, ["tap_probe_summary_required"]
  reasons: list[str] = []
  if int(summary.get("packetsReceived", 0) or 0) <= 0:
    reasons.append("no_tap_packets_received")
  if int(summary.get("recordsSaved", 0) or 0) <= 0:
    reasons.append("no_tap_records_saved")
  if int(summary.get("decodeErrors", 0) or 0) > 0:
    reasons.append("tap_decode_errors")
  return (GateStatus.FAIL if reasons else GateStatus.PASS), reasons


def build_t0_t3_report(
  *,
  t0: dict | None,
  t1: dict | None,
  t2: dict | None,
  t3: dict | None,
  limits: InterferenceLimits | None,
  t3_tap_probe: dict | None = None,
) -> QualificationReport:
  phases: list[PhaseResult] = []
  notes = [
    "T0 is the unpatched active-model baseline.",
    "T1-T3 are compared against T0; PASS requires explicit experiment limits.",
    "This qualification is an engineering research gate, not a comma safety certification.",
  ]

  if t0 is None or int(t0.get("samples", 0) or 0) <= 0:
    phases.append(PhaseResult("T0", "original baseline", GateStatus.HOLD, ("baseline_evidence_required",), t0))
    for phase, desc, stats in (
      ("T1", "patch installed, tap disabled", t1),
      ("T2", "tap enabled, receiver absent", t2),
      ("T3", "tap enabled + receiver, no inference", t3),
    ):
      phases.append(PhaseResult(phase, desc, GateStatus.HOLD, ("t0_baseline_required",), stats))
    return QualificationReport(GateStatus.HOLD, tuple(phases), tuple(notes))

  phases.append(PhaseResult("T0", "original baseline", GateStatus.PASS, (), t0))

  for phase, desc, stats in (
    ("T1", "patch installed, tap disabled", t1),
    ("T2", "tap enabled, receiver absent", t2),
    ("T3", "tap enabled + receiver, no inference", t3),
  ):
    if stats is None:
      phases.append(PhaseResult(phase, desc, GateStatus.HOLD, ("phase_evidence_required",), None))
      continue
    decision = evaluate_interference_gate(t0, stats, limits)
    status = decision.status
    reasons = list(decision.reasons)
    tap_probe = None
    if phase == "T3":
      tap_probe = t3_tap_probe
      tap_status, tap_reasons = _tap_checks(t3_tap_probe)
      reasons.extend(tap_reasons)
      if status == GateStatus.FAIL or tap_status == GateStatus.FAIL:
        status = GateStatus.FAIL
      elif status == GateStatus.HOLD or tap_status == GateStatus.HOLD:
        status = GateStatus.HOLD
      else:
        status = GateStatus.PASS
    phases.append(PhaseResult(phase, desc, status, tuple(dict.fromkeys(reasons)), stats, _gate_dict(decision), tap_probe))

  statuses = [p.status for p in phases]
  if GateStatus.FAIL in statuses:
    overall = GateStatus.FAIL
  elif GateStatus.HOLD in statuses:
    overall = GateStatus.HOLD
  else:
    overall = GateStatus.PASS
  return QualificationReport(overall, tuple(phases), tuple(notes))


def report_to_dict(report: QualificationReport) -> dict[str, Any]:
  return {
    "overallStatus": report.overall_status.value,
    "phases": [
      {
        **asdict(p),
        "status": p.status.value,
        "reasons": list(p.reasons),
      }
      for p in report.phases
    ],
    "notes": list(report.notes),
  }


def render_markdown(report: QualificationReport) -> str:
  lines = [
    "# EGPU-Future T0-T3 Commissioning Qualification",
    "",
    f"**Overall: {report.overall_status.value}**",
    "",
    "| Phase | Description | Status | Reasons | Samples | p99 (ms) | Max (ms) |",
    "|---|---|---|---|---:|---:|---:|",
  ]
  for p in report.phases:
    stats = p.active_stats or {}
    reasons = ", ".join(p.reasons) if p.reasons else "-"
    lines.append(
      f"| {p.phase} | {p.description} | {p.status.value} | {reasons} | "
      f"{stats.get('samples', '-')} | {stats.get('p99Ms', '-')} | {stats.get('maxMs', '-')} |"
    )
  lines += ["", "## Notes", ""]
  lines += [f"- {note}" for note in report.notes]

  t3 = next((p for p in report.phases if p.phase == "T3"), None)
  if t3 and t3.tap_probe is not None:
    tap = t3.tap_probe
    lines += [
      "",
      "## T3 Tap Receiver",
      "",
      f"- packets received: {tap.get('packetsReceived')}",
      f"- records saved: {tap.get('recordsSaved')}",
      f"- superseded packets: {tap.get('supersededPackets')}",
      f"- decode errors: {tap.get('decodeErrors')}",
      f"- save coverage: {tap.get('saveCoverage')}",
    ]
  return "\n".join(lines) + "\n"
