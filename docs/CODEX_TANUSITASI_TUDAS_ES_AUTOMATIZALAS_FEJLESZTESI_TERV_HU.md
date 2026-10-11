# Codex tanúsítási tudás- és automatizálási fejlesztési terv

## 1. Cél

A fejlesztés célja, hogy a Codex és a helyi workerek egy tervcsomagból,
ellenőrizhető emberi döntésekkel, végig tudják vezetni a magyar energetikai
tanúsítás munkafolyamatát, és végül érvényes tanúsítási `UploadRequest` XML-t
állítsanak elő.

A kész rendszer ne csak XML-t szerializáljon. Bizonyítsa azt is, hogy:

- a felhasznált szakmai szabály verziója és forrása ismert;
- a tervből származó geometria visszakövethető;
- a WinWatt-modell újranyitható és visszaolvasható;
- a számítás ténylegesen lefutott;
- a tanúsítási XML a számítás aktuális eredményéből készült;
- a kötelező számítási PDF valóban az XML része;
- a végső energetikai mutatók eltérése referenciaeseten mérhető;
- minden automatikus és emberi döntés auditálható.

## 2. Vizsgált kiinduló állapot

### 2.1 AutoWinWatt

Az AutoWinWattban már rendelkezésre áll:

- verzióprofilhoz kötött WinWatt automatizálás;
- kurált `certification_knowledge.json` tudástár;
- `certification_tools.json` képességregiszter;
- tool runner és futási bizonyítékok;
- offline `envelope` és `full_certificate` preflight;
- helyiség-, szerkezet-, határoló-, zóna- és több gépészeti roundtrip tool;
- WinWatt számítási eredmény roundtrip;
- tanúsítási XML-export bizonyított minimális projekten;
- változatlan forrás-WWP és friss kimeneti könyvtár követelménye;
- a `winwatt-certification-orchestrator` Codex skill.

Az `energetika` könyvtárban rendelkezésre állnak a szakmai források, a WinWatt
anyagkatalógus, a hőtermelő-tábla, meteorológiai háttéradatok és a tanúsítási
XML/JSON 3.0.12035 dokumentáció mintafájlokkal.

### 2.2 Magyar Mentor / WebWatt

A `M:\Repositories\magyar-mentor` repositoryban a tanúsítás jelentős része
már implementált:

- `CertificationControlCenterPage.tsx`: G0-G7 kapus tanúsítási folyamat;
- `NewCertificatePage.tsx`: projekt- és épületszintű készültségi áttekintés,
  számítási PDF- és fényképcsatolás, XML-export;
- `CertificateImportPage.tsx`: meglévő tanúsítási XML importja;
- `ProjectEvidenceReviewPage.tsx`: PDF-ből felismert értékek forráshelyes
  elfogadása, javítása és elutasítása;
- `ReviewFormPage.tsx`: adminisztratív projektadatok emberi ellenőrzése;
- `certificateDraft.ts`: projektadatokból tanúsítvány-draft felépítése;
- `certificateValidation.ts`: mező-, enum-, tartomány-, média- és kötelezőadat-
  validáció;
- `certificateExport.ts`: `UploadRequest` XML szerializálása;
- `certificationProjectReview.ts`: rétegrend-, helyiség-, szerkezet- és
  gépészeti készenléti vizsgálat;
- Supabase migrációk a tanúsítási esethez, evidence review-hoz és kapukhoz;
- worker intake és review handoff szerződések;
- XML mezőmátrix, exportterv és WinWatt XML gap lista;
- célzott regressziós tesztek.

A vizsgálatkor futtatott nyolc célzott tesztfájl 32 tesztje sikeres volt:
draft builder, shared draft, validáció, export, projekt-review, PDF-review,
WinWatt handoff és származtatott WinWatt-adatok.

### 2.3 Meglévő ellenőrző oldalak értékelése

A felületek szakmailag hasznosak, de két párhuzamos readiness-modell alakult ki:

1. A vezérlőközpont G0-G7 állapotgépe.
2. Az Új tanúsítvány oldal nyolc készültségi blokkja.

