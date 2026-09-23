# Délceg utca 56 - kétépületes WinWatt-előkészítés

## A `.wwp` állapota

`Delceg_56_meglevo_es_bovitmeny_ELOZETES.wwp` önálló Délceg-projekt, nem
tartalmaz Kerepesi-adatot. A programban két épület szerepel:

| Épület | Helyiségek | Forrás |
|---|---:|---|
| A - Meglévő épület (2018 tanúsított állapot) | 1 aggregált helyiség, 68,94 m² | 2018-as tanúsítvány |
| B - Tervezett bővítmény és átépítés (2026 terv) | 18 helyiség, 314,58 m² | É02, É02B és É02C tervlapok |

Az állományt WinWattba történő import, mentés, bezárás és újbóli megnyitás
után XML-visszaolvasással ellenőriztem: 2 épület és 19 helyiség maradt meg.

## A metszetlapból azonosított rétegrendek

Az É03 tervlap teljes rétegrendjegyzékét helyben olvastam ki. Ezek a
megnevezések és a rétegsorrend forrásadatok; a következő WinWatt-körben
anyagkatalógus-azonosítóval kell őket összerendelni.

| Kód | Rendeltetés | Hőtechnikailag lényeges, terven megadott rétegek |
|---|---|---|
| R1 | meglévő tető | cserép, lécezés, páraáteresztő fólia, 10/15 cm szarufa; kiszellőztetett padlástér |
| R2 | meglévő padlásfödém | 2 cm burkolat, 6 cm esztrich, PE fólia, 4 cm lépésálló hőszigetelés, meglévő födém |
| R3 | meglévő talajon fekvő padló | meglévő rétegrend |
| R4 | meglévő homlokzati fal | meglévő rétegrend |
| R5 | új homlokzati fal | 20 cm AUSTROTHERM AT-H80, légzáró vakolat, 30 cm Porotherm 38, belső vakolat |
| R6 | tetőterasz | 15 cm PUR hőszigetelés, 2 réteg bitumenes vízszigetelés, lejtésadó beton, meglévő födém |
| R7 | padlás / ferde tető | 25 cm kőzetgyapot, párazáró és páraáteresztő fólia, 2 réteg tűzgátló gipszkarton |
| R8 | közbenső födém | 4 cm lépésálló hőszigetelés, 20 cm monolit vasbeton |
| R9 | közbenső födém | 12 cm lépésálló hőszigetelés, 20 cm monolit vasbeton |
| R10 | csatlakozó belső fal | 20 cm Porotherm 38, dilatációs hézag, meglévő falazat |
| R13 | terasz a talajon | 15 cm vasalt lemez, 20 cm tömörített kavicságyazat |
| R1B | új tetőszerkezet | 25 cm PIR hőszigetelés, lég- és párazáró fólia, 2,5 cm deszkaburkolat, 10/15 cm fa szarufa |
| R14 | új talajon fekvő padló | 5 cm védőbeton, 2 réteg bitumenes vízszigetelés, 25 cm monolit lemezalap, 25 cm kavicsfeltöltés |
| R15 | új pincefal | 20 cm XPS, 2 réteg Villas OV4F/K, 30 cm zsalukő, vakolat |
| R16 | meglévő pincefal | 2 réteg Villas OV4F/K, 25 cm zsalukő, vakolat |

## Tudatosan még nem véglegesített elemek

- Az R1B, R5, R6, R7, R14 és R15 valódi, többrétegű WinWatt-szerkezetté
  alakítható; a rétegvastagságok tervben adottak.
- Az Anyagok-katalógus tényleges rekordjait ezen a futáson nem lehetett
  elérni: a Windows-alkalmazásvezérlő csak böngészőt adott vissza, natív
  WinWatt-ablakot nem. Emiatt nem írtam be feltételezett katalógusazonosítót
  és nem hoztam létre helyettesítő anyagot.
- Nem töltöttem ki becsült külső felületeket, tájolásokat, nyílászárókat vagy
  gépészetet. Ezek nélkül az állomány szerkeszthető előkészítés, nem
  végleges energetikai számítás vagy tanúsítvány.

## Következő bizonyítható lépés

Amikor a helyi WinWatt Anyagok ablaka hozzáférhető, az R5-ben név és
hővezetési tényező szerint az AT-H80 és Porotherm 38 rekordját kell elsőként
kiválasztani. Ugyanezzel a módszerrel következhet a PIR, kőzetgyapot, XPS,
vasbeton, zsalukő és a fóliarétegek. Csak az ellenőrzött, megfelelő rekord
hiányában indokolt új anyag létrehozása.
