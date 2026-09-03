# Energetikai minőségtanúsítvány ablak feltárása

## Futás dátuma

2026-09-03

## Cél

A WinWatt következő útvonalának runtime feltárása:

`Fájl -> Energetikai minőségtanúsítvány...`

A megnyíló ablak tényleges címe:

`Energetikai minőségtanúsítvány készítése`

## Használt natív parancs

A UIA szövegfelismerése ezen a WinWatt-felületen hibásan több menüpontot
`Végrehajtás` néven adott vissza. Ezért a feltárás a natív Win32 menüazonosítót
használta:

- Fájl szülőparancs: `1`
- Energetikai tanúsítvány parancs: `ETAction`
- ETAction parancsazonosító: `18`
- Megnyílt ablak osztálya: `TETDocumentForm`

A célpont megnyitása runtime szinten igazolt: az ETAction 18 aktiválása után a
WinWatt megnyitotta az `Energetikai minőségtanúsítvány készítése` ablakot.

## Környezet

- Python: `3.12.10`
- Python architektúra: `32 bit`
- WinWatt: `WinWatt32.exe`
- Projekt: `data/runtime_maps/buildings_runs/20260830T214001/sandbox/testwwp.wwp`
- Explorer: `explore_room_state_graph`

## Mentett artefact

A részleges, folytatható eredmény könyvtára:

`winwatt_automation/data/runtime_maps/file_energy_certificate_deep_native_20260903T154050/`

A futás utolsó mentett állapota a `progress.json` alapján:

```json
{
  "states": 3,
  "edges": 72,
  "failures": 1,
  "queue": 57,
  "complete": false
}
```

## Eredmény

A feltárás részlegesen sikeres:

- a célmenü és a célablak azonosítása sikerült;
- a `TETDocumentForm` ablakból 3 különböző UI-állapot mentődött;
- 72 állapotátmenet került a gráfba;
- 57 útvonal feldolgozatlanul maradt;
- 1 hiba került naplózásra;
- a teljes feltárás nem zárult le.

A futást szándékosan leállítottuk, mert a `session_islands` mód ismétlődő
WinWatt-újraindításokat okozott. A folytatás ezt kikapcsolva futott, de minden
útvonal friss WinWatt-munkamenetet indított, ami lassú és instabil volt.

A feltárás végén az általunk indított sandbox WinWatt32 folyamatot leállítottuk.

## Technikai megállapítások

1. A célablak nem az Épületek szerkesztőablakának közvetlen része, hanem a főablak
   `Fájl` menüjének ETAction parancsából nyílik.
2. A UIA-alapú popup-szövegkinyerés ennél a menünél nem megbízható; a natív
   parancsazonosító stabilabb belépési pont.
3. A célablak megnyitása gyorsan sikerült, de a mélységi explorer jelenlegi
   replay-modellje minden függő útvonalnál újraindítja a WinWattot.
4. A `TETDocumentForm` esetében külön, ablak-specifikus root-opener és
   visszaállítási stratégia szükséges a teljes feltáráshoz.

## Következő lépés

A teljes feltárás folytatásához célszerű:

- a `TETDocumentForm` megnyitását külön célzott explorer scriptbe emelni;
- az állapotgráf replay-jét ugyanazon WinWatt-munkamenetben megoldani, ahol ez
  biztonságosan lehetséges;
- a natív ETAction 18 azonosítót megtartani, és nem a hibás popup-feliratokra
  támaszkodni;
- a `graph.checkpoint.json` és `queue.checkpoint.json` fájlokból folytatni;
- a célablak bezárását minden ág végén explicit módon ellenőrizni.

A jelenlegi artefact bizonyítja a célablak elérését és az első részleges
állapotgráfot, de nem bizonyítja az összes vezérlő teljes feltárását.
