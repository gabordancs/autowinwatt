# Munka-PC: Helyiségek feltérképező indítása

Ez a gép futtatja a WinWattot és a SafeNet USB kulcsot a VirtualHere
kapcsolaton keresztül. A futás csak a `Helyiségek` területet járja be;
a radiátor-, felületfűtés-hűtés- és fan-coil választék/leadó fülek ki vannak
zárva.

## Egyszeri előkészítés

Nyiss egy PowerShellt a Munka-PC-n, majd futtasd:

```powershell
git clone --branch codex/remote-room-mapper --single-branch https://github.com/gabordancs/autowinwatt.git $env:USERPROFILE\source\autowinwatt
cd $env:USERPROFILE\source\autowinwatt\winwatt_automation
py -3.12-32 -m venv .venv-win32
.\.venv-win32\Scripts\python.exe -m pip install --upgrade pip
.\.venv-win32\Scripts\python.exe -m pip install -e ".[dev]"
```

Ehhez 32 bites Python 3.12 és Git kell. A WinWatt, a Sentinel driver és a
VirtualHere kliens már a Munka-PC-n legyen telepítve; a SafeNet USB
SuperPro/UltraPro eszköznek a VirtualHere kliensben `Use` állapotban kell
lennie.

## Futtatás

Ments egy külön, eldobható WinWatt projektet a `full_authorized_sandbox`
könyvtár alá, majd indítsd:

```powershell
$root = "$env:USERPROFILE\source\autowinwatt\winwatt_automation"
$project = "$root\data\runtime_maps\full_authorized_sandbox\remote\testwwp.wwp"
$out = "$root\data\runtime_maps\room_deep_runs\remote_$(Get-Date -Format yyyyMMddTHHmmss)"
Set-Location $root
New-Item -ItemType Directory -Force -Path (Split-Path $project) | Out-Null
Copy-Item .\tests\testwwp.wwp $project -Force
& .\.venv-win32\Scripts\python.exe -m winwatt_automation.scripts.explore_rooms_deep `
  --project $project --output-dir $out --status-popup --session-islands `
  --exclude-tab 'Radiátorok' `
  --exclude-tab 'Felületfűtés-hűtés' `
  --exclude-tab 'Fan-coilok' `
  --exclude-tab 'Radiátor választék' `
  --exclude-tab 'Felületfűtés-hűtés választék' `
  --exclude-tab 'Fan-coil választék'
```

A futtató a `progress.json`, checkpointok és screenshotok alapján bármikor
folytatható ugyanazzal az `--output-dir` értékkel és `--resume` kapcsolóval.
Leállításhoz `Ctrl+C` használható.

## Eredmények visszaadása

A kész `remote_*` futási könyvtárat másold vissza a fő gépre a
`winwatt_automation/data/runtime_maps/room_deep_runs/` alá. Ezután a központi
elemző össze tudja fűzni a korábbi állapotgráffal.
