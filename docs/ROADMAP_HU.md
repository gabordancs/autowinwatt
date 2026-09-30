# WinWatt → teljes tanúsítás: roadmap

Frissítve: 2026-09-29. A tényleges helyi eredményeket mutatja, nem becsült készültségi százalékot.

## Hol tartunk?

**Az alapinfrastruktúra, az épületablak első leltára és két 2023-as rendszer
írási köre elkészült.** A teljes tanúsítási automatizmus még nincs kész. A
kilenc számítási mód, a hat rendszer-létrehozó ablak, egy világítási rendszer,
egy fűtött zóna és egy minimális elektromos fűtési rendszer teljes
mentés–újranyitás köre ellenőrzött.

| Szakasz | Állapot | Eredmény / továbblépési feltétel |
| --- | --- | --- |
| 1. Korábbi tudás összegyűjtése | Részben kész | 1922 fájlhivatkozás, 1564 külön tartalom közös jegyzékben; 38 történeti forrás hiányzik, 3 JSON hibás. A nyers források teljes helyreállítása nincs igazolva. |
| 2. Helyi futtatókörnyezet és verzióazonosítás | Kész az alap | Külön 32 bites Python, EXE/verzió/erőforrás-lenyomat, elkülönített kampány és sandbox. Nem minden régi belépési pont kapott kötelező verzióvédelmet. |
| 3. Épületablak alapfeltérképezése | Kész az első leltár | Javított, név szerinti épületmegnyitás; 11 elérhető fül, vezérlők, választóértékek és képek; natív mentés és újraindítás utáni megnyitás. |
| 4. Feltételes energetikai ágak | Fűtési alapág igazolt | Mind a 9 számítási mód tesztelve: 8 régi mód → 8 fül, 2023-as mód → 11 fül. A hat rendszer-létrehozó ablak, a fűtött és hűtött zóna űrlapja, valamint 32 hőtermelő-katalóguslevél felvéve. A minimális elektromos fűtési rendszer és a 10 m²-es fűtött zóna együtt megmaradt újranyitás után. **Következő: további rendszerfajták és számítási eredmények.** |
| 5. Mezőkezelés bizonyítása | Négy írási kör igazolt | Tájolás 0 → 42°, világítási rendszer, fűtött zóna és minimális elektromos fűtési rendszer megmarad teljes újraindítás után. 42,5° → 42° eltérés dokumentálva; további rendszermezők és energetikai eredmények hátravannak. |
| 6. Teljes helyi referencia-tanúsítás | Hátravan | Ellenőrzött épületadatok, rendszerek, számítás, felújítási javaslatok, WWP/XML/PDF/fotócsomag és validáció. |
| 7. WebWatt összekötése | Helyi intake igazolt, élő kapcsolat hátravan | A hálózatfüggetlen PDF/XML intake hashes manifesttel, AI és WinWatt nélkül fut, azonos forrásnál helyben újraindítható. Az élő Supabase-feltöltés idempotenciáját és a bizonyított WinWatt-lépésekkel való queue-összekötést még igazolni kell. |
| 8. Fogadóoldali ellenőrzés és véglegesítés | Hátravan | Aktuális célformátum ellenőrzése, valós fogadóoldali visszajelzés, tanúsítói felülvizsgálat és végleges dokumentumcsomag. |
| 9. Tool-, skill- és knowledge-réteg | Hét igazolt tool, három skill kész | Verzió- és evidence-kötött regiszter, szemantikus tool-runner és kurált tanúsítási knowledge készült. Végrehajtható négy WinWatt roundtrip, az offline teljes preflight, az élő kampány összesítése és a helyi WebWatt PDF/XML intake. A fűtési, mapping-kampány és teljes tanúsítási koordinátor skillek telepítve vannak; az egyparancsos helyi fűtési workflow sikeresen végigfutott. A puszta rendszer- és zónadialógus-leltár továbbra is `observed`. |

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

**Cél: a 2023-as mód további épülettechnikai rendszereinek és számítási eredményeinek bizonyítása.**

A jelenlegi mappingfolyamat befejezése után elsőbbséget kap három korábbi
képesség újraigazolása és bekötése a verziózott tool-regiszterbe:
`winwatt.building.room.create_roundtrip`,
`winwatt.building.structure.layered.create_roundtrip` és
`winwatt.building.room.boundary.assign_roundtrip`. Mindháromhoz külön
sandboxmásolat, mentés–teljes újranyitás–visszaolvasás és változatlan
forráshash szükséges.

1. A mentett sandboxot megnyitni a meglévő 32 bites Python-eszközökkel,
   a verzióprofil és a projektazonosság ellenőrzésével.
2. A 2023-as számítási módot és az Épülettechnikai rendszerek lapot aktiválni.
3. A fűtés hőtermelő alablakait felvenni; az elérhető rendszertípusokat és
   függő mezőket helyben kiolvasni. A zónaűrlapok leltára elkészült, a
   `probe_heating_generator_catalog` pedig 32 katalóguslevelet és a hozzájuk
   tartozó mezőállapotokat rögzítette változtatás nélkül.
4. A minimális elektromos fűtési rendszer és a tesztzóna tartóssági köre
   elkészült; ugyanezt egy összetettebb hőtermelővel vagy HMV-rendszerrel megismételni.
5. A számítás indítását, eredménymezőit és hibajelzéseit feltérképezni, majd
   legalább egy eredményt teljes újranyitás után visszaolvasni.
6. A futásból függőségi táblát és rövid hibajegyzéket készíteni; a sandbox
   kiinduló állapotát megőrizni, minden próba eredményét külön naplózni.

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
- A mentés és az épület újramegnyitása működik; egész fokértékű tájolás, egy
  minimális világítási rendszer, a fűtött zóna neve és egy minimális elektromos
  fűtési rendszer tartóssága igazolt. Teljes számítási eredmény még nincs igazolva.
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
