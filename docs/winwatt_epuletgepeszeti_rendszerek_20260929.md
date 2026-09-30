# Épülettechnikai rendszerek: helyi feltárás

Verzió: WinWatt gólya 9.60.0.0; profil:
`winwatt_8c137b67c0a2214bb91aeae8`. A futások másolt WWP-projekten, a külön
32 bites helyi Python-környezettel történtek, külső AI-hívás nélkül.

## Létrehozó ablakok

Az épületre dupla kattintás után a 2023-as **Épülettechnikai rendszerek** lapon
három rendszerlista és három nyolcgombos eszköztár jelenik meg. Az első lista
hat létrehozó gombjának ellenőrzött sorrendje:

| Index | Funkció | Delphi ablakosztály |
| ---: | --- | --- |
| 0 | Fűtési rendszer | `THeatingEnergyForm` |
| 1 | Melegvízellátó rendszer | `TWaterHeatingEnergyForm` |
| 2 | Világítási rendszer | `TLightingEnergyForm` |
| 3 | Légtechnikai rendszer | `TAiringEnergyForm` |
| 4 | Gépi hűtés | `TCoolingEnergyForm` |
| 5 | Nyereségáram vagy egyéb veszteség | `TSolarEnergyForm` |

Az index 6 elválasztó, az index 7 üres listánál letiltott törlés. A feltáró
script mind a hat ablak mezőit és választóértékeit JSON-ba írja, képernyőképet
készít, majd az **Elvet** gombbal bezárja. A forrás és a munkamásolat hash-e a
futás végén változatlan volt.

## Első tartós rendszerpróba

A minimális világítási rendszer alapállapotban engedélyezett **OK** gombbal
rendelkezik. A próba egy egyedi nevet írt be, elfogadta a rendszerablakot és az
épületablakot, a natív projektmentést használta, szabályosan bezárta a programot,
majd új WinWatt-folyamatban visszanyitotta ugyanazt az épületet.

Az `AUTOWINWATT_LIGHTING_ROUNDTRIP` rekord létrehozás előtt hiányzott, létrehozás
után megjelent az eredeti rendszerek listájában, és teljes újraindítás után is
ugyanott szerepelt. A másolat SHA-256 értéke megváltozott, a kiinduló WWP-é nem.
Ez a rendszerrekord tartósságát igazolja; energetikai helyességet vagy teljes
tanúsítást még nem.

## Reprodukálás

Párbeszédablak-leltár:

```powershell
..\.venv-winwatt32\Scripts\python.exe -m winwatt_automation.scripts.probe_building_system_dialogs --profile ../docs/winwatt_local_profile_20260929.json --source <forras.wwp> --output <uj-kimenet>
```

Világítási mentés–újranyitás próba:

```powershell
..\.venv-winwatt32\Scripts\python.exe -m winwatt_automation.scripts.probe_lighting_system_roundtrip --profile ../docs/winwatt_local_profile_20260929.json --source <forras.wwp> --output <uj-kimenet>
```

Az output mappa nem létezhet. A bizonyító riportok:
`winwatt_automation/data/runtime_maps/systems_dialogs_20260929c/report.json` és
`winwatt_automation/data/runtime_maps/lighting_roundtrip_20260929b/report.json`.

## Következő lépés

A 2023-as **Zónák** lapon a „Fűtött zóna megadása” és „Hűtött zóna megadása”
ablak is `TThermicZoneForm`. Mindkettő teljes épület, egyesítő név vagy
helyiségek alapján képezhet területet. Az üres épület alap fűtött zónája
„Lakóépület egésze”, 0,00 m² területtel; a hűtött zóna szintén 0,00 m².
A leltár mindkét ablakot mentés nélkül zárta, a projektmásolat változatlan maradt.

A következő tartóssági próbához elkészült a
`full_authorized_sandbox/certification_seed_20260929b/prepared.wwp`: egy 10 m²-es
„Tanúsítás teszthelyiség 1” helyiséget és egy hozzárendelt külső falat tartalmaz.
Ennek létrehozása közben javítottuk a külső fal X mezőjének koordinátafüggő
azonosítását, és regressziós teszt készült hozzá. A helyiséges projekt első
zóna-visszaolvasási próbája kétszer Windows aktív-asztal/előtérazás hibába futott,
ezért a 10 m² zónaterület még nincs igazolva.

A következő futásban, aktív Windows-asztal mellett, először a helyiséges zóna
területét kell visszaolvasni. Utána a fűtési rendszer **Hőtermelők** alfolyamatát
kell feltérképezni, egy minimális fűtési rendszert a zónához rendelni, majd az
egész kapcsolatot mentés és teljes újraindítás után ellenőrizni.
