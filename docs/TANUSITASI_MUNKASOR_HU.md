# Teljes tanúsítási munkasor

Ez a lista a helyi WinWatt-helyiségmapping után végrehajtandó feladatok
sorrendje. Egyszerre csak egy WinWatt UI-automatizálás futhat. Minden módosító
próba külön sandboxmásolatot, változatlan forrás-SHA-256-ot, mentést, teljes
WinWatt-bezárást, újranyitást és gépi utófeltételt igényel.

| Sorrend | Feladat | Állapot | Kész feltétel |
| ---: | --- | --- | --- |
| 1 | Tanúsításkritikus helyiségmapping lezárása | kész | 385 állapot, 3726 él, üres várólista, változatlan forráshash |
| 2 | Helyiséggráf auditja és tömör bizonyítékriport | kész | teljes állapot- és képbizonyíték, 0 függő él |
| 3 | HMV-rendszer roundtrip tool | kész | elektromos HMV létrehozása, mentése, teljes újranyitása és gépi visszaolvasása sikeres |
| 4 | Légtechnikai és hűtési roundtrip toolok | kész | mindkét rendszer mentés–bezárás–újranyitás bizonyítéka sikeres |
| 5 | Számítás indítása és eredmény-roundtrip | kész | a 25 mezős helyiségeredmény újraszámítás, mentés és teljes újranyitás után gépileg azonosan visszaolvasható |
| 6 | ET-varázsló és tanúsítási XML | kész | a minimális tesztépület és valamennyi szerkezet kiválasztása, a kötelező adminmezők pótlása és a jól formált `UploadRequest` XML előállítása igazolt |
| 7 | Teljes exportcsomag | kész | WWP, natív XML, számítási PDF, tanúsítási XML és valódi JPEG-ként ellenőrzött szintetikus tesztfotó hash-elt manifestben |
| 8 | WebWatt élő összekötés | folyamatban | helyi intake és újraindítási idempotencia igazolt; az élő queue-feltöltés, worker-visszatöltés és G0–G4 élő kapupróba hátravan |
| 9 | Teljes referencia-tanúsítás | várakozik | teljes lánc lefut, majd emberi szakmai és grafikus jóváhagyást kap |

A gépészeti és ET-gráfok megfigyelési bizonyítéka már rendelkezésre áll. Egy
megfigyelt útvonal csak sikeres roundtrip után kerülhet a verziózott
tool-regiszterbe. Hiányzó adminisztratív adatot az ET-folyamatban kézzel is meg
kell tudni adni; külső feltöltés és véglegesítés emberi jóváhagyás nélkül nem
végezhető.

A géppel olvasható állapot:
`winwatt_automation/data/runtime_maps/certification_queue/certification_work_queue.json`.

A Q7 bizonyítéka:
`winwatt_automation/data/runtime_maps/complete_export_package_20261004a/q7_completion_report.json`.
A WinWatt közvetlen PDF-nyomtatási útja a telepített nyomtatót elutasította, ezért
a számítási PDF a WinWatt RTF-exportjából, helyi Microsoft Word 16 konverzióval
készült. A PDF-export útvonal emiatt még nem kerülhet `verified` toolként a
regiszterbe.

A Q8 helyi bizonyítéka:
`winwatt_automation/data/runtime_maps/q8_webwatt_integration_20261004a/report.json`.
Az élő worker indítása előtt a WebWatt-adatbázisban alkalmazni kell a worker RPC-ket
`service_role` jogosultságra szűkítő migrációt, majd a kulcsot csak a helyi worker
folyamat környezetében szabad megadni.
