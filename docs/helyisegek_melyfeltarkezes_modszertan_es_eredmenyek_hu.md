# Helyiségek mélyfeltérképezése – módszertan és eddigi eredmények

## Cél és hatókör

A feltérképező kizárólag az `full_authorized_sandbox` alatti, erre a célra létrehozott WinWatt-projekten dolgozik. A cél a **Helyiségek** jegyzékben elérhető összes felület és vezérlő rekuzív bejárása: tabok, mezők, listák, kombinált listák, gombok, fák, párbeszédablakok és ezek további alfelületei. A végső kimenet egy állapotgráf, amelyből később megbízható automatizálási workflow-k (például `create_room()`) építhetők.

## Bejárási modell

Minden vizsgált útvonal a stabil kiindulópontból indul újra:

1. Megnyitja vagy újrahasználja a sandbox-projektet.
2. Megnyitja a `Room graph explorer` nevű helyiséget.
3. A gyökértől újrajátssza az adott vezérlőutat.
4. UI Automation alapján felveszi az aktív ablak vezérlőtérképét és a natív felsőmenüt.
5. Képernyőképet, `state.json` állapotleírást és az előző állapothoz viszonyított eltérést ment.
6. Csak az új szerkezeti állapotból bővíti tovább a gráfot.

Az újrajátszás szándékosan teljes gyökér–cél útvonalas, nem egy élő ablakban történő „visszalépés a csomóponthoz”. Ez lassabb, de a WinWatt MDI- és modális ablakkezelésével lényegesen stabilabb.

## Állapotok, élek és hibatűrés

- Egy állapot tartalmazza a vezérlőket, az aktuális kiválasztott értékeket, a natív menüszerkezetet, az odavezető utat és a képernyőképet.
- Az élek egy konkrét UI-műveletet jelentenek. Állapotuk `pending`, `running`, `discovered`, `revisited` vagy `failed`.
- A kombinált lista értékváltása külön állapot, mert új funkciókat tehet elérhetővé. A már látható, azonos testvérműveleteket azonban nem járjuk be újra minden értékváltozatból: ezzel elkerülhető a tartalmatlan kombinatorikus robbanás.
- A hibás útvonalak legfeljebb három alkalommal kerülnek újrapróbálásra. A hiba és az útvonal mentve marad.
- Minden feldolgozott út után azonnal, `fsync`-kel ment egy kisméretű eseménynaplóba. Az állapotgráf és a teljes várólista 50 lépésenként tömörül új checkpointtá. Indításkor a napló visszajátszásával a pontos várólista áll helyre, ezért a ritkább nagy írás nem jelent adatvesztést.
- Induláskor az azonos várólista-utak, a már háromszor hibás és a bizonyítottan ismétlődő ágak kikerülnek a várólistából. Ez az útvonal-pruning nem hagy ki olyan ágat, amely új UI-szerkezetet adhat.

## Eddigi eredmények (2026-08-27, utolsó leállításkor)

| Mutató | Érték |
| --- | ---: |
| Rögzített, eltérő UI-állapot | 127 |
| Feltárt vezérlőél | 3926 |
| Dokumentált hiba / újrapróbálási kísérlet | 1126 |
| Folytatásra mentett útvonal | 3635 |
| Futás lezárt állapota | nem kész |

Az eredmények a [egyesített futási könyvtárban](../winwatt_automation/data/runtime_maps/room_deep_runs/20260826T154506_merged) találhatók. Minden `states/<állapot>/state.json` mellé UI-kép tartozik; a checkpointok a futás közben is olvasható gráfot és várólistát adják.

## Látható futási állapot

A mélyfeltérképező `--status-popup` kapcsolóval indul. Külön, rejtett segédfolyamat folyamatosan látható kis állapotablakot jelenít meg az állapotok, ágak, várólista és hibák számával. Az első öt perc után a tényleges várólista-fogyásból hátralévő időt is becsül, és ezt ötpercenként frissíti. Az ablak `SW_SHOWNOACTIVATE` megjelenítésű, tehát nem veheti el a fókuszt a WinWatttól; a fő futás befejezésekor a segédfolyamat is leáll.

## Folyatás parancsa

```powershell
.\.venv-win32\Scripts\python.exe -m winwatt_automation.scripts.explore_rooms_deep `
  --project data\runtime_maps\full_authorized_sandbox\20260826T123933Z\testwwp.wwp `
  --output-dir data\runtime_maps\room_deep_runs\20260826T154506_merged `
  --resume --retry-failures --status-popup
```
