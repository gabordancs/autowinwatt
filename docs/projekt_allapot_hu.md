# AutowinWatt / WinWatt Automation – projektállapot és működési összefoglaló

## Mi a projekt célja?

A projekt célja, hogy a **WinWatt desktop alkalmazást automatizálhatóvá** tegye úgy, hogy **nem módosítja magát a WinWattot**, hanem külső Python-eszközökkel:

- feldolgozza a rendelkezésre álló XML alapú UI-leírást,
- egységes belső modellt épít a felületről,
- parancsokat és workflow-kat szervez a vezérléshez,
- futás közben élő UI-felderítést végez,
- és fokozatosan felépít egy runtime tudásbázist arról, hogyan működik a program valós állapotokban.

Röviden: ez egy **WinWatt-automatizálási toolkit**, amely egyszerre használ **statikus forrásokat** (pl. `Hungarian.xml`) és **élő UI-ellenőrzést** (pywinauto alapú feltérképezés).

---

## Hogyan működik a projekt?

A projekt jelenlegi felépítése több, egymásra épülő rétegből áll.

### 1. Statikus UI-feldolgozás

A kiindulási pont a `data/raw/Hungarian.xml`, amelyből a parser réteg felolvassa a WinWatt felületi elemeit.

Ebben a részben jelenleg megvan:

- XML parser,
- Pydantic alapú UI modellek,
- szemantikus osztályozás,
- normalizálás,
- JSON export,
- programtérkép és katalógusépítés.

Ez a réteg arra jó, hogy legyen egy **konzisztens, kereshető, strukturált leírásunk** a WinWatt felépítéséről már azelőtt, hogy élőben kattintanánk bármit.

### 2. Parancs- és műveletmodell

A statikus UI-modellből a rendszer parancsokat és kereshető regisztereket tud építeni.

Ez azt szolgálja, hogy ne csak nyers UI-elemek legyenek, hanem:

- megtalálható akciók,
- formokhoz és vezérlőkhöz kötött műveletek,
- workflow-seedek,
- a későbbi automatizált végrehajtás alapjai.

### 3. Élő UI-kapcsolódás a WinWatthoz

A `live_ui` és kapcsolódó modulok a futó WinWatt alkalmazáshoz próbálnak kapcsolódni, ablakokat kiválasztani, vezérlőket lokalizálni, menüket és dialógusokat felismerni.

Ez a réteg kezeli többek között:

- főablak kiválasztását,
- UIA / win32 fallback logikát,
- menü- és popup-felderítést,
- fájldialógusok felismerését,
- fókusz- és várakozáskezelést,
- UI snapshotok készítését.

### 4. Runtime mapping

A projekt egyik legfontosabb jelenlegi része a **runtime programtérkép építése**.

Ez a folyamat:

1. elindít vagy elér egy WinWatt példányt,
2. feltérképezi a felületet egy adott állapotban,
3. menüket és dialógusokat próbál bejárni,
4. elmenti az eredményt strukturált JSON / Markdown fájlokba,
5. összehasonlít több állapotot,
6. és létrehoz egy diffet + tudásösszefoglalót.

Jelenleg külön kezelt állapotok:

- `no_project` – amikor nincs megnyitott projekt,
- `project_open` – amikor van megnyitott projekt.

### 5. Futásnaplózás és fejlesztői ciklus

A rendszer minden fontosabb futást naplóz a `data/run_logs/` alá.

Ez azért fontos, mert a projekt nem csak kódot épít, hanem **tanul a futásokból**:

- mi sikerült,
- hol akadt el,
- milyen menük / dialógusok jelentek meg,
- mennyi információt sikerült feltérképezni.

A fejlesztői ciklust egy külön vezérlőréteg (`controller`) segíti, amely össze tudja fogni:

- a git státuszt,
- a futásnaplók kiolvasását,
- chat brief készítését,
- WinWatt indítását / leállítását,
- script futtatását timeouttal.

---

## Milyen fő komponensek vannak most?

