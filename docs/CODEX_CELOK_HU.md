# Codex céljegyzék

## Aktív cél

### Tanúsítási tudás integrálása a Codexbe

A `M:\Repositories\autowinwatt\energetika` szakmai és tanúsítási
tudásanyagának integrálása a Codex helyi működésébe.

A cél eredménye:

- forráshivatkozásos, verziózott tanúsítási tudáscsomag;
- a `winwatt-certification-orchestrator` skill tudásoldali bővítése;
- világos forrásprioritás és tanúsítási munkafolyamat;
- az AI, a determinisztikus kód és az emberi döntés felelősségi határainak
  dokumentálása;
- olyan ellenőrzési példák, amelyek bizonyítják, hogy a Codex helyesen keresi
  vissza és alkalmazza a tanúsítási tudást.

### Kifejezett scope-határ

Ez a cél nem tartalmaz:

- tanúsítási projekt végrehajtását;
- WinWatt UI-műveletet vagy számításfuttatást;
- WWP vagy natív WinWatt projekt módosítását;
- beadást vagy külső rendszer módosítását;
- végleges tanúsítási XML előállítását;
- geometriai modell tanítását vagy tervcsomag feldolgozását.

Az aktív cél részletes fejlesztési alapja:
`docs/CODEX_TANUSITASI_TUDAS_ES_AUTOMATIZALAS_FEJLESZTESI_TERV_HU.md`.

## Archivált cél

### SR8 teljes végrehajtási és tanítási rendszer

Archiválás dátuma: 2026-10-11.

Korábbi cél:

> Az SR8 teljes PDF tervcsomagja, a kanonikus natív WinWatt épületmodell és a
> kész tanúsítási XML-ek alapján valósíts meg egy stabil, helyben futó,
> auditálható tanítási és feldolgozási rendszert, amely új tervcsomagból
> önállóan azonosítja a lakásokat és helyiségeket, kiválasztja az
> energetikailag releváns külső vagy fűtetlen térrel határos falakat,
> hozzárendeli a nyílászárókat és méreteket, létrehozza és WinWattban
> újraszámolja a modellt, végleges tanúsítási XML-t állít elő, majd mezőnként
> és energetikai eredmény szerint összeveti a referencia-tanúsítvánnyal.
> Használj train/validation/test szétválasztást, XML-alapú gyenge felügyeletet,
> magas bizonyosságú automatikus tanítópárokat és egyszerű jó/rossz vizuális
> ellenőrzést; dokumentáld külön, mi AI és mi determinisztikus kód. A cél csak
> akkor teljes, ha a folyamat új PDF-en lokálisan futtatható, reprodukálható és
> mérhető hibájú.

Archiválási ok: a felhasználó a teljes végrehajtás helyett először kizárólag a
tanúsítási tudás Codexbe integrálását kívánja elvégezni.

Az archiválás nem állítja, hogy a korábbi cél teljesült. A későbbiekben külön
felhasználói döntéssel újraindítható.
