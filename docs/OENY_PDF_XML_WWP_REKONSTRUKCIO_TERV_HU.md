# OÉNY PDF+XML → WinWatt WWP rekonstrukciós terv

Az első konkrét pilot végrehajtási állapota és az AI → helyi worker átvezetés:
`docs/OENY_10479210_PILOT_ALLAPOT_HU.md`.

## 1. Cél és pontos kimenet

Az OÉNY-ből letöltött `UploadRequest` XML és annak
`CalculationsPdfFileContent` mezőjében lévő WinWatt számítási PDF alapján
ellenőrizhető, új WinWatt projektet kell készíteni.

Egy sikeres job kimenete:

- `reconstructed.wwp` – új, újranyitható WinWatt projekt;
- `reopened_native.xml` – a mentett és újranyitott projekt natív WinWatt exportja;
- `certificate.xml` – az új projektből, a WinWatt ET-varázslójával előállított
  `UploadRequest`;
- `calculation.pdf` – a fenti XML Base64 mezőjéből dekódolt PDF;
- `comparison.json` – mező-, táblázat-, számítási és eltérésriport;
- `manifest.json` – forrás-, program-, projekt- és kimeneti SHA-256 lenyomatok.

A `calculation.pdf` nem az OÉNY által kiadott hiteles tanúsítvány-PDF. A hiteles
PDF az OÉNY oldali feldolgozás eredménye; azt a WinWatt önmagában nem állítja
elő. A jelen terv a WinWatt számítási munkarész-PDF-jére vonatkozik.

## 2. Mit jelent a rekonstrukció

Két külön célt kell nyilvántartani:

1. **Eredményazonos modell:** az új WWP lényegi számítási adatai, nyomtatott
   táblázatai és az ET XML ellenőrzött mezői a forrás eredményeivel egyeznek.
2. **Eredeti projekt rekonstrukciója:** a belső helyiség-, objektum-, katalógus-
   és azonosítóstruktúra is azonos az elveszett eredeti WWP-vel.

PDF+tanúsítási XML alapján általánosan csak az első cél bizonyítható. A PDF
sok részletes szerkezeti, felületi, zóna-, havi és rendszeradatot tartalmaz, az
XML pedig aggregált tanúsítási és adminisztratív adatokat. Ezek nem tartalmazzák
garantáltan az eredeti WWP minden belső objektumát, katalógusazonosítóját,
helyiségfelosztását, alaprajzi kapcsolatát és rejtett alapértékét. Egyetlen
eredményhez ezért több különböző WWP is vezethet.

A rendszer minden állítást `exact`, `derived`, `inferred` vagy `unresolved`
provenance státusszal tárol. `inferred` és `unresolved` adat nem kerülhet
automatikusan kiadási WWP-be.

## 3. Jelenlegi helyzet és verziókapu

A helyi állományban 1060 szabályosan elnevezett XML van. A
`CertifierDetails/SoftwareAndVersion` megoszlása:

| WinWatt-verzió | Darab |
|---|---:|
| 9.06 | 2 |
| 9.11 | 225 |
| 9.17 | 59 |
| 9.19 | 3 |
| 9.22 | 152 |
| 9.27 | 289 |
| 9.36 | 112 |
| 9.43 | 28 |
| 9.51 | 44 |
| 9.54 | 16 |
| 9.56 | 130 |

A bizonyított helyi profil jelenleg `winwatt_8c137b67c0a2214bb91aeae8`, WinWatt
9.60 x86. Régebbi motorral készült PDF bájtszintű vagy teljes tördelési
azonossága 9.60 alatt nem várható, és kisebb számítási eltérés is lehetséges.

Ezért minden job egyik módot kapja:

- `current_engine_reconstruction`: 9.60-as újraszámítás, dokumentált eltéréssel;
- `version_exact_reconstruction`: csak azonos verziójú, lenyomattal rögzített,
  külön helyi profil esetén;
- `blocked_missing_version`: ha a követelt verzióazonosság motorja hiányzik.

