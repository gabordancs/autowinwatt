# Új WinWatt-verzió feltérképezése és teljes tanúsítás

Az első, nem kézzel rajzolt dokumentumokra épülő vak WWP-rekonstrukció részletes
terve: [CASE02_CODEX_WWP_REKONSTRUKCIO_TERV_HU.md](CASE02_CODEX_WWP_REKONSTRUKCIO_TERV_HU.md).

Dátum: 2026-09-29. Állapot: helyi forrásokra alapozott végrehajtási terv.
Az új kiadás pontos verziója és képernyői még nem ismertek; a felhasználó
jelzése szerint az épület megnyitásakor más és több energetikai beállítás jelenik meg.
Az alábbi témák vizsgálati feladatok, nem állítások az új verzió tényleges mezőiről.

## 1. Cél és befejezési feltétel

A cél egy felmért épület teljes tanúsítási folyamatának végigvitele:
forrásadatok → ellenőrzött épületmodell → natív WinWatt-projekt → épületenergetika
és gépészet → számítás → felújítási javaslatok → számítási PDF, fotók és
tanúsítási XML → fogadóoldali ellenőrzés → tanúsítói ellenőrzés és véglegesítés.

Három külön mérföldkövet kell nyilvántartani:

1. **Feltérképezett:** ismert a kiválasztott kiadás tanúsításhoz szükséges UI-ja,
   az elérési utak, mezők és feltételes ágak.
2. **Helyileg elkészült:** teljes, visszaolvasással ellenőrzött projekt és dokumentumcsomag;
   nincs kitöltetlen kötelező adat vagy feloldatlan számítási eltérés.
3. **Végleges tanúsítás:** a tényleges fogadó rendszer visszajelzése és a tanúsítói
   véglegesítés is dokumentált. Egy helyi `upload_ready=true` nem ennek bizonyítéka.

A mostani munka a terv és a rendelkezésre álló tudás egyesítése. Új WinWattot
nem telepítettünk, éles projektet nem módosítottunk, UI-bejárást nem indítottunk.

## 2. Ellenőrzött helyi kiindulás

| Terület | Megtalált alap | Következmény |
| --- | --- | --- |
| Telepített WinWatt | `C:\Program Files (x86)\Bausoft\WinWatt gólya\WinWatt32.exe`; FileVersion `9.60.0.0`, ProductVersion `1.0.0.0` | A ProductVersion önmagában nem verzióazonosító |
| EXE SHA-256 | `E3440D191B0A09999B13A330B15E0F30552109E8D0DDE13B4E9A6045C5EE01AD` | Régi helyi bináris összehasonlítási alapja |
| Python | 3.12.10, 32 bit | A régi programhoz illeszkedik; új EXE architektúráját külön ellenőrizni kell |
| AutoWinWatt Git | `9281dbf`, helyi HEAD a vizsgálatkor | A reprodukálható futásokban teljes commitazonosító is legyen |
| WebWatt | A `../magyar-mentor` repó alkalmazása | Nem találtunk külön `webwatt` nevű helyi repót |
| Régi tudás | 1922 fájlhivatkozás, 1564 különböző SHA-256 tartalom | A közös jegyzék: `mapping_evidence_union.json` |
| Globális gráf | 979 állapot, 384 átmenet, 15 konfliktus | Régi megfigyelések, nem az új verzió validált képességei |
| Navigációs tudás | 787 állapot, 212 átmenet | Átfedhet a globális gráffal; a számokat nem szabad összeadni |
| Történeti importmanifest | 43 hivatkozásból 5 eredeti relatív útvonalon megvan, 38 hiányzik | A hiányzó nyers anyagokat nem pótolja teljesen az összesített gráf |

A történeti JSON-okban `Admin` és `dancsg` felhasználói útvonalak vannak.
Ez több környezetre utal, de a fizikai gépek személyazonosságát és azt, melyik
volt kompromittált, önmagában nem bizonyítja. A jelenlegi másolatban mindkét
forráskörnyezet nyomait együtt indexeltük.