Ezek részben ugyanazt vizsgálják, de eltérő kóddal és eltérő fogalmakkal.
Hosszú távon ez eltérő „kész” állapotot eredményezhet a felületen, az edge
functionben és a Codex döntésében. Egyetlen kanonikus readiness-szolgáltatásra
kell őket átállítani.

## 3. Legfontosabb feltárt kockázatok

### K1. Az eredeti XML validáció nélkül kiadható

A `certificateExport.ts` jelenlegi `original_xml` ága az alakilag
`UploadRequest`-nek tűnő XML-t `upload_ready: true` értékkel adja vissza. Nem
ellenőrzi, hogy:

- az XML a jelenlegi projektrevízióhoz tartozik-e;
- megfelel-e az aktuális validációs szabályverziónak;
- tartalmazza-e az aktuális számítási PDF-et;
- az eredményei egyeznek-e az aktuális WinWatt-számítással.

Ez kiadásblokkoló hiba. Az eredeti XML csak megőrzött forrás lehet, automatikus
kiadási készültséget nem adhat.

### K2. A validációs szabályok kézzel vannak kódolva

A validátor erős kiindulópont, de a kódban rögzített enumok és szabályok nem
kapcsolódnak gépileg a 3.0.12035 dokumentációhoz. A szabályverzió és a forrás
hash-e nem része a validációs eredménynek.

### K3. Duplikált szakmai források

Az energetikai források az AutoWinWatt és a Magyar Mentor alatt is megvannak.
Kanonikus forrás és hash-manifest nélkül észrevétlenül eltérhetnek. A kanonikus
hely legyen `M:\Repositories\autowinwatt\energetika`; a WebWatt csak verziózott
generált adatot vagy explicit forráshivatkozást használjon.

### K4. Származtatott és importált értékek eredete elmosódhat

A draft builder több fallbackből képez tanúsítványmezőket. Ez hasznos, de minden
mezőhöz rögzíteni kell az eredetet: közvetlen projektadat, PDF-felismerés,
WinWatt-import, számított érték, korábbi tanúsítvány vagy emberi felülírás.

### K5. A G5 és G6 nincs teljesen összekötve az AutoWinWatt bizonyítékaival

A vezérlőközpont G5 panelje jelenleg előkészítési tájékoztató. A WinWatt
projekt, számítás, eredmény-visszaolvasás, PDF és végső XML futási riportjai még
nem képeznek egységes WebWatt-kapufeltételt.

### K6. A geometriai hiba hatása nincs végig mérve

A geometriai eltérést már tudjuk mérni, de a fontos kérdés a végső hatás:
fajlagos hőveszteségtényező, fűtési energiaigény, összesített energetikai
jellemző, CO2 és besorolás. Ehhez ellenőrzött ellenpontszámítás szükséges.

## 4. Célarchitektúra és felelősségek

### 4.1 AutoWinWatt felelőssége

- kanonikus energetikai források és verziómanifest;
- forrásból generált szabály- és kódtáblák;
- WinWatt profil és lokális automatizálás;
- determinisztikus számítási és validációs toolok;
- tanúsítási XML szemantikus összevetés;
- referenciaesetek és numerikus toleranciák;
- Codex tanúsítási skill;
- futási evidence és artefakthash.

### 4.2 Magyar Mentor / WebWatt felelőssége

- projekt- és ügykezelés;
- felhasználói adatbevitel;
- PDF- és geometriai jelöltek vizuális ellenőrzése;
- kérdés-válasz és emberi döntés;
- kapuállapotok megjelenítése;
- helyi worker job indítása és eredményének fogadása;
- végleges emberi jóváhagyás és átadás.

### 4.3 ETAI / helyi geometriamunkás felelőssége

- PDF-oldalak renderelése és regisztrációja;
- helyiségkontúrok, virtuális falak és helyiséglista;
- külső/fűtetlen térrel határos falszakasz-jelöltek;
- falhossz, belmagasság és bruttó felület;
- nyílászáró-jelöltek és méretek;
- bizonytalanság, evidence bbox és modellverzió;
- emberi döntésekből képzett tanulópárok.

### 4.4 Futási topológia

