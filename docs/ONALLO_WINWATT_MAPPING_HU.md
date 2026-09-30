# Önálló WinWatt mapping-végrehajtó

A végrehajtó helyi, 32 bites Pythonból működik, és nem hív LLM-et vagy Codexet.
Arra szolgál, hogy a tanúsítási adapterhez szükséges WinWatt-bizonyítékokat
felügyelet nélkül gyűjtse, miközben a Codex-keret nem elérhető.

## Igazolt fűtési workflow

A fűtött zóna és a minimális elektromos fűtési rendszer teljes
mentés–újranyitás köre egyetlen helyi paranccsal futtatható:

```powershell
.\Start-WinWattHeatingCertification.ps1
```

A parancs új projektmásolatokat készít, először a fűtött zónát, majd arra építve
a fűtési rendszert ellenőrzi. A közös `workflow_report.json` csak akkor kap
`passed` státuszt, ha mindkét részriport sikeres, a zóna és a rendszer is
megmarad újranyitás után, a verzióprofil egyezik, és az eredeti WWP hash-e nem
változik. A futás több percig tarthat, és feloldott Windows-asztalt igényel.

## Egyszerű indítás

A repository gyökerében dupla kattintással indítható:

```text
start_winwatt_mapping.cmd
```

Alapértelmezésben hat órán át dolgozik. A legutóbbi helyiséges `prepared.wwp`
projektet választja, ellenőrzi a rögzített WinWatt-verzióprofilt, majd sorban:

1. felveszi a hat épülettechnikai rendszer létrehozó ablakát;
2. felveszi a fűtött és hűtött zóna ablakát;
3. változtatás nélkül feltérképezi a fűtési hőtermelő-katalógust;
4. elvégzi a világítási rendszer mentés–újranyitás próbáját;
5. külön másolatokon végigfuttatja a fűtött zóna és a minimális elektromos
   fűtési rendszer közös mentés–újranyitás ellenőrzését;
6. a hátralévő időben az épület részletező rekurzív állapotgráfját járja be,
   külön kampánymásolaton és folytatható checkpointtal.

A Windows munkamenetnek feloldva kell maradnia. A monitor kikapcsolhat, de a
Windows zárolása megszakíthatja a Delphi/pywinauto kattintásokat. A felügyelő az
ilyen hibát felismeri, állapotot ment, vár, és a határidőn belül újrapróbálja.

## PowerShell indítás és időkeret

```powershell
.\Start-WinWattMapping.ps1 -Hours 10
```

Másik forrásprojekt megadása:

```powershell
.\Start-WinWattMapping.ps1 -Hours 8 -Project "C:\utvonal\projekt.wwp"
```

Csak a célzott, rövid tanúsítási próbák, háttér-crawler nélkül:

```powershell
.\Start-WinWattMapping.ps1 -Hours 1 -SkipBackground
```

Leállítás: `Ctrl+C`. A futó gyermekfolyamat először megszakítási jelet kap, hogy
checkpointot írhasson; csak ezután következhet kényszerített leállítás.

## Folytatás

A legutóbbi befejezetlen kampány folytatása:

```powershell
.\Start-WinWattMapping.ps1 -ResumeLatest -Hours 6
```

A már sikeres fázisokat kihagyja. A background mapper ugyanazt a checkpointot
és kampányon belüli tudástárat használja tovább. A normál folytatás először
csak a mentett, még fel nem dolgozott várólistát járja be; a korábbi hibás
útvonalakat nem teszi automatikusan újra sorba.

A korábbi hibák célzott újrapróbálása külön kérhető:

```powershell
.\Start-WinWattMapping.ps1 -ResumeLatest -RetryFailures -Hours 2
```

Ezt a normál várólista elfogyása után érdemes használni. Az új hibabejegyzések
az exception típusát és `repr` értékét is tárolják, ezért az üres pywinauto
hibaüzenetek is diagnosztizálhatók.

