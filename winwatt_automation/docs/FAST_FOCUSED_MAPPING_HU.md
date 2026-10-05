# Gyors, célzott WinWatt mapping

Az épület-mapper gyorsított módja ugyanabban a WinWatt-folyamatban próbál
visszatérni az Épületek jegyzékhez. A teljes program- és projekt-újranyitás
csak helyreállítási út: akkor történik meg, ha a párbeszédablakok bezárása,
a jegyzék aktiválása vagy a keresett tesztépület azonosítása nem sikerül.

A `--focus-tab` kapcsolóval egy vagy több konkrét lap teljes részfája járható
be. Új, külön output könyvtárat kell használni, hogy a célzott futás ne írja
át egy teljes kampány függőben levő sorát.

Példa csak a Fűtés terület feltérképezésére:

```powershell
Set-Location M:\Repositories\autowinwatt\winwatt_automation
$env:PYTHONPATH = "src"
..\.venv-winwatt32\Scripts\python.exe -m winwatt_automation.scripts.explore_buildings_deep `
  --project C:\utvonal\sandbox\testwwp.wwp `
  --output-dir C:\utvonal\maps\building-heating `
  --focus-tab "Fűtés" `
  --session-islands
```

Több területhez a `--focus-tab` ismételhető. A futás checkpointolható, és
ugyanazzal az output könyvtárral, valamint a `--resume` kapcsolóval
folytatható.

A gyorsítás biztonsági feltételei változatlanok: csak eldobható sandbox
projekt használható, minden visszaállított állapotot szerkezeti aláírás
ellenőriz, és eltéréskor a mapper automatikusan friss WinWatt-munkamenetre
vált. A már futó Python-folyamat a betöltött régi kódot használja; a gyorsított
logika a következő mapper-indításkor vagy kampány-folytatáskor lép életbe.
