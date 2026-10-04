# WebWatt helyi tanúsítási worker

Ez a worker a WebWatt felületén feltöltött **PDF** vagy **XML** forrásokat veszi fel a `certificate_intake` sorból. A helyi gépen fut: a böngészőnek nincs WinWatt-vezérlési és nincs Supabase service-role jogosultsága.

## Mit csinál

1. Letölti a privát `project-documents` tárból a forrásfájlt.
2. PDF-nél helyben futtatja a bizonyíték-első `CertificateProjectBuilder` feldolgozást és a helyi WinWatt-anyagkatalógus alapján készít anyag-egyezési döntéseket.
3. XML-nél kizárólag struktúraösszesítést készít.
4. Az eredmény JSON-okat visszatölti a projekt dokumentumai közé és a queue feladat eredményébe írja az elérhetőségüket.

Nem hív ChatGPT-t (`allow_llm=False`), nem indít WinWattot, nem importál natív XML-t és nem hoz létre WWP-t. Ezekhez az ellenőrzött geometriai modell és külön, emberi jóváhagyással létrehozott WinWatt-feladat kell.

## Telepítés és indítás Windows alatt

Hálózat és Supabase-kulcs nélküli XML dry-run:

```powershell
python scripts\webwatt_certificate_worker.py dry-run `
  --source tests\test.xml `
  --workspace data\webwatt_jobs\manual_xml_test
```

PDF esetén a `--catalog C:\...\anyagkatalogus.xml` kapcsoló is kötelező. A
dry-run `intake_manifest.json` fájlt készít a forrás hashével, az eredményfájlok
hashével és méretével, valamint `review_required: true`, `winwatt_started:
false` és `llm_used: false` kapukkal. Azonos forrás és teljes manifest esetén a
helyi eredmény újrafelhasználható; megváltozott forrást ugyanabban a
könyvtárban elutasít.

Az élő queue-workerhez:

A `winwatt_automation` virtuális környezetéből állítsd be a helyi változókat. A service role kulcsot ne tedd sem a böngészős `.env` fájlba, sem gitbe.

```powershell
$env:SUPABASE_URL = 'https://<projekt-ref>.supabase.co'
$env:SUPABASE_SERVICE_ROLE_KEY = '<service-role-secret>'
$env:WINWATT_CATALOG_XML = 'C:\teljes\utvonal\winwatt_anyagkatalogus.xml'
$env:WEBWATT_WORKER_ID = "$env:COMPUTERNAME-certificate-worker"
python scripts\webwatt_certificate_worker.py watch
```

Titkok kiírása nélküli kapcsolat-előellenőrzés:

```powershell
python scripts\webwatt_certificate_worker.py preflight
```

PDF-feladatokhoz a katalógus meglétét is kötelezően ellenőrizheted a
`preflight --require-catalog` paranccsal. Sikeres előellenőrzéskor a worker
service-role jogosultsággal, kizárólag olvasva ellenőrzi a `job_queue` és a
`certification_cases` REST-végpontokat; nem foglal le feladatot.

Egyszeri, ellenőrizhető futáshoz:

```powershell
python scripts\webwatt_certificate_worker.py once
```

Az adatbázisban előbb alkalmazni kell a WebWatt `20260915110000_add_certificate_intake_job_type.sql` migrációt. A worker csak a saját `certificate_intake` típusát foglalja le, más fájlkonverziós feladatot nem érint.

## Működési hely

A feldolgozás átmeneti, helyi munkamappája alapból `data\webwatt_jobs\<job-id>`. A forrás és az eredmény JSON a privát Supabase Storage-ban marad; a projektben azok piszkozat dokumentumként jelennek meg. A dolgozó gép kikapcsolt állapotában a feladat várakozó státuszban marad.

Az élő Supabase-feltöltés hálózati idempotenciáját külön integrációs teszttel
kell még bizonyítani; a helyi cache újraindíthatósága ezt önmagában nem igazolja.

A worker újrapróbáláskor előbb ellenőrzi a cél Storage-objektumot. A
`project_documents` sorhoz a projektazonosítóból és a teljes storage-útvonalból
determinista UUID készül; a PostgREST beszúrás `ignore-duplicates` móddal fut.
Így ugyanaz a job/artefakt pár soros retry és beszúrási verseny esetén is
ugyanarra a Storage-kulcsra és elsődleges kulcsra mutat. Ezt helyi fake API-val
teszteljük; a tényleges Supabase Storage HEAD/409 és PostgREST viselkedést az
élő környezetben még külön integrációs próbával kell igazolni.
