# Codex tanúsítási tudásrouter

Ez a dokumentum a magyar energetikai tanúsítás helyi, forrásalapú tudásához
irányít. Nem engedélyez tanúsítási végrehajtást vagy WinWatt-műveletet.

## Kanonikus adatok

- Forrásmanifest:
  `winwatt_automation/data/knowledge/certification_source_manifest.json`
- Kurált szakmai állítások, workflow, felelősségi határok és ellenőrző kérdések:
  `winwatt_automation/data/knowledge/certification_domain_knowledge.json`
- Korábban bizonyított WinWatt-képességek:
  `winwatt_automation/data/knowledge/certification_knowledge.json`
- Végrehajtható toolregiszter:
  `winwatt_automation/data/capabilities/certification_tools.json`

## Kötelező használati sorrend

1. Tanúsítási szakmai kérdésnél először auditáld a tudáscsomagot.
2. A kérdést sorold be: forrásirányítás, számítási módszer, XML, validáció,
   anyag, gépészet vagy workflow.
3. Csak a megfelelő témát kérdezd le; ne töltsd be automatikusan az összes
   PDF-et és katalógust.
4. A válaszban különítsd el a forrásból származó állítást, a gépi ellenőrzést,
   az AI-következtetést és az emberi döntést.
5. A helyi jogszabálymásolatból ne állítsd, hogy az a beadáskor aktuális.
6. A dokumentációs teljes JSON-minta nem életszerű szakmai etalon.
7. A tervezési vagy magyarázati kérés nem engedélyez WinWatt-futtatást,
   projektmódosítást vagy végleges XML előállítását.

## Visszakeresés

A parancsokat a `winwatt_automation` könyvtárból futtasd. A wrapper a helyi
Python-környezetet és a csomagútvonalat determinisztikusan beállítja.

Tudáscsomag auditja:

```powershell
.\Query-CertificationKnowledge.ps1 --audit
```

Téma keresése:

```powershell
.\Query-CertificationKnowledge.ps1 --topic certificate_xml
.\Query-CertificationKnowledge.ps1 --topic materials
```

Workflow-szakasz:

```powershell
.\Query-CertificationKnowledge.ps1 --workflow G1-G3
```

Ellenőrző kérdés:

```powershell
.\Query-CertificationKnowledge.ps1 --check-id check.calculation_pdf
```

## Források megnyitása

A visszakereső minden hivatkozásnál abszolút fájlutat, SHA-256 lenyomatot és
szűk lokátort ad. A tényleges válaszhoz csak a hivatkozott fejezetet vagy
oldalt olvasd el. Ha a hash audit sikertelen, a tudást ne kezeld aktuálisként;
előbb regeneráld a manifestet és vizsgáld felül a kurált állításokat.

## Felelősségi határ

- AI: kérdésosztályozás, forráskeresés, bizonytalanság és következő ellenőrzés.
- Determinisztikus kód: hash, képlet, katalóguslekérdezés, XML- és mezőszabály.
- Emberi szakember: alkalmazhatóság, bizonytalan szakmai értelmezés és kiadás.

A részletes, géppel ellenőrzött határok a
`responsibility_boundaries` tömbben találhatók.
