# WebWatt E2E #001 – PDF → validált projekt → WinWatt

## Mi lett új, és mi lett újrahasznosítva

| Igény | Meglévő megoldás | Hely | Döntés |
| --- | --- | --- | --- |
| PDF-szöveg, koordinátás evidence | PyMuPDF text-layer/OCR evidence | `ETAI_Agents/apps/api/etai_api/pdf_evidence.py` | újrahasználási szerződés; a desktop app csak renderel |
| Fal-, helyiség-, nyílászáró-geometria | vektor/raster felismerés, Shapely topológia | `ETAI_Agents/.../floorplan_recognition.py`, `floorplan_topology.py`, `floorplan_evidence.py` | reuse |
| Golden mérés | room IoU, fal/opening precision–recall, Hausdorff | `ETAI_Agents/golden/floorplans` | reuse |
| WebWatt canonical térmodell | room/boundary/nyílászáró, constraint solver | `magyar-mentor/src/utils/floorplan`, `supabase/migrations/20260329123000_add_core_canonical_model.sql` | extend adapterrel |
| WinWatt XML/WWP | natív XML compiler, UI-import/export, readback diff | `winwatt_automation/certificates/native_xml.py`, `validation.py`, `services/xml_native_service.py` | reuse |
| Review és audit | nincs közös Python desktop review queue | ez a csomag | új, minimális réteg |

## Fázis 1: lokális validáló

Kód: `src/winwatt_automation/e2e_review/`.

- `domain.py`: `ReviewCandidate` és `DocumentEvidence`; a `machine_value` minden állapotváltozáson érintetlen.
- `adapters.py`: a Google Sheetből exportált XLSX négy adatlapját olvassa. A UI ettől független domain objektumokat kap.
- `persistence.py`: WAL-os SQLite, automatikus mentés és append-only audit.
- `pdf_evidence.py`: csak olvasó PyMuPDF render, evidence bbox körüli zoom; bbox hiányában `missing_evidence_location`.
- `gui.py`: kétpaneles felület; A/E/R/U, bal/jobb nyíl, Ctrl+S.
- `exporter.py`: `approved_project.xlsx`-be eredeti lapok + `Review audit` + `Canonical project`. Csak `accepted` és `edited` sor canonical.

Indítás (PowerShell, az `autowinwatt/winwatt_automation` könyvtárban):

```powershell
.venv\Scripts\python.exe scripts\review_project.py <Google-Sheetből-exportált.xlsx> --database data\delceg-review.sqlite --pdf-root ..\test --reviewer Gabor
```

Export:

```powershell
.venv\Scripts\python.exe scripts\review_project.py <forras.xlsx> --database data\delceg-review.sqlite --export approved_project.xlsx
```

## Fázis 2: approved workbook → WWP

```powershell
.venv\Scripts\python.exe scripts\build_wwp.py approved_project.xlsx --output project.wwp --template-xml native-template.xml --execute-winwatt
```

Mindig létrejön `build_report.json` és egy canonical JSON modell. WWP csak akkor minősül elkészültnek, ha a jóváhagyott adatban szerepel minden szükséges U-érték, helyiségmagasság, határoló `x/y/A`, kapcsolt szerkezet, és a natív WinWatt import+export utáni diff is lefutott. Ellenkező esetben a program nem gyárt üres vagy hamis WWP-t; a hiányokat a report `unresolved` mezője sorolja.

## Fázis 3 állapot

### Délceg golden input

Olvasható pillanatkép készült a jelenlegi Google Sheetről:
`data/e2e/delceg_source_snapshot.xlsx`, SHA-256
`7131cd4ce0b31f8d52d745ca6805698370645bbed1cf7ad8ed793edbb9063fff`.
Ez nem ír vissza a Sheetbe és nem módosítja az eredeti PDF-eket. A jelenlegi
import 368 review candidate-et adott; mivel egyet sem hagytak még jóvá, az
első `approved_project.xlsx`-ben szándékosan nulla canonical adat van.

### Implementációs roadmap – itt a kötelező stop point