Külön WinWatt-verziók nem futhatnak egyszerre, és minden verzióhoz saját
profil-, EXE-, erőforrás- és katalóguslenyomat kell.

## 4. Helyi worker-architektúra

Az AI csak fejlesztési és bizonytalanság-feloldási szerepet kap. A tömeges
feldolgozást determinisztikus helyi Python workerek végzik.

```text
forráspár
  │
  ├─ W0 leltár/hash
  ├─ W1 XML parser ─────────┐
  ├─ W2 PDF parser/OCR ─────┼─ W3 normalizált reconstruction_spec.json
  └─ W4 katalógusfeloldó ───┘
                                │
                         W5 offline preflight
                                │
                    egyetlen WinWatt UI worker
                  W6 build → save → reopen → calculate
                                │
                    ET XML export + PDF dekódolás
                                │
                 W7 diff/constraint/új iteráció
                                │
                         W8 csomag és review
```

### Párhuzamosság

- W0–W5 és W7–W8: 4–8 helyi CPU workerrel párhuzamosítható.
- W6: mindig pontosan egy WinWatt UI worker. A helyi invariant tiltja két
  WinWatt UI automatizmus egyidejű futását.
- A CPU-workerek fájljobalapú sort töltenek; a WinWatt-worker csak `ready`
  állapotú, preflightolt jobot vesz át.
- Minden job saját, új output könyvtárat és WWP-másolatot kap.

## 5. Feldolgozási szakaszok

### P0 – Forrásleltár

1. XML/PDF pár azonosítása tanúsítványazonosítóval.
2. XML jólformáltság, gyökérelem és Base64 szigorú dekódolása.
3. A dekódolt tartalom `%PDF-` és `%%EOF` ellenőrzése.
4. Források SHA-256 lenyomata és változatlansági kapu.
5. WinWatt-verzió, oldalszám, fő blokkok és fotók leltára.

### P1 – XML worker

Az XML worker strukturáltan kinyeri legalább:

- épület- és adminisztratív adatokat;
- hasznos alapterületet, kondicionált térfogatot, A/V arányt;
- kategóriákat és számított főértékeket;
- határoló- és nyílászáró-típusok aggregált U-értékét és méretét;
- rendszer-minősítéseket;
- energiahordozó és felhasználási cél szerinti értékeket;
- fotókat;
- a beágyazott számítási PDF-et.

### P2 – PDF worker

Elsődleges út: szöveg- és táblázatkivonás. OCR csak képoldal vagy hibás font
esetén. Minden értékhez oldalszám, szövegrész/bbox és confidence tartozik.

Kinyerendő blokkok:

- szerkezettípusok, rétegek és anyagjellemzők;
- nyílászáró komponensek;
- határoló felületek, tájolás, hajlás, U/U*, hossz és hőhíd;
- hőtároló tömegek;
- használati, hőegyensúlyi és számítási zónák;
- havi hőmérleg;
- fűtés, HMV, hűtés, légtechnika, világítás és megújulók;
- veszteségek, segédenergiák és energiahordozók;
- végső, primer és CO2-eredmények;
- felújítási javaslatok, ha vannak.

### P3 – Normalizált rekonstrukciós modell

A két parser eredménye `reconstruction_spec.json` fájlba kerül. Minden mező:

```json
{
  "value": 32.8,
  "unit": "m2",
  "source": {"file": "10479210.xml", "path": "BuildingData/UsefulFloorArea"},
  "status": "exact",
  "confidence": 1.0
}
```

Az XML és PDF eltérése blokkoló konfliktus, nem átlagolandó. A worker külön
kezeli a megjelenített kerekített értéket és a számításhoz szükséges lehetséges
értéktartományt.

### P4 – Modellváltozat kiválasztása

Ha a PDF nem tartalmaz helyiségenkénti geometriát, a job
`result_equivalent_surrogate` jelölést kap. Ekkor a cél a nyomtatott zóna- és
épületeredmények reprodukálása, nem az elveszett helyiséggráf kitalálása.

