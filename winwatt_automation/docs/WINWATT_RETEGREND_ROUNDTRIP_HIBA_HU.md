# WinWatt rétegrend-roundtrip: ablak-handle hiba és futtatási szabály

## Tünet

A `winwatt.building.structure.reviewed_handoff.roundtrip` futás időnként
`InvalidWindowHandle` hibával leállt. A bemeneti rétegrend JSON és a generált
WinWatt XML eközben érvényes maradt, és ugyanaz a rétegrend más futásban
sikeresen átment a mentés–bezárás–újranyitás–XML-visszaolvasás ellenőrzésen.

## Gyökérok

A WinWatt régi natív felülete projekt létrehozásakor és XML-import után úgy is
lecserélheti a `TMainForm` ablakot, hogy maga a `WinWatt32` folyamat változatlan
marad. Az AutoWinWatt főablak-cache-e legfeljebb négy másodpercig állapotvizsgálat
nélkül visszaadhatta a korábbi UIA-wrappert. Ha annak HWND-je közben megszűnt,
az ezt követő `set_focus()` vagy `is_enabled()` `InvalidWindowHandle` hibát adott.

Ez UI-életciklus- és időzítési hiba volt, nem katalógus-, anyag-, rétegrend- vagy
XML-adathiba.

## Javítás

Az alábbi állapotváltásoknál kötelező a WinWatt kapcsolat-cache törlése és a
főablak friss feloldása:

1. új projekt létrehozása előtt;
2. az új projekt fájljának létrejötte után;
3. a `Projekt adatok` párbeszédpanel elfogadása után;
4. XML-import párbeszédpanel bezárása után;
5. az import által megnyitott `Projekt adatok` panel elfogadása után.

A WebWatt-handoff roundtrip jelentése a `failed_phase` mezőben azt is rögzíti,
hogy egy esetleges későbbi hiba melyik műveletben történt.

## Helyes bizonyító futás

A tesztet kizárólag a regisztrált certification tool runnerrel kell indítani:

- 32 bites Python környezetből;
- a rögzített `winwatt_8c137b67c0a2214bb91aeae8` profillal;
- változatlan forrás-WWP-vel;
- minden alkalommal új kimeneti könyvtárba;
- párhuzamos WinWatt UI-automatizálás nélkül.

Siker csak akkor fogadható el, ha a gépi jelentésben egyidejűleg teljesül:

- `status == "passed"`;
- `roundtrip_passed == true`;
- `copy_changed == true`;
- `source_unchanged == true`;
- minden réteg visszaolvasási ellenőrzése `passed == true`.

A folyamat nem hoz létre új anyagkatalógus-elemeket. A jóváhagyott, meglévő
WinWatt-katalógusanyagok tulajdonságaiból `WinWatt32Panel` rétegrendet és annak
`PanelLayer` sorait hozza létre a külön sandbox `.wwp` projektben.

## Ellenőrzött javítás

A javítás utáni `webwatt_handoff_roundtrip_20261005f` futás sikeres lett:

- jelentés: `data/runtime_maps/webwatt_handoff_roundtrip_20261005f/report.json`;
- létrehozott sandbox: `data/runtime_maps/webwatt_handoff_roundtrip_20261005f/sandbox/reviewed.wwp`;
- forrás SHA-256: `e5fce19ad799b06290cd2c28153c35cb881708141c084a87faf26001af2751ff`;
- handoff SHA-256: `b8a9c6664b5457157827fd357feba580f2a61f18b0f73abed955817d58789525`;
- katalógus SHA-256: `a4ec5f1bb49f461f5761e8e75dc946d9c7c717feb75d59ac2cb2616cfe8af768`;
- `status`, `roundtrip_passed`, `copy_changed` és `source_unchanged`: sikeres;
- a `Rockwool Airrock ND` 150 mm és `Rockwool Airrock LD` 50 mm rétegek
  mentés utáni visszaolvasása sikeres.
