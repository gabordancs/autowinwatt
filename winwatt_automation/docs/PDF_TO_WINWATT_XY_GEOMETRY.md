# PDF-to-WinWatt: X x Y falgeometria

## Kötelező adatmodell

Minden függőleges hőhatároló (`külső fal`, `lábazati fal`) három, egymással konzisztens adatot kap:

| Mező | Jelentés | Forrás |
|---|---|---|
| `x_m` | falhossz méterben | tervi méretlánc |
| `y_m` | falmagasság méterben | helyiségmagasság / metszet |
| `area_m2` | `x_m * y_m` | determinisztikus számítás |

A natív WinWatt XML-ben ugyanez: `<x> = x_m`, `<y> = y_m`, `<A> = area_m2`.

## Feldolgozási lánc

1. A helyi PyMuPDF-feldolgozó kiolvassa a vektoros méretvonalat, a két ferde végjelet, a méretszöveget és a segédvonalakat.
2. A helyiségkontúr és a külső épületkontúr közös éle azonosítja a falszakaszt.
3. A méretlánc csak akkor rendelhető a falszakaszhoz, ha a segédvonalak a fal két végpontjára vetülnek.
4. A helyiség rögzített belmagassága adja `y_m` értékét; a program előállítja `area_m2 = x_m * y_m` értéket.
5. A natív XML-fordító ellenőrzi az azonosságot. `project.require_wall_xy=true` mellett bármely hiányzó vagy inkonzisztens falblokkolja a WWP importot.
6. A visszaellenőrzés összehasonlítja a forrás `x_m`, `y_m`, `area_m2` értékeit a WinWattból visszaexportált `<x>`, `<y>`, `<A>` mezőkkel.

## Átmeneti állapot

A régi, összevont falrekordok `X=felület`, `Y=1` formátuma csak örökölt reprezentáció. Szabályos, végleges WWP-ben nem megengedett, ha a projekt `require_wall_xy` jelzője be van kapcsolva.

## Példa: B10a

| Falszakasz | X | Y | A |
|---|---:|---:|---:|
| felső | 1,92 m | 2,84 m | 5,45 m² |
| jobb oldali | 4,02 m | 2,84 m | 11,42 m² |
