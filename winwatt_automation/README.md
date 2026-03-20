# WinWatt Automation

Python toolkit to automate the WinWatt desktop application without cloning or modifying WinWatt itself.

## Implemented milestone

- Project scaffold
- XML parser for `Hungarian.xml`
- Pydantic UI models
- Semantic classifier and normalizer
- UI model JSON export
- Typer CLI commands:
  - `parse-xml`
  - `export-ui-model`
  - `list-forms`
  - `list-actions`

## Összefoglaló (magyar)

- Elkészült a kért projektstruktúra (`src/`, `data/`, `tests/`, valamint a package-en belüli `src/winwatt_automation/scripts/`) az első mérföldkőhöz szükséges alapokkal.
- Megvalósult a `Hungarian.xml` feldolgozása Pydantic modellekkel (`UIProperty`, `UIItem`, `UIForm`, `UIModel`).
- Bekerült a szemantikus besorolás és normalizálás (`semantic_role`, `normalized_name`, `normalized_caption`, `stable_key`).
- Elkészült a parancs-regiszter, amely név, űrlap, felirat és elemtípus szerint kereshető.
- Elérhető a CLI-alapú export és listázás (`parse-xml`, `export-ui-model`, `list-forms`, `list-actions`).

## Quick start

> **Monorepo note:** the Python project lives in `winwatt_automation/`.
> If your shell is one level above it, first run `cd winwatt_automation`.

```bash
pip install -r requirements.txt
pip install -e .
python -m winwatt_automation.cli.main parse-xml --xml-path data/raw/Hungarian.xml
python -m winwatt_automation.cli.main list-forms
python -m winwatt_automation.cli.main list-actions
```


## Dialog Explorer quick example

```python
from winwatt_automation.dialog_explorer import explore_dialog

# dialog: pywinauto UIA dialog wrapper
report = explore_dialog(dialog, max_depth=3, safe_mode=True)
print(report["dialog_title"], len(report["controls"]))
```

## Runtime futásnaplók (run logs)

A futásnapló rendszer a repo-n belül ide ír:

- `data/run_logs/index.json` – időrendi futásindex (sorszám, run_id, rövid summary, log/meta útvonal)
- `data/run_logs/latest.txt` – legfrissebb futás gyors szöveges pointere
- `data/run_logs/latest.json` – legfrissebb futás teljes strukturált meta rekordja
- `data/run_logs/runs/*.log` – teljes/kiemelt terminálkimenet
- `data/run_logs/runs/*.json` – strukturált futás meta + summary

### Mit nézzen Codex először?

1. `data/run_logs/latest.txt`
2. `data/run_logs/latest.json`
3. szükség esetén a hivatkozott `runs/<run_id>.log` fájl

### Konkrét futás visszakeresése

- Az `index.json` `runs` tömbjében keresd a `sequence_number` vagy `run_id` mezőt.
- A rekordból a `log_path` és `json_path` megadja a kapcsolódó fájlokat.

### Retention stratégia

Első körben csak a struktúra és a konzisztens index/latest frissítés készült el.
A futáslogok automatikus törlése még nincs bekötve; a helye dokumentálva van `TODO` jelöléssel az indexben és a helper modulban.

## Dev Cycle Controller (helyi fejlesztői vezérlő)

Első iterációban egy CLI-alapú vezérlő érhető el, amely a fejlesztési/test ciklus fő lépéseit fogja össze a repón belül.

### Cél

- `git pull` / `git status` / opcionális `git add`-`commit`-`push`
- run log (`data/run_logs/latest.json`, `latest.txt`, `index.json`) gyors kiolvasása
- ChatGPT-be bemásolható brief készítése (`data/chat_prep/latest_chat_brief.txt`)
- WinWatt folyamat indítás/ellenőrzés/lezárás (óvatos alapértelmezések)
- script futtatás egységesen timeout kezeléssel

### Fő modulok

- `src/winwatt_automation/controller/config.py` – környezeti változók + fallback konfiguráció
- `src/winwatt_automation/controller/git_ops.py` – git parancs wrapper
- `src/winwatt_automation/controller/runlog_reader.py` – latest run log betöltés
- `src/winwatt_automation/controller/chat_brief_builder.py` – másolható státusz/prompt blokk
- `src/winwatt_automation/controller/winwatt_process.py` – WinWatt process kezelés
- `src/winwatt_automation/controller/script_runner.py` – script futtatás timeouttal
- `src/winwatt_automation/controller/dev_cycle_controller.py` – orchestration réteg
- `src/winwatt_automation/scripts/dev_cycle_controller.py` – CLI entrypoint

