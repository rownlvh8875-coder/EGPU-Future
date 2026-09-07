import json

from integrations.carrot_wip_integrated.runtime.egpu_integration_observer import EgpuIntegrationObserver


def test_observer_writes_backend_and_fallback_state(tmp_path):
  state = tmp_path / "state.json"
  obs = EgpuIntegrationObserver(enabled=True, state_path=state, publish_interval_s=0.1, latency_window=32)
  obs.note_fallback(frame_id=101, reason="runtime_model_execution_failed")
  obs.observe(
    frame_id=101,
    state_frame_id=103,
    attempted_backend="egpu",
    active_backend="qcom",
    model_execution_s=0.041,
  )

  data = json.loads(state.read_text(encoding="utf-8"))
  assert data["frameId"] == 101
  assert data["stateFrameId"] == 103
  assert data["frameAge"] == 2
  assert data["attemptedBackend"] == "egpu"
  assert data["activeBackend"] == "qcom"
  assert data["fallbackCount"] == 1
  assert data["lastFallbackFrameId"] == 101
  assert data["modelExecutionMs"] == 41.0


def test_disabled_observer_is_noop(tmp_path):
  state = tmp_path / "state.json"
  obs = EgpuIntegrationObserver(enabled=False, state_path=state)
  obs.note_fallback(frame_id=1, reason="ignored")
  obs.observe(frame_id=1, state_frame_id=1, attempted_backend="egpu", active_backend="egpu", model_execution_s=1.0)
  assert not state.exists()
  assert obs.fallback_count == 0


def test_observer_write_failure_does_not_escape(tmp_path):
  # Make the requested state path impossible to create by using a regular file as its parent.
  parent_file = tmp_path / "not_a_directory"
  parent_file.write_text("x", encoding="utf-8")
  obs = EgpuIntegrationObserver(enabled=True, state_path=parent_file / "state.json", publish_interval_s=0.1)

  # These calls must never raise into modeld.
  obs.note_fallback(frame_id=7, reason="test")
  obs.observe(frame_id=7, state_frame_id=7, attempted_backend="egpu", active_backend="qcom", model_execution_s=0.02)
  assert obs.write_errors >= 1