### Parser és modellréteg
- XML beolvasás
- UI modellek
- normalizálás
- szemantikus besorolás
- exporterek
- program map builder

### Commands / workflow réteg
- command registry
- menü-, form-, project- és control-commandok
- alap workflow modellek
- demo workflow-k
- állapotgép jellegű workflow támogatás

### Live UI / runtime réteg
- WinWatt kapcsolat
- ablakfa és snapshot kezelés
- locatorok
- menu helper-ek
- wait helper-ek
- file dialog kezelés
- dialog explorer
- runtime safety és osztályozás
- runtime mapping serializer és modellek

### Controller réteg
- git műveletek
- runlog olvasás
- chat brief generálás
- script futtatás
- WinWatt process kezelés
- fejlesztői ciklus-vezérlő

### Tesztek
A tesztkészlet már kifejezetten széles, és lefedi többek között:

- XML parser működését,
- command registry-t,
- live UI ablakválasztást,
- fájldialógus-kezelést,
- menu phase és popup-kezelést,
- runtime mapping diffet,
- recovery logikát,
- run recorder működését,
- dev cycle helper-eket,
- workflow validációt.

Ez alapján a projekt nem csak prototípus, hanem már **jól tesztelt fejlesztési alap**.

---

## Hogyan használható most a projekt?

### Alap CLI funkciók
Jelenleg elérhetőek olyan CLI parancsok, amelyek a statikus modellépítést végzik:

- `parse-xml`
- `export-ui-model`
- `list-forms`
- `list-actions`
- `build-program-map`

Ezekkel a projekt képes a `Hungarian.xml` alapján használható adatállományokat generálni.

### Runtime mapping script
Az egyik fő script a teljes runtime feltérképezésre szolgál.

Ez képes többek között:

- project path megadására,
- safe mode kezelésre,
- output könyvtár megadására,
- top menu szűkítésre,
- submenu mélység szabályozására,
- disabled elemek kezelésére,
- progress overlay használatára.

### Dev cycle controller
A helyi fejlesztői munkát a controller script támogatja. Ez használható:

- státusz lekérdezésre,
- pull-ra,
- chat brief generálásra,
- WinWatt indításra/leállításra,
- script futtatásra,
- teljes fejlesztési ciklus összefogására,
- git add/commit/push műveletekre.

---

## Meddig jutottunk el eddig?

## 1. Elkészült az alap architektúra
A projekt már nem ötletszinten van, hanem több, jól elkülönített modulból álló rendszer:

- parser
- models
- commands
- live_ui
- runtime_mapping
- runtime_logging
- workflows
- controller
- CLI script-ek

## 2. Megvan a statikus WinWatt-modell feldolgozása
A `Hungarian.xml` feldolgozása működik, és ebből több exportált adatfájl is létrejön a `data/parsed/` alatt.

Ez azt jelenti, hogy a WinWatt felületének egy jelentős része már **strukturáltan reprezentálható**.

## 3. Megvan a program map generálás
A rendszer képes forms / controls / actions / dialogs / workflow seeds jellegű kimeneteket generálni.

Ez fontos mérföldkő, mert a projekt így már nem csak nyers XML-parsing, hanem **automatizálási tudásbázis-építés**.

## 4. Megvan az élő UI-felderítés alapja
A WinWatt futó példányához kapcsolódó logika, az ablakok és vezérlők felismerése, a menük és dialógusok kezelése, valamint a file dialog kezelés már külön modulokban létezik.

Ez a gyakorlati automatizálás előfeltétele.

## 5. Megvan a runtime mapping pipeline
A rendszer képes két fontos állapotot külön kezelni és elmenteni:

- projekt nélküli állapot,
- projekt megnyitott állapot.

A futások eredményei jelenleg mentésre kerülnek a `data/runtime_maps/` és `data/run_logs/` alá.

## 6. Megvan a run logging és státuszkezelés
A projekt képes futásonként:

