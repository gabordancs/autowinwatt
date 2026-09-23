# Kapus energetikai tanúsítási orchestrator - automatizálási leltár és rendszerterv

## Döntési összefoglaló

Az ajánlott termék nem egy „egy kattintásos tanúsító”, hanem egy **bizonyítékvezérelt, kapus projektfolyam**. A gép minden feldolgozható részfeladatot elvégez, látható rész-eredményt és konkrét hiánylistát ad; a tanúsító fogadja el, javítja vagy utasítja el. Csak az elfogadott állapot léphet a következő kapuba.

Ez egyben tanuló rendszer is: a kézi korrekció nem elvesző javítás, hanem forráshoz kötött annotáció, amely a későbbi javaslatokat rangsorolhatja.

## 1. Feltárt automatizálási leltár

| Terület | Automatizálható munka | Feltárt állapot | Kiadási korlát / következő lépés |
|---|---|---|---|
| Lead, ajánlat, projekt | lead, ajánlatverzió, elfogadás, projekt- és feladatkapcsolat | **van alap**: `crm_leads`, `crm_offers`, `survey_projects`, pipeline állapotgép | egy közös `certification_case` azonosító hiányzik, amely összeköti a teljes tanúsítási ügyet |
| Dokumentumfogadás | PDF, fotó, régi tanúsítvány, XML, adatbekérő strukturált rögzítése | **részben van**: projekt/dokumentumtár és ügyfél-adatbekérő | dokumentumszintű bizonyosság, oldal/fotó-hivatkozás és kötelező hiánylista kell |
| Alaprajz-előkészítés | PDF-alávetítés, kalibráció, kézi falrajz, falhálózatból helyiségdetektálás | **működő alap** a Draftsmanben | a PDF-ből vonal/fal automatikus kinyerése és review UI még fejlesztési terv, nem kiadható automatizmus |
| Fal- és helyiségjelöltek | faljelölt, párhuzamos falpár, helyiségpoligon, OCR/kóta jelölt | **tervezett / részleges alap**: autotrace-session/candidate adatmodell és tervdokumentáció | mindig jelöltként indul; elfogadás, elutasítás, kézi rajz és javítás eseménye kötelező |
| PDF → WinWatt geometria | helyiség, határoló, falhossz és magasság feltárása, vizuális audit | **részben működő** AutoWinWatt helyi folyamat | a teljes fal-kontúr ↔ méretlánc automatikus összerendelés még hiányos; nincs bizonyíték nélküli kitöltés |
| X/Y/A fal-ellenőrzés | külső/lábazati fal: `X=hossz`, `Y=magasság`, `A=X×Y`; XML-visszaolvasás | **működő, szigorú kapu** az AutoWinWattban | hiányzó vagy inkonzisztens X/Y blokkolja a végleges fordítást |
| Rétegrend és anyag | meglévő katalógusanyag legjobb egyezése, egyedi anyag csak indokkal | **részben működő**: WinWatt rétegrend/XML kezelés | összehasonlítható anyagmatch, forrás és tanúsítói jóváhagyás kell |
| Gépészet | fűtés, HMV, hűtés, szellőzés, hőleadók és adatlapok strukturálása | **importban részben megvan** | fénykép/adattábla-alapú adatlap, hiánykérő és tanúsítói rendszer-review szükséges |
| WinWatt XML import/export | épület, panelek, rétegek, helyiségek, határolók és több rendszeradat | **van** WebWatt Edge Function és AutoWinWatt native XML ismeret | több összesített, referencia- és tanúsítási mező jelenleg csak raw XML-ben vagy hiányzik a normalizált DB-ből |
| Számítás és összevetés | eredmények, referenciaépület, CO2, tanúsítási eredmények összehasonlítása | **részben működő / fejlesztés alatt** | WinWatt ↔ WebWatt számítási paritás és teljes tanúsítási eredmény-import kötelező kiadási kapu |
| OÉNY előnézet és feltöltés | XML-előnézet, végleges beküldés, HET dokumentum mentése | **feltárt helyi eszköz**: OÉNY uploader | végleges feltöltés nem ismételhető automatikusan; az OÉNY jelenlegi sémáját és jogosultságot mindig ellenőrizni kell |
| Számlázás és kintlévőség | számla-vázlat, kiállítás, fizetési határidő, fizetett/kintlévő státusz | **van alap**: `project_invoices`, dashboard és szinkronirány | számlaindító eseményt a hiteles átadáshoz kell kötni, nem egy szabad projektstátuszhoz |
| LLM | dokumentumosztályozás, OCR-eredmény normalizálása, hiánykérő megfogalmazása, ellentmondás-jelzés | **AutoWinWattban kontrolláltan rendelkezésre áll**; WebWattban még nincs éles LLM-végrehajtó | kizárólag strukturált javaslatot ad; nem állíthat szakmai tényt, nem küldhet be XML-t, nem változtathat jóváhagyott adatot |

