# Jegyzékek belső nézetek — képernyőképes inventory

Állapot: a `tests/testwwp.wwp` tesztprojekt megnyitva, WinWatt gólya 9.60, 32 bites folyamat.

| Sor | Nézet | Bizonyíték |
| --- | --- | --- |
| 0 | Anyagok | `data/snapshots/catalog_view_probes_9_60/00_Anyagok.png` |
| 1 | Globális szerkezetek adatbázis | `data/snapshots/catalog_view_probes_9_60/01_Globális szerkezetek adatbázis.png` |
| 2 | Szerkezetek | `data/snapshots/catalog_view_probes_light_9_60/02_Szerkezetek.png` |
| 3 | Helyiségek | `data/snapshots/catalog_view_probes_light_9_60/03_Helyiségek.png` |
| 4 | Épületek | `data/snapshots/catalog_view_probes_light_9_60/04_Épületek.png` |
| 5 | Egycsöves körök | `data/snapshots/catalog_view_probes_light_9_60/05_Egycsöves körök.png` |
| 6 | Felületfűtés-hűtés körök | `data/snapshots/catalog_view_probes_light_9_60/06_Felületfűtés-hűtés körök.png` |
| 7 | Ismert teljesítményű fogyasztók | `data/snapshots/catalog_view_probes_light_9_60/07_Ismert teljesítményű fogyasztók.png` |
| 8 | Hőcserélők, keverőszelepek | `data/snapshots/catalog_view_probes_light_9_60/08_Hőcserélők, keverőszelepek.png` |
| 9 | Szakaszok | `data/snapshots/catalog_view_probes_light_9_60/09_Szakaszok.png` |
| 10 | Túláramszelepek | `data/snapshots/catalog_view_probes_light_9_60/10_Túláramszelepek.png` |
| 11 | Nyomáskülönbség szabályozók | `data/snapshots/catalog_view_probes_light_9_60/11_Nyomáskülönbség szabályozók.png` |
| 12 | Csomópontok | `data/snapshots/catalog_view_probes_light_9_60/12_Csomópontok.png` |
| 13 | Hibalista | `data/snapshots/catalog_view_probes_light_9_60/13_Hibalista.png` |

Megállapítások:

- Minden felsorolt ág MDI belső nézetet nyitott; a próba nem módosított adatot és nem választott ki elemet.
- A `Szerkezetek` MDI-nézetben jelenik meg a dinamikus `Szerkesztés` (15 parancs), `Csoport` (3) és `Elem` (7) főmenü.
- Ezek között import/export, törlés, átnevezés és egyéb potenciálisan módosító parancsok vannak, ezért alapértelmezetten nem automatikusak.
- Egy külön, nem megerősítő mélyebb Fájl-menüpróba a `Nyomtatás` (`TPrintingForm`) modált nyitotta meg. Képernyőképe: `data/snapshots/deep_file_used_materials_submenu_9_60.png`; a modált közvetlenül bezártuk, nyomtatás vagy mentés nem történt.

## Projektbeállítások párbeszédablak

- Natív útvonal: `Beállítások` (88) → `ProjektOptions` (90).
- Form osztály: `TProjektOptionsForm`; képernyőkép: `data/snapshots/project_options_probe_9_60.png`; vezérlők: `data/snapshots/project_options_controls_9_60.json` (126 vezérlő).
- Feltárt lapok: Szerkezetek; Épület; Energetika; Energiahordozók; Téli hőszükséglet; Nyári hőterhelés; Radiátorok; Felületfűtés-hűtés; Egycsöves körök; Ismert teljesítményű fogyasztók; Hőcserélők, keverőszelepek; Normál szakaszok; Csomóponti elemek; Fan-coilok; Hőmérséklet szimbólumok.
- A párbeszédablak betöltési/mentési gombokat és OK/Elvet vezérlőket tartalmaz, ezért az automatizálási rétegben kizárólag megnyitás–ellenőrzés–közvetlen bezárás műveletként engedélyezett.

## Súgó tartalom

- Natív útvonal: `Súgó` (97) → `Tartalom` (98).
- A WinWatt saját `WinWatt32.chm` állományát egy külső `HH Parent` ablakban nyitja meg; bizonyíték: `data/snapshots/help_contents_9_60.png`.
- Az ablak tartalomjegyzéket, keresőmezőt, navigációt és nyomtatási gombot tartalmaz. A biztonságos workflow csak az általa megnyitott ablakot zárja vissza, előzetesen meglévő help-ablakhoz nem nyúl.

