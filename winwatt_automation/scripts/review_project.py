"""Launch or export the evidence-first local review project."""
from __future__ import annotations
import argparse
from pathlib import Path
from winwatt_automation.e2e_review.adapters import import_workbook
from winwatt_automation.e2e_review.exporter import export_approved_workbook
from winwatt_automation.e2e_review.persistence import ReviewStore

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("workbook",type=Path); parser.add_argument("--database",type=Path,default=Path("review.sqlite")); parser.add_argument("--pdf-root",type=Path,default=Path(".")); parser.add_argument("--reviewer",default="local-reviewer"); parser.add_argument("--export",type=Path); args=parser.parse_args()
    store=ReviewStore(args.database)
    try:
        imported=store.seed(import_workbook(args.workbook))
        print(f"Imported {imported} new candidates; total {len(store.list())}.")
        if args.export:
            print(export_approved_workbook(args.workbook,args.export,store)); return 0
        from winwatt_automation.e2e_review.gui import run_gui
        return run_gui(store,args.pdf_root,args.reviewer)
    finally: store.close()

if __name__ == "__main__": raise SystemExit(main())