Három JSON szintaktikailag hibás: `project_data_controls_9_60.json`,
`project_options_controls_9_60.json`, `xml_export_save_dialog_controls_9_60.json`
a `data/snapshots` alatt. Lenyomatuk megmaradt, strukturált importjuk javításig
nem megengedett. Az eredeti fájlokat meg kell őrizni; a javítás külön származtatott fájl.

## 3. Tudásegyesítés és a másik laptop anyagai

A már elkészült egyesítés **hivatkozásos bizonyítékjegyzék**: azonos tartalomhoz
egy SHA-256 kulcs és valamennyi forrásút tartozik. A nyers gráfok, képek és
mentett tudástárak változatlanok. Ez a repo korábbi `unified_mapping.py`
`references_only` elvét követi. Nem állítja, hogy minden régi gráfot egyetlen,
végrehajtható gráffá alakítottunk vagy minden laptopadat megvan.

Újraépítés a repo gyökeréből, csak helyi olvasással:

```powershell
python winwatt_automation/src/winwatt_automation/scripts/consolidate_mapping_evidence.py --output docs/mapping_evidence_union.json
```

További egyesítési feladatok:

1. A hiánylistát összevetni megbízható Git-előzményekkel és meglévő mentésekkel.
   A `data/runtime_maps/` gitignore alatt van: egy GitHub-klón nem teljes mappingmentés.
2. A kompromittált laptopról csak külön kezelt adatmentésből átemelt bizonyíték
   kerülhet be; régi virtuális környezet, EXE, DLL vagy szkript onnan nem futtatandó.
   Rögzítendő a mentés eredete, ideje, lenyomata és a bizalmi státusz.
3. A hiányzó nyers forrású összegzések `historical_unverified` besorolásúak;
   a fizikai forrásszámítógép ismeretlensége külön mező, nem kikövetkeztetett tény.
4. Verzión belüli, azonos sémájú room/deep gráfokra a `merge_rooms_deep.py`
   használható, új kimeneti könyvtárral és utána `audit_rooms_deep.py` audittal.
   Nem általános importáló, és új verzióba nem vihető át a régi checkpoint.
5. A `LegacyMappingImporter` és `import_navigation_knowledge.py` adaptációja
   külön verzióhoz kötött célstore-ba történjen. A régi abszolút út helyett
   forráscsomag + relatív út + tartalmi hash legyen az importazonosság.
6. A különféle gráfsémákhoz külön adapter kell; a puszta menükép nem bizonyít
   végrehajtott átmenetet. Ellentmondó megfigyelés konfliktus marad.

## 4. Verzióellenőrzés és átállás

**V0 – Telepítés előtt:** régi EXE-azonosság, környezet, beállítások, katalógusok,
`Hungarian.xml`, tesztprojektek és mappingek mentése hash-manifesttel. Az új program
régi projektet kizárólag másolaton nyisson meg. A visszaállítás alapja a régi
projektek mentése; az új verzióban mentett WWP visszafelé kompatibilitása nem feltételezhető.

**V1 – Telepítés után:** EXE abszolút út, FileVersion, ProductVersion, SHA-256,
PE architektúra; Névjegyben látható kiadás/modul/licenc; telepített katalógusok
és nyelvi erőforrások lenyomata. A Névjegyhez a `safe_about_probe.py` használható,
miután annak belépési útja az új verzión igazolt. Eltérő UI-nevek esetén helyi,
csak olvasó UI-inspekció az első lépés.

**V2 – Futási profil:** új `version_profile.json` tervezett mezői:
`exe_path`, `file_version`, `product_version`, `exe_sha256`, `pe_machine`,
`edition`, `enabled_modules`, `language`, `dpi`, `resource_hashes`, `catalog_hashes`,
`python_version`, `python_bitness`, `automation_commit`, `machine_id`, `captured_at`.
A `machine_id` helyi kiosztott azonosító, nem felhasználónévből kitalált gépnév.

**V3 – Elkülönítés:** minden új futás `data/runtime_maps/versions/<version>_<hash>/`
alá kerül. A navigációs és szemantikus képességek ellenőrzöttsége ehhez a profilhoz
kötött. Bináris-, modul- vagy lényeges erőforrásváltozás új ellenőrzési kört nyit.
Ismeretlen profilnál az író automatizmus álljon meg; diagnosztika maradjon elérhető.

