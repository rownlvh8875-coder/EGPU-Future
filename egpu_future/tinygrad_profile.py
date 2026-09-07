"""Pure-Python analysis helpers for tinygrad hardware profile data.

The current tinygrad HCQ path records device-side start/end timestamps around
kernel execution when PROFILE=1 and also stores a ProfileDeviceEvent clock
offset. This module intentionally avoids importing tinygrad so aggregation and
host-clock alignment can be unit-tested on GitHub Actions.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Any, Iterable

from egpu_future.interference import percentile


@dataclass(frozen=True)
class KernelRange:
  device: str
  name: str
  start_us: float
  end_us: float

  @property
  def duration_ms(self) -> float:
    return (self.end_us - self.start_us) / 1000.0


def _float(value: Any) -> float | None:
  try:
    out = float(value)
  except (TypeError, ValueError):
    return None
  return out if isfinite(out) else None


def _name(value: Any) -> str:
  if hasattr(value, "display_name"):
    return str(value.display_name)
  return str(value)


def _field(event: Any, key: str, default=None):
  return event.get(key, default) if isinstance(event, dict) else getattr(event, key, default)


def normalize_profile_event(event: Any) -> KernelRange | None:
  """Normalize a tinygrad range event or dict without importing tinygrad.

  tinygrad ProfileRangeEvent fields are currently `device`, `name`, `st`, and
  `en`. HCQ timestamps are represented in microseconds, so this module keeps
  the normalized clock in microseconds and reports durations in milliseconds.
  """
  device = _field(event, "device")
  name = _field(event, "name")
  st = _field(event, "st", _field(event, "start_us"))
  en = _field(event, "en", _field(event, "end_us"))

  start_us, end_us = _float(st), _float(en)
  if device is None or name is None or start_us is None or end_us is None:
    return None
  if end_us < start_us:
    return None
  return KernelRange(str(device), _name(name), start_us, end_us)


def device_clock_offsets_us(events: Iterable[Any]) -> dict[str, float]:
  """Return tinygrad ProfileDeviceEvent device->host clock offsets in us."""
  offsets: dict[str, float] = {}
  for event in events:
    device = _field(event, "device")
    tdiff = _float(_field(event, "tdiff"))
    # Range events have st/en; device-clock events do not.
    if device is None or tdiff is None or _field(event, "st") is not None:
      continue
    offsets[str(device)] = tdiff
  return offsets


def normalize_profile_events(
  events: Iterable[Any],
  device_prefix: str | None = None,
  *,
  align_to_host: bool = False,
) -> list[KernelRange]:
  events_list = list(events)
  offsets = device_clock_offsets_us(events_list) if align_to_host else {}
  out: list[KernelRange] = []
  for event in events_list:
    row = normalize_profile_event(event)
    if row is None:
      continue
    if device_prefix is not None and not row.device.upper().startswith(device_prefix.upper()):
      continue
    if align_to_host:
      offset = offsets.get(row.device)
      if offset is None:
        # Match tinygrad viz semantics: no offset means no clock correction.
        offset = 0.0
      row = replace(row, start_us=row.start_us + offset, end_us=row.end_us + offset)
    out.append(row)
  return sorted(out, key=lambda r: (r.start_us, r.end_us, r.device, r.name))


def _stats(values: list[float]) -> dict:
  return {
    "samples": len(values),
    "meanMs": sum(values) / len(values) if values else None,
    "p50Ms": percentile(values, 0.50),
    "p95Ms": percentile(values, 0.95),
    "p99Ms": percentile(values, 0.99),
    "maxMs": max(values) if values else None,
    "totalMs": sum(values),
  }


def union_busy_us(rows: list[KernelRange]) -> float:
  if not rows:
    return 0.0
  intervals = sorted((r.start_us, r.end_us) for r in rows)
  busy = 0.0
  cur_st, cur_en = intervals[0]
  for st, en in intervals[1:]:
    if st <= cur_en:
      cur_en = max(cur_en, en)
    else:
      busy += cur_en - cur_st
      cur_st, cur_en = st, en
  busy += cur_en - cur_st
  return busy


def summarize_kernel_ranges(rows: list[KernelRange], top_n: int = 20) -> dict:
  if not rows:
    return {
      "samples": 0,
      "devices": [],
      "spanMs": None,
      "unionBusyMs": 0.0,
      "unionBusyPercent": None,
      "kernelStats": _stats([]),
      "topKernels": [],
    }

  first_us = min(r.start_us for r in rows)
  last_us = max(r.end_us for r in rows)
  span_us = max(0.0, last_us - first_us)
  busy_us = union_busy_us(rows)
  durations = [r.duration_ms for r in rows]

  by_name: dict[tuple[str, str], list[float]] = {}
  for row in rows:
    by_name.setdefault((row.device, row.name), []).append(row.duration_ms)

  ranked = []
  for (device, name), vals in by_name.items():
    stats = _stats(vals)
    ranked.append({"device": device, "name": name, **stats})
  ranked.sort(key=lambda r: (r["totalMs"], r["maxMs"] or 0.0), reverse=True)

  return {
    "samples": len(rows),
    "devices": sorted({r.device for r in rows}),
    "firstTimestampUs": first_us,
    "lastTimestampUs": last_us,
    "spanMs": span_us / 1000.0,
    "unionBusyMs": busy_us / 1000.0,
    "unionBusyPercent": (busy_us / span_us * 100.0) if span_us > 0 else None,
    "kernelStats": _stats(durations),
    "topKernels": ranked[:max(0, top_n)],
  }


def summarize_profile_events(events: Iterable[Any], device_prefix: str = "QCOM", top_n: int = 20) -> dict:
  events_list = list(events)
  raw_rows = normalize_profile_events(events_list, device_prefix=device_prefix)
  host_rows = normalize_profile_events(events_list, device_prefix=device_prefix, align_to_host=True)
  offsets = device_clock_offsets_us(events_list)
  return {
    "devicePrefix": device_prefix,
    "timingBasis": "tinygrad HCQ ProfileRangeEvent hardware timestamps",
    "timestampUnit": "microseconds",
    "deviceClockOffsetsUs": {k: v for k, v in offsets.items() if k.upper().startswith(device_prefix.upper())},
    "rawDeviceClock": summarize_kernel_ranges(raw_rows, top_n=top_n),
    "hostAlignedClock": summarize_kernel_ranges(host_rows, top_n=top_n),
  }