- Egy Codex-orchestrator koordinálja a teljes folyamatot.
- Több AI-mentes CPU worker végezheti párhuzamosan a PDF-, geometria-,
  tudásindex- és XML-ellenőrzést.
- Egyszerre csak egy WinWatt UI worker futhat, feloldott Windows-asztalon.
- A validátor és a regressziós összevető WinWatt és AI nélkül fusson.

## 5. A Codex „tanítása”

### 5.1 Nem modell-finomhangolás az első lépés

A rendeleteket, képleteket, kódtáblákat és XML-szabályokat nem érdemes a modell
súlyaiba tanítani. Ezek változó, verziózott és pontosan ellenőrizendő adatok.
Forráshivatkozásos tudástár és determinisztikus tool legyen belőlük.

Tényleges ML-tanítás elsősorban a vizuális geometriafelismeréshez indokolt.

### 5.2 Skill szerkezete

A meglévő `winwatt-certification-orchestrator` skill maradjon az egyetlen
belépési pont. A `SKILL.md` csak a döntési sorrendet és a kötelező kapukat
tartalmazza. A részletes tudás külön referenciákba kerüljön:

```text
winwatt-certification-orchestrator/
  SKILL.md
  references/
    source-priority.md
    certification-workflow.md
    geometry-and-envelope.md
    structures-and-openings.md
    building-services.md
    calculation-method.md
    certificate-xml.md
    validation-and-release.md
```

A skill feladata:

1. az alkalmazandó profil és forrásverzió kiválasztása;
2. a jelenlegi kapu és hiányok megállapítása;
3. csak `verified` tool futtatása;
4. bizonytalan adatnál evidence-alapú kérdés létrehozása;
5. preflight, számítás, visszaolvasás és XML-validáció kikényszerítése;
6. számszerű referencia-eltérés jelentése;
7. emberi jóváhagyás nélkül a végleges státusz tiltása.

### 5.3 Tudásmanifest

Létrehozandó:

```text
energetika/generated/source_manifest.json
```

Minden forráshoz tartozzon:

- relatív elérési út;
- SHA-256;
- dokumentumtípus;
- kiadás vagy hatályállapot;
- elsődleges/segéd/teszt besorolás;
- feldolgozó verzió;
- utolsó sikeres feldolgozás;
- az előállított artefaktok listája.

### 5.4 Strukturált tudáscsomag

Generált, verziózott kimenetek:

```text
energetika/generated/regulation_index.jsonl
energetika/generated/calculation_rules.json
energetika/generated/certificate_schema_3_0_12035.json
energetika/generated/certificate_validation_rules_3_0_12035.json
energetika/generated/material_catalog.json
energetika/generated/heat_generator_catalog.json
energetika/generated/climate_reference.json
```

Minden szabály tartalmazzon forrás- és oldalszintű hivatkozást, státuszt,
alkalmazási feltételt, bemenetet, mértékegységet, kerekítést és gépi
ellenőrzési azonosítót.

## 6. Kanonikus tanúsítási állapotgép

A WebWatt két readiness-modellje és az AutoWinWatt workflow-ja közös állapotgépet
használjon:

| Kapu | Tartalom | Kötelező gépi kapu |
| --- | --- | --- |
| G0 | projekt, adminisztráció, scope, források | forrásmanifest és kötelező adatok |
| G1 | rétegrendek, anyagok, U-értékek | anyag- és szerkezetpreflight |
| G2 | épület, szint, helyiség, zóna | helyiséglista, terület, magasság |
| G3 | külső/fűtetlen határolók, nyílászárók | envelope preflight és evidence |
| G4 | fűtés, HMV, hűtés, szellőzés | gépészeti teljesség és jóváhagyás |
| G5 | natív modell és WinWatt-számítás | roundtrip, számítás, eredmény-readback |
| G6 | tanúsítási XML és számítási PDF | szabályvalidáció és szemantikus regresszió |
| G7 | beadás, HET, átadás, archiválás | emberi jóváhagyás és végleges hash-manifest |

Minden kapu eredménye egységes szerződésű legyen:

