# AutoWinWatt MVP – repository audit

Dátum: 2026-09-01.  A dokumentum csak forráskóddal vagy mentett runtime
evidence-szel igazolt állítást tesz; a `verified` itt nem feltételezést jelent.

## Következtetés

Az első MVP megvalósítható a meglévő UI-automatizálási rétegre építve. A
helyiségek létrehozása és a projektmentés bizonyított, a `Helyiségek` lista
visszaolvasása bizonyított. A név biztosan kezelhető; az alapterület,
belmagasság és hőmérséklet automatikus kitöltése és visszaolvasása még nem
igazolt, ezért az első függőleges szeletben csak akkor kapnak értéket, ha a
célzott UI-feltérképezés ezt előbb bizonyítja.

## Bizonyított UI-képességek

| Képesség | Állapot | Konkrét evidence |
| --- | --- | --- |
| Helyiségek jegyzék aktiválása | verified | `runtime_mapping/room_deep_explorer.py:_activate_rooms_catalog_fast()` a `Jegyzékek` natív menüből a rögzített `ROOMS_CATALOG_INDEX` elemet nyitja; UIA-alapú visszaesési útja `activate_rooms_catalog()`. |
| Új helyiség létrehozása | verified | `_create_sandbox_room()` útja: `Elem → Új elem → TNewGroupForm → TRoomModifyForm → Enter`; a végén `_room_list_item()` ellenőrzi a listát. |
| Helyiség megnyitása/szerkesztése | verified | `open_sandbox_room()` kiválasztja a név szerinti `ListItem`-et, majd `Elem` második parancsával `TRoomModifyForm`-ot vár. |
| Projekt mentése | verified | `scripts/create_building_with_rooms.py:_save_project()` a főablak fókuszában `Ctrl+S`-t küld; a 2026-08-31-i sandbox futás ezt minden objektum után használta. |
| Létrehozott név visszaolvasása | verified | `_room_list_item(main, room_name)` UIA `ListItem.window_text()` alapján keresi a nevet. |
| Helyiséghez Külső fal felvétele | verified | `create_building_with_rooms.py:add_external_wall()` és `building_three_rooms_persisted_20260831T153835/creation_report.json`. |
| Alapterület, belmagasság, hőmérséklet írása/visszaolvasása | unverified | A mély állapotgráf mezőit őrzi, de nincs névhez kötött, ismételhető service és save/reopen bizonyíték. |
| Natív projekt-XML import/export | unverified | Csak nem író `safe_xml_export_probe.py` és nem importáló `safe_xml_import_probe.py` létezik. |

## Stabil locator-stratégia

Az MVP ne képernyőkoordinátára épüljön. A már bevált sorrend:

1. projekt és aktív MDI-kontekstus;
2. ablakosztály (`TChildWinForm`, `TNewGroupForm`, `TRoomModifyForm`);
3. vezérlőtípus és felirat (`ListItem`, `Edit`, `Elem`);
4. ismert állapotátmenet és eredmény-ellenőrzés;
5. csak külön kezelt fallbackként natív Win32-koordináta.

Kivétel: a szerkezetválasztó alsó `TListViewWithHeader` listájában a UIA-kattintás
nem állítja be a Delphi natív kijelölést. Itt a `create_building_with_rooms.py`
natív kijelölést alkalmaz, majd `LVM_GETNEXTITEM/LVNI_SELECTED` üzenettel
ellenőriz. Ez bizonyított speciális adapter, nem általános locator-minta.

## Runtime atlasz és folytatható mapping

A mély explorer (`runtime_mapping/room_deep_explorer.py`) minden eltérő
ablakállapothoz `state.json`-t, képet, menü-snapshotot és az előző állapothoz
viszonyított diffet rögzít. Az útvonalak eseménynaplóba azonnal, `fsync`-kel
kerülnek; a gráf és a várólista külön checkpointot kap. Emiatt leállás után
`--resume` pontosan onnan folytat, ahol a napló szerint tartott.

