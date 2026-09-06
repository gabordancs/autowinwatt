from winwatt_automation.planner.models import RecentDiscoveredControl, RecentResearchStep
from winwatt_automation.research.orchestrator import select_safe_anonymous_control


def _step(fingerprint: str = "anonymous-menu") -> RecentResearchStep:
    return RecentResearchStep(
        action="auto_inspect", semantic_context="any unknown catalogue", resulting_window="TMenu",
        state_fingerprint=fingerprint,
        discovered_controls=[
            RecentDiscoveredControl(identity="anonymous-1", caption="", control_type="MenuItem", enabled=True),
            RecentDiscoveredControl(identity="disabled", caption="", control_type="MenuItem", enabled=False),
        ],
    )


def test_captionless_enabled_menu_item_is_a_general_effect_candidate() -> None:
    candidate = select_safe_anonymous_control([_step()], set())
    assert candidate is not None
    assert candidate.identity == "anonymous-1"


def test_anonymous_effect_candidate_is_not_repeated_in_same_state() -> None:
    assert select_safe_anonymous_control([_step()], {("anonymous-menu", "anonymous-1")}) is None

