# WinWatt → teljes tanúsítás: roadmap

Frissítve: 2026-09-29. A tényleges helyi eredményeket mutatja, nem becsült készültségi százalékot.

## Hol tartunk?

**Az alapinfrastruktúra és az épületablak első leltára elkészült.**
A teljes tanúsítási automatizmus még nincs kész. A kilenc számítási mód
fülváltása és az első mezőmentési kör már ellenőrzött; a 2023-as mód
gépészeti rendszerablakainak és további mezőinek feltárása következik.

| Szakasz | Állapot | Eredmény / továbblépési feltétel |
| --- | --- | --- |
| 1. Korábbi tudás összegyűjtése | Részben kész | 1922 fájlhivatkozás, 1564 külön tartalom közös jegyzékben; 38 történeti forrás hiányzik, 3 JSON hibás. A nyers források teljes helyreállítása nincs igazolva. |
| 2. Helyi futtatókörnyezet és verzióazonosítás | Kész az alap | Külön 32 bites Python, EXE/verzió/erőforrás-lenyomat, elkülönített kampány és sandbox. Nem minden régi belépési pont kapott kötelező verzióvédelmet. |
| 3. Épületablak alapfeltérképezése | Kész az első leltár | Javított, név szerinti épületmegnyitás; 11 elérhető fül, vezérlők, választóértékek és képek; natív mentés és újraindítás utáni megnyitás. |
| 4. Feltételes energetikai ágak | Részben kész | Mind a 9 számítási mód tesztelve: 8 régi mód → 8 fül, 2023-as mód → 11 fül. **Következő: gépészeti gyerekdialógusok és zónakapcsolatok.** |
| 5. Mezőkezelés bizonyítása | Első mező igazolt | Tájolás 0 → 42° megmarad teljes újraindítás után. 42,5° → 42° eltérés dokumentálva; további mezők és energetikai eredmények hátravannak. |
| 6. Teljes helyi referencia-tanúsítás | Hátravan | Ellenőrzött épületadatok, rendszerek, számítás, felújítási javaslatok, WWP/XML/PDF/fotócsomag és validáció. |
| 7. WebWatt összekötése | Meglévő alap, bővítés kell | A magyar-mentor/WebWatt előfeldolgozó workerét a bizonyított helyi WinWatt-lépésekkel összekötni; újraindítható, ismételt futáskor nem duplikáló feladatlánc. |
| 8. Fogadóoldali ellenőrzés és véglegesítés | Hátravan | Aktuális célformátum ellenőrzése, valós fogadóoldali visszajelzés, tanúsítói felülvizsgálat és végleges dokumentumcsomag. |

## A következő konkrét munkacsomag

**Cél: a 2023-as mód épülettechnikai rendszereinek létrehozása és zónához rendelése.**

1. A mentett sandboxot megnyitni a meglévő 32 bites Python-eszközökkel,
   a verzióprofil és a projektazonosság ellenőrzésével.
2. A 2023-as számítási módot és az Épülettechnikai rendszerek lapot aktiválni.
3. A fűtés, HMV, hűtés és szellőzés létrehozó/szerkesztő ablakait egyenként
   felvenni; az elérhető rendszertípusokat és függő mezőket helyben kiolvasni.
4. Egy minimális fűtési rendszer és tesztzóna kapcsolatát létrehozni,
   a rendszerazonosítót és a hozzárendelést rögzíteni.
5. Egy rendszerparaméteren végrehajtani a teljes
   módosítás–mentés–újranyitás–visszaolvasás próbát.
6. A futásból függőségi táblát és rövid hibajegyzéket készíteni; a sandbox
   kiinduló állapotát megőrizni, minden próba eredményét külön naplózni.

**A munkacsomag akkor kész**, ha a vizsgált rendszerablakok elérési útja
reprodukálható, és a tesztrendszer paramétere és zónakapcsolata a teljes
újranyitás után igazoltan megmarad. Ismeretlen feltétel külön blokkoló tétel.

## Mi biztos, és mi nem?

- A telepített program Névjegye: WinWatt gólya 9.60 (2026. 8. 5.);
  EPBD, EPBD-2023 és Agros2D modul. A bináris a korábban rögzítettel azonos;
  újabb telepített kiadás nincs bizonyítva.
- A 11 fül felvétele alapleltár: két önálló lapcsoport van, kombinációik és
  feltételes ágai még nincsenek teljesen bejárva.
- A mentés és az épület újramegnyitása működik; egész fokértékű tájolás
  tartóssága igazolt. Gépészeti mező és teljes számítási eredmény még nincs igazolva.
- Az első implementáció 20 célzott tesztje sikeres. Ez nem teljes tanúsítási E2E-teszt.
- A korábbi tudás hivatkozásos egyesítése kész; nem lett minden régi gráfból
  egyetlen, az aktuális kiadásra ellenőrzött végrehajtási gráf.

## Költségtakarékos végrehajtás

A rutinbejárást, választólisták olvasását, diffeket, mentési próbákat és
ellenőrzéseket helyi Python végzi, AI-hívás nélkül. Az AI a kódjavításokat,
az ismeretlen eltérések értelmezését és az összesítést kezeli. Véges feladatcsomagok,
mentett állapotok és rövid összefoglalók csökkentik az ismételt bejárást és a kredithasználatot.

## Kapcsolódó anyagok

- [Részletes végrehajtási terv](uj_winwatt_teljes_tanusitas_terv_hu.md)
- [Első megvalósítás eredményei](winwatt_mapping_megvalositas_20260929.md)
- [Korábbi bizonyítékok közös jegyzéke](mapping_evidence_union.json)
- [Rögzített helyi verzióprofil](winwatt_local_profile_20260929.json)
- [Kilenc számítási mód és tájoláspróba](winwatt_energetikai_agak_20260929.md)