```json
{
  "gate": "G3",
  "status": "passed | review_required | failed",
  "input_revision": "...",
  "ruleset_version": "...",
  "checks": [],
  "issues": [],
  "evidence": [],
  "next_actions": []
}
```

A React oldalak ne saját maguk számolják a készültséget. Ugyanezt a szerződést
jelenítsék meg, amelyet a worker és a Codex is használ.

## 7. Fejlesztési munkacsomagok

### WP0. Forráskonszolidáció

Feladatok:

- az AutoWinWatt `energetika` mappájának kijelölése kanonikusnak;
- a Magyar Mentor duplikált forrásainak hash-összevetése;
- `source_manifest.json` generátor;
- eltérő vagy frissebb forrás automatikus blokkolása;
- a két validációs markdown verziójának explicit verziókezelése.

Kimenet: reprodukálható, hash-elt forrásjegyzék.

Elfogadás: egyetlen paranccsal kimutatható minden hiányzó, módosult vagy
duplikált forrás.

### WP1. Tanúsítási tudásfordító

Feladatok:

- tanúsítási szótár feldolgozása;
- validációs szabályok strukturált modellje;
- XML/JSON mintákból mezőfa és mintatípusok előállítása;
- jogszabályi és számítási PDF-ek oldalszintű indexe;
- anyag- és hőtermelő-katalógus normalizálása;
- tudáselemek státusz- és forráshivatkozása.

Kimenet: az 5.4 fejezet generált tudáscsomagja.

Elfogadás: a generálás determinisztikus; azonos forrásból azonos hash-ű
kimenet készül; minden állítás visszavezethető forrásra.

### WP2. Verziózott tanúsítvány-validátor

Feladatok:

- a meglévő `certificateValidation.ts` leválasztása a kézzel karbantartott
  kódtáblákról;
- ruleset adapter a 3.0.12035 verzióhoz;
- XML-szintaktikai és szemantikai ellenőrzés;
- Base64 PDF dekódolás, PDF-fejléc és méretellenőrzés;
- fényképkategória és tartalom ellenőrzés;
- ruleset-verzió és forráshash a validációs riportban;
- hibakódok stabil azonosítóval.

Kimenet: `certificate.xml.validate` tool és újrahasznosítható TypeScript/Python
könyvtár.

Kritikus javítás: az `original_xml` exportág csak sikeres validáció és aktuális
projektrevízió-egyezés után kaphat `upload_ready: true` állapotot.

### WP3. Szemantikus tanúsítvány-összevető

Feladatok:

- XML kanonizálás;
- sorrendtől független listapárosítás;
- mezőnkénti toleranciák;
- szerkezet-, gépészet- és energiaeredmény-diff;
- beágyazott PDF jelenlét- és hash-összevetés;
- ember számára áttekinthető HTML/JSON riport.

Kiemelt mutatók:

- hasznos alapterület és kondicionált térfogat;
- határolószerkezet-típusonkénti felület;
- nyílászáró-felület;
- U-érték és minőségi kategória;
- fajlagos hőveszteségtényező;
- fűtés, HMV, hűtés és egyéb energiafelhasználás;
- összesített energetikai jellemző;
- CO2-kibocsátás;
- energetikai és CO2-besorolás.

Kimenet: `certificate.xml.compare` tool.

### WP4. Kanonikus readiness és kapuszolgáltatás

Feladatok:

- közös G0-G7 szerződés;
- a `certificationProjectReview.ts` logika kiszervezése közös domainrétegbe;
- a `NewCertificatePage` blokklistájának leképezése a kapukra;
- Supabase kapufüggvények bekötése a gépi checkekhez;
- minden mező forrásának és felülírásának tárolása;
- stale projektrevízió esetén a későbbi kapuk automatikus visszanyitása.

Kimenet: egy readiness API, amelyet React, edge function, worker és Codex is
ugyanúgy használ.

### WP5. Geometria és evidence integráció

Feladatok:

- egységes `geometry_candidate` séma;
- helyiség, virtuális fal, külső falszakasz és nyílászáró jelölt;
- PDF-oldal, bbox, confidence, worker- és modellverzió;
- vizuális „jó / nem jó / javított érték” review;
- jóváhagyott jelöltből immutable tanulópár;
- negatív példák és nehéz esetek tárolása;
- lakás és teljes szinti terv kapcsolatának rögzítése;
- több PDF-oldalon lévő lakás támogatása.