## Projektadatok

- Natív útvonal: `Fájl` (1) → `ProjektData` (7); form: `TProjektDataForm`.
- A futás 64 vezérlőt azonosított: 32 szerkesztőmező, 13 gomb, 4 kombinált lista, 4 szöveges megjegyzésmező, 3 lapvezérlő, 7 lap és 1 jelölőnégyzet.
- A párbeszédablak adatvédelmi szempontból érzékeny projektmezőket tartalmazhat. A runtime workflow sem értéket, sem képernyőtartalmat nem ad vissza: csak strukturális vezérlő-összesítést, ablakazonosítót és bezárási ellenőrzést.
## XML export (file dialog only)

- Native route: `Fajl` (1) -> `XMLExportAction` (9).
- Runtime target: Windows `#32770` Save As dialog; snapshot: `data/snapshots/xml_export_save_dialog_9_60.png` and `data/snapshots/xml_export_save_dialog_controls_9_60.json` (100 controls).
- The safe mapping workflow opens the dialog, verifies its exact process/class/title identity, then cancels with Escape. It never supplies a path, confirms Save, or creates an export file.

## Used materials submenu

- Native parent: `Fajl` (1) -> `UsedMaterialsItem` (14). Its three native children are 15, 16, and 17.
- Static captions resolve them as `UsedMaterialsPrintAction` (15, `Nyomtatas...`), `UsedMaterialsExportAction` (16, `Export...`), and `UsedMaterialsExportToFileAction` (17, `Export fajlba...`).
- Runtime probes established that 15 opens `TUsedMaterialsPrintingForm`, while both 16 and 17 open `TUsedMaterialsExportForm`. Each was dismissed with Escape before any print, preview, clipboard, or file-export control was activated; the main window recovered afterwards.
- The actual export controls inside those forms remain deliberately uninvoked.

## Energy certificate entry

- Native route: `Fajl` (1) -> `ETAction` (18), captioned as the energy-certificate workflow.
- The route opens `TETDocumentForm` (energy-certificate creation). The mapping probe used Escape to dismiss that exact form and verified that the main window was enabled again.
- No document generation, calculation, preview, print, export, or project-value modification control was invoked.

## Custom reports entry

- Native route: `Fajl` (1) -> `CreateReportAction` (19).
- The first runtime transition is a Windows `#32770` `Megnyitas` file picker, rather than report generation. It was cancelled with Escape and the main window recovered.
- No template was selected and no report was generated or written.

## Helyisegek MDI context

- Opening `Jegyzekek` row 3 produced the Helyisegek MDI context without selecting or editing an item; screenshot: `data/snapshots/deep_rooms_mdi_9_60/03_Helyisegek.png`.
- Its context-sensitive native roots are `Szerkesztes` 187 (12 children), `Csoport` 203 (3), and `Elem` 207 (7), evidenced in `data/runtime_maps/deep_native_menu_rooms_mdi_9_60.json`.
- The corresponding visual menu-popups are in `data/snapshots/deep_rooms_mdi_top_menus_9_60/`. These command IDs differ from the Szerkezetek context (130/146/150), so automation must require an explicitly verified active MDI context before resolving any dynamic command.

## Epuletek MDI context

- Opening `Jegyzekek` row 4 produced the Epuletek MDI context; screenshot: `data/snapshots/deep_buildings_mdi_9_60/04_Epuletek.png`.
- Its dynamic roots are `Szerkesztes` 244 (12 children), `Csoport` 260 (3), and `Elem` 264 (7), recorded in `data/runtime_maps/deep_native_menu_buildings_mdi_9_60.json` and visually in `data/snapshots/deep_buildings_mdi_top_menus_9_60/`.
- The state also adds a ninth `Ablak` child because the newly opened MDI view is now present; menu content therefore depends on both active-view type and the open MDI window set.

## Egycsoves korok MDI context

- Opening `Jegyzekek` row 5 established the Egycsoves korok MDI context; screenshot: `data/snapshots/deep_single_pipe_mdi_9_60/05_Egycsoves korok.png`.
- Its dynamic roots are `Szerkesztes` 301 (12 children), `Csoport` 317 (3), and `Elem` 321 (7), saved in `data/runtime_maps/deep_native_menu_single_pipe_mdi_9_60.json`.
- The `Ablak` root grew to 10 children, proving that its dynamic window-list suffix changes as MDI views are opened.
