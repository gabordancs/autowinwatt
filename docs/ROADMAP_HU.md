# WinWatt → teljes tanúsítás: roadmap

Frissítve: 2026-10-03. A tényleges helyi eredményeket mutatja, nem becsült készültségi százalékot.

## Hol tartunk?

**Az alapinfrastruktúra, az épület- és ET-belépési út, hét módosító roundtrip,
az ET-varázsló és mind a hat 2023-as rendszergráf, valamint a WebWatt
tanúsítási adatbázis elkészült.** A teljes tanúsítási automatizmus még nincs
kész. A hét lezárt mély gráf 210 állapotot és 1521 átmenetet tartalmaz. A WebWatt
adatbázis telepítését 17/17 csak olvasó ellenőrzés igazolja, az élő queue E2E
még hátravan.

| Szakasz | Állapot | Eredmény / továbblépési feltétel |
| --- | --- | --- |
| 1. Korábbi tudás összegyűjtése | Részben kész | 1922 fájlhivatkozás, 1564 külön tartalom közös jegyzékben; 38 történeti forrás hiányzik, 3 JSON hibás. A nyers források teljes helyreállítása nincs igazolva. |
| 2. Helyi futtatókörnyezet és verzióazonosítás | Kész az alap | Külön 32 bites Python, EXE/verzió/erőforrás-lenyomat, elkülönített kampány és sandbox. Nem minden régi belépési pont kapott kötelező verzióvédelmet. |
| 3. Épületablak alapfeltérképezése | Kész az első leltár | Javított, név szerinti épületmegnyitás; 11 elérhető fül, vezérlők, választóértékek és képek; natív mentés és újraindítás utáni megnyitás. |
| 4. Feltételes energetikai ágak | Mind a hat 2023-as rendszergráf és az ET-gráf kész | Mind a 9 számítási mód tesztelve: 8 régi mód → 8 fül, 2023-as mód → 11 fül. ET: 16/143; fűtés: 21/191; HMV: 37/276; légtechnika: 27/267; hűtés: 24/133; világítás: 47/260; nyereség/veszteség: 38/251 állapot/él. **Következő: rendszer-roundtripek és számítási eredmények.** |
| 5. Mezőkezelés bizonyítása | Tizenegy roundtrip igazolt | Tájolás, világítás, fűtött zóna, elektromos fűtés, elektromos HMV, légtechnika, direkt hűtés, helyiség, rétegrendes szerkezet, helyiséghatároló-hozzárendelés és a 25 mezős energetikai eredménysor megmarad teljes újraindítás után. |
| 6. Teljes helyi referencia-tanúsítás | Hátravan | Ellenőrzött épületadatok, rendszerek, számítás, felújítási javaslatok, WWP/XML/PDF/fotócsomag és validáció. |
| 7. WebWatt összekötése | Adatbázis és helyi intake igazolt; élő queue hátravan | A tanúsítási táblák, projektmezők, G0–G4 függvények, `certificate_intake` enum és táblajogosultságok 17/17 ellenőrzéssel telepítve. A hálózatfüggetlen PDF/XML intake hashes manifesttel fut. Az élő queue-feltöltés, worker-visszatöltés és idempotencia még bizonyítandó. |
| 8. Fogadóoldali ellenőrzés és véglegesítés | Hátravan | Aktuális célformátum ellenőrzése, valós fogadóoldali visszajelzés, tanúsítói felülvizsgálat és végleges dokumentumcsomag. |
| 9. Tool-, skill- és knowledge-réteg | Tíz igazolt tool, három skill kész | Hét módosító WinWatt-roundtrip, az offline teljes preflight, a kampányösszesítő és a helyi WebWatt PDF/XML intake végrehajtható. A fűtési, mapping-kampány és teljes tanúsítási koordinátor skillek telepítve vannak. A rendszer- és zónadialógus-leltár továbbra is `observed`. |

## Skillek és toolok helye a fő rendszerben

