from __future__ import annotations

from winwatt_automation.domain.results import EvidenceItem
from winwatt_automation.domain.room import RoomInput


class VerificationService:
    def verify_rooms(self, expected: list[RoomInput], actual_names: list[str]) -> tuple[bool, list[EvidenceItem]]:
        actual_by_key = {name.casefold(): name for name in actual_names}
        evidence = [
            EvidenceItem(kind="room_exists", message=f"Room {room.name!r} {'found' if room.name.casefold() in actual_by_key else 'missing'}", data={"expected": room.name, "actual": actual_by_key.get(room.name.casefold())})
            for room in expected
        ]
        return all(room.name.casefold() in actual_by_key for room in expected), evidence
