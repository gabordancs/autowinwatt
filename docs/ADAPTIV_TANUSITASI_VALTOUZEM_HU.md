# Adaptív tanúsítási váltóüzem

Utolsó frissítés: 2026-10-14

## Cél

A PDF/XML → WinWatt rekonstrukció a fő munkafolyamat. Az általános, hosszú
UI-crawler helyett a mapping csak konkrét rekonstrukciós elakadásnál indul,
korlátozott akció- és mélységkerettel. A feltárt viselkedés önmagában
`observed`; a rekonstrukció csak mentés–teljes bezárás–újranyitás–visszaolvasás
után használhatja igazolt capabilityként.

```text
rekonstrukció → UI-elakadás → célzott mapping → roundtrip ellenőrzés
      ↑                                             │
      └──────────────── igazolt capability ─────────┘
```

## Kötelező szétválasztás

- `ui_gap`: a forrásadat megvan, de a WinWatt művelet nem ismert vagy hibás;
- `validation_failure`: a művelet lefutott, de az utófeltétel nem igazolható;
- `input_gap`: mérnöki adat vagy jóváhagyás hiányzik.

Az `input_gap` soha nem kerülhet mappingre. Ilyenkor a folyamat
`awaiting_input` állapotban megáll; a hiányzó érték nem feltételezhető.

## Állapotgép és fájlok

A helyi, AI-mentes vezérlő:

```text
winwatt_automation.certificates.adaptive_cycle
winwatt_automation.scripts.adaptive_certification_cycle
```

Egy job könyvtárában a `cycle_state.json` tartalmazza:

- a tanúsítvány- és WinWatt-profilazonosítót;
- a rekonstrukciós projekt útvonalát és SHA-256 lenyomatát;
- az aktív gapet és annak bizonyítékait;
- a következő determinisztikus műveletet;
- az egyetlen WinWatt UI-worker lease-ét;
- az `llm_used: false` jelzőt.

Az állapotok:

| Állapot | Következő lépés |
|---|---|
| `reconstructing` | ismert, igazolt workerek futtatása a következő checkpointig |
| `mapping_required` | kizárólag az aktív gap korlátozott feltérképezése |
| `verification_required` | külön sandboxos mentés–újranyitás–readback próba |
| `awaiting_input` | forrás vagy mérnöki jóváhagyás kérése, feltételezés nélkül |
| `blocked` | elutasított vagy nem igazolható gap kézi vizsgálata |

## Használat

Inicializálás:

```powershell
cd M:\Repositories\autowinwatt\winwatt_automation
..\.venv-winwatt32\Scripts\python.exe -m winwatt_automation.scripts.adaptive_certification_cycle `
  --workspace <uj-job-konyvtar> init `
  --certificate-id <azonosito> `
  --profile-id winwatt_8c137b67c0a2214bb91aeae8 `
  --project <checkpoint.wwp> `
  --checkpoint <rekonstrukcios-riport.json>
```

Gap felvétele és státusz:

```powershell
..\.venv-winwatt32\Scripts\python.exe -m winwatt_automation.scripts.adaptive_certification_cycle `
  --workspace <job> add-gap --gap <gap.json>

..\.venv-winwatt32\Scripts\python.exe -m winwatt_automation.scripts.adaptive_certification_cycle `
  --workspace <job> status
```

A WinWattot vezérlő rekonstrukciós vagy mapping-worker indulás előtt köteles
`acquire-ui` lease-t kérni, befejezéskor pedig `release-ui` művelettel elengedni.
Második worker aktív lease mellett nem indulhat.

## Mapping-korlátok

Minden `ui_gap` és `validation_failure` rekordban kötelező a pozitív
`mapping_budget.max_actions` és `mapping_budget.max_depth`. Listaértékek
katalógusként kerülnek a bizonyítékba; nem képeznek Descartes-szorzatot más
listákkal. Feltöltési, beküldési, hitelesítési és aláírási művelet nem része a
mappingnek.

## Átállási checkpoint – 2026-10-14

Az `et_systems_20260930T2218` általános ET-kampány biztonságos útvonalhatáron
megállt:

- kampányállapot: `interrupted`;
- állapotok: 123;
- élek: 1636;
- hibarekordok: 125;
- hátralévő útvonalak: 104;
- a forrás SHA-256 változatlan:
  `e5fce19ad799b06290cd2c28153c35cb881708141c084a87faf26001af2751ff`;
- a WinWatt- és workerfolyamatok bezárultak;
- a `pause.request` megmaradt, ezért a régi általános kampány véletlenül sem
  folytatódik automatikusan.

A 10479210 pilot első aktív célzott gapje a számítási dokumentum RTF/PDF
mentése. A korábbi próbán a save dialog megnyílt és megkapta a célútvonalat,
de nem jött létre fájl. A javított worker közvetlenül a `Mentés` gombot
aktiválja, ellenőrzi a visszaolvasott útvonalat, és sikertelenségnél minden
WinWatt felsőablakot és képet rögzít a következő célzott mappinghez.

Az első adaptív kör bizonyította, hogy a mentési párbeszéd után a WinWatt
`Printer selected is not valid.` hibát ad, majd a nyomtatókapcsolatra vár. A
Windows alapértelmezett nyomtatójának ideiglenes Adobe PDF-re állítása nem
írja felül a dokumentumoldalon megmaradó `Xerox(R) B225 MFP` választást. A
`Beállít...` gomb ezen a gépen nem adott automatizálható nyomtatóválasztó
modalt. Emiatt a gap bizonyítékszintje `observed`, állapota
`verification_required`; a PDF-export még nem verified capability. A következő
célzott mapping kizárólag a WinWatt belső nyomtató-hozzárendelésének forrását
és módosítását vizsgálhatja.