Az alábbi terv a `Forrás és automatizálás` lap és a három repo tényleges
állapota alapján készült. A `jelenleg` állítások kódra, nem csak tervre
vonatkoznak.

#### 1. Dokumentum-előkészítés / DocumentEvidence

- Cél: immutable PDF → hasholt oldal, text/word bbox, tervlapszám, lépték, dátum.
- Jelenleg/reuse: `ETAI_Agents/.../pdf_evidence.py` már PyMuPDF text layer + OCR fallback + page digestet kezel.
- Hiány / repo / fájl: WebWatt adapter; `magyar-mentor` új `prepareProjectFromFiles()` szolgáltatás, amely az ETAI rekordot `DocumentEvidence` API-ra fordítja.
- API: `DocumentEvidence(file_id, sha256, page, sheet_no, doc_type, bbox, raw_text, extraction_method, confidence)`.
- Függőség / teszt: tárhely és PDF hash; ugyanazon PDF kétszeri ingestje azonos hash és stabil oldalbbox.
- Golden metrika / sorrend / kockázat / nyereség: 1.; `page-evidence recall=100%`; rossz PDF-verzió; teljes provenance és újrafuttathatóság.

#### 2. Determinisztikus geometria és GeometryCalibration

- Cél: a mérethálóból bizonyított pixel→m transzformáció, nem névleges léptékből.
- Jelenleg/reuse: ETAI `floorplan_recognition.py`, `floorplan_topology.py`, `tools/calibrate_pdf_dimensions.py`, valamint a WebWatt `constraintSolver.ts`.
- Hiány / repo / fájl: több anchoros least-squares/affine illesztés és residual-gate; ETAI új `geometry_calibration.py`.
- API: `GeometryCalibration(anchors, transform, residual_cm, source_evidence_ids, confidence, status)`.
- Függőség / teszt: dimension-text, extension/witness line; szintetikus ismert skála + É-02/É-02B/É-02C jóváhagyott méretlánc.
- Golden metrika / sorrend / kockázat / nyereség: 2.; median residual cm, 95p residual; hibás méretvonal összekötés; mérhető falszakaszok és alaprajzi területek.

#### 3. RoomCandidate és topológia

- Cél: helyiségbélyeg + zárt topology cell párosítása, azonos nevű szobák összemosása nélkül.
- Jelenleg/reuse: ETAI Shapely polygonize/stabil cell-id; WebWatt `roomDetection.ts`, `reconciliation.ts` és autotrace room candidates.
- Hiány / repo / fájl: evidence-fusion matcher; ETAI `candidate_matching.py`, WebWatt adapter.
- API: `RoomCandidate(id, name, area, finish, level, bbox, polygon, evidence_ids, confidence, status)` és `CandidateMatch(residuals, score)`.
- Függőség / teszt: kalibráció és text bbox; névazonos roomok, hiányos cella, területeltérés regresszió.
- Golden metrika / sorrend / kockázat / nyereség: 3.; room precision/recall, matched-room IoU, area residual; nyitott falháló; gyors helyiséglista emberi ellenőrzéssel.

#### 4. BoundaryCandidate és termikus burok

- Cél: kétoldali zónakapcsolatból heated↔external/ground/unheated boundary.
- Jelenleg/reuse: ETAI felülvizsgálati falkimenet; WebWatt canonical migration és room/wall tree; AutoWinWatt `certificates/geometry.py` x/y/A-szabály.
- Hiány / repo / fájl: explicit adjacency graph és fűtöttségi review; WebWatt `thermalEnvelope.ts`, ETAI export adapter.
- API: `BoundaryCandidate(room_id, adjacent_space_id_or_type, structure_id, x_m, y_m, area_m2, gross_net, evidence_ids, confidence, status)`.
- Függőség / teszt: jóváhagyott room topology + zónastátusz; pince-fűtöttség átváltása, több külső falú room, x*y=A.
- Golden metrika / sorrend / kockázat / nyereség: 4.; boundary precision/recall és A-residual; bizonytalan pince; WinWatt mezők közvetlen előkészítése.

