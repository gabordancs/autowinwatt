# Hatékony, bizonyíték-alapú mélybejárás

2026-08-31-i, meglévő futásokból készült elemzés. A korábbi grafok és
képernyőképek változatlanok maradnak a `winwatt_automation/data/runtime_maps`
alatt; ez a dokumentum csak az új futások szabályait írja le.

## Megfigyelések

| Forrás | Állapot | Él | Sikertelen visszajátszás | Következtetés |
| --- | ---: | ---: | ---: | --- |
| Helyiségek / határoló szerkezetek | 28 | 1 016 | 871 | A görgetés és választólista-értékek uralják a munkát. |
| Helyiségek / nyári hőterhelés | 145 | 4 067 | 3 540 | A teljes értékkombinációk nem alkalmasak korlátlan mélységű grafhoz. |
| Épületek | 3 | 18 | 13 | A lista-MDI gyökér nem helyettesítheti a szerkesztőablak gyökerét. |
| Anyagok, első két próba | 1 | 14 | 2 | A rádiógomb kiválasztottsága nem olvasható UIA-n át. |
| Anyagok, javított próba | 55+ | 1 000+ | 50+ | A választóablak elérhető, de a lenyíló listák ágrobbanást okoznak. |

## Új algoritmus

1. **Gyökérprofil-felderítés.** Katalógusonként először csak azt a stabil utat
   keresi meg, amely tényleges belső szerkesztő- vagy típusválasztó ablakhoz
   vezet. Ezt `root_profile.json` rögzíti, így később nem kell a főmenüt újra
   feltalálni.
2. **Szerkezeti állapotok.** Minden új ablakról UI-snapshot, felsőmenü,
   képernyőkép és diff készül. A deduplikáció a vezérlőszerkezetre épül,
   nem újraalkotott UIA-handle-re vagy képernyőpozícióra.
3. **Rejtett választás kezelése.** Rádiógomb vagy jelölőnégyzet után az OK,
   Tovább, Felvesz vagy Módosít megerősítővel alkotott kétlépéses út is külön
   tesztelendő. Így a régi Delphi vezérlők nem olvasható kijelöltsége sem
   takarja el a következő szerkesztőt.
4. **Listakompresszió.** A teljes látható választék a snapshotban megmarad.
   A hosszú, lenyíló értéklistából első/középső/utolsó reprezentáns indul;
   csak eltérő eredményablak-szerkezet indít új mélységi ágat.
5. **Nem szemantikus vezérlők elhagyása.** Görgető, lapozó, oszlopmozgató,
   méretváltó és ComboBox nyílgomb nem új állapotátmenet. Nem futnak önálló
   ágnak.
6. **Stabil fa- és listaazonosság.** Azonos nevű TreeItem/ListItem nem válik
   új ággá pusztán azért, mert a lista legörgetése más képernyőkoordinátára
   tette. A név + vezérlőtípus azonosítja.
7. **Helyreállás és kiosztás.** Minden út eldobható sandboxból visszajátszható;
   a gyökérprofilok és a kész részgráfok önálló munkacsomagok, ezért később
   második gépnek átfedés nélkül kioszthatók.

## Teljesség jelentése

Egy futás akkor tekinthető lezártnak, ha a választott gyökérprofilból nincs
új, eltérő vezérlőszerkezetet vagy menüt létrehozó út. Ez nem azt állítja,
hogy minden lehetséges numerikus értékkombinációt kipróbáltunk: azok külön
paraméter-térképezési feladatok. A látható értékkészletet ekkor is bizonyíték
őrzi, a szerkesztők és funkcionális dialógusok pedig teljes mélységben
bejárhatók maradnak.