**Tool** minden determinisztikus, programból hívható művelet: projekt megnyitása,
verzióellenőrzés, mező írása és visszaolvasása, rendszer létrehozása, mentés,
XML/PDF export, számításindítás vagy validáció. Minden toolhoz kötelező:

- stabil azonosító és verzió;
- típusos bemenet és kimenet;
- WinWatt/WebWatt verzió- és állapot-előfeltétel;
- utófeltétel és gépi visszaellenőrzés;
- létrehozott evidence és artefakt-hash;
- ismételhetőségi, retry- és hibakezelési szabály;
- sandbox/production jogosultsági osztály.

**Skill** egy szakmai munkafolyamat: például helyiségmodell összeállítása,
határoló szerkezetek felvétele, fűtési rendszer zónához rendelése, teljes
tanúsítási előellenőrzés vagy WebWatt–WinWatt parity vizsgálat. A skill toolokat
fűz össze, döntési pontokat, kötelező validációkat és emberi jóváhagyási kapukat
tartalmaz; közvetlen, tetszőleges GUI-kattintást nem végezhet.

Az **ETAI_Agents** koordinálja a skilleket, az **Auto-WinWatt** szolgáltatja a
WinWatt toolokat, a **WebWatt** a domain-, számítási és projekciós toolokat. Az
AI feladata a megfelelő skill kiválasztása, a források értelmezése és a
bizonytalanság felismerése. A számítás, konverzió, validáció és UI-végrehajtás
determinista tool marad.

A mapping során talált művelet először csak `observed` capability. Tool csak
akkor lehet belőle, ha verzióprofilhoz kötött, sandboxban mentés–újranyitás után
igazolt és golden projekten is rendelkezik utófeltétel-bizonyítékkal. A toolokból
ezután készülhetnek a tanúsítási skillek.

Az első gépi regiszter a
`winwatt_automation/data/capabilities/certification_tools.json` fájlban van. A
`winwatt_automation.agent.capabilities.CertificationToolRegistry` kizárja az
agent nézetéből az `observed` elemeket, valamint az eltérő WinWatt-verzióprofilra
igazolt toolokat. Ezt külön automatizált tesztek ellenőrzik.

## A következő konkrét munkacsomag

A végrehajtási sorrend géppel olvasható státuszokkal a
[Tanúsítási munkasor](TANUSITASI_MUNKASOR_HU.md) dokumentumban található.

**A Q1–Q7 elkészült. Következő cél: a WebWatt élő összekötés Q8 feladatai:
queue-feltöltés, worker-visszatöltés, idempotencia és a G0–G4 kapuk igazolása.**

A Q7 csomag WWP-t, natív WinWatt XML-t, számítási PDF-et, `UploadRequest`
tanúsítási XML-t és JPEG-formátumú szintetikus tesztfotót tartalmaz. A manifest
minden fájlt hash-el, ellenőrzi az XML-gyökereket, a PDF-aláírást és a valódi
JPEG fájlszerkezetet. A közvetlen WinWatt PDF-nyomtatóút helyett a számítási
dokumentum a WinWatt RTF-exportjából, helyi Word-konverzióval készült.

A három korábbi képesség újraigazolása és bekötése a verziózott
tool-regiszterbe elkészült:
`winwatt.building.room.create_roundtrip`,
`winwatt.building.structure.layered.create_roundtrip` és
`winwatt.building.room.boundary.assign_roundtrip`. Mindhárom külön
sandboxmásolattal, mentés–teljes újranyitás–visszaolvasással és változatlan
forráshash-sel igazolt.

1. A mentett sandboxot megnyitni a meglévő 32 bites Python-eszközökkel,
   a verzióprofil és a projektazonosság ellenőrzésével.
2. A 2023-as számítási módot és az Épülettechnikai rendszerek lapot aktiválni.
3. A fűtés hőtermelő alablakait felvenni; az elérhető rendszertípusokat és
   függő mezőket helyben kiolvasni. A zónaűrlapok leltára elkészült, a
   `probe_heating_generator_catalog` pedig 32 katalóguslevelet és a hozzájuk
   tartozó mezőállapotokat rögzítette változtatás nélkül.
