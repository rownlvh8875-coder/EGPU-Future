#!/usr/bin/env python3
"""One-command stationary T0-T3 commissioning runner for Carrot eGPU.

This tool is intentionally conservative:
- default invocation is preflight-only; `--run` is required to modify/restart modeld,
- vehicle must remain stationary, selfdrive inactive, and in Park when gear is available,
- UsbGpuActive must stay true,
- the reviewed modeld git blob must match,
- only the two known tap integration files may be modified,
- any failure triggers best-effort rollback to the exact original modeld bytes.

Run from an ignition-on, parked commissioning session. This is not intended for
public-road use or while openpilot is engaged.
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
  # The checkout itself must provide cereal/openpilot. Do not import at module
  # load time so GitHub Actions can compile/test this script without openpilot.
  repo_s = str(repo)
  if repo_s not in sys.path:
    sys.path.insert(0, repo_s)
  try:
    from openpilot.cereal import messaging  # type: ignore
    from openpilot.common.params import Params  # type: ignore
  except Exception as exc:
    raise RuntimeError(f"failed to import openpilot runtime from {repo}: {exc}") from exc
  return messaging, Params


def wait_for_stationary_runtime(repo: Path, timeout_s: float = 20.0, consecutive: int = 5):
  messaging, Params = import_openpilot_runtime(repo)
  sm = messaging.SubMaster(["carState", "selfdriveState", "managerState", "modelV2"])
  good = 0
  deadline = time.monotonic() + timeout_s
  while time.monotonic() < deadline:
    sm.update(1000)
    try:
      assert_stationary(sm)
      if not Params().get_bool("UsbGpuActive"):
        raise RuntimeError("UsbGpuActive is false")
      pid = modeld_pid(sm)
      if pid <= 0:
        raise RuntimeError("modeld is not running")
      good += 1
      if good >= consecutive:
        return sm, Params
    except Exception:
      good = 0
  raise RuntimeError("stationary/eGPU/modeld preflight did not become stable")


def modeld_pid(sm) -> int:
  try:
    for proc in sm["managerState"].processes:
      if str(proc.name) == "modeld" and bool(proc.running):
        return int(proc.pid)
  except Exception:
    pass
  return 0


def restart_modeld_and_wait(repo: Path, timeout_s: float = 35.0) -> dict:
  messaging, Params = import_openpilot_runtime(repo)
  sm = messaging.SubMaster(["managerState", "modelV2", "carState", "selfdriveState"])
  deadline = time.monotonic() + timeout_s
  old_pid = 0
  old_frame = 0
  while time.monotonic() < deadline and old_pid <= 0:
    sm.update(1000)
    assert_stationary(sm)
    old_pid = modeld_pid(sm)
    old_frame = int(getattr(sm["modelV2"], "frameId", 0))
  if old_pid <= 0:
    raise RuntimeError("could not find running modeld PID")

  os.kill(old_pid, signal.SIGINT)
  new_pid = 0
  first_new_frame = 0
  deadline = time.monotonic() + timeout_s
  while time.monotonic() < deadline:
    sm.update(1000)
    assert_stationary(sm)
    pid = modeld_pid(sm)
    if pid > 0 and pid != old_pid:
      new_pid = pid
    if new_pid > 0 and sm.updated["modelV2"]:
      frame = int(getattr(sm["modelV2"], "frameId", 0))
      if frame > 0 and frame != old_frame:
        first_new_frame = frame
        break
  if new_pid <= 0 or first_new_frame <= 0:
    raise RuntimeError(f"modeld did not restart cleanly oldPid={old_pid} newPid={new_pid} frame={first_new_frame}")
  if not Params().get_bool("UsbGpuActive"):
    raise RuntimeError("eGPU did not return active after modeld restart")
  return {"oldPid": old_pid, "newPid": new_pid, "firstNewFrameId": first_new_frame}


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

  elapsed = time.monotonic() - started
  return {
    "stage": stage,
    "durationSeconds": elapsed,
    "samples": samples,
    "invalidModelV2": invalid,
    "frameAgeGt1": frame_age_gt1,
    "frameAgeMax": max_frame_age,
    "continuity": continuity.summary(),
    "output": str(output),
  }


def apply_patch(repo: Path, output_dir: Path) -> dict:
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
  backup_dir = output_dir / "backup"
  backup_dir.mkdir(parents=True, exist_ok=True)
  backup = backup_dir / "modeld.py.original"
  backup.write_text(original, encoding="utf-8")

  runtime_target.parent.mkdir(parents=True, exist_ok=True)
  shutil.copyfile(RUNTIME_SOURCE, runtime_target)
  modeld_path.write_text(patched, encoding="utf-8")
  py_compile.compile(str(modeld_path), doraise=True)
  py_compile.compile(str(runtime_target), doraise=True)
  verify_control_path_unchanged(original, modeld_path.read_text(encoding="utf-8"))
  return {
    "originalText": original,
    "originalBlob": blob,
    "backup": str(backup),
    "patchedModeldSha256": sha256(modeld_path),
    "runtimeSha256": sha256(runtime_target),
  }


def rollback_patch(repo: Path, original_text: str, expected_blob: str) -> dict:
  modeld_path = repo / TARGET_MODELD_PATH
  runtime_target = repo / TARGET_RUNTIME_PATH
  modeld_path.write_text(original_text, encoding="utf-8")
  unlink_if_exists(runtime_target)
  restored_blob = git(repo, "hash-object", TARGET_MODELD_PATH)
  if restored_blob != expected_blob:
    raise RuntimeError(f"rollback blob mismatch got={restored_blob} expected={expected_blob}")
  dirty = git(repo, "status", "--porcelain", "--", TARGET_MODELD_PATH, TARGET_RUNTIME_PATH)
  if dirty:
    raise RuntimeError(f"rollback left target files dirty:\n{dirty}")
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


def build_report(output_dir: Path, limits: Path | None, deadline_ms: float) -> dict:
  json_out = output_dir / "commissioning_qualification.json"
  md_out = output_dir / "commissioning_qualification.md"
  cmd = [
    sys.executable, str(REPORT_SCRIPT),
    "--t0", str(output_dir / "T0.jsonl"),
    "--t1", str(output_dir / "T1.jsonl"),
    "--t2", str(output_dir / "T2.jsonl"),
    "--t3", str(output_dir / "T3.jsonl"),
    "--t3-tap-summary", str(output_dir / "T3_tap_summary.json"),
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


def default_output_dir() -> Path:
  stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  root = Path("/data/egpu_future/commissioning") if Path("/data").is_dir() else Path.cwd() / "commissioning_runs"
  return root / stamp


def preflight(repo: Path, control_path: Path, socket_path: Path) -> dict:
  if not repo.is_dir():
    raise RuntimeError(f"missing repo: {repo}")
  modeld_path = repo / TARGET_MODELD_PATH
  runtime_target = repo / TARGET_RUNTIME_PATH
  if not modeld_path.is_file():
    raise RuntimeError(f"missing modeld: {modeld_path}")
  head = git(repo, "rev-parse", "HEAD")
  blob = git(repo, "hash-object", TARGET_MODELD_PATH)
  dirty = git(repo, "status", "--porcelain", "--", TARGET_MODELD_PATH, TARGET_RUNTIME_PATH)
  if dirty:
    raise RuntimeError(f"target files are dirty:\n{dirty}")
  if "EGPU-FUTURE SHADOW TAP" in modeld_path.read_text(encoding="utf-8"):
    raise RuntimeError("modeld is already patched; restore original before a fresh T0 run")
  if runtime_target.exists():
    raise RuntimeError(f"runtime integration already exists: {runtime_target}")
  if blob != PINNED_MODELD_GIT_BLOB:
    raise RuntimeError(f"modeld blob mismatch got={blob} expected={PINNED_MODELD_GIT_BLOB}")
  if not RUNTIME_SOURCE.is_file() or not RECEIVER_SCRIPT.is_file() or not REPORT_SCRIPT.is_file():
    raise RuntimeError("EGPU-Future commissioning dependencies are incomplete")
  unlink_if_exists(control_path)
  unlink_if_exists(socket_path)
  return {
    "carrotHead": head,
    "latestReviewedHead": PINNED_CARROT_HEAD,
    "headMatchesLatestReviewed": head == PINNED_CARROT_HEAD,
    "modeldBlob": blob,
    "modeldBlobVerified": True,
    "controlPath": str(control_path),
    "socketPath": str(socket_path),
  }


def main() -> int:
  ap = argparse.ArgumentParser(description="Stationary one-command T0-T3 Carrot eGPU commissioning")
  ap.add_argument("repo", type=Path, help="local ajouatom/openpilot checkout")
  ap.add_argument("--run", action="store_true", help="execute T0-T3; without this flag only preflight checks run")
  ap.add_argument("--duration", type=float, default=60.0, help="seconds per stage")
  ap.add_argument("--output-dir", type=Path, default=None)
  ap.add_argument("--limits", type=Path, default=None, help="explicit stage-gate policy JSON; omitted -> HOLD report")
  ap.add_argument("--deadline-ms", type=float, default=50.0, help="research reporting deadline only")
  ap.add_argument("--control-path", type=Path, default=DEFAULT_CONTROL_PATH)
  ap.add_argument("--socket-path", type=Path, default=DEFAULT_SOCKET_PATH)
  ap.add_argument("--keep-patch", action="store_true", help="leave patch installed but disabled after a successful run")
  args = ap.parse_args()
  if args.duration <= 0:
    raise SystemExit("--duration must be > 0")

  repo = args.repo.resolve()
  output_dir = (args.output_dir or default_output_dir()).resolve()
  pf = preflight(repo, args.control_path, args.socket_path)
  print(json.dumps({"preflight": "PASS", **pf}, ensure_ascii=False, indent=2))
  if not args.run:
    print("run=false; no files changed. Re-run with --run from an ignition-on, parked, selfdrive-inactive commissioning session.")
    return 0

  output_dir.mkdir(parents=True, exist_ok=False)
  manifest = {
    "schemaVersion": 1,
    "startedUtc": datetime.now(timezone.utc).isoformat(),
    "repo": str(repo),
    "projectRoot": str(PROJECT_ROOT),
    "preflight": pf,
    "configuration": {
      "durationSecondsPerStage": args.duration,
      "deadlineMs": args.deadline_ms,
      "limits": str(args.limits.resolve()) if args.limits else None,
      "keepPatch": args.keep_patch,
    },
    "stages": {},
    "restarts": [],
    "rollback": None,
  }
  manifest_path = output_dir / "manifest.json"
  patch_info = None
  receiver = None

  try:
    # T0 must be captured before any source modification.
    wait_for_stationary_runtime(repo)
    manifest["stages"]["T0"] = capture_stage(repo, "T0", args.duration, output_dir / "T0.jsonl")

    patch_info = apply_patch(repo, output_dir)
    manifest["patch"] = {k: v for k, v in patch_info.items() if k != "originalText"}
    manifest["restarts"].append({"reason": "load_tap_patch", **restart_modeld_and_wait(repo)})

    unlink_if_exists(args.control_path)
    unlink_if_exists(args.socket_path)
    wait_for_stationary_runtime(repo)
    manifest["stages"]["T1"] = capture_stage(repo, "T1", args.duration, output_dir / "T1.jsonl")

    # T2: dynamic tap enabled, receiver intentionally absent.
    args.control_path.parent.mkdir(parents=True, exist_ok=True)
    args.control_path.write_text("1\n", encoding="utf-8")
    unlink_if_exists(args.socket_path)
    time.sleep(0.5)
    manifest["stages"]["T2"] = capture_stage(repo, "T2", args.duration, output_dir / "T2.jsonl")

    # T3: same enabled tap, but receiver is present; still no shadow inference.
    receiver_duration = args.duration + 1.0
    receiver = run_receiver(
      receiver_duration,
      args.socket_path,
      output_dir / "T3_tap.jsonl",
      output_dir / "T3_tap_summary.json",
    )
    manifest["stages"]["T3"] = capture_stage(repo, "T3", args.duration, output_dir / "T3.jsonl")
    try:
      stdout, stderr = receiver.communicate(timeout=5.0)
    except subprocess.TimeoutExpired:
      receiver.terminate()
      stdout, stderr = receiver.communicate(timeout=3.0)
    if receiver.returncode not in (0, -signal.SIGTERM):
      raise RuntimeError(f"T3 receiver failed rc={receiver.returncode}: {stderr.strip()}")
    manifest["t3ReceiverStdout"] = stdout.strip()
    receiver = None

    unlink_if_exists(args.control_path)
    time.sleep(0.5)
    manifest["qualification"] = build_report(output_dir, args.limits.resolve() if args.limits else None, args.deadline_ms)

    if not args.keep_patch:
      rollback = rollback_patch(repo, patch_info["originalText"], patch_info["originalBlob"])
      manifest["restarts"].append({"reason": "restore_original_modeld", **restart_modeld_and_wait(repo)})
      manifest["rollback"] = rollback
    else:
      manifest["rollback"] = {"skipped": True, "tapDisabled": True}

    manifest["completedUtc"] = datetime.now(timezone.utc).isoformat()
    manifest["status"] = "COMPLETED"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
      "status": manifest["status"],
      "qualification": manifest["qualification"],
      "outputDir": str(output_dir),
      "manifest": str(manifest_path),
    }, ensure_ascii=False, indent=2))
    return 0

  except BaseException as exc:
    manifest["status"] = "ABORTED"
    manifest["error"] = repr(exc)
    unlink_if_exists(args.control_path)
    if receiver is not None and receiver.poll() is None:
      receiver.terminate()
      try:
        receiver.communicate(timeout=3.0)
      except subprocess.TimeoutExpired:
        receiver.kill()
    unlink_if_exists(args.socket_path)

    if patch_info is not None:
      try:
        rollback = rollback_patch(repo, patch_info["originalText"], patch_info["originalBlob"])
        manifest["rollback"] = rollback
        try:
          manifest["restarts"].append({"reason": "abort_restore_original_modeld", **restart_modeld_and_wait(repo)})
        except Exception as restart_exc:
          manifest["rollbackRestartError"] = repr(restart_exc)
      except Exception as rollback_exc:
        manifest["rollback"] = {"failed": True, "error": repr(rollback_exc)}

    manifest["completedUtc"] = datetime.now(timezone.utc).isoformat()
    try:
      manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
      pass
    print(json.dumps({"status": "ABORTED", "error": repr(exc), "outputDir": str(output_dir)}, ensure_ascii=False, indent=2), file=sys.stderr)
    return 3


if __name__ == "__main__":
  raise SystemExit(main())