#### 5. OpeningCandidate

- Cél: falhézag/szimbólum + méretfelirat + parapet → adott fal és helyiség nyílászárója.
- Jelenleg/reuse: ETAI door/window evidence provider, WebWatt autotrace candidate/Opening editor, AutoWinWatt native XML panel típusok.
- Hiány / repo / fájl: stacked size-text és wall-segment association; ETAI `opening_matching.py`.
- API: `OpeningCandidate(type, width_m, height_m, parapet_m, wall_id, room_id, bbox, evidence_ids, confidence, status)`.
- Függőség / teszt: kalibrált wall segment; É-02 180/140 pm100, 95/240 és ambiguous-nearest-label fixture.
- Golden metrika / sorrend / kockázat / nyereség: 5.; opening precision/recall + width/height MAE; szöveg közelségi hiba; bruttó→nettó fal automatikus számítása.

#### 6. R-kód rétegrend és material matcher

- Cél: metszeti R-blokk → rétegek típushelyes tárolása és csak bizonyított katalógusmatch.
- Jelenleg/reuse: AutoWinWatt `certificates/local_extract.py`, `materials.py`, `layer_audit.py`; WebWatt anyagkatalógus; a Sheet konkrét R1–R16 source-evidence.
- Hiány / repo / fájl: `section_size`, range, layer_count és product-name conflict közös canonical típusa; közös `LayerCandidate` adapter.
- API: `LayerCandidate(material_text, thickness|min|max, section_size, layer_count, catalog_id?, match_score, evidence_ids, status)`.
- Függőség / teszt: catalogue snapshot; R1B 30/50 mm, R6 2–5 cm, Porotherm 38/30 cm konfliktus.
- Golden metrika / sorrend / kockázat / nyereség: 6.; exact layer sequence, catalog-match precision; túl agresszív anyag-azonosítás; WinWatt anyagadatbázis biztonságos használata.

#### 7. 3D RoofBoundaryCandidate

- Cél: tetőtéri room polygon + 1,90 m jel + metszeti tetősíkból ferde határoló.
- Jelenleg/reuse: ETAI geometry evidence; WebWatt floorplan geometry; AutoWinWatt explicit x/y/A validation.
- Hiány / repo / fájl: roof-plane clipping és 3D surface calculator; ETAI `roof_geometry.py`.
- API: `RoofBoundaryCandidate(room_id, plane, polygon3d, area_m2, openings, evidence_ids, confidence, status)`.
- Függőség / teszt: 2D rooms, metszeti ridge/eaves/pitch, calibration; TT-01 tetőablak és 1,90 m vonal ne legyen room height.
- Golden metrika / sorrend / kockázat / nyereség: 7.; roof-area residual; hiányos metszeti kapcsolat; reprodukálható tetőtéri energetikai felület.

#### 8. Semantic és opcionális neural evidence

- Cél: a geometria független semantic/raster evidence-t kapjon, sose önálló igazságforrást.
- Jelenleg/reuse: ETAI `floorplan_evidence.py`, `ai/raster2seq/service.py`, evidence cache, coordinate transform.
- Hiány / repo / fájl: WebWatt evidence provider registry + provider attribution a ReviewCandidate-ben.
- API: meglévő `EvidenceSet/Detection`, kiegészítve `SemanticEvidence(type, raw_text, bbox, confidence)`.
- Függőség / teszt: PDF render, hash, opcionális konténer; provider unavailable esetén deterministic pipeline továbbmegy.
- Golden metrika / sorrend / kockázat / nyereség: 8.; geometry-only kontra +semantic kontra +Raster2Seq; model drift/költség; jobb bizonytalanságjelzés, nem kötelező credit.

#### 9. Constraint / evidence fusion és review

