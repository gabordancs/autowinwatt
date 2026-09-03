# WinWatt runtime mapping protokoll

## Cél

A WinWatt felületének állapotfüggő, reprodukálható feltérképezése anélkül, hogy üzemi projektet vagy felhasználói adatot módosítanánk.

Az eredmény a `winwatt_automation/data/runtime_maps/` könyvtárban tárolt, strukturált tudásbázis: ablakok, főmenük, almenük, menüsorok, dialógusok, vezérlők, állapotátmenetek és a végrehajtás bizonyítékai.

## Kötelező előfeltételek

- 32 bites Python-virtuális környezet, mert a WinWatt 9.60 (`WinWatt32.exe`) 32 bites alkalmazás.
- A repo saját, kizárólag mappingre használt tesztprojektje: `winwatt_automation/tests/testwwp.wwp`.
- Nincs nem mentett munka a WinWattban.
- Kifejezett engedély a WinWatt kontrollált leállítására és újraindítására.

## Biztonsági szerződés

- Az alapértelmezett futás nem zárja be a WinWattot.
- A tiszta `no_project` és `project_open` állapotok reprodukálásához szükséges újraindítást a `--allow-process-restart` kapcsoló engedélyezi.
- A futás utáni bezárás csak a `--close-winwatt-after-mapping` kapcsolóval kérhető.
- `--safe-mode safe` módban a mapper kizárólag a jóváhagyott `tests/testwwp.wwp` tesztprojektet nyithatja meg.
- Üzemi `.wwp` fájlt safe módban nem szabad megadni.

## Mapping-szakaszok

1. Kapcsolódás és főablak-azonosítás.
2. `no_project` állapot snapshotja és a főmenük bejárása.
3. A tesztprojekt kontrollált megnyitása.
4. `project_open` állapot snapshotja és a főmenük bejárása.
5. Állapotdiff és knowledge-verification generálása.
6. A lefedettség, hibák, modalok és nem bizonyított útvonalak kiértékelése.

## Ajánlott első teljes futás

PowerShellben, a 32 bites virtuális környezet aktiválása után:

```powershell
cd winwatt_automation
python -m winwatt_automation.scripts.map_full_program `
  --safe-mode safe `
  --allow-process-restart `
  --diagnostic-fast-mode `
  --max-submenu-depth 1 `
  --output-dir data/runtime_maps/first_live_9_60
```

Ez szándékosan nem tartalmaz `--close-winwatt-after-mapping` kapcsolót, így az eredmény ellenőrizhető, mielőtt bármi bezárná az alkalmazást.

## Elfogadási feltételek egy mapping-futáshoz

- A run log `success=true` értéket rögzít.
- Mindkét állapot (`no_project`, `project_open`) rendelkezik snapshot-, menü- és action-katalógussal.
- A `project_open` eredményében a megfigyelt útvonal megegyezik a repo tesztprojektjével.
- A `summary.md` nem csak főmenüket, hanem bizonyított almenüútvonalakat is tartalmaz.
- A `knowledge_summary.md` számszerűsíti a lefedett és hiányzó útvonalakat.
- Minden modal/dialógus esetén rögzítve van a kiváltó művelet, a felismert vezérlők és a helyreállítás eredménye.

## Következő iterációk

- Mélyíteni a menübejárást fokozatosan: 1, majd 2, végül korlátlan mélység.
- A nem címkézett geometriai sorokat célzott single-row probe-pal osztályozni.
- A dialógusokhoz idempotens nyitó/záró workflow-t és ellenőrizhető postconditiont készíteni.
- Csak bizonyított locatorokból építeni későbbi természetes nyelvű parancsokat.