Az utolsó megőrzött Anyagok-kampány:

`winwatt_automation/data/runtime_maps/full_authorized_sandbox/adaptive_anyagok_efficient_v5_20260831T155118/graph/`

Tartalma: `graph.checkpoint.json`, `queue.checkpoint.json`,
`exploration.events.jsonl`, `progress.json`, `states/` és képek. A
`pause.request` fájl jelzi a dokumentáláskor kért biztonságos szünetet. A
folytatáshoz ezt a jelzőt el kell távolítani, majd az alábbi parancs indítható:

```powershell
& .\.venv-win32\Scripts\python.exe -m winwatt_automation.scripts.explore_catalog_profile_deep `
  --profile .\data\runtime_maps\adaptive_catalog_roots\20260831_anyagok\root_profile.json `
  --project .\data\runtime_maps\full_authorized_sandbox\adaptive_anyagok_efficient_v5_20260831T155118\sandbox\testwwp.wwp `
  --output-dir .\data\runtime_maps\full_authorized_sandbox\adaptive_anyagok_efficient_v5_20260831T155118\graph `
  --resume --status-popup --session-islands
```

Az explorer ma már a hibás, kimerített utak mellett az ugyanazon fa- vagy
listaelemhez egy útvonalon belül visszatérő navigációs hurkokat is kihagyja.
Gomb-, menü- és dialógusismétléseket nem szűr, mert azok lehetnek valódi
workflow-lépések.

## XML és Hungarian.xml elhatárolása

`parser/xml_parser.py` a repositoryban lévő `data/raw/Hungarian.xml` statikus
UI-leírását olvassa, és ebből formokat/akciókat katalogizál. Nem WinWatt
projektfájl-import/export adapter. A WinWatt natív XML menüparancsai ugyan
azonosítottak (`MainForm.XMLExportAction`, `MainForm.XMLImportAction`), de a
jelenlegi probe-ok csak a párbeszédablak megjelenését ellenőrzik és megszakítják.
Round-trip nélkül egyetlen domainmező sem jelölhető XML-importálhatóként.

## Első vertical slice – igazolt eredmény

2026-09-01-én a `tests/test_rooms.json` bemenettel lefutott a teljes,
determinista workflow. A kimenet:

`winwatt_automation/data/runtime_maps/mvp_runs/prepare_rooms_20260901T171021Z/operation_result.json`

Igazolt lépések: a fixture másolata → sandbox-épület → `MVP Nappali` és
`MVP Hálószoba` létrehozása → `Projekt mentés másként` → `prepared.wwp`
újranyitása → név szerinti UIA-visszaolvasás. A jelentés `success=true`,
`completed=2`, `verified=true` értéket rögzít. A sima `Projekt mentés` akció
ebben a kiinduló állapotban letiltott; a bizonyított perzisztálási út ezért a
natív `Fájl → Mentés másként…` párbeszédablak.

## MVP-határ és következő sorrend

1. UI-tól független Pydantic `RoomInput`, `PrepareRoomsInput`,
   `OperationResult` modellek.
2. Determinisztikus `RoomService`: név szerinti létrehozás, listázás,
   mentés, ellenőrzés; minden futás eldobható sandbox-kópián.
3. `winwatt prepare-rooms rooms.json` CLI: két egyedi nevű helyiség, mentés,
   újraindítás/újranyitás és expected/actual riport.
4. Csak ezután célzottan feltérképezni és bevezetni a mezőértékeket,
   XML-round-tripet, CSV/Excel-t, majd UI-t és AI-t.

Az AI a későbbi rendszerben kizárólag szemantikus API-t kap (`create_rooms`,
`list_rooms`, `verify_rooms`, `save_project`); a locatorok, replay utak,
native command ID-k és pywinauto objektumok a szolgáltatási réteg belső
implementációs részletei maradnak.
