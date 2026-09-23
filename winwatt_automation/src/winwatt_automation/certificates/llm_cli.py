"""Optional narrow adapter for a user-installed ChatGPT CLI."""
from __future__ import annotations
import json, os, subprocess
def resolve_unresolved(excerpts: list[str]) -> dict:
    executable=os.environ.get("CHATGPT_CLI_COMMAND","chatgpt")
    prompt={"task":"Extract only explicit layer names, thicknesses and cited page/line evidence. Return JSON. Do not infer missing physical properties.","excerpts":excerpts[:40]}
    completed=subprocess.run([executable,"--json",json.dumps(prompt,ensure_ascii=False)],capture_output=True,text=True,timeout=90,check=True)
    return json.loads(completed.stdout)
