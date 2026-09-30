# WinWatt mapping migrációs feladatok

Frissítve: 2026-09-30.

## Cél

A WinWatt mapping olyan elkülönített környezetbe kerüljön, ahol a hosszú helyi
Python-futás nem veszi el a felhasználó egerét vagy billentyűzetfókuszát, közben
megmarad a verzióhoz kötött bizonyíték, a checkpointos folytatás és a
hardverkulcsos licenc működése.

## M1 – Biztonságos kiindulási csomag

- [ ] A jelenlegi WinWatt EXE, modulok, verzióprofil és SHA-256 lenyomat mentése.
- [ ] A 32 bites Python-környezet csomaglistájának és indítási parancsainak mentése.
- [ ] A mapping checkpointok, tool-regiszter, skillek és kurált knowledge külön
  biztonsági másolata.
- [ ] A projektmintákból csak tiszta, hash-elt sandboxpéldányok átvitele.
- [ ] A korábban kompromittálódott laptopot nem szabad migrációs forrásként vagy
  célként használni ellenőrzött újratelepítés nélkül.

## M2 – Elkülönítési mód kiválasztása

- [ ] Elsődleges jelölt: Windows virtuális gép saját képernyővel és USB-
  hardverkulcs átadással.
- [ ] Tartalék: külön, tisztán telepített fizikai Windows-gép.
- [ ] Ugyanazon Windows-munkamenet második virtuális asztala, második monitorja
  vagy második egere nem tekinthető fókusz-elkülönítésnek.
- [ ] A választást dokumentálni kell a Windows-kiadás, hypervisor, WinWatt-
  verzió, licencdriver és USB-kulcs típusa alapján.

## M3 – VM és USB-hardverkulcs próba

- [ ] Tiszta, hálózatilag korlátozott Windows VM létrehozása.
- [ ] WinWatt és a gyártói hardverkulcs-driver telepítése ellenőrzött forrásból.
- [ ] Az USB-kulcs kizárólagos VM-hozzárendelésének próbája; a gazdagép és a VM
  ne használja egyszerre.
- [ ] WinWatt kézi indítás, licencfelismerés, projektmegnyitás és számítás próba.
- [ ] A 32 bites Python és az Auto-WinWatt telepítése rögzített verziókból.
- [ ] Mentés–bezárás–újranyitás roundtrip és forrás-hash ellenőrzés.
- [ ] VM-pillanatkép készítése a működő, tiszta alapállapotról.

## M4 – Kooperatív mapping mód a jelenlegi gépre

- [ ] Windows `GetLastInputInfo` alapján felhasználói aktivitás érzékelése.
- [ ] Egér- vagy billentyűhasználat esetén új művelet indításának tiltása.
- [ ] Az aktuális elemi lépés után checkpoint, majd automatikus szünet.
- [ ] Folytatás csak beállítható, például 90 másodperces üresjárat után.
- [ ] Minden folytatás előtt WinWatt PID-, ablak-, verzió-, projekt- és hash-
  ellenőrzés.
- [ ] Képernyőzárás, felhasználóváltás, RDP-kapcsolat vagy fókuszhiba esetén
  várakozó állapot; automatikus kattintás tilos.
- [ ] Tálca- vagy konzolállapot: fut, emberi aktivitás miatt vár, WinWatt miatt
  vár, hibával megállt.
- [ ] A funkció külön kapcsolóval induljon, a jelenlegi dedikált mapping mód
  viselkedése maradjon reprodukálható.

## M5 – Migrációs elfogadási próba

- [ ] Ugyanazon rögzített sandboxból induló rövid kampány a régi és az új
  környezetben.
- [ ] Azonos verzióprofil és változatlan forrás-SHA-256.
- [ ] Legalább egy ismert épület-, zóna- és rendszerútvonal sikeres visszajátszása.
- [ ] Mentés–újranyitás után az ismert mezők visszaolvasása.
- [ ] Checkpointból megszakítás nélküli folytatás.
- [ ] Kooperatív módban kézi gépelés és egérhasználat alatt nulla automatikus
  inputesemény.
- [ ] A régi környezet leállítása csak az elfogadási jegyzőkönyv után.

## M6 – Üzemeltetés és visszaállás

- [ ] Egyetlen aktív WinWatt UI-mapper engedélyezése gépenként és projektenként.
- [ ] Napi checkpoint- és evidence-mentés a gazdagépre.
- [ ] USB-kulcs leválasztási és visszaadási eljárás dokumentálása.
- [ ] VM-hiba esetére visszaállás a tiszta pillanatképre; kampány folytatása az
  utolsó ellenőrzött checkpointból.
- [ ] A régi és új környezet eredményei külön provenance-azonosítót kapjanak.

## M7 – Időkorlát nélküli helyi kampány

- [x] Külön `-UntilComplete` mód a fő épületmappinghez.
- [x] Dupla kattintásos `start_winwatt_mapping_unlimited.cmd` folytató.
- [x] AI/LLM nélküli végrehajtás, heartbeat és atomikus checkpoint megtartása.
- [x] Lezárt asztalnál határozatlan várakozás a próbálkozások elfogyasztása nélkül.
- [ ] Kooperatív felhasználói aktivitásfigyelés elkészítése az M4 szerint.
- [ ] A régi szerkezetmapping belső dátumhatárának opcionálissá tétele.

## Javasolt sorrend

1. M1 biztonsági csomag.
2. M4 kooperatív mód, mert hardverbeszerzés nélkül is használható.
3. M3 VM és hardverkulcs próba.
4. M5 összehasonlító elfogadási próba.
5. M6 üzemszerű átállás.

Az átállás akkor tekinthető késznek, ha a felhasználó a gazdagépen zavartalanul
dolgozhat, miközben a mapping külön interaktív környezetben fut, vagy a
kooperatív mód minden emberi aktivitás alatt bizonyítottan szünetel.
