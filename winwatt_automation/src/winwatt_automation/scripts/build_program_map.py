from pathlib import Path

from winwatt_automation.parser.program_map import build_program_map

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def main() -> None:
    result = build_program_map(
        xml_path=PROJECT_ROOT / "data/raw/Hungarian.xml",
        output_dir=PROJECT_ROOT / "data/parsed",
    )
    counts = result["counts"]
    print("Program map generated.")
    print(f"forms: {counts['forms']}")
    print(f"controls: {counts['controls']}")
    print(f"actions: {counts['actions']}")
    print(f"dialogs: {counts['dialogs']}")
    print(f"workflow_seeds: {counts['workflow_seeds']}")


if __name__ == "__main__":
    main()
