# Legutóbbi commit működési felülvizsgálat

Commit alap: `4ed5634` (`ujfutas`)

## Rövid összegzés

A commit elsősorban egy új runtime-mapping futás eredményeit menti el. A run napló alapján a teljes futás kb. 15 percig tartott, majd hibával állt meg. A fő probléma nem pusztán a sebesség, hanem az, hogy a fókusz-visszaállítás és a menükattintás túl sok teljes UI-ellenőrzést és várakozást végez, miközben a `Rendszer` menü újranyitásakor a kattintás a tiltott bal felső zónába kerül.

## Fő megállapítások

### 1. A futás instabil fókusz-helyreállítás miatt törik meg

A napló szerint a `no_project` állapot feltérképezése közben már elveszik a fókusz, majd a `project_open` fázisban a `Rendszer` top menu újranyitása végül `click_blocked_forbidden_zone` hibára fut. Ez azt jelzi, hogy az újranyitási logika és a fallback kattintás jelenleg nem elég robusztus, ha a menüsáv geometria eltolódik vagy nem jól oldódik fel.

### 2. A teljes futás idejének nagy része fix várakozásokból áll

A jelenlegi implementáció több helyen fix sleep-eket használ (`0.3s`, `0.25s`, többszöri baseline delay, 15s recovery timeout). Ezek sok menüelem és rekurzív feltérképezés mellett összeadódnak, és a napló alapján percekben mérhető overheaddé válnak.

### 3. A popup-snapshot feldolgozás túl drága a gyors módhoz képest

Bár van `fast` mód, a menünyitás során továbbra is többször történik teljes popup snapshot gyűjtés és diffelés. A logban látható 14 → 82 elemű snapshot-diff és a sok deduplikációs sor arra utal, hogy a feldolgozás jelentős része a teljes UI-fa újraolvasása, nem maga a tényleges kattintás.

### 4. A project-open recovery túl sok időt tölt pollinggal

A recovery ciklus 15 másodperces timeouttal és 0.25 másodperces pollinggal fut. A napló alapján egyszer sikeresnek jelzi a recovery-t akkor is, amikor a projekt ténylegesen nem nyílt meg, később pedig új modal detektálás és zárási kísérlet következik. Ez lassít és félrevezető állapotot is eredményez.

## Javasolt gyorsítások és fejlesztések

### A. Első prioritás: a top menu kattintás stabilizálása

1. A tiltott bal felső zóna ellenőrzése előtt számoljatok új célpontot a menüsáv téglalapján belül.
2. Ha a menüelem közepe tiltott zónába esik, fallbackként ne exception legyen, hanem eltolás jobbra/lefelé egy biztonságos offsettel.
3. A `Rendszer` menüre külön regression teszt kell olyan geometriával, ahol a főablak bal felső sarka negatív koordinátás.

### B. Második prioritás: fix sleep-ek cseréje esemény- vagy állapotvezérelt várakozásra

1. A `prepare_main_window_for_menu_interaction()` végén a fix `sleep(0.3)` helyett foreground/geometry stabilitás ellenőrzés fusson rövid timeouttal.
2. A `click_top_menu_item()` két fél popup-delay-e helyett olyan wait függvény kell, amely addig pollingol, amíg új popup jelenik meg vagy el nem telik egy rövid timeout.
3. A `restore_clean_menu_baseline()` két ESC + delay ciklusa helyett addig kell ismételni, amíg popup eltűnik, de legfeljebb kis számú próbálkozással.

### C. Harmadik prioritás: snapshot- és diffköltség csökkentése

1. `fast` módban a teljes popup snapshot helyett először csak a várt top menu popup régióját érdemes olvasni.
2. A deduplikációs logolást debug módra kell visszavenni; most a nagy menük esetén túl sok I/O-t generál.
3. A már azonosított `popup_state.current_menu_path` + `popup_rows` cache agresszívebben újrahasznosítható, hogy ugyanazt a szülő popupot ne kelljen teljesen újraolvasni.

### D. Negyedik prioritás: recovery logika tisztítása

1. Különítsétek el a "dialog found but wrong item clicked" és a "project actually opened" állapotokat.
2. A recovery csak akkor fusson 15 másodpercig, ha a főablak ténylegesen disabled; egyébként korai kilépés kell.
3. A recovery eredményéhez érdemes explicit `modal_pending`, `close_attempted`, `main_window_reenabled` mezőket menteni, mert jelenleg a napló és a JSON nem ad könnyen feldolgozható teljesítményképet.

### E. Mérhetőség fejlesztése

1. A run recorder töltse ki a `duration_seconds` mezőt minden futás végén.
2. Kerüljenek be fázisidők: top menu open, popup capture, dialog recovery, state snapshot.
3. Érdemes egy egyszerű összesítőt generálni a log végére a leglassabb 10 műveletről.

## Konkrét megvalósítási terv

### Quick win (1-2 óra)
- Safe fallback a tiltott zónás top-menu kattintásra.
- `duration_seconds` kitöltése a run metadata JSON-ban.
- INFO szintű popup-dedupe logok visszavétele DEBUG-ra.

### Közepes munka (0.5-1 nap)
- Fix sleep-ek kiváltása rövid polling alapú wait helperrel.
- Baseline restore rövidebb, állapotvezérelt ciklusra átírása.
- Recovery korai kilépési feltételeinek tisztázása.

### Nagyobb fejlesztés (1-2 nap)
- Célzott popup-inspection a teljes desktop-scan helyett.
- Inkremens popup-state cache a rekurzív menübejárás során.
- Strukturált performance telemetry a runtime mapperhez.

## Várt eredmény

Ha csak a quick win + közepes lépések készülnek el, akkor reálisan:
- csökken a hibás újranyitások száma,
- a teljes futásidő több percet is rövidülhet,
- és a `project_open` utáni menübejárás megbízhatósága jelentősen javulhat.