Az új gráfverzió az alternatív útvonalon újra elért állapotot a korábban
rögzített kanonikus állapotazonosítóhoz köti. A kampányösszesítő megmutatja a
több útvonalú célokat, a még feloldatlan régi `revisited` éleket, az ismétlődő
hibacsoportokat és a várólista következő műveleteit.

## Időkorlát nélküli, AI-mentes folytatás

Ha a Codex-keret elfogy, a legutóbbi befejezetlen kampány dupla kattintással is
folytatható:

```text
start_winwatt_mapping_unlimited.cmd
```

Ennek PowerShell-megfelelője:

```powershell
.\Start-WinWattMapping.ps1 -ResumeLatest -UntilComplete
```

Ebben a módban nincs mesterséges órakorlát. A helyi 32 bites Python addig fut,
amíg a kiválasztott feladatok és az épületmapping várólistája el nem fogynak,
vagy biztonsági hiba, forráshash-eltérés, végleges job-hiba vagy kézi `Ctrl+C`
meg nem állítja. A heartbeat, az atomikus kampányállapot, az élről élre írt
checkpoint és az `llm_used: false` jelző változatlanul megmarad.

Lezárt vagy nem elérhető Windows-asztalnál a korlátlan felügyelő nem fogyasztja
el az újrapróbálási keretet: helyi heartbeat mellett vár az asztal
visszatérésére. Ettől még a mappinghez feloldott, interaktív asztal kell. A
korlátlan mód jelenleg a tanúsítás fő `buildings` scope-jára használható; a
régi `structures` crawler továbbra is határidős.

Az indítót nem szabad egy már aktív WinWatt mapper mellé elindítani. Ha a
korábbi, időkorlátos kampány még fut, az AI/Codex jelenléte nélkül is folytatja
a munkát; a korlátlan folytatót csak annak szabályos befejezése után kell
indítani.

Alapból az épületablak a hosszú mapping célja, mert ez fedi a zónákat és az
épülettechnikai rendszereket. Ha külön a globális Szerkezetek katalógus meglévő
crawlerét kell futtatni, közvetlen Python-indítással használható a
`--background-scope structures` kapcsoló.

## Biztonsági és auditálási tulajdonságok

- A végrehajtó elutasítja a nem 32 bites Python-interpretert.
- Indulás előtt ellenőrzi az EXE-t és a verzióprofil erőforrásait.
- Minden próba saját projektmásolatot készít; a forrás WWP hashét minden fázis
  után újra ellenőrzi, eltérésnél az egész kampány leáll.
- A rekurzív mapper globális store helyett kampányon belüli tudástárba ír, így
  egy éjszakai futás nem módosítja automatikusan a repository tudásfájljait.
- A `campaign_state.json` atomikusan frissül, tartalmazza a heartbeatet, az
  aktuális PID-et, a próbálkozásokat, logokat és riportokat.
- A részletes stdout/stderr külön attempt-logba kerül; a konzol csak rövid
  állapoteseményeket ír.
- A végrehajtó AI-használata minden kampányállapotban `false`.

Az eredmények helye:

```text
winwatt_automation/data/runtime_maps/certification_mapping/campaign_*/
```

Elsőként a `campaign_state.json` fájlt érdemes megnyitni. A célzott próbák
riportjai a `jobs/<feladat>/attempt_*/report.json`, a hosszú crawler összesítése
  épület-crawler esetén a `jobs/recursive_building_mapping/graph`, szerkezet-
  crawler esetén a `jobs/recursive_structure_mapping/run/background_summary.json`
  útvonalon van.

## Korlát

Ez mapping- és adapter-bizonyítékot gyűjt, nem dönt energetikai szakkérdésben,
és nem készít automatikusan hivatalos tanúsítványt. A létrejövő capability csak
akkor válhat a tanúsítási pipeline részévé, ha golden projekten, rögzített
WinWatt-verzióval és explicit utófeltétellel is igazolt.