### Konfiguráció (env)

- `WWA_CONTROLLER_PYTHON` – Python executable (default: aktuális interpreter)
- `WWA_WINWATT_EXE_PATH` – WinWatt `.exe` útvonal
- `WWA_CONTROLLER_TIMEOUT_SECONDS` – default timeout (default: `300`)
- `WWA_CONTROLLER_SAFE_MODE` – `safe|caution|blocked` (default: `safe`)
- `WWA_CHAT_BRIEF_OUTPUT` – chat brief output path (default: `data/chat_prep/latest_chat_brief.txt`)

### Használat

```bash
python -m winwatt_automation.scripts.dev_cycle_controller status
python -m winwatt_automation.scripts.dev_cycle_controller pull
python -m winwatt_automation.scripts.dev_cycle_controller prepare-chat --goal "Mai cél" --request "Mi legyen a következő lépés?"
python -m winwatt_automation.scripts.dev_cycle_controller start-winwatt
python -m winwatt_automation.scripts.dev_cycle_controller stop-winwatt
python -m winwatt_automation.scripts.dev_cycle_controller run map_full_program --safe-mode safe --timeout 300
python -m winwatt_automation.scripts.dev_cycle_controller cycle map_full_program --safe-mode safe --timeout 300
python -m winwatt_automation.scripts.dev_cycle_controller add .
python -m winwatt_automation.scripts.dev_cycle_controller commit -m "controller update"
python -m winwatt_automation.scripts.dev_cycle_controller push
```

### Chat brief formátum

A generált fájl fő blokkjai:

- `Cél`
- `Jelenlegi állapot` (branch, git status, latest run adatok)
- `Legfrissebb futás summary`
- `Konkrét kérés`

Ha nincs `latest.json/latest.txt`, fallback szöveget generál.

### Mapping Cycle Orchestrator (MVP)

A meglévő dev-cycle controllerre ráépítve most már van egy kifejezetten a runtime mapping fejlesztési körre optimalizált, fájlalapú orchestration flow is.

#### Fő artefactok

- `data/mapping_cycle/status.json` – milestone/state + legutóbbi ingest/test/handoff állapot
- `data/mapping_cycle/codex_prompt.txt` – következő Codex prompt sablonból generálva
- `data/mapping_cycle/codex_result.json` – szabványos Codex result input
- `data/mapping_cycle/chatgpt_handoff.md` – tömör ChatGPT handoff összefoglaló
- `data/mapping_cycle/log_extract.json` – releváns logminták kivágata

#### Támogatott mezők a Codex resultben

- `diagnosis`
- `changes`
- `files`
- `tests_run`
- `test_results`
- `manual_run_command`
- `expected_logs`
- `open_risks`
- `next_step`
- `commit`

#### Mapping-cycle CLI

```bash
python -m winwatt_automation.scripts.dev_cycle_controller prepare --milestone placeholder_traversal --state active
python -m winwatt_automation.scripts.dev_cycle_controller ingest --result data/mapping_cycle/codex_result.json
python -m winwatt_automation.scripts.dev_cycle_controller test --result data/mapping_cycle/codex_result.json
python -m winwatt_automation.scripts.dev_cycle_controller handoff --result data/mapping_cycle/codex_result.json
python -m winwatt_automation.scripts.dev_cycle_controller mapping-cycle --result data/mapping_cycle/codex_result.json
```

#### WinWatt mappinghez előkészített milestone-ok és logminták

- milestone-ok: `top_menu_stability`, `placeholder_traversal`, `modal_handling`, `recent_projects_policy`, `project_open_transition`, `full_state_mapping`
- default log patternök: `PLACEHOLDER_ACTION_OUTCOME`, `MODAL_CLOSE_RESULT`, `ROOT_MENU_REOPEN_EXECUTED`, `FRESH_ROOT_SNAPSHOT_CAPTURED`, `ACTION_CHANGED_MENU_STATE`, `PROJECT_OPEN_STATE_TRANSITION`, `DBG_PHASE_TIMING phase=subtree_traversal`

### Korlátok (v1)

- Nincs ChatGPT/Codex API integráció (szándékosan).
- A WinWatt "normál bezárás" folyamat-szinten kezelt; UI-s graceful close nem teljes.
- A script runner timeout esetén `terminate` jelet küld, nem végez veszélyes cleanup-ot automatikusan.
- A `cycle` parancs első körben egyszerű, bővíthető workflow.
