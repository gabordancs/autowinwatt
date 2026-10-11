"""Query and audit the local Hungarian certification knowledge package."""
from __future__ import annotations

import argparse
import json

from winwatt_automation.knowledge.certification_domain import (
    PROJECT_ROOT,
    audit_domain_knowledge,
    load_domain_knowledge,
    load_source_manifest,
)


def _citation(citation, manifest) -> dict[str, object]:
    source = manifest.source(citation.source_id)
    return {
        "source_id": source.source_id,
        "path": str((PROJECT_ROOT.parent / manifest.source_root / source.relative_path).resolve()),
        "sha256": source.sha256,
        "locator": citation.locator,
        "assertion": citation.assertion,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--audit", action="store_true")
    group.add_argument("--topic")
    group.add_argument("--check-id")
    group.add_argument("--workflow")
    group.add_argument("--sources", action="store_true")
    args = parser.parse_args()

    manifest = load_source_manifest()
    knowledge = load_domain_knowledge()

    if args.audit:
        errors = audit_domain_knowledge(knowledge, manifest)
        result = {
            "status": "passed" if not errors else "failed",
            "knowledge_id": knowledge.knowledge_id,
            "manifest_id": manifest.manifest_id,
            "source_count": len(manifest.sources),
            "claim_count": len(knowledge.claims),
            "workflow_stage_count": len(knowledge.workflow),
            "knowledge_check_count": len(knowledge.knowledge_checks),
            "errors": errors,
        }
    elif args.sources:
        result = {
            "manifest_id": manifest.manifest_id,
            "sources": [source.model_dump(mode="json") for source in manifest.sources],
        }
    elif args.topic:
        needle = args.topic.casefold()
        matches = [
            claim for claim in knowledge.claims
            if needle in claim.topic.casefold()
            or needle in claim.claim_id.casefold()
            or needle in claim.claim.casefold()
        ]
        result = {
            "query": args.topic,
            "matches": [
                {
                    **claim.model_dump(mode="json", exclude={"citations"}),
                    "citations": [_citation(item, manifest) for item in claim.citations],
                }
                for claim in matches
            ],
        }
    elif args.check_id:
        check = next(
            (item for item in knowledge.knowledge_checks if item.check_id == args.check_id),
            None,
        )
        if check is None:
            parser.error(f"unknown knowledge check: {args.check_id}")
        result = {
            **check.model_dump(mode="json"),
            "sources": [manifest.source(source_id).model_dump(mode="json") for source_id in check.required_source_ids],
        }
    else:
        needle = args.workflow.casefold()
        stages = [
            stage for stage in knowledge.workflow
            if needle in stage.stage_id.casefold() or needle in stage.title.casefold()
        ]
        result = {
            "query": args.workflow,
            "matches": [
                {
                    **stage.model_dump(mode="json", exclude={"citations"}),
                    "citations": [_citation(item, manifest) for item in stage.citations],
                }
                for stage in stages
            ],
        }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
