from __future__ import annotations

from loguru import logger

from winwatt_automation.live_ui.locators import LocatorError, find_control


class CommandError(Exception):
    pass



def click_element(form_name: str, element_name: str) -> None:
    """Resolve and click a UI element inside a form."""

    try:
        control = find_control(form_name=form_name, control_name=element_name)
    except LocatorError as error:
        raise CommandError(
            f"Unable to click '{element_name}' in form '{form_name}': {error}"
        ) from error

    logger.info("Clicking element '{}' in form '{}'", element_name, form_name)
    try:
        control.click_input()
    except Exception as error:
        raise CommandError(
            f"Click failed for '{element_name}' in form '{form_name}': {error}"
        ) from error