## 2. Célállapot: állapotgép és kapuk

```text
NEW → INTAKE_READY → EVIDENCE_READY → GEOMETRY_REVIEW → SYSTEMS_REVIEW
    → CALCULATION_REVIEW → CERTIFICATE_REVIEW → READY_TO_SUBMIT
    → SUBMITTED → DELIVERED → INVOICED → PAID → ARCHIVED

                   └── NEEDS_INPUT / NEEDS_CORRECTION ──┘
```

`NEEDS_INPUT` és `NEEDS_CORRECTION` nem hibavégállapot. A rendszer konkrét, tulajdonossal és határidővel rendelkező kéréscsomagot generál, majd csak az érintett kaput nyitja újra.

### Kapuk

| Kapu | Gépi eredmény | Emberi döntés | Kötelező kilépési feltétel |
|---|---|---|---|
| G0 Beérkezés | fájlosztályozás, duplikátum- és olvashatóság-ellenőrzés | ügyintéző validál | tanúsítás tárgya, cím, megrendelő és adatvédelmi hozzájárulás tiszta |
| G1 Bizonyíték | forrásjegyzék, hiányzó dokumentumok, ellentmondások | tanúsító kijelöli az elfogadható forrásokat | szemle/dokumentum bizonyítékcsomag elégséges |
| G2 Geometria | PDF-alávetítés, fal/helyiségjelöltek, címkézett X/Y/A audit-PDF | energetikus elfogad, javít vagy kézzel kiegészít | minden energetikai határoló azonosított; külső/lábazati falnál X/Y/A konzisztens |
| G3 Szerkezet és gépészet | rétegrend- és anyagmatch, gépészeti adatlapok, ismeretlenek listája | tanúsító jóváhagyja a feltételezést vagy kér adatot | minden számítási inputnak forrása vagy indokolt, naplózott feltételezése van |
| G4 Számítás | WinWatt/ WebWatt számítás, XML-visszaellenőrzés, eltéréslista | tanúsító ellenőrzi és aláírja a számítási verziót | nincs blokkoló eltérés; eredmények szakmailag plausibilisek |
| G5 Tanúsítvány | XML-séma/üzleti validáció, OÉNY előnézet, kiadási csomag | csak jogosult tanúsító engedélyez | az OÉNY előnézet elfogadható és a csatolmányok készek |
| G6 Hitelesítés és átadás | OÉNY válasz, HET-azonosító, átadási csomag | tanúsító/admin rögzíti | hiteles dokumentum archivált és átadás naplózva |
| G7 Számla és lezárás | számlatervezet, fizetési státusz és kintlévőségjelzés | admin kiállítja/egyezteti | a számla a hiteles átadáshoz kötött; fizetés vagy követeléskezelés állapota ismert |

## 3. Az ügy központi adata: `certification_case`

Minden kapcsolódó rekord egy ügyazonosítóhoz kötődjön. Ez nem váltja ki a meglévő táblákat, hanem összefogja őket.

```json
{
  "id": "case_2026_000184",
  "crm_lead_id": "…",
  "survey_project_id": "…",
  "offer_id": "…",
  "status": "GEOMETRY_REVIEW",
  "current_gate": "G2",
  "assigned_certifier_id": "…",
  "basis": {"purpose": "sale", "certification_scope": "functional_unit"},
  "source_bundle_id": "…",
  "model_version_id": "…",
  "winwatt_export_id": null,
  "oeny_submission_id": null,
  "invoice_id": null,
  "review_required_count": 3,
  "blocked_by_count": 1
}
```

