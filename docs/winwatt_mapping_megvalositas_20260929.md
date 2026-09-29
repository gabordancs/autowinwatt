# Helyi WinWatt mapping – első megvalósított szakasz

## Működő alap

- Külön `.venv-winwatt32` környezet: Python 3.12, 32 bit, pywinauto 0.6.9.
- A meglévő Delphi/Win32/UIA kapcsolódás és mappingfüggvények újrahasznosítása.
- `version_profile.py` és `scripts/version_check.py`: EXE-verzió, SHA-256,
  PE-architektúra, alkalmazásoldali DLL/XML/INI lenyomat, összehasonlítás és
  külön sandboxot létrehozó kampány-előkészítés. Nem indítanak programot.
- `scripts/capture_building_tabs.py`: meglévő épületablak véges, helyi bejárása;
  fülenként screenshot, vezérlők, natív választóértékek, kiválasztott fülek és
  látható/rejtett natív lapok. A kiválasztás visszaellenőrzött.
- Javított `open_sandbox_building`: a régi `(30, 24)` kattintás ezen a gépen
  fejlécet talált. Az épületet most pontos névvel, egyedi natív listasorként
  azonosítja és dupla kattintással nyitja meg. Hiányzó/többszörös név hibát ad.
- `explore_buildings_deep --version-profile ...`: opcionális, UI-művelet előtti
  verzióellenőrzés. A mapper a `WWA_WINWATT_EXE_PATH` beállítást is figyelembe veszi.

## Megfigyelt program

A megadott EXE továbbra is ugyanaz a 9.60.0.0 bináris, mint a tervezéskor.
A Névjegy szerint **WinWatt gólya 9.60 (2026. 8. 5.)**, modulok:
**EPBD, EPBD-2023, Agros2D**. Újabb telepített binárisra nincs bizonyíték.
A program indításkor rejtett főablakkal kezd, ezért a látható/engedélyezett
Delphi főablakot meg kell várni; a gyors általános ablakkeresés kevés volt.

Kampány: `../winwatt_automation/data/runtime_maps/versions/winwatt_8c137b67c0a2214bb91aeae8/20260929T103113936631Z/`.
A forrás tesztprojekt másolatán létrejött a `Building graph explorer` épület.

Elérhetőként felvett 11 fül:

1. Helyiségek
2. Fűtött teret határoló szerkezetek
3. Épülettechnikai rendszerek
4. Felújítás (szerkezetek)
5. Fotók
6. PDF fájlok
7. Általános adatok
8. Hőszükséglet, fajlagos hőveszteségtényező
9. Nyári hőterhelés
10. Zónák
11. Referencia épület adatai

Az ablakban két külön lapcsoport van, ezért két kiválasztott fül egyidejűleg
helyes állapot. Ez 11 megfigyelést jelent, nem minden fülkombináció bejárását.
További natív, de a mostani állapotban nem választható lapok: „Energia igény
tervezési adatok”, „Primer energia igény számítása”, „Becsült éves fogyasztás,
CO2 kibocsátás”. Aktiválási feltételeik további feltárást igényelnek.

Bizonyítékok: `about.png`, `about.json`,
`building_tabs_20260929T170509/summary.json`, az ottani JSON/PNG párok,
`native_save.json`. A 17:04-es első felvétel kevesebb kontextust tartalmaz;
a 17:05-ös sorozat a választóértékeket és a natív lapokat is rögzíti.

A natív `MainForm.SaveProjekt` és szabályos bezárás után a sandbox fájl
SHA-256 értéke megváltozott. A Ctrl+S-próba ezt nem érte el; a meglévő
`WinWattService.save_project()` szükséges, ahogy annak dokumentációja is jelzi.
Egyetlen mező írási/újraszámítási képességét sem nyilvánítottuk még igazoltnak.

A mentést követő program-újraindítás és a javított épületmegnyitó élő próbája
is sikeres: ismét a `TBuildingModifyForm`, „Épületek - Building graph explorer”
ablak nyílt meg. A visszaolvasott állapot a kampány `building_reopened.json`
fájljában található. Ez még nem teljes energetikai mező-roundtrip.

## Újrafuttatás

A parancsokat a `winwatt_automation` könyvtárból kell futtatni, mert a repo
gyökerének azonos nevű csomagja elfedheti a `src` csomagot.

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
$env:PYTHONIOENCODING = 'utf-8'
..\.venv-winwatt32\Scripts\python.exe -m winwatt_automation.scripts.version_check check --against ../docs/winwatt_local_profile_20260929.json
```

Új kampányhoz:

```powershell
..\.venv-winwatt32\Scripts\python.exe -m winwatt_automation.scripts.version_check prepare --root data/runtime_maps/versions --project tests/testwwp.wwp
```

Nyitott tesztépület leltárához `capture_building_tabs --campaign <kampánykönyvtár>`.
A program a futó EXE útvonalát és az előzetesen rögzített fájlazonosságot ellenőrzi.
A kampány- és nyitottprojekt-azonosság teljes automatizált összekötése még hátravan;
ebben a futásban az explicit sandbox-megnyitással biztosítottuk.
A teljes mélybejáró továbbra is külön indítandó, és még nem kapott futási korlátot;
a mostani tabfelvétel véges. A források olvasása, a kattintások és az adatrögzítés
helyben történik, a scriptek nem hívnak AI-t.

## Ellenőrzés és következő szakasz

20 célzott teszt sikeres: verzióazonosság és eltérés, PE-fejléc, külön kampányok,
forrásmegőrzés, meglévő állapothash/diff és gráfaudit. `git diff --check` sikeres.

Következő helyi munkacsomag: számítási módok és rejtett energetikai lapok
aktiválási feltételei; gépészeti rendszerek gyerekdialógusai; egy mező módosítása,
natív mentés, teljes projekt-újranyitás és visszaolvasás. Ezek után következhet
a számítás és a teljes tanúsítási export; a jelenlegi eredmény még UI-alapleltár.