- sorszámozott logot menteni,
- latest rekordot fenntartani,
- strukturált JSON összefoglalót írni,
- élő státuszfájlt frissíteni.

Ez nagyon hasznos a hosszabb, sérülékeny UI-automatizálási futásoknál.

## 7. Megvan a fejlesztői vezérlőréteg
A `DevCycleController` már egy fontos produktivitási elem:

- összefogja a gitet,
- olvassa a legutóbbi run logot,
- briefet készít,
- futtat scriptet,
- kezeli a WinWatt folyamatot.

## 8. Jelentős tesztlefedettség van
A tesztek alapján sok kritikus részre már vannak egységtesztek és viselkedési ellenőrzések.

Ez különösen értékes, mert a desktop automatizálás eleve törékeny terület.

---

## Mi az aktuális állapot a runtime mapping eredmények alapján?

A jelenlegi mentett runtime summary-k alapján a két fő állapotban:

- 7 top menü látszik,
- de a menüpontok mélyebb feltérképezése még nem termelt használható menüfát,
- a mentett összegzésekben az összes menüpont száma jelenleg 0,
- dialog candidate sincs eltárolva,
- a knowledge verification jelenlegi állapotában 100% coverage látszik, de ez most azért félrevezetően jó, mert a known path készlet még gyakorlatilag üres.

Magyarul: **a runtime pipeline már lefut és adatot ment**, de a mély, stabil, érdemi menüfeltérképezés még nincs kész.

---

## Mi működik már stabilabban?

A jelenlegi kódszerkezet és tesztek alapján viszonylag érettnek tűnnek ezek a részek:

- XML parsing és modellépítés,
- program map és statikus export,
- command registry,
- run recorder / run log infrastruktúra,
- controller helper-ek,
- több low-level UI helper és safety osztályozás,
- recovery és menu phase körüli logika jelentős része legalább tesztelt.

---

## Mi a fő elakadás most?

A jelenlegi dokumentált állapot alapján a fő szűk keresztmetszet a **runtime mapping megbízhatósága és mélysége**, különösen:

- top menu újranyitás stabilitása,
- fókusz-helyreállítás,
- tiltott zónába eső kattintások kezelése,
- túl sok fix várakozás,
- drága popup snapshot/diff feldolgozás,
- project-open recovery túl hosszú és néha félrevezető működése.

Vagyis a projekt legfontosabb következő fázisa nem az alapok megírása, hanem a **valós WinWatt UI-val való robusztus együttműködés finomítása**.

---

## Rövid, őszinte állapotkép

### Amit már tud a projekt
- fel tudja dolgozni a statikus UI-forrást,
- tud belső modellt építeni,
- tud parancs- és workflow-alapokat generálni,
- tud a futó alkalmazással kapcsolatot felépíteni,
- tud runtime mapping futást indítani és naplózni,
- van köré fejlesztői vezérlő és elég sok teszt.

### Ami még nincs kész
- a teljes, megbízhó, mély menü- és dialógusfeltérképezés,
- a runtime tudásbázis érdemi feltöltése valós menüútvonalakkal,
- a gyors és stabil recovery minden problémás UI-helyzetben,
- a production-szintű, végigrobosztus automatizálási végrehajtás.

---

## Következő logikus lépések

1. A top-menu kattintás további stabilizálása.
2. A fix sleep-ek lecserélése rövid, állapotvezérelt wait logikára.
3. A popup snapshot és diff költségének csökkentése.
4. A project-open recovery pontosítása és gyorsítása.
5. Több valós menüútvonal és dialógus sikeres rögzítése a runtime knowledge-be.
6. A runtime mapping eredmények minőségének javítása, hogy a `summary.md` fájlok már valódi menüstruktúrát mutassanak.

---

## Egymondatos összefoglaló

A projekt jelenleg ott tart, hogy **az automatizálási keretrendszer gerince már kész és tesztelt**, a fő következő feladat pedig az, hogy a **valós WinWatt UI runtime feltérképezése stabilan, gyorsan és mélyen működjön**.