Kimenet: jóváhagyott, szobánkénti energetikai geometria és tanulóadat.

Elfogadás: minden tanúsításba bekerülő fal és nyílászáró visszamutat a rajzi
evidence-re vagy explicit emberi döntésre.

### WP6. AutoWinWatt teljes modell- és számítási híd

Feladatok:

- reviewed WebWatt-modell exportja kanonikus handoff JSON-ba;
- natív WinWatt-projekt létrehozása vagy ellenőrzött importja;
- teljes close/reopen/readback;
- számítás futtatása;
- eredmény- és számítási PDF export;
- tanúsítási XML export;
- valamennyi artefakt hash-elése;
- a G5/G6 WebWatt kapu automatikus frissítése.

Kimenet: `reviewed_model -> WWP -> calculation -> PDF -> certificate XML`
reprodukálható helyi workflow.

Elfogadás: az input projektrevízió, a WWP, a számítási eredmény, a PDF és a
tanúsítási XML egy futási manifestben össze van kötve.

### WP7. Codex skill bővítése

Feladatok:

- a forrásprioritás és G0-G7 workflow rögzítése;
- referenciafájlok létrehozása;
- új tool ID-k bejegyzése a képességregiszterbe;
- AI/kód/ember döntési határ rögzítése;
- kötelező stopping conditionök;
- tipikus tanúsítási kérések előretesztelése.

Kimenet: a Codex az aktuális kapuból folytatni tudja a munkát, meg tudja
indokolni a következő lépést, és nem állít késznek nem validált tanúsítványt.

### WP8. Referenciaesetek és végponttól végpontig vizsga

Első referencia: egy SR8 lakás, amelyhez rendelkezésre áll:

- bemeneti tervcsomag;
- jóváhagyott geometria;
- kanonikus natív WinWatt XML;
- végleges tanúsítási XML;
- szükség esetén kézi WinWatt referenciaprojekt.

Tesztváltozatok:

1. referencia-geometria és referencia-gépészet;
2. automatikusan felismert geometria és azonos gépészet;
3. kontrollált +1%, +3%, +5% falhosszhiba;
4. kontrollált nyílászáró-terület hiba;
5. hiányzó külső falszakasz;
6. falszakasz téves külső/belső besorolása.

Minden változatnál mérendő a WP3 mutatók eltérése. A tesztből hatásgörbe
készül: milyen geometriai hiba okoz még elfogadható energetikai eltérést.

## 8. Javasolt megvalósítási sorrend

### Mérföldkő A: megbízható tudás és XML-kapu

WP0 -> WP1 -> WP2.

Eredmény: a Codex forrásból tud válaszolni, az XML pedig verziózott szabályok
szerint ellenőrizhető. Ez közvetlenül javítja a jelenlegi WebWatt exportot is.

### Mérföldkő B: mérhető referencia-eltérés

WP3 -> egy SR8 referenciaeset alapváltozata.

Eredmény: már meg tudjuk mondani, hogy egy generált tanúsítvány végső értékei
mennyire térnek el a kész tanúsítványtól.

### Mérföldkő C: egységes ellenőrző felület

WP4 -> meglévő ellenőrző oldalak átállítása.

Eredmény: nincs kétféle készültségi igazság; a felhasználó egy helyen csak a
valódi blokkoló hibákat és kérdéseket látja.

### Mérföldkő D: tervből automatikus modell

WP5 -> WP6.

Eredmény: reviewed tervgeometria közvetlenül eljut a WinWatt-számításig és a
tanúsítási XML-ig.

### Mérföldkő E: Codex önálló, de felügyelt tanúsítás

WP7 -> WP8 teljes vizsgasor.

Eredmény: a Codex önállóan koordinál, de a szakmai és beadási felelősséget nem
veszi át; bizonytalan vagy jogilag változó kérdésnél review-t kér.

## 9. Első végrehajtható fejlesztési szelet

Az első szelet legyen kicsi, de végponttól végpontig bizonyítható:

