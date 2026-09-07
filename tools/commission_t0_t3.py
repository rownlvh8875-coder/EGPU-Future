#!/usr/bin/env python3
"""Reboot-aware stationary T0-T3 commissioning runner for Carrot eGPU.

Why two sessions are required:
Carrot manager pre-imports Python model processes and then forks modeld. Editing
modeld.py and killing only the child does not guarantee the new source is
imported. A full device/manager restart is therefore an explicit boundary
between T0 and T1.

Workflow:
  preflight -> prepare (T0 + write patch) -> reboot -> resume (T1/T2/T3 + report + restore source)
  -> optional final reboot -> finalize verification

No reboot is triggered automatically. This tool is intended only for an
ignition-on, parked, selfdrive-inactive commissioning session.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import py_compile
import shutil
import signal
import subprocess
import sys
import time

from egpu_future.carrot_patch import (
  PINNED_CARROT_HEAD,
  PINNED_MODELD_GIT_BLOB,
  TARGET_MODELD_PATH,
  TARGET_RUNTIME_PATH,
  patch_modeld_text,
  verify_control_path_unchanged,
)
from egpu_future.commissioning import FrameContinuityCounter, StationarySnapshot, evaluate_stationary_guard


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SOURCE = PROJECT_ROOT / "integrations/carrot/egpu_future_shadow_tap.py"
RECEIVER_SCRIPT = PROJECT_ROOT / "tools/shadow_tap_receiver_probe.py"
REPORT_SCRIPT = PROJECT_ROOT / "tools/build_commissioning_report.py"
DEFAULT_CONTROL_PATH = Path("/tmp/egpu_future_shadow_tap.enable")
DEFAULT_SOCKET_PATH = Path("/tmp/egpu_future_shadow_input.sock")


def git(repo: Path, *args: str) -> str:
  result = subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=False)
  if result.returncode != 0:
    raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
  return result.stdout.strip()


def sha256(path: Path) -> str:
  h = hashlib.sha256()
  with path.open("rb") as f:
    for chunk in iter(lambda: f.read(1024 * 1024), b""):
      h.update(chunk)
  return h.hexdigest()


def boot_id() -> str:
  path = Path("/proc/sys/kernel/random/boot_id")
  return path.read_text(encoding="utf-8").strip() if path.is_file() else "unavailable"


def unlink_if_exists(path: Path) -> None:
  try:
    path.unlink()
  except FileNotFoundError:
    pass


def gear_name(car_state) -> str | None:
  value = getattr(car_state, "gearShifter", None)
  if value is None:
    return None
  text = str(value).strip().lower()
  if not text or text in {"unknown", "none"}:
    return None
  return text.rsplit(".", 1)[-1]


def safety_snapshot(sm) -> StationarySnapshot:
  c = sm["carState"]
  s = sm["selfdriveState"]
  return StationarySnapshot(
    v_ego=float(getattr(c, "vEgo", 0.0)),
    standstill=bool(getattr(c, "standstill", False)),
    selfdrive_active=bool(getattr(s, "active", False)),
    gear=gear_name(c),
  )


def assert_stationary(sm) -> StationarySnapshot:
  snap = safety_snapshot(sm)
  ok, reasons = evaluate_stationary_guard(snap, require_park=True)
  if not ok:
    raise RuntimeError(f"stationary safety guard failed: {','.join(reasons)} snapshot={snap}")
  return snap


def import_openpilot_runtime(repo: Path):
  repo_s = str(repo)
  if repo_s not in sys.path:
    sys.path.insert(0, repo_s)
  try:
    from openpilot.cereal import messaging  # type: ignore
    from openpilot.common.params import Params  # type: ignore
  except Exception as exc:
    raise RuntimeError(f"failed to import openpilot runtime from {repo}: {exc}") from exc
  return messaging, Params


def modeld_pid(sm) -> int:
  try:
    for proc in sm["managerState"].processes:
      if str(proc.name) == "modeld" and bool(proc.running):
        return int(proc.pid)
  except Exception:
    pass
  return 0


def wait_for_stationary_runtime(repo: Path, timeout_s: float = 20.0, consecutive: int = 5):
  messaging, Params = import_openpilot_runtime(repo)
  sm = messaging.SubMaster(["carState", "selfdriveState", "managerState", "modelV2"])
  params = Params()
  good = 0
  deadline = time.monotonic() + timeout_s
  while time.monotonic() < deadline:
    sm.update(1000)
    try:
      assert_stationary(sm)
      if not params.get_bool("UsbGpuActive"):
        raise RuntimeError("UsbGpuActive is false")
      if modeld_pid(sm) <= 0:
        raise RuntimeError("modeld is not running")
      good += 1
      if good >= consecutive:
        return
    except Exception:
      good = 0
  raise RuntimeError("stationary/eGPU/modeld preflight did not become stable")


def capture_stage(repo: Path, stage: str, duration_s: float, output: Path) -> dict:
  messaging, Params = import_openpilot_runtime(repo)
  sm = messaging.SubMaster(["modelV2", "carState", "selfdriveState"])
  params = Params()
  continuity = FrameContinuityCounter()
  started = time.monotonic()
  last_frame = None
  samples = 0
  invalid = 0
  frame_age_gt1 = 0
  max_frame_age = 0
  last_param_check = 0.0
  egpu_active = False

  output.parent.mkdir(parents=True, exist_ok=True)
  with output.open("w", encoding="utf-8", buffering=1) as out:
    while time.monotonic() - started < duration_s:
      sm.update(1000)
      snap = assert_stationary(sm)
      now = time.monotonic()
      if now - last_param_check >= 0.5:
        egpu_active = bool(params.get_bool("UsbGpuActive"))
        last_param_check = now
      if not egpu_active:
        raise RuntimeError(f"{stage}: UsbGpuActive became false")
      if not sm.updated["modelV2"]:
        continue

      m = sm["modelV2"]
      frame_id = int(getattr(m, "frameId", 0))
      if frame_id > 0 and frame_id == last_frame:
        continue
      last_frame = frame_id
      continuity.observe(frame_id)
      frame_age = int(getattr(m, "frameAge", 0) or 0)
      max_frame_age = max(max_frame_age, frame_age)
      if frame_age > 1:
        frame_age_gt1 += 1
      valid = bool(sm.valid["modelV2"])
      if not valid:
        invalid += 1
      action = m.action
      mono_ns = time.monotonic_ns()
      row = {
        "source": stage,
        "logMonoTimeNs": mono_ns,
        "logMonoTimeS": mono_ns / 1e9,
        "frameId": frame_id,
        "frameIdExtra": int(getattr(m, "frameIdExtra", 0) or 0),
        "frameAge": frame_age,
        "timestampEofNs": int(getattr(m, "timestampEof", 0) or 0),
        "modelExecutionTimeS": float(getattr(m, "modelExecutionTime", 0.0) or 0.0),
        "big": egpu_active,
        "backendLabelSource": "UsbGpuActiveParam",
        "usbGpuActive": egpu_active,
        "valid": valid,
        "desiredCurvature": float(action.desiredCurvature),
        "desiredAcceleration": float(action.desiredAcceleration),
        "shouldStop": bool(action.shouldStop),
        "speedMps": snap.v_ego,
        "standstill": snap.standstill,
        "selfdriveActive": snap.selfdrive_active,
        "gear": snap.gear,
      }
      out.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
      samples += 1

  return {
    "stage": stage,
    "durationSeconds": time.monotonic() - started,
    "samples": samples,
    "invalidModelV2": invalid,
    "frameAgeGt1": frame_age_gt1,
    "frameAgeMax": max_frame_age,
    "continuity": continuity.summary(),
    "output": str(output),
  }


def apply_patch(repo: Path, session_dir: Path) -> dict:
  modeld_path = repo / TARGET_MODELD_PATH
  runtime_target = repo / TARGET_RUNTIME_PATH
  original = modeld_path.read_text(encoding="utf-8")
  if "EGPU-FUTURE SHADOW TAP" in original:
    raise RuntimeError("modeld.py is already patched")
  if runtime_target.exists():
    raise RuntimeError(f"runtime target already exists: {runtime_target}")
  dirty = git(repo, "status", "--porcelain", "--", TARGET_MODELD_PATH, TARGET_RUNTIME_PATH)
  if dirty:
    raise RuntimeError(f"target files are dirty:\n{dirty}")
  blob = git(repo, "hash-object", TARGET_MODELD_PATH)
  if blob != PINNED_MODELD_GIT_BLOB:
    raise RuntimeError(f"modeld blob mismatch got={blob} expected={PINNED_MODELD_GIT_BLOB}")

  patched = patch_modeld_text(original)
  verify_control_path_unchanged(original, patched)
  backup_dir = session_dir / "backup"
  backup_dir.mkdir(parents=True, exist_ok=True)
  backup = backup_dir / "modeld.py.original"
  backup.write_text(original, encoding="utf-8")

  wrote_runtime = False
  wrote_modeld = False
  try:
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(RUNTIME_SOURCE, runtime_target)
    wrote_runtime = True
    modeld_path.write_text(patched, encoding="utf-8")
    wrote_modeld = True
    py_compile.compile(str(modeld_path), doraise=True)
    py_compile.compile(str(runtime_target), doraise=True)
    verify_control_path_unchanged(original, modeld_path.read_text(encoding="utf-8"))
  except BaseException:
    if wrote_modeld:
      modeld_path.write_text(original, encoding="utf-8")
    if wrote_runtime:
      unlink_if_exists(runtime_target)
    raise

  return {
    "originalBlob": blob,
    "backup": str(backup),
    "patchedModeldSha256": sha256(modeld_path),
    "runtimeSha256": sha256(runtime_target),
  }


def restore_patch(repo: Path, session_dir: Path, expected_blob: str) -> dict:
  modeld_path = repo / TARGET_MODELD_PATH
  runtime_target = repo / TARGET_RUNTIME_PATH
  backup = session_dir / "backup/modeld.py.original"
  if not backup.is_file():
    raise RuntimeError(f"missing original backup: {backup}")
  modeld_path.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
  unlink_if_exists(runtime_target)
  restored_blob = git(repo, "hash-object", TARGET_MODELD_PATH)
  if restored_blob != expected_blob:
    raise RuntimeError(f"restore blob mismatch got={restored_blob} expected={expected_blob}")
  dirty = git(repo, "status", "--porcelain", "--", TARGET_MODELD_PATH, TARGET_RUNTIME_PATH)
  if dirty:
    raise RuntimeError(f"restore left target files dirty:\n{dirty}")
  return {"restoredBlob": restored_blob, "targetFilesClean": True}


def run_receiver(duration_s: float, socket_path: Path, raw_path: Path, summary_path: Path) -> subprocess.Popen:
  env = dict(os.environ)
  env["PYTHONPATH"] = str(PROJECT_ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
  cmd = [
    sys.executable, str(RECEIVER_SCRIPT),
    "--socket", str(socket_path),
    "--duration", str(duration_s),
    "--output", str(raw_path),
    "--summary-output", str(summary_path),
  ]
  proc = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
  deadline = time.monotonic() + 5.0
  while time.monotonic() < deadline:
    if socket_path.exists():
      return proc
    if proc.poll() is not None:
      stdout, stderr = proc.communicate()
      raise RuntimeError(f"tap receiver exited early rc={proc.returncode} stdout={stdout} stderr={stderr}")
    time.sleep(0.05)
  proc.terminate()
  raise RuntimeError("tap receiver socket did not appear")


def build_report(session_dir: Path, limits: Path | None, deadline_ms: float) -> dict:
  json_out = session_dir / "commissioning_qualification.json"
  md_out = session_dir / "commissioning_qualification.md"
  cmd = [
    sys.executable, str(REPORT_SCRIPT),
    "--t0", str(session_dir / "T0.jsonl"),
    "--t1", str(session_dir / "T1.jsonl"),
    "--t2", str(session_dir / "T2.jsonl"),
    "--t3", str(session_dir / "T3.jsonl"),
    "--t3-tap-summary", str(session_dir / "T3_tap_summary.json"),
    "--deadline-ms", str(deadline_ms),
    "--json-output", str(json_out),
    "--md-output", str(md_out),
  ]
  if limits is not None:
    cmd += ["--limits", str(limits)]
  env = dict(os.environ)
  env["PYTHONPATH"] = str(PROJECT_ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
  result = subprocess.run(cmd, text=True, capture_output=True, env=env, check=False)
  if result.returncode not in (0, 2):
    raise RuntimeError(f"qualification report failed rc={result.returncode}: {result.stderr.strip()}")
  data = json.loads(json_out.read_text(encoding="utf-8"))
  return {"status": data.get("overallStatus"), "json": str(json_out), "markdown": str(md_out)}


def default_session_dir() -> Path:
  stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  root = Path("/data/egpu_future/commissioning") if Path("/data").is_dir() else Path.cwd() / "commissioning_runs"
  return root / stamp


def source_preflight(repo: Path, expect_unpatched: bool) -> dict:
  if not repo.is_dir():
    raise RuntimeError(f"missing repo: {repo}")
  modeld_path = repo / TARGET_MODELD_PATH
  runtime_target = repo / TARGET_RUNTIME_PATH
  if not modeld_path.is_file():
    raise RuntimeError(f"missing modeld: {modeld_path}")
  head = git(repo, "rev-parse", "HEAD")
  blob = git(repo, "hash-object", TARGET_MODELD_PATH)
  text = modeld_path.read_text(encoding="utf-8")
  patched = "EGPU-FUTURE SHADOW TAP" in text
  runtime_exists = runtime_target.exists()

  if expect_unpatched:
    dirty = git(repo, "status", "--porcelain", "--", TARGET_MODELD_PATH, TARGET_RUNTIME_PATH)
    if dirty:
      raise RuntimeError(f"target files are dirty:\n{dirty}")
    if patched or runtime_exists:
      raise RuntimeError("fresh T0 requires unpatched modeld and no tap runtime")
    if blob != PINNED_MODELD_GIT_BLOB:
      raise RuntimeError(f"modeld blob mismatch got={blob} expected={PINNED_MODELD_GIT_BLOB}")
  else:
    if not patched or not runtime_exists:
      raise RuntimeError("resume requires patched modeld and installed tap runtime after reboot")

  return {
    "carrotHead": head,
    "latestReviewedHead": PINNED_CARROT_HEAD,
    "headMatchesLatestReviewed": head == PINNED_CARROT_HEAD,
    "modeldBlob": blob,
    "patched": patched,
    "runtimeExists": runtime_exists,
  }


def load_manifest(session_dir: Path) -> tuple[Path, dict]:
  path = session_dir / "manifest.json"
  if not path.is_file():
    raise RuntimeError(f"missing manifest: {path}")
  return path, json.loads(path.read_text(encoding="utf-8"))


def write_manifest(path: Path, manifest: dict) -> None:
  manifest["updatedUtc"] = datetime.now(timezone.utc).isoformat()
  path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_preflight(args) -> int:
  repo = args.repo.resolve()
  pf = source_preflight(repo, expect_unpatched=True)
  print(json.dumps({"sourcePreflight": "PASS", "bootId": boot_id(), **pf}, ensure_ascii=False, indent=2))
  return 0


def command_prepare(args) -> int:
  repo = args.repo.resolve()
  session_dir = (args.session_dir or default_session_dir()).resolve()
  source_pf = source_preflight(repo, expect_unpatched=True)
  wait_for_stationary_runtime(repo)
  unlink_if_exists(args.control_path)
  unlink_if_exists(args.socket_path)

  session_dir.mkdir(parents=True, exist_ok=False)
  manifest = {
    "schemaVersion": 2,
    "status": "PREPARING",
    "startedUtc": datetime.now(timezone.utc).isoformat(),
    "repo": str(repo),
    "projectRoot": str(PROJECT_ROOT),
    "prepareBootId": boot_id(),
    "sourcePreflight": source_pf,
    "configuration": {
      "durationSecondsPerStage": args.duration,
      "deadlineMs": args.deadline_ms,
      "limits": str(args.limits.resolve()) if args.limits else None,
      "controlPath": str(args.control_path),
      "socketPath": str(args.socket_path),
    },
    "stages": {},
  }
  manifest_path = session_dir / "manifest.json"
  write_manifest(manifest_path, manifest)

  try:
    manifest["stages"]["T0"] = capture_stage(repo, "T0", args.duration, session_dir / "T0.jsonl")
    manifest["patch"] = apply_patch(repo, session_dir)
    manifest["status"] = "AWAITING_REBOOT_FOR_T1"
    write_manifest(manifest_path, manifest)
    print(json.dumps({
      "status": manifest["status"],
      "sessionDir": str(session_dir),
      "manifest": str(manifest_path),
      "next": f"After a full device reboot, run: {Path(__file__).name} resume {session_dir}",
    }, ensure_ascii=False, indent=2))
    return 0
  except BaseException as exc:
    manifest["status"] = "PREPARE_ABORTED"
    manifest["error"] = repr(exc)
    if "patch" in manifest:
      try:
        manifest["restore"] = restore_patch(repo, session_dir, manifest["patch"]["originalBlob"])
      except Exception as restore_exc:
        manifest["restore"] = {"failed": True, "error": repr(restore_exc)}
    write_manifest(manifest_path, manifest)
    print(json.dumps({"status": manifest["status"], "error": repr(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
    return 3


def command_resume(args) -> int:
  session_dir = args.session_dir.resolve()
  manifest_path, manifest = load_manifest(session_dir)
  repo = Path(manifest["repo"]).resolve()
  if manifest.get("status") != "AWAITING_REBOOT_FOR_T1":
    raise RuntimeError(f"session is not awaiting T1 reboot: status={manifest.get('status')}")
  current_boot = boot_id()
  if current_boot == manifest.get("prepareBootId"):
    raise RuntimeError("full device reboot has not occurred since T0/patch preparation")

  source_pf = source_preflight(repo, expect_unpatched=False)
  wait_for_stationary_runtime(repo)
  control_path = Path(manifest["configuration"]["controlPath"])
  socket_path = Path(manifest["configuration"]["socketPath"])
  unlink_if_exists(control_path)
  unlink_if_exists(socket_path)
  duration = float(manifest["configuration"]["durationSecondsPerStage"])
  limits = Path(manifest["configuration"]["limits"]) if manifest["configuration"].get("limits") else None
  deadline_ms = float(manifest["configuration"]["deadlineMs"])
  receiver = None

  manifest["resumeBootId"] = current_boot
  manifest["resumeSourcePreflight"] = source_pf
  manifest["status"] = "RUNNING_T1_T3"
  write_manifest(manifest_path, manifest)

  try:
    manifest["stages"]["T1"] = capture_stage(repo, "T1", duration, session_dir / "T1.jsonl")

    control_path.parent.mkdir(parents=True, exist_ok=True)
    control_path.write_text("1\n", encoding="utf-8")
    unlink_if_exists(socket_path)
    time.sleep(0.5)
    manifest["stages"]["T2"] = capture_stage(repo, "T2", duration, session_dir / "T2.jsonl")

    receiver = run_receiver(duration + 1.0, socket_path, session_dir / "T3_tap.jsonl", session_dir / "T3_tap_summary.json")
    manifest["stages"]["T3"] = capture_stage(repo, "T3", duration, session_dir / "T3.jsonl")
    try:
      stdout, stderr = receiver.communicate(timeout=5.0)
    except subprocess.TimeoutExpired:
      receiver.terminate()
      stdout, stderr = receiver.communicate(timeout=3.0)
    if receiver.returncode not in (0, -signal.SIGTERM):
      raise RuntimeError(f"T3 receiver failed rc={receiver.returncode}: {stderr.strip()}")
    manifest["t3ReceiverStdout"] = stdout.strip()
    receiver = None

    unlink_if_exists(control_path)
    time.sleep(0.5)
    manifest["qualification"] = build_report(session_dir, limits, deadline_ms)
    manifest["restore"] = restore_patch(repo, session_dir, manifest["patch"]["originalBlob"])
    manifest["status"] = "SOURCE_RESTORED_FINAL_REBOOT_RECOMMENDED"
    write_manifest(manifest_path, manifest)
    print(json.dumps({
      "status": manifest["status"],
      "qualification": manifest["qualification"],
      "sessionDir": str(session_dir),
      "note": "Source is restored. The currently running manager/modeld still has the patched module in memory with tap disabled; reboot once more for byte-for-byte runtime restoration.",
    }, ensure_ascii=False, indent=2))
    return 0

  except BaseException as exc:
    unlink_if_exists(control_path)
    if receiver is not None and receiver.poll() is None:
      receiver.terminate()
      try:
        receiver.communicate(timeout=3.0)
      except subprocess.TimeoutExpired:
        receiver.kill()
    unlink_if_exists(socket_path)
    manifest["status"] = "RESUME_ABORTED"
    manifest["error"] = repr(exc)
    try:
      manifest["restore"] = restore_patch(repo, session_dir, manifest["patch"]["originalBlob"])
    except Exception as restore_exc:
      manifest["restore"] = {"failed": True, "error": repr(restore_exc)}
    write_manifest(manifest_path, manifest)
    print(json.dumps({"status": manifest["status"], "error": repr(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
    return 3


def command_finalize(args) -> int:
  session_dir = args.session_dir.resolve()
  manifest_path, manifest = load_manifest(session_dir)
  repo = Path(manifest["repo"]).resolve()
  if manifest.get("status") != "SOURCE_RESTORED_FINAL_REBOOT_RECOMMENDED":
    raise RuntimeError(f"session is not awaiting final reboot verification: status={manifest.get('status')}")
  current_boot = boot_id()
  if current_boot == manifest.get("resumeBootId"):
    raise RuntimeError("final reboot has not occurred since T1-T3/source restore")
  pf = source_preflight(repo, expect_unpatched=True)
  wait_for_stationary_runtime(repo)
  manifest["finalBootId"] = current_boot
  manifest["finalSourcePreflight"] = pf
  manifest["status"] = "COMPLETED_RUNTIME_RESTORED"
  manifest["completedUtc"] = datetime.now(timezone.utc).isoformat()
  write_manifest(manifest_path, manifest)
  print(json.dumps({"status": manifest["status"], "qualification": manifest.get("qualification"), "sessionDir": str(session_dir)}, ensure_ascii=False, indent=2))
  return 0


def add_common_capture_args(parser) -> None:
  parser.add_argument("--duration", type=float, default=60.0, help="seconds per stage")
  parser.add_argument("--limits", type=Path, default=None, help="explicit gate policy; omitted -> HOLD")
  parser.add_argument("--deadline-ms", type=float, default=50.0, help="research reporting deadline only")
  parser.add_argument("--control-path", type=Path, default=DEFAULT_CONTROL_PATH)
  parser.add_argument("--socket-path", type=Path, default=DEFAULT_SOCKET_PATH)


def main() -> int:
  ap = argparse.ArgumentParser(description="Reboot-aware stationary T0-T3 Carrot eGPU commissioning")
  sub = ap.add_subparsers(dest="command", required=True)

  p0 = sub.add_parser("preflight", help="source-only preflight; no changes")
  p0.add_argument("repo", type=Path)
  p0.set_defaults(func=command_preflight)

  pp = sub.add_parser("prepare", help="capture T0 and stage the tap patch, then stop for reboot")
  pp.add_argument("repo", type=Path)
  pp.add_argument("--session-dir", type=Path, default=None)
  add_common_capture_args(pp)
  pp.set_defaults(func=command_prepare)

  pr = sub.add_parser("resume", help="after reboot: run T1/T2/T3, report, and restore source")
  pr.add_argument("session_dir", type=Path)
  pr.set_defaults(func=command_resume)

  pf = sub.add_parser("finalize", help="after final reboot: verify original runtime/source restored")
  pf.add_argument("session_dir", type=Path)
  pf.set_defaults(func=command_finalize)

  args = ap.parse_args()
  if hasattr(args, "duration") and args.duration <= 0:
    raise SystemExit("--duration must be > 0")
  try:
    return int(args.func(args))
  except Exception as exc:
    print(json.dumps({"status": "ERROR", "error": repr(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
    return 4


if __name__ == "__main__":
  raise SystemExit(main())