Teljes belső modell csak akkor épülhet, ha minden helyiség, határoló és
nyílászáró hozzárendeléshez forrás van. Forrás nélküli tipikus érték vagy
automatikus szakmai feltételezés tilos.

### P5 – Offline kapuk

1. Dimenzió- és mértékegység-ellenőrzés.
2. Összegazonosságok: felületek, terület, térfogat, energiahordozók.
3. PDF–XML főérték-egyezés.
4. Anyag- és katalógusfeloldás.
5. `winwatt.certificate.preflight --scope envelope`, majd a rendszerek után
   `g5_calculation`.

`review_required` vagy `failed` job nem kerülhet a WinWatt-sorba.

### P6 – WWP létrehozás és roundtrip

Profilazonos 32 bites Python használatával, új sandboxban:

1. helyiségek;
2. rétegrendes és egyéb szerkezetek;
3. határolók, nyílászárók, tájolások;
4. fűtött/hűtött zónák;
5. jóváhagyott gépészeti rendszerek;
6. mentés;
7. teljes WinWatt-bezárás és újranyitás;
8. natív XML export és gépi visszaolvasás.

A zónát nem szabad pusztán név alapján elfogadni: pozitív, várt terület és
újranyitás utáni tagság szükséges.

### P7 – Számítás, XML és PDF

1. `winwatt.building.calculation.result_roundtrip` futtatása.
2. `full_certificate` preflight.
3. `winwatt.certificate.et_xml.export` futtatása.
4. Az új `certificate.xml` `CalculationsPdfFileContent` mezőjének szigorú
   Base64-dekódolása `calculation.pdf` fájlba.
5. A külön PDF hashének összevetése az XML-be ágyazott bájtok hashével.

Ezzel a PDF és az XML ugyanabból a WinWatt ET-exportból származik. A meglévő
`probe_et_calculation_pdf_export.py` külön PDF-export út, de amíg nincs a
verified tool-regiszterben, nem ez az elsődleges termelési út.

### P8 – Eltérésvezérelt iteráció

A diff worker három szinten hasonlít:

1. **XML:** kanonizált mezőút, típus, enum és számérték;
2. **PDF:** táblázati/címkeértékek, oldalak, kategóriák és számítási sorok;
3. **WWP readback:** objektumszám, terület, térfogat, szerkezet, zóna és rendszer.

Az optimalizálás csak olyan bemenetet változtathat, amelynek forrása vagy
jóváhagyott tartománya van. Egy eltérés nem jogosít fel ismeretlen adat
önkényes hangolására.

## 6. Elfogadási feltételek

### WWP

- mentés, teljes bezárás és újranyitás sikeres;
- natív XML readback egyezik a reviewed modellel;
- a forrásfájlok hash-e változatlan;
- nincs `unresolved` kiadási mező.

### Számítási PDF

- érvényes PDF és minden oldal renderelhető;
- a WinWatt-verzióhoz kötött összehasonlítási mód rögzített;
- minden kategorikus érték és táblázatsor egyezik;
- minden kijelzett szám a forrás kijelzési pontosságán egyezik;
- az XML-ből dekódolt PDF hash-e megegyezik a leadott `calculation.pdf` hashével.

Bájtszintű PDF-egyezés csak azonos WinWatt-verzió, azonos nyomtatási út,
azonos metaadat és determinisztikus PDF-generálás esetén elvárható. Egyébként
tartalmi és vizuális egyezést kell mérni.

### Tanúsítási XML

- jól formált `UploadRequest`;
- a beágyazott PDF dekódolható és teljes;
- a determinisztikus szakmai mezők pontosan egyeznek;
- kerekített számok a dokumentált tolerancián belül egyeznek;
- adminisztratív és fotómezők explicit forrásból származnak;
- az XML még helyi artefaktum, nem OÉNY-feltöltés és nem tanúsítói kiadás.

## 7. Szükséges új capability-k

A teljes automatikus lánc jelenleg még nincs verified állapotban. A tömeges
rekonstrukció előtt bizonyítani és regisztrálni kell:

