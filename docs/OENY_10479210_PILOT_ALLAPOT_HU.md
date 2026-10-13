# OÉNY 10479210 rekonstrukciós pilot – állapot és bizonyíték

Utolsó frissítés: 2026-10-13

## Rövid állapot

A 10479210 számú OÉNY-tanúsítványból egy számítás-egyenértékű WinWatt
projekt készült. Az épületburok, az egyetlen nyomtatott számítási zóna, a
forrásban megnevezett gázkonvektoros fűtés és a villanybojler helyi WinWatt
projektbe került. A projekt újraszámítása, mentése, teljes bezárása és
újranyitása sikeres.

Ez még nem kiadási csomag. A WinWatt számítási PDF külön exportja az első
próbán nem hozott létre RTF fájlt, a tanúsítási XML exportját pedig addig nem
szabad véglegesnek tekinteni, amíg a tényleges adminisztratív adatok és a
`full_certificate` kapu nincsenek igazolva.

## Forrás és rekonstrukciós mód

- OÉNY azonosító: `10479210`
- cím: `2310 Szigetszentmiklós, Üdülő sor 26.`
- helyrajzi szám: `10039`
- hasznos alapterület: `32,80 m²`
- kondicionált térfogat: `88,56 m³`
- forrás WinWatt-verzió: `9.51`
- telepített és használt WinWatt-verzió: `9.60 x86`
- mód: `current_engine_reconstruction`

A verziókülönbség miatt bájtszintű PDF-azonosság és teljesen azonos belső WWP
nem állítható. A cél a nyomtatott és XML-ben szereplő eredmények forráshű
reprodukciója.

## Bizonyított eredmények

### Forrásfeldolgozás

A helyi intake worker szigorúan dekódolta az XML
`CalculationsPdfFileContent` Base64 mezőjét, ellenőrizte a PDF aláírását,
hash-elte a forrásokat, és strukturált rekonstrukciós specifikációt készített.
Az intake és a parser nem használ LLM-et.

### Épületburok és zóna

- egyetlen forrásban megjelenő számítási zóna: `F1`;
- `32,8 m²`, `88,56 m³`, effektív magasság `2,7 m`;
- 6 szerkezet, 14 réteg, 11 helyiséghatároló;
- a függőleges falaknál az `A` felület a hiteles mennyiség; az `x` érték
  determinisztikusan `A / 2,7`, és nem helyszíni falhossz;
- a tető tájolása `45° (ÉK)`, hajlása `10°` a natív WinWatt UI-ban igazolva;
- a zóna neve és `32,80 m²` területe teljes újranyitás után megmaradt.

### Gépészeti rendszerek

A helyi `build_oeny_actual_systems.py` worker külön projektmásolaton létrehozta
és újranyitás után visszaolvasta:

- fűtés: `Gázkonvektor`;
  - hőtermelő: `Egyedi fűtések / gázkonvektor / szabályozó nélküli, vagy csak
    folyamatos hőmérsékletszabályozással`;
  - energiahordozó: földgáz;
  - szabályozás: `Gázkonvektor / saját, segédenergia nélküli termosztatikus
    szabályozással / külső falnál lehelyezve`;
  - tárolás és elosztás: `Nincs`, a forrás szerint.
- HMV: `Bojler`;
  - hőtermelő: `Elektromos / átfolyós vízmelegítő, tároló`;
  - energiahordozó: elektromos áram;
  - tárolás: `Elhelyezés a fűtött térben / nappali árammal működő elektromos
    boyler`;
  - elosztás: `Nincs`, cirkulációs segédenergia: nincs.

Az eredeti WWP SHA-256 lenyomata változatlan maradt. A másolat változott, majd
a két rendszer neve teljes újranyitás után is megmaradt. A worker riportjában
a `session_closed=false` egy utólagos, már bezárt WinWatt-példányon végzett
második takarítási kísérlet eredménye; a folyamat ténylegesen nem maradt futva.

### Számítási roundtrip

A regisztrált `winwatt.building.calculation.result_roundtrip` worker az
`Üdülő sor 26.` épületet újraszámolta. A 25 mezős gépi eredménysor mentés és
teljes újranyitás után változatlan maradt. Fő értékek:

| Mező | Eredmény |
|---|---:|
| zóna | F1 |
| alapterület | 32,8 m² |
| magasság | 2,7 m |
| belső hőmérséklet | 20 °C |
| hőigény | 3348 W |
| fajlagos hőigény | 102,1 W/m² |
| térfogatra vetített érték | 19,2 W/m³ |

A számítási másolat SHA-256 lenyomata:
`5a2616143d4c1da002a831b4cb92be79edb606657c3838c88e95709c4dcc5242`.

## Sikertelen, de biztonságos próba

A `probe_et_calculation_pdf_export.py` worker az ET scope-ot helyesen az
`Üdülő sor 26.` épületre, az `F1` zónára és minden szerkezetre állította. Az
RTF mentési párbeszédig eljutott, de 120 másodpercen belül nem keletkezett
nem üres RTF. A futás `failed` állapotú, a forrás hash-e változatlan, a WinWatt
munkamenet bezárt. Ezért nincs még új, WinWattból előállított `calculation.pdf`.

## Hol használtunk AI-t

Az AI fejlesztői és koordinációs szerepet végzett:

1. a PDF és XML emberi értelemben vett blokkjainak áttekintése;
2. a pilot kiválasztása és a bizonyítékok összekapcsolása;
3. a forrásban megnevezett rendszerek WinWatt katalógusútvonalainak célzott
   feltérképezése;
4. a helyi workerek megírása, hibáik javítása és futtatásuk koordinálása;
5. a riportok értelmezése és a következő biztonságos kapu kiválasztása.

Az AI nem adott meg hiányzó mérnöki értéket. A falaknál a felület maradt a
forrás szerinti hiteles adat; az `x` csak dokumentált számítás-egyenértékű
segédméret. Az egyhelyiséges modell a felhasználó kifejezett döntésén és a PDF
egyetlen `F1` számítási zónáján alapul.

## AI-lépésekből helyi workerek

| Korábbi AI-feladat | Helyi megoldás | Állapot |
|---|---|---|
| XML/Base64/PDF leltár | `oeny_reconstruction.py`, intake CLI | kész, determinisztikus |
| PDF/XML főérték-kivonás | rekonstrukciós parser és tesztek | részben kész |
| anyagkatalógus-egyezés | lokális anyagfeloldó + jóváhagyási rekord | kész a pilothoz |
| egyzónás jelölt modell | `build_one_zone_candidate` | kész, explicit döntést követel |
| burok/zóna audit | `audit_oeny_pilot_wwp.py` és roundtrip workerek | kész a pilothoz |
| rendszerútvonal feltárás | `probe_oeny_actual_system_paths.py` | kész, read-only probe |
| forrásazonos rendszerek létrehozása | `build_oeny_actual_systems.py` | piloton passed |
| tetszőleges épület számítása | runner `building_name` paraméter | elkészült és piloton passed |
| PDF/XML tartalmi összehasonlítás | általános diff worker | még hiányzik |
| WinWatt számítási PDF export | RTF/PDF worker | javítandó, még nem verified |
| valós adminadatú ET XML export | paraméterezett admin worker | még hiányzik |

## Következő kapuk

1. A rendszerek mezőszintű újranyitási readbackjének bővítése, nem csak a
   rendszernevek visszaolvasása.
2. Determinisztikus PDF/XML eredmény-diff worker készítése a kézi összevetés
   kiváltására.
3. Az RTF mentési párbeszéd javítása és új, üres output könyvtárban ismételt
   PDF-export.
4. A forrás XML tényleges adminisztratív adatainak paraméterezett beírása.
5. `g5_calculation`, majd `full_certificate` preflight.
6. ET XML export, a beágyazott PDF dekódolása és hash-egyezés.

OÉNY-feltöltés, tanúsítói aláírás vagy végleges kiadás ebben a pilotban nem
történt.

## Fő bizonyítékfájlok

- `winwatt_automation/data/oeny_reconstruction/pilot_10479210_final_audit_20261013a.json`
- `winwatt_automation/data/oeny_reconstruction/actual_system_build_10479210_20261013a/report.json`
- `winwatt_automation/data/oeny_reconstruction/calculation_roundtrip_10479210_20261013b/report.json`
- `winwatt_automation/data/oeny_reconstruction/calculation_pdf_10479210_20261013a/report.json`
- `winwatt_automation/data/oeny_reconstruction/calculation_roundtrip_10479210_20261013b/testwwp.wwp`
