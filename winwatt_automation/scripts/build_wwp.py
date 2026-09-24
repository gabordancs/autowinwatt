from __future__ import annotations
import argparse, json
from pathlib import Path
from winwatt_automation.e2e_review.wwp_builder import build

def main() -> int:
    parser=argparse.ArgumentParser(description="Approved workbook to validated WinWatt WWP")
    parser.add_argument("approved_project",type=Path); parser.add_argument("--output",type=Path,required=True); parser.add_argument("--template-xml",type=Path); parser.add_argument("--catalog-xml",type=Path); parser.add_argument("--execute-winwatt",action="store_true"); parser.add_argument("--report",type=Path)
    args=parser.parse_args(); report=build(args.approved_project,args.output,template_xml=args.template_xml,catalog_xml=args.catalog_xml,execute_winwatt=args.execute_winwatt); target=args.report or args.output.with_name("build_report.json"); target.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps(report,ensure_ascii=False,indent=2)); return 0 if report.get("wwp_created") else 2
if __name__ == "__main__": raise SystemExit(main())