**V4 – Aktiválás:** csak a tanúsítási regressziós csomag és a szükséges útvonalak
ellenőrzése után lehet az új profilt aktívvá tenni. Először párhuzamosan őrzött
régi/új tudás és teszteredmény, utána explicit aktívprofil-váltás.

Megvalósítási hiány: a jelenlegi navigációs modell nem tartalmaz programverziót;
a globális állapotazonosító sem tartalmazza azt. Az elkülönítés ezért szükséges
fejlesztés, nem már meglévő garancia. A controller `WWA_WINWATT_EXE_PATH` értéke
és a mapper beégetett EXE-útvonala közös konfigurációra hozandó.

## 5. Az épületenergetikai modul feltérképezése

### E0 – Régi kiindulási tudás

Felhasználandó: `catalog_contexts_9_60`, `mdi_runtime_states_9_60`,
`buildings_runs`, `snapshots/deep_buildings_mdi_9_60`,
`runtime_mapping/room_deep_explorer.py`, `scripts/explore_buildings_deep.py`.
A régi fa navigációs segítség és összehasonlítási alap; az új mezőlistát mindig
az új UI-ból kell felvenni, a régi listából nem lehet teljesnek nyilvánítani.

### E1 – Új épületablak belépési útja

1. Indulás egyetlen friss, eldobható tesztprojektből, egy egyértelmű nevű épülettel.
2. Jegyzék → Épületek → kijelölt épület → megnyitás útvonal inspekciója;
   dupla kattintás és Elem/Módosítás eredményének összevetése, ha mindkettő létezik.
3. Ablakosztály, szülőablak, modalitás, fülek, faelemek és belső görgethető panelek
   felvétele. Minden valódi gyerekdialógust is fel kell venni.
4. A korábbi `TBuildingModifyForm` csak hipotézis. A felirat, osztály és szülői
   kapcsolat együtt azonosítson; a koordináta és menüindex ne legyen elsődleges kulcs.
5. Nyitás–bezárás–újranyitás bizonyítása, projekt- és processzazonosság ellenőrzésével.

Kritikus meglévő korlát: `open_sandbox_building()` régi ablakosztályt, első
listasort, menüindexeket és koordinátát használ; új kiadásra változtatás nélkül
nem tekinthető megbízhatónak. `prepare_buildings_exploration.py` hat feladatot
tervez, de csak a baseline feladatot hajtja végre; a többi lefoglalása nem kész mapping.

### E2 – Mező- és állapotkatalógus

Minden képernyőn: Win32/UIA vezérlőfa, natív menü, képernyőkép, időbélyeg,
verzióprofil, tesztprojekt-hash, végrehajtott út és állapot-ujjlenyomat.
Elsődleges eszköz a meglévő pywinauto/Win32 és natív export. Kép/OCR csak
olyan mezőhöz kell, amelyet ezek nem adnak vissza; OCR-érték önmagában nem igazolt.

Mezőnként tárolandó: szemantikus név; tényleges felirat és locator; típus;
mértékegység; alapérték; értékkészlet; engedélyezési/láthatósági feltétel;
kötelezőség; tartomány; adatforrás; natív XML-út, ha van; eredményre gyakorolt hatás;
olvasás/írás/mentés-utáni-visszaolvasás bizonyítéka; verzió; bizalmi státusz.

### E3 – Feltételes ágak és vizsgálati témák

