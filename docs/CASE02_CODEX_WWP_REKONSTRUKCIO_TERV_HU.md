# Case02: Codexszel támogatott WWP-rekonstrukció

## Cél és választás

A `project25_test_corpus_20261004a/case02_multistorey_xml` projektből a nyers,
nem WWP és nem XML források alapján ellenőrizhető WinWatt-modell, majd sandbox
WWP készül. Az eredeti `model.wwp` és `certificate_upload.xml` a rekonstrukció
alatt lezárt referencia. Csak a kész eredmény vak kiértékelésekor használható.

A projektet azért választjuk első próbának, mert nem kézzel rajzolt tervből
indul. Három szint alaprajza, homlokzati terv, helyszínrajz és öt fotó áll
rendelkezésre. A tervlapok géppel készültek, de a PDF-ben lapított képként
szerepelnek: a jelenlegi szöveg- és vektorkivonó ezért nem olvassa őket. A
Codex vizuálisan feldolgozhatja őket; ugyanez referenciafeladatot ad a későbbi
helyi OCR- és geometriafeldolgozóhoz.

## Engedélyezett és tiltott bemenetek

| Szerep | Tesztmásolat |
|---|---|
| földszinti alaprajz | `case02_multistorey_xml/floor_ground.pdf` |
| első emeleti alaprajz | `case02_multistorey_xml/floor_1.pdf` |
| második emeleti alaprajz | `case02_multistorey_xml/floor_2.pdf` |
| homlokzati terv | `case02_multistorey_xml/facade.pdf` |
| helyszínrajz | `case02_multistorey_xml/site.pdf` |
| homlokzati fotó | `case02_multistorey_xml/photo_facade.jpg` |
| kazánfotó | `case02_multistorey_xml/photo_boiler.jpg` |
| hűtési fotó | `case02_multistorey_xml/photo_cooling.jpg` |
| napelemfotó | `case02_multistorey_xml/photo_solar.jpg` |
| osztó-gyűjtő fotó | `case02_multistorey_xml/photo_manifold.jpg` |

Tiltott generálási bemenet a `model.wwp`, a `certificate_upload.xml`, valamint
bármely ezekből korábban kinyert projektérték vagy jel.

## Biztonsági és bizonyítási szabályok

1. Minden feldolgozás a tesztmásolaton történik.
2. A forrásfájlok SHA-256 értéke futás előtt és után azonos marad.
3. Minden felismert mezőhöz forrásfájl, oldalszám, képi terület, confidence és
   döntési mód tartozik.
4. A Codex csak javaslatot készít; bizonytalan szakmai adat nem válhat
   automatikusan jóváhagyott bemenetté.
5. A geometriai és szakmai review külön kapu.
6. WinWatt csak teljesített envelope preflight után indulhat.
7. Minden WinWatt-írás új, üres output könyvtárban és új WWP-ben történik.
8. Sikerhez kötelező a mentés, teljes bezárás, újranyitás, natív XML-export és
   gépi visszaolvasás.
9. A meglévő referencia-WWP soha nem módosítható.

## Tervezett kimeneti szerkezet

```text
case02_reconstruction_<run-id>/
├── 00_source_inventory/
├── 01_visual_evidence/
├── 02_geometry_review/
├── 03_model/
│   ├── model.draft.json
│   ├── model.reviewed.json
│   ├── unresolved_items.json
│   └── layer_audit.json
├── 04_preflight_envelope/
├── 05_winwatt_roundtrip/
│   ├── native_import.xml
│   ├── reconstructed.wwp
│   ├── reopened_export.xml
│   └── readback_validation.json
├── 06_systems_and_calculation/
├── 07_certificate_export/
└── 08_blind_reference_comparison/
```

## R1 – Forrásleltár és vak referenciazár

A futás létrehozza az engedélyezett bemenetek hash-listáját. A WWP és az XML
csak fájlnévvel, mérettel és hash-sel kerül a zárt listába. Tartalmuk sem a
Codexnek adott kivonatba, sem a strukturált modellbe nem kerülhet.

Sikerkritérium: tíz engedélyezett forrás, két visszatartott referencia és a
corpus manifesttel egyező másolathashek.

## R2 – Vizuális dokumentumfeldolgozás

Minden tervlap nagy felbontású képként készül elő. A Codex oldalanként
strukturált jelölteket készít:

- szint és rajztípus;
- helyiségnév és feltüntetett terület;
- külső és belső faljelölt;
- nyílászáró és méretjelölt;
- méretlánc;
- szintmagasság, belmagasság és szintjel;
- fűtött, fűtetlen vagy bizonytalan tér;
- terven szereplő szerkezeti vagy anyagmegjegyzés.

