# Mély UI-bejárók megőrzött algoritmusai

Ez a dokumentum a WinWatt frissítése után is újrahasználandó, jelenleg
ellenőrzött bejárási elveket rögzíti. Nem a nyers bizonyítékok helyett van:
a képek, `state.json` állományok, gráfok és eseménynaplók változatlanul a
`winwatt_automation/data/runtime_maps` alatt maradnak.

## Közös állapotgráf-algoritmus

Forrás: `runtime_mapping/room_deep_explorer.py`.

1. Minden útvonal egy külön, eldobható `.wwp` sandboxból indul.
2. A gyökér-megnyitó egy ismert, szerkeszthető elem részletező ablakát adja.
3. A bejáró az aktív ablak minden látható, engedélyezett gombját, tabját,
   faelemét, listaelemét, kombinált listáját, jelölőnégyzetét és rádiógombját
   műveleti élként veszi fel.
4. Minden él végrehajtása után UI-szerkezet, felsőmenü, képernyőkép és a
   szülőhöz viszonyított diff készül.
5. Csak az új szerkezeti hash új állapot; ismétlődő állapotból nem nő tovább
   a gráf.
6. A várólista, a gráf és a hibalista checkpointtal, valamint minden lépés
   után `fsync`-elt eseménynaplóval helyreállítható.
7. Egy hibás útvonal legfeljebb háromszor próbálható újra. A hiba nem elvesző
   ág: a teljes útvonal és kivétel rögzül.
8. A `pause.request` jelzőfájlt a bejáró csak két útvonal között figyeli;
   ezért a státuszablak „Pillanat, állj” gombja nem szakít félbe kattintást.

Az `--session-islands` optimalizálás modal gombok után megpróbál `Esc`-szel
visszatérni a pontosan ellenőrzött szülő-aláíráshoz. Sikertelenség esetén
automatikusan visszaesik az 1. pont szerinti teljes gyökér-visszajátszásra.

## Helyiségek

Gyökérútvonal:

`Jegyzékek → Helyiségek → Room graph explorer → Elem → Módosítás… → TRoomModifyForm`

Ha a dedikált helyiség hiányzik, az algoritmus létrehozza, a név mezőjét
kitölti, majd a Delphi alapértelmezett Enter-gyorsbillentyűjével elfogadja a
`TNewGroupForm`, utána a `TRoomModifyForm` párbeszédet. A lista megjelenése
kötelező ellenőrzési pont. Ezután indul a közös állapotgráf-algoritmus.

Ismert, értékes ág: `Szerkezetek… → Határoló szerkezetek kiválasztása →
Külső fal → Felvesz… → TWallBoundaryModifyForm`. A korábbi célzott futásban
az `x=1` értékkel való felvétel igazoltan működött.

Lezárt részfutások:

| Terület | Állapot | Művelet | Eredmény |
| --- | ---: | ---: | --- |
| Határoló szerkezetek | 28 | 1 016 | lezárt |
| Nyári hőterhelés | 145 | 4 067 | lezárt |

Az összesített régi gráf és a részfutások megtartandók; a hibaszámok sok
nem végrehajtható vagy ismételt vezérlőágat is tartalmaznak, nem kizárólag
alkalmazáshibát.

## Épületek

Ellenőrzött létrehozási útvonal:

`Jegyzékek → Épületek → Elem → Létrehozás… → TNewGroupForm → TBuildingModifyForm`

Az Épületek lista faállapot-függő: a `Családi ház` faelem kiválasztása után
válik elérhetővé a megfelelő lista. Emiatt az Épületek gyökér-visszajátszója
nem támaszkodhat az előző futás fa- vagy listakijelölésére. A tervezett
stabil forma minden út előtt visszaállítja kizárólag az eldobható Buildings
sandbox `.wwp` fájlját az eredeti `tests/testwwp.wwp` mintából, majd ugyanazt
a dedikált tesztépületet hozza létre és nyitja meg.

Aktuális állapot (2026-08-30):

- a gyökér létrehozása és `TBuildingModifyForm` megnyitása közvetlen
  próbával működött;
- az első általános mélyfutások nem tekinthetők eredménynek: vagy a MDI
  listanézetet járták, vagy a kiválasztás nélküli `Elem → Módosítás…`
  menüelem letiltott volt;
- a teljes Épületek-gráf ezért **még nincs kész**. A következő javítási pont
  a faelem és a létrehozott elem stabil kiválasztásának rögzítése, közvetlenül
  a `TBuildingModifyForm` megnyitása előtt.

## Frissített WinWatt esetén

1. Először csak a gyökérútvonalat validáld képernyőképpel és natív menüvel.
2. Ha vezérlőazonosítók vagy koordináták változnak, ne azokat tedd elsődleges
   azonosítóvá: név + vezérlőtípus + szerkezeti hash a tartós alap.
3. Futtass új, elkülönített sandboxot; korábbi `.wwp` vagy gráf nem írható
   felül.
4. A régi és az új gráf `logical_signature_hash` alapján hasonlítható össze,
   mert ez nem tartalmaz képernyőméret- vagy UIA-handle-függő adatot.
5. Csak a gyökérútvonal bizonyítása után indíts korlátlan mélységű futást.