- Cél: magyarázható, maradékokat mutató jelöltpárosítás, majd mérnöki kapu.
- Jelenleg/reuse: ETAI evidence model; WebWatt candidate review; az új SQLite/PySide6 validáló.
- Hiány / repo / fájl: közös scoring policy és WebWatt API adapter; `e2e_review` későbbi HTTP adaptere.
- API: `ReviewCandidate` kész; `CandidateMatch(score, spatial_score, area_residual, topology_score, ai_agreement, evidence_ids)` új.
- Függőség / teszt: 1–8; conflict/low-confidence állapot, reject nem kerül canonicalba, audit replay.
- Golden metrika / sorrend / kockázat / nyereség: 9.; accepted-data precision és review-idő/candidate; score látszólagos bizonyossága; auditálható emberi felelősség.

#### 10. Canonical WebWatt → AutoWinWatt/WWP

- Cél: kizárólag accepted/edited canonical adatokból való, verziózott WWP és readback diff.
- Jelenleg/reuse: WebWatt export-contract, AutoWinWatt `native_xml.py`, `validation.py`, `NativeXmlService`.
- Hiány / repo / fájl: approved XLSX/JSON → WebWatt canonical → AutoWinWatt mapping adapter; ez az első verzióban `e2e_review/wwp_builder.py`.
- API: `build_wwp.py approved_project.xlsx --output project.wwp`; `build_report.json`.
- Függőség / teszt: jóváhagyott U, layer properties, x/y/A, room height, native template; full native import/export/reopen diff.
- Golden metrika / sorrend / kockázat / nyereség: 10.; source-vs-readback object count, area, U×A, x/y/A diff=0; WinWatt-version eltérés; nem csak szintaktikus WWP.

#### 11. Délceg golden set és ablation

- Cél: három alaprajz és metszet kézzel jóváhagyott referenciával, fejlesztési döntések mérésére.
- Jelenleg/reuse: ETAI `golden/floorplans/METRICS.md`, `run_floorplan_golden_set.py`.
- Hiány / repo / fájl: Délceg manifest + approved geometry/evidence export, source hash; `ETAI_Agents/golden/floorplans/delceg.*`.
- API: `GoldenFloorplan(source_hash, approved_geometry, metrics, fixture_version)`.
- Függőség / teszt: explicit reviewer signoff; fixture checksum, split-by-project, four ablation runs.
- Golden metrika / sorrend / kockázat / nyereség: 11.; room IoU, wall P/R, opening P/R, Hausdorff, area residual; túlillesztés egy projektre; objektív fejlesztési prioritás.

#### 12. Human correction → training sample

- Cél: csak opt-in, anonimizált és jóváhagyott korrekció váljon tanítóadattá.
- Jelenleg/reuse: ETAI geometry-learning migration és export eszközök, új audit trail.
- Hiány / repo / fájl: explicit consent, anonymizer, data manifest; ETAI `training_samples` exporter.
- API: `TrainingSample(source_hash, predictions, corrections, approved_geometry, consent, dataset_version)`.
- Függőség / teszt: Golden review és jogi hozzájárulás; personal-data stripping, no-consent export blocked.
- Golden metrika / sorrend / kockázat / nyereség: 12.; annotation completeness, holdout improvement; ügyfélanyag szivárgása; minőségi tanítóadat.

#### 13. Saját Raster2Seq tréning – csak később

- Cél: csak mérhető baseline-utáni finomhangolás.
- Jelenleg/reuse: ETAI Raster2Seq service, container, dataset preparation és remote-run docs.
- Hiány / repo / fájl: elegendő projekt-szintű train/valid split és model registry promotion gate.
- API: meglévő `EvidenceSet(model, model_version, input_hash)`; új `TrainingRun(dataset_version, split, metrics, approval)`.
- Függőség / teszt: legalább 20–30 jóváhagyott, anonim projekt; held-out project evaluation, regression baseline.
- Golden metrika / sorrend / kockázat / nyereség: 13.; a négy ablation változatban javuló holdout room IoU/opening recall; kevés mintás túlillesztés; csak akkor emelkedő automatizálási arány.

**Stop point:** a 3. fázis terve elkészült. A 4. fázis – ezen komponensek iteratív implementációja, golden evaluation és commitok – csak külön, kifejezett `mehet` / `OK, implementáld` jóváhagyás után indulhat.