1. több helyiség és teljes határoló/nyílászáró gráf batch roundtripjét;
2. minden, a korpuszban előforduló szerkezettípus paraméterezését;
3. tetszőleges, nem csak minimális fűtési/HMV/hűtési/légtechnikai rendszer
   mezőszintű roundtripjét;
4. natív XML-import utáni valódi zónatagság és pozitív terület megtartását;
5. a PDF-parser táblázati sémáit és kerekítési modelljét;
6. a rekonstrukciós spec → WWP teljes buildert;
7. a PDF/XML szemantikus diffet;
8. igény esetén a külön számítási PDF-export probe verified tool-lá emelését;
9. opcionálisan a szükséges régi WinWatt-verziók izolált profiljait.

Megfigyelt UI-gráf önmagában nem végrehajtható capability; minden új író tool
mentés–teljes újranyitás–visszaolvasás bizonyítást kap.

## 8. Bevezetési sorrend

### Pilot A – egy egyszerű 9.56-os ügy

- egy zóna;
- egyszerű fűtés és HMV;
- nincs hűtés, légtechnika vagy helyi energiatermelés;
- a PDF szövegesen jól olvasható.

Cél: teljes helyi lánc, nem feltétlen nulla eltérés.

### Pilot B – három reprezentatív ügy

1. egyszerű;
2. több szerkezet/nyílászáró;
3. összetettebb gépészet vagy megújuló.

Cél: parser- és builder-lefedettség, eltéréstípusok katalogizálása.

### Pilot C – verzióstratifikált validáció

Minden forrásverzióból legalább egy egyszerű és egy összetett ügy. Ha csak
9.60 érhető el, ezek `current_engine_reconstruction` módban futnak.

### Tömeges feldolgozás

Csak akkor indul, ha a pilotokon:

- a WWP roundtrip kapu passed;
- a PDF/XML diff determinisztikus;
- az automatikus retry idempotens;
- az ismeretlen mezők review-sorba, nem csendes defaultba kerülnek;
- a WinWatt UI-worker hosszú futásban checkpointolható és folytatható.

## 9. Felelősségi határok

- **Helyi determinisztikus kód:** parsing, OCR előfeldolgozás, hash, képlet,
  katalógus, queue, preflight, diff, retry és manifest.
- **AI:** ismeretlen PDF-elrendezés értelmezése, parserfejlesztési javaslat,
  ellentmondás és review-kérdés megfogalmazása; nem tömeges rejtett döntés.
- **WinWatt UI-worker:** projektépítés, mentés/újranyitás, számítás és ET export.
- **Tanúsító szakember:** bizonytalan műszaki adat, szakmai alkalmazhatóság és
  végleges kiadás.

## 10. Helyi bizonyítékok

- `winwatt_automation/data/knowledge/certification_knowledge.json` –
  `building.calculation.result_roundtrip`, `certificate.et_xml.export`,
  `building.native_xml_zone_membership_gap`.
- `winwatt_automation/data/capabilities/certification_tools.json` – verified és
  observed tool-szerződések.
- `docs/WINWATT_CODEX_MUNKAMODSZER_HU.md` – profil-, sandbox-, roundtrip- és
  forrásváltozatlansági invariantok.
- `energetika/tanúsítvány/dokumentacio-v3.0.12035/docs/validationRules.md` –
  `13. calculationsPdfFileContent`.
- `energetika/tanúsítvány/dokumentacio-v3.0.12035/test/system/data/xml/general_cert.xml`
  – `UploadRequest` blokkok és `CalculationsPdfFileContent` példa.
- `docs/Q7_EXPORTCSOMAG_HU.md` – WWP, natív XML, számítási PDF, tanúsítási XML
  és fotócsomag ellenőrzési szerződése.
- `docs/CASE02_CODEX_WWP_REKONSTRUKCIO_TERV_HU.md` – provenance, reviewed model,
  preflight, WWP roundtrip és vak összehasonlítás mintája.
