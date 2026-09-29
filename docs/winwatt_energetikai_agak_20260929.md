# Energetikai ágak helyi vizsgálata

Verzió: WinWatt gólya 9.60.0.0; profil: `winwatt_8c137b67c0a2214bb91aeae8`.
A vizsgálat másolt tesztprojekten, 32 bites helyi Pythonnal történt, AI-hívás nélkül.
A megfigyelések a program működését írják le, nem az alkalmazandó előírás kiválasztását.

## Igazolt UI-függőség

Belépési út: **Beállítások → Projekt beállítások → Energetika → Számításhoz
alkalmazott előírás**. A választó kilenc értékét külön-külön beállítottuk,
elfogadtuk, majd újranyitottuk ugyanannak a tesztépületnek a részletezőjét.
Mindegyik állapothoz vezérlőfa és képernyőkép készült.

| Választóértékek | Elérhető épületfülek | Jellegzetes eltérés |
| --- | --- | --- |
| 0–7: a listában található korábbi TNM-változatok és MSZ-04-140-2:1991 | 8 | Energia igény tervezési adatok; Primer energia igény számítása; Becsült éves fogyasztás, CO2 kibocsátás |
| 8: 9/2023. ÉKM rendelet 2023.XI.1-i állapot | 11 | Zónák; Referencia épület adatai; Épülettechnikai rendszerek; Felújítás (szerkezetek); Fotók; PDF fájlok |

Közös öt fül: Általános adatok; Hőszükséglet, fajlagos hőveszteségtényező;
Nyári hőterhelés; Helyiségek; Fűtött teret határoló szerkezetek.

**Következmény:** a három korábban rejtett lap a korábbi számítási ág része.
A 2023-as mód vizsgálatakor nem hiányzó funkcióként kell őket számolni.
Az egyes lapok teljes tartalma, belső kapcsolói és gépészeti gyermekablakai
ettől még külön feltárandók.

## Tájolás: első tartóssági próba

Mező: Épület → Általános adatok → Tájolás. Az adott képernyőn egyetlen látható,
engedélyezett `TEdit`; ezt a kód ellenőrzi, bizonytalan találat esetén megáll.

Az első próba `0 → 42,5°` írást, a meglévő `WinWattService.save_project()`
natív mentését, szabályos bezárást, új folyamatban projektmegnyitást és ugyanazon
épület visszaolvasását tartalmazta. A visszakapott érték **42°**, ezért a próba
helyesen sikertelen: a tizedes pontosság nem bizonyított. Azt külön kell
vizsgálni, hogy a veszteség az ablak elfogadásakor vagy a fájlmentéskor történik:
a mentés előtti UI-snapshot még `42,5` értéket tartalmaz.

Az egész fokértékkel megismételt **0 → 42° → natív mentés → teljes újraindítás
→ 42°** próba sikeres. A script visszaírta az eredeti 0 értéket és mentett;
a 2023-as mód megőrzését és a forrásfájl változatlanságát is ellenőrizte.
Ez az egy mező, ebben a profilban és egész fokértékkel bizonyított;
általános tizedes pontosságot vagy energetikai számítási egyezést nem igazol.

A 2023-as mód újranyitás után is megmaradt, a kiinduló forrásfájl SHA-256
értéke változatlan. A próbák a saját másolataikat módosítják.

## Reprodukálás

Script: `winwatt_automation/src/winwatt_automation/scripts/probe_building_energy_modes.py`.
A `winwatt_automation` könyvtárból, beállított `PYTHONPATH=src` mellett:

```powershell
..\.venv-winwatt32\Scripts\python.exe -m winwatt_automation.scripts.probe_building_energy_modes --profile ../docs/winwatt_local_profile_20260929.json --source <forras.wwp> --output <uj-futasi-mappa>
```

Az output mappa nem létezhet; oda készül a projektmásolat és valamennyi bizonyíték.
A futás kontrolláltan újraindítja a WinWattot. A munkamenet kizárólag a mappingre
használandó. `--skip-mode-survey --angle 42` csak a mezőpróbát futtatja;
`--angle 42.5` a tizedesérték megőrzését vizsgálja. Nincs néma tolerancia vagy
automatikus sikerre minősítés. Hiba esetén a script elmenti a részállapotot.

Nyers bizonyítékok: `../winwatt_automation/data/runtime_maps/e20260929a/report.json`
és az azonos mappa `mode_00`–`mode_08`, `orientation_written`,
`orientation_reopened` JSON/PNG fájljai. A teljes `report.json` összstátusza a
szándékosan szigorú tizedes mezőpróba miatt `failed`, a kilenc mód felvétele sikerült.
A sikeres egészfok-próba: `../winwatt_automation/data/runtime_maps/e20260929b/report.json`,
összstátusza `passed`. A két futás tömör eredménye a
`energy_mode_probe_summary_20260929.json` fájlban is megmarad.

## Következő feltárás

A 2023-as Épülettechnikai rendszerek gyerekablakai és a rendszerek zónákhoz
rendelése következik, majd a tanúsításhoz szükséges mezők további mentési próbái.
A sikeres geometriai mezőpróba önmagában nem igazol energetikai számítást.