1. Forrásmanifest készítése az AutoWinWatt `energetika` könyvtáráról.
2. A 3.0.12035 validációs szabályok strukturált JSON modellje.
3. A Magyar Mentor validátorának ruleset-verziózása.
4. Az `original_xml -> upload_ready: true` kerülőút megszüntetése.
5. Az általános minta-XML, a teljes teszt-JSON és legalább három valós XML
   validációs regressziós tesztje.
6. `certificate.xml.compare` minimális változata a fő energetikai mutatókra.
7. Egy SR8 referencia tanúsítvány összevetési riportja.

Ez a szelet még nem igényli a geometriai modell újratanítását, mégis azonnal
megteremti a stabil mérési és kiadási kaput.

## 10. Tesztstratégia

### 10.1 Unit tesztek

- szabályparser;
- enum és tartományvalidáció;
- XML szerializálás és escaping;
- PDF Base64 felismerés;
- forrásprioritás és provenance;
- toleranciás numerikus összevetés.

### 10.2 Contract tesztek

- WebWatt readiness API;
- local worker handoff;
- AutoWinWatt tool invocation;
- Supabase kapuátmenet;
- immutable artefakthash.

### 10.3 Golden tesztek

- dokumentációs `general_cert.xml`;
- teljes, de nem életszerű JSON tesztminta;
- több valós végleges tanúsítvány;
- WinWatt által újraexportált tanúsítási XML.

### 10.4 E2E tesztek

- teljes SR8 lakás;
- több PDF-oldalas lakás;
- közbenső és szélső lakás;
- külső és fűtetlen térrel határos szerkezetek;
- hibás geometria kontrollált változatai;
- megszakítás és checkpointból folytatás.

## 11. Minőségi mutatók

Nem egyetlen „pontosság” számot kell használni.

### Geometria

- helyiséglista precision/recall;
- helyiségenkénti területeltérés;
- külső falszakasz precision/recall;
- falhossz és bruttó felület relatív hibája;
- nyílászáró darabszám és összterület eltérése.

### Tanúsítás

- XML szabályhibák száma;
- hiányzó kötelező mezők;
- fajlagos hőveszteségtényező eltérése;
- energiafelhasználás célonkénti eltérése;
- összesített energetikai jellemző eltérése;
- CO2-eltérés;
- besorolási osztály egyezése;
- számítási PDF jelenléte és érvényessége.

### Folyamat

- automatikusan elfogadható döntések aránya;
- emberi kérdések száma lakásonként;
- javított jelöltek aránya;
- újrafuttatás reprodukálhatósága;
- egy tanúsítvány teljes feldolgozási ideje;
- hibásan „kész” állapotok száma, amelynek nullának kell lennie.

## 12. Definition of Done a teljes célhoz

A rendszer akkor tekinthető késznek egy támogatott tervtípuson, ha:

- a források és szabályok verziója rögzített;
- minden tanúsítási adatnak ismert eredete van;
- a geometria review-ja lezárt;
- az AutoWinWatt preflight `passed`;
- a WWP mentés-újranyitás-visszaolvasás sikeres;
- a WinWatt-számítás bizonyítottan lefutott;
- a végső számítási mutatók visszaolvasott értékek;
- a számítási PDF bekerült a tanúsítási XML-be;
- a tanúsítási XML átmegy a verziózott validátoron;
- a referenciaeltérések a jóváhagyott tolerancián belül vannak, vagy minden
  eltérés ember által indokolt és elfogadott;
- a teljes futás reprodukálható az input hash-ekből;
- az emberi tanúsítói jóváhagyás auditnaplóban szerepel.

## 13. Azonnali következő lépés

A következő implementációs feladat a WP0 és WP2 együtt:

1. forrásmanifest-generátor;
2. `certificate.xml.validate` verziózott tool;
3. az `original_xml` kiadási rés megszüntetése;
4. meglévő 32 sikeres teszt megtartása és új negatív regressziók hozzáadása.

Ezzel létrejön az a megbízható kapu, amelyre a Codex skill, a WebWatt
ellenőrző oldalak és a későbbi teljes automatizálás is biztonságosan építhető.
