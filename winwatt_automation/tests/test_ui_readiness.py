from types import SimpleNamespace

from winwatt_automation.research.ui_readiness import recover_transient_ui_readiness, wait_for_ui_ready


class Explorer:
    def __init__(self, samples): self.samples = iter(samples)
    def inspect_window(self):
        count, fp = next(self.samples)
        return SimpleNamespace(controls=[object()] * count, state_fingerprint=fp)


def test_delayed_ui_becomes_ready() -> None:
    result, snapshot = wait_for_ui_ready(Explorer([(0, "empty"), (0, "empty"), (15, "A"), (15, "A")]), timeout_seconds=2, interval_seconds=0)
    assert result.ready and result.fingerprint == "A" and snapshot.state_fingerprint == "A"


def test_unstable_ui_waits_for_stable_state() -> None:
    result, _ = wait_for_ui_ready(Explorer([(10, "A"), (12, "B"), (12, "B")]), timeout_seconds=2, interval_seconds=0)
    assert result.ready and result.fingerprint == "B"


def test_never_ready_is_not_a_state() -> None:
    class Empty:
        def inspect_window(self): return SimpleNamespace(controls=[], state_fingerprint="da39")
    result, snapshot = wait_for_ui_ready(Empty(), timeout_seconds=0.01, interval_seconds=0)
    assert not result.ready and result.reason == "ui_not_ready:zero_controls" and snapshot is None


def test_transient_unstable_state_recovers_without_planner_or_action() -> None:
    explorer = Explorer([(10, "A"), (11, "B"), (12, "C"), (12, "C")])
    result, snapshot, recovery = recover_transient_ui_readiness(explorer, retries=2, backoff_seconds=(0, 0))
    assert result.ready and snapshot.state_fingerprint == "C"
    assert recovery.recovered and recovery.attempts == 1


def test_persistent_unstable_state_exhausts_bounded_recovery() -> None:
    explorer = Explorer([(10, "A"), (11, "B")] * 20)
    result, snapshot, recovery = recover_transient_ui_readiness(explorer, retries=2, backoff_seconds=(0, 0))
    assert not result.ready and snapshot is None
    assert not recovery.recovered and recovery.attempts == 2
