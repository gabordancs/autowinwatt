# OÉNY 10479210 rekonstrukciós pilot – állapot és bizonyíték

Utolsó frissítés: 2026-10-14

## Rövid állapot

A 10479210 számú pilotban technikailag működő WinWatt-projekt készült, de ezt
nem tekintjük még igazolt PDF → WinWatt rekonstrukciónak. A korábbi intake a
PDF mellett az eredeti XML-ből származó mezőket is bevont, ami az új kötelező
forrásszétválasztási szabály szerint tiltott. Az épületburkot, zónát és
gépészetet ezért PDF-only specifikációból újra kell építeni és ellenőrizni.

Ez még nem kiadási csomag. A WinWatt számítási PDF közvetlen exportja már
igazolt; a tanúsítási XML exportját azonban addig nem szabad véglegesnek
tekinteni, amíg a tényleges adminisztratív adatok és a `full_certificate`
kapu nincsenek igazolva.

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

Az új kötelező láncban kizárólag az önálló PDF lehet építési bemenet. A
`build_pdf_reconstruction_spec` közvetlen PDF-provenienciát ír elő; a
`build_one_zone_candidate` elutasítja az XML-ből származó területet,
térfogatot vagy más építési mezőt. Az eredeti XML csak az új WinWatt XML
elkészülése után, végellenőrzésre használható.

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

## Számítási PDF export

A `probe_et_calculation_pdf_export.py` worker az ET scope-ot az `Üdülő sor
26.` épületre, az `F1` zónára és minden szerkezetre állította, majd a WinWatt
`PDF fájlba...` műveletével közvetlenül előállította a számítási dokumentumot.
A korábbi `Printer selected is not valid.` hibát a Windows automatikus
alapértelmezett-nyomtató módjának futásidejű kikapcsolása oldotta meg.

Két tiszta futás ugyanazt a 9 oldalas, 935 761 bájtos PDF-et adta. SHA-256:
`eaed66fb8cc255ea946b422dad0019212e212d18d151772304120fdeb4474a04`.
A forrás és a munkapéldány változatlan maradt, a WinWatt bezárult, az eredeti
nyomtató- és Windows-beállítások visszaálltak. A végleges ellenőrzött példány:
`output/pdf/10479210_alatamaszto_munkaresz.pdf`.

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
| WinWatt számítási PDF export | közvetlen PDF worker | kész, két futással verified |
| valós adminadatú ET XML export | paraméterezett admin worker | még hiányzik |

## Következő kapuk

## 2026-10-15-i PDF-only összevetési állapot

A legutóbbi teljes, helyi worker-lánc kizárólag a számítási PDF-ből építette
fel a modellt. Az eredeti OÉNY XML csak az elkészült WinWatt-visszaolvasás
utólagos ellenőrzésére szolgált.

Bizonyított egyezések:

- hasznos alapterület: `32,8 / 32,8 m²`;
- fűtött térfogat: `88,6 / 88,6 m³`;
- mind a hat szerkezettípus összes felülete pontos;
- a tájolásonkénti felületek pontosak (`0°`, `45°`, `135°`, `225°`);
- a tető natív határfeltétele `Type=3`, tájolása `45°`, hővesztesége `434 W`;
- a talajjal érintkező fal és padló natív típusa `25`, illetve `26`;
- fűtési/HMV-rendszernév, energiahordozó és teljesítménytényező pontos;
- HMV végenergia: `927 / 927 kWh/a`.

Fennmaradó számítási eltérés:

| Mező | PDF / eredeti XML | Új WinWatt | Eltérés |
|---|---:|---:|---:|
| fűtés nettó hőenergia | 8154 kWh/a | 4718 kWh/a | -42,14% |
| fűtés végenergia | 13698 kWh/a | 7926 kWh/a | -42,14% |
| összes primerenergia-jellemző | 478,43 kWh/m²a | 304,21 kWh/m²a | -36,41% |

