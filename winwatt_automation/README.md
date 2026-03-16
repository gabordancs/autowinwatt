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