Minden jelölt `pending` állapotú. A terven nem látható adatot nem szabad
tipikus értékkel helyettesíteni.

## R3 – Geometriai gráf és grafikus review

A vizuális jelöltekből szintenként gráf készül. Csomópontjai a
falcsatlakozások, élei a falszakaszok, zárt poligonjai a helyiségek. A gráf
tárolja az ajtókat, ablakokat, szomszédságokat, a külső kontúrt és az egyes
élekhez rendelt méretbizonyítékot.

A rendszer összeveti a poligonból számolt és a tervre írt helyiségterületet.
Eltérésnél nem átlagol: review-feladatot készít. Az overlay külön színnel
mutatja a jóváhagyható, bizonytalan és hiányos elemeket.

Kötelező emberi döntések várhatóan az északi irány, a fűtött–fűtetlen határ,
a falvastagság és nettó/bruttó méretezés, a lépcsők és aknák, az egymás fölötti
szintek kapcsolata, valamint a hiányos méretláncok.

### Meglévő, újrahasználandó review-rendszer

Ehhez nem készül új grafikus ellenőrző felület nulláról. A már elkészült
megoldás két repóban, egymást kiegészítve található:

- `M:\Repositories\ETAI_Agents\apps\api\etai_api\floorplan_recognition.py`
  a helyi raszter/vektor felismerő. Fal-, helyiség-, nyílászáró-, méret- és
  kontúrjelölteket ad, és a koordinátákat a PDF-oldal előnézetének
  koordinátarendszerében tartja;
- `M:\Repositories\ETAI_Agents\apps\api\etai_api\main.py` biztosítja a
  felismerési, előnézeti és evidence-végpontokat;
- `M:\Repositories\magyar-mentor\src\components\draftsman\FloorplanCanvas.tsx`
  a tervre rajzolja a fal- és helyiségjelölteket;
- `M:\Repositories\magyar-mentor\src\components\draftsman\AutotraceReviewPanel.tsx`
  kijelölést, confidence-kijelzést, elfogadást, elutasítást, visszaállítást,
  felezést és összevonást ad;
- `M:\Repositories\magyar-mentor\src\modules\pdfReviewContract.ts` és a
  `20260924090000_add_pdf_review_evidence.sql` migráció az oldal-, bbox-,
  forráshash-, felismerési mód-, confidence- és review-státusz szerződése.

A case02 integráció egy vékony adapter legyen: az ETAI felismerési eredményét
a Draftsman `AutotraceWallCandidate` és room-candidate formátumára alakítja,
majd ugyanazt az oldalképet használja háttérként. Így egy listaelem
kiválasztása a PDF megfelelő fal- vagy helyiségjelöltjét emeli ki. Csak az
`accepted` vagy kézzel javított elemek kerülhetnek a `model.reviewed.json`
geometriájába; az elutasítás és minden javítás eseményként megmarad.

A két megoldás jelenleg nem igazoltan alkot egyetlen, case02-ig végig bekötött
folyamatot. Az adaptert és a koordinátaazonosságot teszttel kell bizonyítani:
ugyanaz a jelölt jelenjen meg a forrásoldalon, a preview PNG-n és a review
canvasen, egyértelmű oldal- és bbox-hivatkozással.

## R4 – Strukturált épületmodell

A `model.draft.json` a meglévő natív XML-fordító szerződését követi:

- `project`: név, fűtött alapterület, fűtött térfogat,
  `require_wall_xy: true`;
- `buildings`: épület vagy épületrészek;
- `rooms`: név, szint, terület, magasság, térfogat, téli hőmérséklet és
  légcsere;
- `structures`: név, típus, U-érték vagy rétegrendi eredet;
- `layers`: sorrend, anyag, vastagság és fizikai adatok;
- `boundaries`: helyiség, szerkezet, hossz, magasság, felület, lejtés és
  azimut;
- `systems`: külön review alatt álló gépészeti objektumok.

Minden adat hordozza a forrást, confidence értéket, döntési módot és review
állapotot. A `model.reviewed.json` csak jóváhagyott vagy determinisztikusan
bizonyított adatot tartalmazhat.

## R5 – Szerkezetek és rétegrendek

Az alaprajzok a geometriát jól támogathatják, de önmagukban várhatóan nem
adják meg a teljes rétegrendet és U-értéket. Ezek forrása tervmegjegyzés,
rétegrendi dokumentum, felhasználói adat vagy más, az épülethez kötött
bizonyíték lehet. Forrás nélkül a rendszer nem állít elő tipikus rétegrendet;
az envelope preflight `review_required` marad.

## R6 – Gépészeti adatmodell

