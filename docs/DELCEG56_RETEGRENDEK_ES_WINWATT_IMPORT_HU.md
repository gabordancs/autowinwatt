# Délceg utca 56 rétegrendek és WinWatt import

## Források

- É-03 Tervezett metszetek, 2026. július 30.
- É-02, É-02B és É-02C tervezett alaprajzok.
- `Delceg_56_helyiseglista.xlsx`.

## Kinyert rétegrendek

| Kód | Megnevezés | Forrás szerinti fő rétegek | Állapot |
| --- | --- | --- | --- |
| R1 | Meglévő tető | kerámia cserép, tetőléc, páraáteresztő fólia, ellenléc, 10/15 cm szarufa | részleges, nem hőhatároló padlástető |
| R2 | Padlásfödém | 2 cm burkolat, 6 cm estrich, PE fólia, 4 cm lépésálló hőszigetelés, meglévő födém | meglévő födém anyaga hiányzik |
| R3 | Talajon fekvő padló | meglévő rétegrend | nincs rétegadat |
| R4 | Homlokzati fal | meglévő rétegrend | nincs rétegadat |
| R5 | Homlokzati fal | külső vakolat, 20 cm AT-H80 hőszigetelés, légzáró vakolat, 30 cm Porotherm falazat, belső vakolat | a terv felirata és a megnevezett falazat vastagsága ellentmondásos; ellenőrzendő |
| R6 | Tetőterasz | 2 cm WPC, 3 cm bazaltzúzalék, elválasztó réteg, 2 réteg bitumenes vízszigetelés, 15 cm PUR, 2–5 cm lejtésbeton, meglévő födém | meglévő födém hiányos |
| R7 | Padlásfödém | páraáteresztő fólia, 25 cm kőzetgyapot, párazáró fólia, 2 réteg tűzgátló gipszkarton, fogópár | rétegvastagság részben hiányos |
| R8 | Közbenső födém | 2 cm burkolat, 6 cm estrich, PE fólia, 4 cm lépésálló hőszigetelés, 20 cm vasbeton | nem külső határoló |
| R9 | Közbenső födém | 2 cm burkolat, 6 cm estrich, PE fólia, 12 cm lépésálló hőszigetelés, 20 cm vasbeton | nem külső határoló |
| R10 | Közbenső fal | vakolat, 20 cm Porotherm falazat, dilatáció, meglévő fal, vakolat | meglévő fal hiányos |
| R11–R12 | Nincs részletezve | a kiadott metszeten nem található kiolvasható rétegrend | hiány |
| R13 | Terasz | 2 cm fagyálló burkolat, lejtésbeton, 2 réteg kenhető vízszigetelés, 15 cm vasalt lemez, 20 cm kavics | lejtésbeton vastagsága feltételezett |
| R1B | Új tető | kerámia cserép, 3/5 cm tetőléc, 5/7,5 cm ellenléc, páraáteresztő fólia, 25 cm PIR, párazáró fólia, 2,5 cm deszka, 10/15 cm szarufa | fóliák tömeg nélküli rétegként kezelendők |
| R14 | Talajon fekvő pincepadló | 5 cm védőbeton, 2 réteg bitumenes vízszigetelés, 25 cm vasbeton lemezalap, 25 cm kavics | belső burkolat nincs megadva |
| R15 | Pincefal | talaj/terasz alaptest, 20 cm XPS, 2 réteg bitumenes lemez, kellősítés, légzáró vakolat, 30 cm zsalukő, belső felületképzés | ellenőrzendő rétegsorrend |
| R16 | Pincefal | meglévő alaptest, felületkiegyenlítés, kellősítés, 2 réteg bitumenes lemez, 25 cm zsalukő, belső vakolat | külső hőszigetelés nincs megadva |

## Importmodell

A gépi bemenet a `data/delceg56/delceg56_winwatt_model.json` fájlban található. A 28 helyiség alapterülete változtatás nélkül került át. A belmagasság munkafeltételezés: földszint 2,80 m, tetőtér 2,60 m átlagos, pince 2,32 m.

Az anyagok hőtechnikai tulajdonságai előzetes értékek. A WinWatt anyagkatalógusával való tételes egyeztetés, a határoló felületek X/Y/A geometriája, a nyílászárók és a fűtött–fűtetlen térhatárok még mérnöki felülvizsgálatot igényelnek.