| Téma | Feltárandó kapcsolat | Igazoló kimenet |
| --- | --- | --- |
| Épületazonosság, rendeltetés, tanúsítási egység | Egész épület/részegység, lakó/nem lakó, több épület | Helyes scope és épületazonosító minden exportban |
| Számítási mód, követelményprofil | Választóértékek, hatály és számítási ág; tényleges új opciók | UI ↔ natív mentés ↔ eredmény megfeleltetés |
| Geometria és zónák | Alapterület/térfogat forrása, helyiség–zóna–épület hozzárendelés | Összegek és kizárások egyezése |
| Határolók és nyílászárók | Rétegek, U, tájolás, dőlés, árnyékolás, hőhidak | XML- és UI-visszaolvasás; nincs elvesző tulajdonság |
| Használat, belső terhelés, szellőzés | Rendeltetésfüggő profilok, légcsere, hővisszanyerés | Aktiválódó mezők és számítási hatások |
| Fűtés és HMV | Termelés, elosztás, tárolás, szabályozás, energiahordozó | Rendszer–zóna hozzárendelés, részarányok, energiaeredmények |
| Hűtés, gépi szellőzés, világítás | Alkalmazhatóság, kapcsolóval megnyíló paraméterek | Kikapcsolt/bekapcsolt állapot, megmaradó vagy törlődő adatok |
| Megújuló és exportált energia | A modulban ténylegesen támogatott technológiák, elszámolás | Eredmény és export mezőazonosság |
| Eredmények és referencia | Hőigény, vég-/primerenergia, CO₂, besorolás és követelmények | Natív számításból származó, visszavezethető eredmény |
| Felújítási javaslatok | Szerkezet/gépészet, önálló és kombinált változatok | Kiinduló és javasolt állapot elkülönítése |
| Tanúsítási adatok és mellékletek | Cím, azonosítók, tanúsító, fotók, számítási PDF | Hiánytalan célformátum és fogadóoldali ellenőrzés |

A táblázat nem állítja, hogy minden téma külön fül. A tényleges UI szerint
keletkezik a végleges katalógus. Nem alkalmazható témához indokolt `not_applicable`
státusz kell, nem üres mező és nem fiktív nulla.

Módszer: először minden választó összes értékének helyi enumerálása; majd egy
független változó módosítása ugyanabból a sandbox-alapból. Rögzítendő az újonnan
megjelenő, eltűnő, átneveződő, letiltott és új alapértéket kapó mező. A függő
kombinációkat külön próbák fedik le; páronkénti kombinációk csak a független
ágaknál csökkenthetik a futásszámot. Üres/érvényes/határértékes/érvénytelen
bemenet próbája a ténylegesen megismert tartományok alapján történjen.

### E4 – Szemantikai bizonyítás

Minden szükséges írási képesség kísérlete: előtte UI + natív XML → egy mező
módosítása → mentés → bezárás/újranyitás → UI + natív XML → újraszámítás → diff.
Az XML-ben nem szereplő mezőhöz determinisztikus UI-visszaolvasás és a kapcsolódó
natív riport ellenőrzése kell. Bináris WWP közvetlen szerkesztése nem része a tervnek.

A `knowledge` réteg existing save/reopen + verification elve újrahasználandó.
Más verzió régi `verified` állapota az új profilban nem öröklődik.

### E5 – Lefedettség és megállás

A tanúsítási célhoz szükséges valamennyi ág kapjon `verified`, indokolt
`not_applicable` vagy `blocked` státuszt. `Blocked` kötelező ág mellett nincs
teljesítés. Külön számoljuk a megnyitott ablakokat, a felvett mezőket, az igazolt
mezőírásokat, a feltételes ágakat és a kész tanúsítási forgatókönyveket.
A feltárásnak legyen idő-/lépésszám-/újrapróbálkozás-korlátja és checkpointja;
a határ elérése `incomplete`, nem siker. A régi korlátlan bejárót ehhez adaptálni kell.

## 6. Meglévő eszközök és szükséges módosítások