4. A minimális elektromos fűtési rendszer és a tesztzóna tartóssági köre
   elkészült; ugyanezt egy összetettebb hőtermelővel vagy HMV-rendszerrel megismételni.
5. A számítás indítása és egy 25 mezős eredménysor teljes újranyitás utáni
   visszaolvasása elkészült.
6. Az ET-varázsló minimális épülettel végigfutott; a hiányzó kötelező
   adminmezők helyben kitölthetők, a létrejött `UploadRequest` XML jól formált.

**Az előző fűtési alap-munkacsomag elkészült:** a rendszerablak elérési útja
reprodukálható, az elektromos tesztrendszer és a fűtött zóna neve teljes
újranyitás után igazoltan megmarad. Az új munkacsomag akkor kész, ha egy
összetettebb rendszerág vagy számítási eredmény ugyanilyen roundtrip-
bizonyítékot kap.

## Mi biztos, és mi nem?

- A telepített program Névjegye: WinWatt gólya 9.60 (2026. 8. 5.);
  EPBD, EPBD-2023 és Agros2D modul. A bináris a korábban rögzítettel azonos;
  újabb telepített kiadás nincs bizonyítva.
- A 11 fül felvétele alapleltár: két önálló lapcsoport van, kombinációik és
  feltételes ágai még nincsenek teljesen bejárva.
- A mentés és az épület újramegnyitása működik; a mező- és rendszer-roundtripek
  mellett egy 25 mezős számítási eredménysor is igazolt. A minimális ET-folyamat
  helyi, jól formált tanúsítási XML-ig eljutott.
- Az első implementáció 20 célzott tesztje sikeres. Ez nem teljes tanúsítási E2E-teszt.
- A korábbi tudás hivatkozásos egyesítése kész; nem lett minden régi gráfból
  egyetlen, az aktuális kiadásra ellenőrzött végrehajtási gráf.

## Költségtakarékos végrehajtás

A rutinbejárást, választólisták olvasását, diffeket, mentési próbákat és
ellenőrzéseket helyi Python végzi, AI-hívás nélkül. Az AI a kódjavításokat,
az ismeretlen eltérések értelmezését és az összesítést kezeli. Véges feladatcsomagok,
mentett állapotok és rövid összefoglalók csökkentik az ismételt bejárást és a kredithasználatot.

A 2026-09-29-én elindított fő kampány könyvtára:
`winwatt_automation/data/runtime_maps/certification_mapping/mainroadmap_20260929T230344`.
Az első hatórás szakasz az időkorlátnál szabályosan checkpointot írt. A kampány
2026-09-30-án újabb hat órára folytatódott: előbb a teljes zóna–fűtés
roundtripot futtatja, majd a fennmaradt épületgráf-ágakat járja be. Mindez külön
32 bites Python-folyamatban, AI-hívás nélkül történik.
Az állapot a `campaign_state.json` fájlban követhető; a forrás WWP hashét minden
fázis után ellenőrzi, és csak kampányon belüli másolaton végez módosítást.

## Kapcsolódó anyagok

- [WinWatt mapping migrációs feladatok](MIGRACIOS_FELADATOK_HU.md)
- [Codex skill-, tool- és knowledge-munkamódszer](WINWATT_CODEX_MUNKAMODSZER_HU.md)
- [Részletes végrehajtási terv](uj_winwatt_teljes_tanusitas_terv_hu.md)
- [Első megvalósítás eredményei](winwatt_mapping_megvalositas_20260929.md)
- [Korábbi bizonyítékok közös jegyzéke](mapping_evidence_union.json)
- [Rögzített helyi verzióprofil](winwatt_local_profile_20260929.json)
- [Kilenc számítási mód és tájoláspróba](winwatt_energetikai_agak_20260929.md)
- [Épülettechnikai rendszerablakok és világítási kör](winwatt_epuletgepeszeti_rendszerek_20260929.md)