A fotók alapján a Codex berendezés- és rendszerjelölteket készíthet a kazán,
hűtés, napelem és osztó-gyűjtő számára. A fotó önmagában nem igazolja a
teljesítményt, hatásfokot, szabályozást vagy veszteségi adatokat. Ezek csak
olvasható adattábla, gépkönyv, felhasználói adat vagy más egyértelmű bizonyíték
alapján hagyhatók jóvá.

A jelenlegi verified rendszertoolok a végrehajtási mechanizmust igazolják. A
minimális tesztbeállításaik nem helyettesítik a valós épület szakmai
paraméterezését.

## R7 – Envelope preflight

A `winwatt.certificate.preflight` először `envelope` scope-pal fut. A WinWatt
előtti kapunál a `model.project`, `model.references`, `model.wall_geometry` és
`model.heated_totals` ellenőrzésnek passed állapotúnak kell lennie. A
`materials.catalog` csak feloldott anyagdöntésekkel fogadható el.

A `winwatt.readback` ekkor még jogszerűen `review_required`, mert a WWP nem
készült el. Ez az egyetlen elfogadható nyitott envelope-ellenőrzés a WinWatt
első indítása előtt.

## R8 – Sandbox WWP roundtrip

A jóváhagyott modellből verzióazonos sablonnal natív XML készül. A rendszer
új WWP-célfájlt hoz létre, importálja az XML-t, ment, teljesen bezárja a
WinWattot, újranyitja a projektet és natív XML-be visszaexportálja.

A readback kapu összeveti az objektumszámokat, terület- és térfogatösszegeket,
szerkezettípus és tájolás szerinti felületeket, falgeometriát, nyílászárókat,
helyiségfeltételeket, rétegsorokat és anyagtulajdonságokat. Csak az a WWP
tekinthető sikeres tervezetnek, amely újranyitás után is egyezik a jóváhagyott
modellel, miközben minden forráshash változatlan.

## R9 – Gépészet, számítás és ET export

A jóváhagyott rendszereket a profile-compatible verified toolok állítják be.
Ezután a `g5_calculation` preflight, a számítási roundtrip és a
`full_certificate` preflight következik. Az ET-varázsló csak teljes épület,
szerkezetek, rendszerek, adminisztráció és számítási eredmények mellett indul.

A `winwatt.certificate.et_xml.export` helyi UploadRequest XML-t készít. Ez még
nem külső feltöltés és nem tanúsítói véglegesítés.

## R10 – Vak összehasonlítás a referenciával

A referencia-WWP és a Lechner/OÉNY XML csak a rekonstruált projekt lezárása
után használható. Az összehasonlítás méri az objektum- és helyiségszámot, a
fűtött területet és térfogatot, határoló felületeket, szerkezeteket, U-értékeket,
rendszereket, számítási eredményeket és az ET XML lényegi mezőit.

Az eltérés nem írhatja vissza automatikusan a rekonstruált modellt. Javítás
csak dokumentált második iterációban történhet, hogy az első vak próba
eredménye megmaradjon.

## Mérföldkövek

| Mérföldkő | Kimenet | Kész, ha |
|---|---|---|
| M1 – forrászár | két manifest | minden hash egyezik |
| M2 – vizuális kivonás | evidence ledger | minden tervlap és fotó feldolgozva |
| M3 – geometria | három szint gráfja és overlaye | minden fűtött helyiség zárt vagy review-listán van |
| M4 – reviewed modell | `model.reviewed.json` | nincs forrás nélküli adat |
| M5 – envelope | preflight report | modellkapuk passed |
| M6 – WWP | sandbox WWP és readback | teljes roundtrip passed |
| M7 – számítás | calculation report | G5 és eredmény-roundtrip passed |
| M8 – tanúsítvány | ET XML | jól formált, helyileg validált XML |
| M9 – értékelés | comparison report | vak referencia-összevetés elkészült |

## Szerepek

**Codex:** vizuális értelmezés, bizonyítékhoz kötött modelljavaslat,
ellentmondások és hiányok felismerése, workflow-koordináció.

**Helyi Python:** fájlhash, OCR/parser eredmények, geometriai és modellkapuk,
natív XML-fordítás, tool-végrehajtás, readback és riportok.

**Felhasználó/tanúsító:** bizonytalan geometria, szerkezeti adatok, gépészeti
paraméterek, adminisztráció és szakmai véglegesítés jóváhagyása.

**WinWatt:** projektfájl létrehozása, natív import, rendszerek, számítás és ET
XML export.

## Első végrehajtandó munkacsomag

Az első futás M1–M3-ig tartson: forrászár, az öt tervlap teljes vizuális
kivonása, majd a három szint geometriai jelöltgráfja és review-overlaye.
WinWatt ebben a munkacsomagban még nem indul el.