Kapuk és döntések eseménynaplóban maradnak: ki, mikor, melyik modellverziót, milyen megjegyzéssel fogadta el vagy küldte vissza. Jóváhagyott adat módosítása mindig új verziót és az érintett későbbi kapuk érvénytelenítését hozza létre.

## 4. Hiánykérő és korrekciós protokoll

Az automatika ne szabad szövegű „nem tudom” állapotot adjon, hanem gépileg feldolgozható `evidence_request` rekordot. Egy kérés lehet ügyfélnek, helyszíni felmérőnek vagy tanúsítónak címzett.

```json
{
  "id": "req_0142",
  "case_id": "case_2026_000184",
  "gate": "G3",
  "severity": "blocking",
  "owner_role": "client",
  "subject": "Hőtermelő adattáblája",
  "why": "A kazán típusa és névleges teljesítménye nem olvasható a feltöltött fotón.",
  "requested_schema": "heating_system_v1",
  "accepted_formats": ["photo", "pdf", "json", "xml"],
  "evidence_target": {"system": "heating", "field": "generator.model"},
  "status": "open",
  "due_at": "2026-09-22"
}
```

**Ügyféloldali élmény:** rövid nyelvű kérdés, példa arra, mit kell lefotózni, feltöltési mező és alternatív űrlap. **Mérnöki oldali élmény:** a kapun látszik, hogy a válasz mely mezőt töltötte ki, mi változott a modellben, és újra kell-e futtatni a számítást.

### Adatcsere-formátumok

- **JSON**: elsődleges belső API és kérés-válasz formátum; verziózott JSON Schema-val.
- **XML**: WinWatt és OÉNY illesztés; csak adapterrétegben, validált sémával.
- **PDF/fotó**: bizonyíték, nem közvetlen számítási tény; oldalszám, képkivágás vagy annotáció hivatkozza.
- **CSV/XLSX**: tömeges helyiség-, szerkezet- vagy berendezéslista; import után ugyanúgy review-sorba kerül.

Minden adattételhez javasolt minimum: `value`, `unit`, `source_id`, `source_locator`, `confidence`, `entered_by`, `review_status`, `model_version`.

## 5. Felhasználói felület: „Tanúsítási vezérlőpult”

### Oldalszerkezet

1. **Felső kapusáv:** G0–G7, a kész, aktuális, blokkolt és még zárolt állapotok egy sorban. Egyetlen kattintás a kapu részleteire visz.
2. **Bal oldali bizonyítéktár:** dokumentumok, oldalak/fotók, eredet, feldolgozási státusz; innen indul a PDF-feldolgozás vagy az új adatbekérés.
3. **Középső munkafelület:** az aktuális kapu vizuális tárgya. G2-n alaprajz, fal- és X/Y/A címkékkel; G3-n gépészeti séma; G4-n eredmény- és eltérésnézet; G5-n XML-validáció és előnézet.
4. **Jobb oldali „Döntés és hiányok” sáv:** blokkoló, felülvizsgálandó és információs elemek; `Elfogad`, `Javít`, `Adatot kérek` műveletek, döntési naplóval.
5. **Alsó verziócsík:** forráscsomag → modell → WinWatt XML/WWP → OÉNY csomag verziói, összehasonlítható módon.

### Állapotjelölés

- **Kész:** a kapu minden kötelező ellenőrzése elfogadva.
- **Aktuális:** itt van a következő emberi döntés.
- **Blokkolt:** hiányzó bizonyíték vagy ellentmondó, számítást befolyásoló adat.
- **Felülvizsgálat:** gépi javaslat vagy nem blokkoló bizonytalanság.
- **Zárolt:** korábbi kapu jóváhagyása nélkül nem szerkeszthető és nem futtatható.

Szín mellett mindig legyen szöveges státusz és darabszám: a szín nem lehet az egyetlen jelentéshordozó.

