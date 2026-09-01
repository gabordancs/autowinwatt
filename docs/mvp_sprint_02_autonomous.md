# AutoWinWatt MVP – 2. önálló sprint

Kiindulópont: az első vertical slice igazoltan létrehoz két név szerinti
helyiséget, `Mentés másként` útvonalon perzisztálja a sandbox projektet, majd
újranyitás után ellenőrzi a neveket.

## Sprintcél

A `prepare-rooms` workflow legyen mezőszintű evidence-re kész, jól
diagnosztizálható és regressziótesztelhető. Csak olyan mező kap tényleges író
útvonalat, amelyet a runtime map és egy friss sandboxos round-trip igazol.

## Vállalható feladatok

1. **Helyiség Általános adatok célzott felmérése**
   - `TRoomModifyForm` állapotban rögzíteni az Edit/ComboBox/CheckBox
     vezérlőket, címkéiket, olvasható értékeiket és a hozzájuk tartozó tabot.
   - Külön evidence minden `area_m2`, `height_m`, `temperature_c` jelölthöz.
   - Nem igazolt mező nem kap automatikus kitöltést.

2. **Capability registry**
   - `data/capabilities/room_capabilities.json`.
   - Mezőnként: `ui_read`, `ui_write`, `roundtrip_verified`, `preferred` és
     evidence-hivatkozás.

3. **Verification hardening**
   - A név mellett a bizonyított mezők expected/actual összevetése.
   - Sikertelenségkor aktuális ablak-state, screenshot, kísérelt művelet és
     projektútvonal rögzítése az `OperationResult.evidence` listában.

4. **CLI és E2E regresszió**
   - A riport tartalmazza a tényleges `prepared.wwp` útvonalát és annak SHA-256
     hash-ét.
   - Elkülönített, explicit `--e2e` jelzésű WinWatt-integrációs teszt, amely
     csak erre alkalmas Windows környezetben fut.
   - A normál unit tesztek nem indítanak WinWattot.

5. **Dokumentáció**
   - Az audit frissítése a mezőcapability-k tényleges állapotával.
   - A futtatható JSON-példa és a hibaelhárítási útmutató frissítése.

## Kész definíciója

`prepare-rooms` két helyiség esetén sandboxot készít, perzisztálja a
`prepared.wwp` fájlt, újranyitja, és név szerint ellenőrzi őket. Ha egy
mezőcapability igazolt, annak értékét is expected/actual alapon ellenőrzi;
ha nem igazolt, figyelmeztetésként jelenik meg, nem hamis siker eredményeként.

## Tudatosan későbbre hagyva

- natív XML round-trip és hibrid XML/UI routing;
- CSV/Excel parser és preview;
- Streamlit;
- LLM provider, OpenAI integráció és MCP.