| Meglévő elem | Újrahasznosítás | Előfeltétel / hiány |
| --- | --- | --- |
| `map_full_program.py` | Főmenü, projekt nélküli/projektes alapállapot | Új profil, sandbox, helyes EXE-konfiguráció |
| `inspect_live_ui.py`, natív menükinyerők | Új ablak és vezérlők első leltára | Csak megfigyelés az első körben |
| `explore_buildings_deep.py` | Épületrészletező állapotgráf | Új root opener, stabil locator, korlátos futás |
| `map_mechanical_tabs.py` | Gépészeti lapok feltárási mintája | Új UI-n ellenőrzendő belépési utak |
| `compare_runtime_states()` | Menük és action-útvonalak összevetése | Mező-, egység-, enum- és függőségdiff kiegészítés kell |
| `merge_rooms_deep.py`, `audit_rooms_deep.py` | Kompatibilis régi gráfok összevetése, bizonyítékaudit | Verzió- és sémakompatibilitás ellenőrzése |
| `NativeXmlService`, `certificate-native-project` | Új projekt + natív XML-import + mentés | Új kiadás friss natív XML-mintája; import összevonó jellege miatt üres cél |
| `VerificationService`, szemantikus knowledge | Visszaolvasás és bizonyítás | Épület/gépészet/export képességek bővítése |
| `webwatt_certificate_worker.py` | Lokális sorfeldolgozás és PDF/XML előfeldolgozás | Teljes WinWatt-tanúsítás külön workflow-ként fejlesztendő |

Csak az E1 belépési út igazolása és az új profile kezelés beépítése után
indítandó a létező mélybejáró. Példa a jelenlegi CLI-vel, a `winwatt_automation`
könyvtárból; a helykitöltők tényleges, új profilhoz tartozó útvonalra cserélendők:

```powershell
python -m winwatt_automation.scripts.explore_buildings_deep --project <eldobhato-tesztprojekt.wwp> --output-dir <uj-profil-epulet-futas>
python -m winwatt_automation.scripts.audit_rooms_deep <uj-profil-epulet-futas>
```

Az épületbejáró jelenleg újraindítja az alkalmazást. Futás előtt a nyitott munka
mentése és elkülönített mapping-munkamenet szükséges. A tervkészítés során nem indult el.

## 7. WebWatt / magyar-mentor integráció

Átnézett konkrét források a `../magyar-mentor` alatt:
`supabase/functions/winwatt-import/index.ts`, `_shared/winwattProjectDerivedData.ts`
(kapcsolat az importban), `_shared/certificateExport.ts`, `_shared/certificateValidation.ts`,
`docs/tanusitasi-xml-export-sprint-terv.md`, `docs/winwatt-xml-gap-list-2026-04-09.md`.
Az áprilisi gap-lista történeti: a jelenlegi import már olvas EPBD-,
EnergyConsumptions-, RefEnergyConsumptions- és BaseEnergyConsumptions-adatokat;
minden fennmaradó hiányt az új kiadás mintájával újra kell bizonyítani.

Tervezett szereposztás:

- WebWatt: felmérés, forrásdokumentumok, kötelező adatbekérés, projektállapot és eredmények.
- AutoWinWatt helyi Python worker: determinisztikus natív projektírás, UI-kiegészítés,
  számítás, mentés és visszaellenőrzés, export.
- WinWatt: a célverzióban ténylegesen végrehajtott számítás és natív eredmény.
- ETAI_Agents: hasznos audit/QA és ellenőrzési minta; nem szükséges új főrendszert
  bevezetni a tanúsítási lánc elkészítéséhez.

Mezőszintű integrációs mátrix készítendő: felmérési forrás → WebWatt-mező →
WinWatt UI/nyers XML → számítási eredmény → tanúsítási célmező. Külön kezelendő
a natív WinWatt projekt-XML és a tanúsítási `UploadRequest`; nem felcserélhetők.
Ismeretlen XML-mező megőrzendő raw adatként és hiányként jelölendő.

Konkrét javítandó kiadási kapu: a `certificateExport.ts` meglévő
`original_xml` ága az XML visszaadásakor közvetlen `upload_ready: true` értéket ad.
Az új munkafolyamatban ez csak eredetmegőrző export lehet: a ténylegesen kiadott
XML-t is validálni kell, és ellenőrizni, hogy megfelel a jelenlegi projektrevíziónak.
A korábbi besorolás és szoftververzió nem örökíthető új számítás helyett.