A korábbi `-52%` fűtési eredmény egy azonosított hibás köztes állapot volt:
a tető pincefödém-kódot (`Type=5`) kapott, ezért nem vett részt megfelelően a
hőveszteségben. A `Type=3` javítás ezt megszüntette és a hibát `-42,14%`-ra
csökkentette.

A jelenlegi fő gap nem geometriai. A PDF szerinti összes hőtároló tömeg
`12,26 t`, illetve az effektív fajlagos hőkapacitás `325,37 kJ/m²K`. A natív
visszaolvasásban `61,984 t`, illetve `1587 kJ/m²K` marad, vagyis az utóbbi
mintegy `+388%`. A PDF-parser már strukturáltan átadja a szerkezetenként
nyomtatott fajlagos tömeg-, hőtároló tömeg- és hőkapacitás-adatokat, de a
WinWatt natív XML-importja ezeket származtatott mezőként felülírja a kiinduló
projekt értékeivel. Az épület `Mindet újraszámol` művelete sem frissíti őket.
A következő célzott mapping-feladat ezért a hat szerkezet szerkesztőjének
determinisztikus megnyitás–OK roundtripje és az ezt követő tömeg-readback.

A PDF-ben nyomtatott légcsereadatok is rögzítve vannak: `n_szüks=0,50 1/h`,
`n_filt=0,06 1/h`, `H_szell=17,4 W/K`. Ezeket nem kell feltételezni. A jelenlegi
projektben a használati zóna `0,50` értéke megvan, de az éves EPBD
visszaolvasás `AirVolumeInf=0`, ezért a `0,06` infiltráció zónakapcsolatát a
hőtároló tömeg javítása után külön kell ellenőrizni.

Az ET tanúsítási XML export külön UI-azonossági hibán állt meg
(`No enabled WinWatt top-level window is active`); ez nem projekt- vagy
számítási sérülés. Tanúsításra kész állapot továbbra sincs kimondva.

2026-10-14-től a pilot az
[`ADAPTIV_TANUSITASI_VALTOUZEM_HU.md`](ADAPTIV_TANUSITASI_VALTOUZEM_HU.md)
szerinti gapvezérelt módban halad. Az általános ET-crawler leállt; mapping csak
az aktív rekonstrukciós elakadásra, korlátozott kerettel futhat. Az első ilyen
gap, a számítási dokumentum mentése lezárult; a pilot ismét a rekonstrukciós
szakaszban van.

1. A rendszerek mezőszintű újranyitási readbackjének bővítése, nem csak a
   rendszernevek visszaolvasása.
2. Determinisztikus PDF/XML eredmény-diff worker készítése a kézi összevetés
   kiváltására.
3. A forrás XML tényleges adminisztratív adatainak paraméterezett beírása.
4. `g5_calculation`, majd `full_certificate` preflight.
5. ET XML export, a beágyazott PDF dekódolása és hash-egyezés.

OÉNY-feltöltés, tanúsítói aláírás vagy végleges kiadás ebben a pilotban nem
történt. A jelenlegi WWP és a belőle nyomtatott PDF technikai bizonyíték a
helyi WinWatt-workerekre, de a PDF-only rekonstrukció újrafuttatásáig nem
kiadási jelölt.

## Fő bizonyítékfájlok

- `winwatt_automation/data/oeny_reconstruction/pilot_10479210_final_audit_20261013a.json`
- `winwatt_automation/data/oeny_reconstruction/actual_system_build_10479210_20261013a/report.json`
- `winwatt_automation/data/oeny_reconstruction/calculation_roundtrip_10479210_20261013b/report.json`
- `winwatt_automation/data/oeny_reconstruction/calculation_pdf_10479210_20261013a/report.json`
- `winwatt_automation/data/oeny_reconstruction/adaptive_10479210_20261014a/direct_pdf_attempt_003/report.json`
- `winwatt_automation/data/oeny_reconstruction/adaptive_10479210_20261014a/direct_pdf_attempt_004/report.json`
- `winwatt_automation/data/oeny_reconstruction/calculation_roundtrip_10479210_20261013b/testwwp.wwp`
