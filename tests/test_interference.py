from egpu_future.interference import compare_latency_stats, latency_stats_ms


def rows(times_s, ages=None, big=True):
  ages = ages or [0] * len(times_s)
  return [
    {
      "frameId": 100 + i,
      "frameAge": ages[i],
      "modelExecutionTimeS": value,
      "big": big,
    }
    for i, value in enumerate(times_s)
  ]


def test_latency_stats_and_deadline_misses():
  s = latency_stats_ms(rows([0.030, 0.040, 0.060], [0, 1, 2]), deadline_ms=50.0)
  assert s["samples"] == 3
  assert s["meanMs"] == 130.0 / 3.0
  assert s["p50Ms"] == 40.0
  assert s["maxMs"] == 60.0
  assert s["deadlineMisses"] == 1
  assert s["deadlineMissRate"] == 1 / 3
  assert s["frameAgeGt0"] == 2
  assert s["frameAgeGt1"] == 1


def test_big_only_filter():
  mixed = rows([0.030], big=True) + [{
    "frameId": 200,
    "frameAge": 0,
    "modelExecutionTimeS": 0.100,
    "big": False,
  }]
  assert latency_stats_ms(mixed, require_big=True)["samples"] == 1
  assert latency_stats_ms(mixed, require_big=False)["samples"] == 2


def test_compare_reports_latency_delta():
  before = latency_stats_ms(rows([0.030, 0.040]))
  after = latency_stats_ms(rows([0.040, 0.050]))
  d = compare_latency_stats(before, after)
  assert d["mean"]["absoluteMs"] == 10.0
  assert round(d["mean"]["relativePercent"], 6) == round(10 / 35 * 100, 6)
