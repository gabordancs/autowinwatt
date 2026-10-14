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

A 10479210 pilot első célzott gapje, a számítási dokumentum PDF-mentése
2026-10-14-én lezárult. A hiba oka a Windows automatikus
alapértelmezett-nyomtató kezelése volt: a
`LegacyDefaultPrinterMode=0` beállítás WinWatt indulásakor visszaváltotta az
alkalmazást a legutóbb használt Xerox WSD nyomtatóra. A worker most a futás
idejére `LegacyDefaultPrinterMode=1` értéket állít, az Adobe PDF-et teszi
alapértelmezetté, közvetlenül a `PDF fájlba...` műveletet hajtja végre, majd
mindkét Windows-beállítást visszaállítja.

Két egymást követő, üres kimeneti könyvtárban végzett futás `passed` lett. A
két 9 oldalas PDF bájtszinten azonos, SHA-256 lenyomatuk
`eaed66fb8cc255ea946b422dad0019212e212d18d151772304120fdeb4474a04`.
Mindkét riport igazolja a változatlan forrás- és projektmásolatot, a bezárt
WinWatt-munkamenetet, az eredeti Xerox alapértelmezés és a
`LegacyDefaultPrinterMode=0` visszaállítását. A gap eredménye `verified`, az
adaptív ciklus ismét `reconstructing` állapotban van.
