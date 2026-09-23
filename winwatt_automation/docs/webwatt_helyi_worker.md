# WebWatt helyi tanúsítási worker

Ez a worker a WebWatt felületén feltöltött **PDF** vagy **XML** forrásokat veszi fel a `certificate_intake` sorból. A helyi gépen fut: a böngészőnek nincs WinWatt-vezérlési és nincs Supabase service-role jogosultsága.

## Mit csinál

1. Letölti a privát `project-documents` tárból a forrásfájlt.
2. PDF-nél helyben futtatja a bizonyíték-első `CertificateProjectBuilder` feldolgozást és a helyi WinWatt-anyagkatalógus alapján készít anyag-egyezési döntéseket.
3. XML-nél kizárólag struktúraösszesítést készít.
4. Az eredmény JSON-okat visszatölti a projekt dokumentumai közé és a queue feladat eredményébe írja az elérhetőségüket.

Nem hív ChatGPT-t (`allow_llm=False`), nem indít WinWattot, nem importál natív XML-t és nem hoz létre WWP-t. Ezekhez az ellenőrzött geometriai modell és külön, emberi jóváhagyással létrehozott WinWatt-feladat kell.

## Telepítés és indítás Windows alatt

A `winwatt_automation` virtuális környezetéből állítsd be a helyi változókat. A service role kulcsot ne tedd sem a böngészős `.env` fájlba, sem gitbe.

```powershell
$env:SUPABASE_URL = 'https://<projekt-ref>.supabase.co'
$env:SUPABASE_SERVICE_ROLE_KEY = '<service-role-secret>'
$env:WINWATT_CATALOG_XML = 'C:\teljes\utvonal\winwatt_anyagkatalogus.xml'
$env:WEBWATT_WORKER_ID = "$env:COMPUTERNAME-certificate-worker"
python scripts\webwatt_certificate_worker.py watch
```

Egyszeri, ellenőrizhető futáshoz:

```powershell
python scripts\webwatt_certificate_worker.py once
```

Az adatbázisban előbb alkalmazni kell a WebWatt `20260915110000_add_certificate_intake_job_type.sql` migrációt. A worker csak a saját `certificate_intake` típusát foglalja le, más fájlkonverziós feladatot nem érint.

## Működési hely

A feldolgozás átmeneti, helyi munkamappája alapból `data\webwatt_jobs\<job-id>`. A forrás és az eredmény JSON a privát Supabase Storage-ban marad; a projektben azok piszkozat dokumentumként jelennek meg. A dolgozó gép kikapcsolt állapotában a feladat várakozó státuszban marad.
