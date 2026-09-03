# Ellenőrzött WinWatt-létrehozási workflow-k

Ez a dokumentum csak futás közben igazolt, ismételhető útvonalakat rögzít.
Minden automatikus létrehozást eldobható `.wwp` sandboxban kell végezni,
amíg a felhasználó nem nevez meg kifejezetten egy valódi projektet.

## Épület + három helyiség + egy-egy külső fal

Igazolva: 2026-08-31.

Végrehajtott eredmény egy friss sandboxban:

- `Automation demo building` épület;
- `Automation demo room 1`, `Automation demo room 2`,
  `Automation demo room 3`;
- minden helyiséghez pontosan egy `Külső fal`;
- minden fal szerkesztőablaka `TWallBoundaryModifyForm` volt;
- az eredmények minden lépés után a projektfájlba mentődtek.

Az adott futás bizonyítéka:
`winwatt_automation/data/runtime_maps/full_authorized_sandbox/`
`building_three_rooms_persisted_20260831T153835/creation_report.json`.

### Stabil útvonal

1. `Jegyzékek → Épületek → Elem → Új elem`, név megadása,
   `TNewGroupForm → TBuildingModifyForm → Enter`.
2. Főablakban `Ctrl+S`: az épület katalogizált mentése nem hagyható a
   munkamenet végére.
3. Helyiségenként: `Jegyzékek → Helyiségek → Elem → Új elem`, név megadása,
   `TNewGroupForm → TRoomModifyForm`.
4. A helyiségben: `Szerkezetek... → TSelectBoundarisForm`.
5. A bal alsó fában: `Szerkezetek → Határoló szerkezetek`.
6. A jobb alsó szerkezetkönyvtárból: `Külső fal`, majd `Felvesz...`.
7. `TWallBoundaryModifyForm → Enter`, utána a választóablak `OK`, majd a
   helyiségablak `Enter`.
8. Ismét `Ctrl+S`.

### Fontos technikai sajátosság

A `TSelectBoundarisForm` jobb alsó `TListViewWithHeader` listája UIA-n
olvasható, de a UIA `ListItem.click_input()` nem állítja be megbízhatóan a
Delphi natív kijelölt sort. Emiatt a `Felvesz...` gomb letiltva marad.

Megbízható eljárás:

- a jobb alsó natív `TListViewWithHeader` sort kell kiválasztani;
- a kijelölt indexet `LVM_GETNEXTITEM` + `LVNI_SELECTED` lekérdezéssel kell
  ellenőrizni;
- csak ezután kattintható a `Felvesz...`.

Az ismételhető program: 
`winwatt_automation/src/winwatt_automation/scripts/create_building_with_rooms.py`.

## Általános mentési szabály

A rekord-szerkesztő `Enter` elfogadja az adott dialógust, de nem helyettesíti
biztosan a projektfájl mentését. Több rekordos automatikus folyamatban minden
lényeges objektum vagy objektumcsoport után fókuszálni kell a főablakot és
`Ctrl+S`-t kell küldeni.