### Három kulcsnézet

| Nézet | Mit lát a felhasználó | Döntés |
|---|---|---|
| Alaprajz-review | PDF alatt falak, helyiségek, nyílászárók; minden külső falon `X × Y = A`; hiány esetén egyértelmű címke | fal elfogadása, felosztása, hossz/magasság javítása, forrás megjelölése |
| Gépészeti-review | rendszerfa: hőtermelő → elosztás → hőleadó; HMV, hűtés, szellőzés, PV; minden csomóponton forrás vagy hiánykérés | adatlap elfogadása, paraméter megadása, helyszíni fotó kérése |
| Kiadási-review | számítási összefoglaló, XML-validáció, OÉNY-előnézet, eltéréslista és kiadási csomag | számítás jóváhagyása, XML újragenerálása, beküldés engedélyezése |

## 6. Automatizálási szabályok

| Művelet | Automatikus? | Emberi jóváhagyás |
|---|---|---|
| fájlok osztályozása, OCR, oldalak/címek kinyerése | igen | csak bizonytalan vagy ellentmondó találatnál |
| fal- és helyiségjelöltek előállítása | igen, javaslatként | minden jelölt importja előtt |
| méretlánc és fal összerendelése | igen, ha geometriailag bizonyított | nem egyértelmű esetben kötelező |
| `A=X×Y`, terület- és konzisztencia-ellenőrzés | igen, determinisztikusan | hiba javítását mérnök hitelesíti |
| katalógusanyag egyezés rangsorolása | igen | kiválasztás és új anyag létrehozása előtt |
| gépészeti fotó/OCR adatjavaslat | igen, alacsony bizalommal is | minden számítási paraméter előtt |
| WinWatt XML/WWP előállítása | igen, csak teljes kapu után | végleges kiadási XML előtt |
| OÉNY előnézet | igen, ellenőrzött szándékkal | eredmény elfogadása előtt |
| OÉNY végleges feltöltés | **nem** | kizárólag jogosult tanúsító explicit művelete |
| ügyfélnek küldött hiánykérés | előkészíthető | kiküldés előtt, sablon- vagy jogosultságfüggően |
| számlatervezet | igen, hiteles átadási eseményből | számlakiállítás előtt |

## 7. Megvalósítási sorrend

1. **Orchestrator alap:** `certification_case`, kapuállapotok, döntési és verzió-napló, `evidence_request` API. Ettől lesz minden meglévő modul egy folyamat része.
2. **Review Center UI:** kapusáv, hiánylista, döntési napló, fájl- és bizonyítékhivatkozás. Kezdetben a meglévő feldolgozások kézi indítógombjai kerülnek ide.
3. **Geometriai kapu integráció:** AutoWinWatt X/Y/A audit-PDF és eltéréslista automatikus becsatolása; blokkoló hibából közvetlen korrekciós kérés.
4. **Gépészeti adatlap és hiánykérő:** strukturált hőtermelő/HMV/szellőzés/hűtés űrlap, fotó-feldolgozás és tanúsítói review.
5. **WinWatt/OÉNY kiadási csomag:** export, validáció, előnézet, egyszeri végleges beküldés, válasz- és HET-archívum.
6. **Tanuló visszacsatolás:** elfogadott/elutasított/javított jelöltekből mérhető minőség és rangsorolás; csak validált annotáció kerül tanulóadatba.

## 8. Sikerfeltételek

- Egy projekt aktuális kapuja, felelőse, blokkoló oka és következő konkrét teendője egy képernyőn látszik.
- Egyetlen adat sem kerül végleges WinWatt/OÉNY kiadásba bizonyíték, verzió és megfelelő emberi döntés nélkül.
- A rendszer nem elrejti a hiányt, hanem kitölthető, célzott JSON/űrlap/fotó-kéréssé alakítja.
- Minden automata eredmény újrafuttatható, visszavezethető a forrásra és összehasonlítható a jóváhagyott előző verzióval.
- A végleges OÉNY-feltöltés csak jogosult tanúsító explicit, naplózott jóváhagyásával történhet.
