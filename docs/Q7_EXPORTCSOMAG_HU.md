# Q7 – teljes exportcsomag

A Q7 célja a `TANUSITASI_MUNKASOR_HU.md` szerint a WWP, natív XML, számítási PDF,
tanúsítási XML és fotócsomag ellenőrzött összeállítása.

A `winwatt_automation.certificates.export_package` modul a WinWatt nélküli,
determinisztikus ellenőrzési réteget adja. Nem állítja elő a WinWatt-artefaktumokat,
és nem tekinti a natív XML-t a WWP teljes reprezentációjának.

## Kötelező artefaktumok

- `wwp`: pontosan egy `.wwp`
- `native_xml`: pontosan egy natív export `.xml`
- `calculation_pdf`: pontosan egy `.pdf`
- `certificate_xml`: pontosan egy tanúsítási `.xml`
- `photos`: legalább egy `.jpg`, `.jpeg`, `.png` vagy `.webp`

A két XML szerepét a hívónak explicit kell megadnia. Ez szándékos: a fájlnév vagy a
kiterjesztés alapján nem találgatjuk, melyik XML milyen szemantikájú.

## Ellenőrzések

A manifest csak akkor készül el, ha:

1. minden kötelező artefaktum jelen van;
2. minden fájl az exportkönyvtáron belül található;
3. egyik fájl sem üres;
4. a kiterjesztések megfelelnek a szerepüknek;
5. mindkét XML jól formált;
6. minden fájl SHA-256 lenyomatot kap.

A manifestben külön tárolható a kiinduló projekt SHA-256 lenyomata és tetszőleges
verzió-/evidence-metaadat. A fájlok rendezve kerülnek a manifestbe, hogy a csomag
könnyen diffelhető legyen.

## Fontos korlát

A `checks.xml_well_formed = true` kizárólag XML-szintaktikai bizonyíték. Nem
bizonyítja, hogy a WinWatt az XML minden adatát importálja, vagy hogy például a
fotókapcsolatok működnek. Az ilyen állapotokra továbbra is WWP/UI roundtrip
evidence szükséges.

## Következő helyi lépés

Amikor a WinWatt-gép elérhető, a Q7 exportfolyamat az öt artefaktumot egy közös
könyvtárba teszi. Ezután a validator manifestet készít; a WinWatt-specifikus
szemantikai ellenőrzések (újranyitás, fotókapcsolatok, számítási eredmény,
PDF-tartalom) külön evidence-ként kapcsolhatók hozzá.
