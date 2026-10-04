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
| 7 | Teljes exportcsomag | várakozik | WWP, natív XML, számítási PDF, tanúsítási XML és fotócsomag ellenőrzött |
| 8 | WebWatt élő összekötés | várakozik | queue-feltöltés, worker-visszatöltés, idempotencia és G0–G4 kapuk igazoltak |
| 9 | Teljes referencia-tanúsítás | várakozik | teljes lánc lefut, majd emberi szakmai és grafikus jóváhagyást kap |

A gépészeti és ET-gráfok megfigyelési bizonyítéka már rendelkezésre áll. Egy
megfigyelt útvonal csak sikeres roundtrip után kerülhet a verziózott
tool-regiszterbe. Hiányzó adminisztratív adatot az ET-folyamatban kézzel is meg
kell tudni adni; külső feltöltés és véglegesítés emberi jóváhagyás nélkül nem
végezhető.

A géppel olvasható állapot:
`winwatt_automation/data/runtime_maps/certification_queue/certification_work_queue.json`.