Tervezett lokális workflow-állapotok:
`intake → needs_data → model_ready → native_project_ready → building_settings_verified
→ calculated → results_verified → package_validated → ready_for_submission → finalized`.
Minden lépés idempotens az input hash + profil + projektrevízió alapján;
megszakítás után bizonyított checkpointból folytatódjon. Sikertelen kötelező
ellenőrzés blokkolja a továbblépést. A mappinghez nem szükséges felhő vagy LLM;
WebWatt sorintegráció a helyileg sikeres E2E után következik.

## 8. Ellenőrzési minták és teljes tanúsítás

1. Minimális új épület: az új energetikai modul összes alaplapjának felvétele.
2. Egyszerű családi ház: egy épület, egyszerű fűtés és HMV, teljes dokumentumcsomag.
3. Lakás/részegység: határolók és tanúsítási scope eltérései.
4. Nem lakóépület: eltérő rendeltetés, világítás/szellőzés/hűtés alkalmazható ágai.
5. Több zóna és több épület: rendszerek és eredmények ne keveredjenek.
6. Összetett gépészet/megújuló: a ténylegesen elérhető függő opciók és részarányok.

A Kerepesi-v14 meglévő geometriai kontroll jó regressziós alap: 1 épület,
2 energetikai zóna, 2 helyiség, 21 szerkezet, 67 rétegsor, 61 határoló,
2970,5 m², 12189 m³. Nem bizonyít kész tanúsítást. A régi tetőtájolás-normalizálási
eltérés külön újratesztelendő; nem vihető át automatikus kivételként.

Elfogadás: azonosítók és enumok pontos egyezése; numerikus toleranciák
mezőnként, a tárolási pontosság alapján előre rögzítve; valamennyi eltérés
magyarázattal. Az új számítási módszer miatt eltérő energiaeredmény nem automatikus
hiba, de verzióhoz kötött ok és kontrollszámítás kell. Azonos új verzióban kézzel
beállított referenciaprojekt és automatizált projekt eredménye is összevetendő.

Helyi tanúsítási referenciák ténylegesen megvannak:
`../magyar-mentor/external/energetika/tanúsítvány/dokumentacio-v3.0.12035/`
(`docs/validationRules.md`, `docs/dictionary.md`, `test/system/data/xml/general_cert.xml`).
Ezek helyi tesztalapok, jelenlegi fogadóoldali érvényességük most nincs igazolva.
A beadási szakasz előtt az aktuális hivatalos séma/szabályverzió és a tényleges
elfogadás ellenőrzése külön kötelező feladat. Konkrét jogszabályi küszöböt a terv nem feltételez.

## 9. Végrehajtási sorrend és kézzelfogható eredmények

| Sorrend | Feladat | Leszállítandó eredmény | Továbblépési kapu |
| --- | --- | --- | --- |
| 0 | Történeti tudás összesítése | Elkészült SHA-256 jegyzék, hiányok és parse-hibák | Források megkülönböztethetők |
| 1 | Új kiadás azonosítása, környezetmentés | Verzióprofil és mentésmanifest | Ismert EXE, modul, architektúra |
| 2 | Épület belépési útjának adaptációja | Determinisztikus opener és baseline snapshot | Helyes tesztépület nyílik meg |
| 3 | Új energetikai UI és függőségei | Mezőkatalógus, állapotgráf, régi/új diff | Nincs felderítetlen kötelező ág |
| 4 | Mezőírás, mentés és számítás bizonyítása | Verziózott képességek és round-trip riport | Minden szükséges írás igazolt |
| 5 | Teljes helyi referencia-tanúsítás | WWP + natív XML + számítási PDF + tanúsítási XML + mellékletek | Tartalmi egyezés és validáció |
| 6 | WebWatt mezőadapter és worker bővítés | Verzióhoz kötött, idempotens workflow | Ugyanaz az eredmény UI-indításból is |
| 7 | Fogadóoldali ellenőrzés és véglegesítés | Visszajelzés, javítási kör, végleges csomag | Valós tanúsítási folyamat lezárva |

Az új verziószám és első referenciaépület kiválasztása az 1. és 5. lépés
pontosításához kell. Addig az eszközök és a fenti adapterek előkészíthetők;
az új modul tényleges feltérképezése a telepítés után végezhető el.
