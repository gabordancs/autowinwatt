# Délceg utca 56 – WinWatt modellezési napló

## Cél és eredmény

Az épületet két WinWatt-épületként rögzítettem: az eredeti tanúsítványból megmaradó A01 meglévő zóna, valamint a bővítés B01–B18 helyiségei. A végleges projektben 29 helyiség, 12 szerkezettípus és 78 energetikailag releváns határoló van.

Végleges fájl: `Delceg_56_minden_helyiseg_hatarolokkal.wwp`.

## Kiinduló adatok

- É-02 földszinti, É-02B tetőtéri, É-02C pinceszinti alaprajz;
- É-03 metszetek;
- a 2018-as tanúsítvány a meglévő A01 zónához;
- az AutoWinWatt XML-mapping és a helyi WinWatt telepítés viselkedése.

## Munkamenet

1. Helyben kiolvastam a tervlapok szövegét és a helyiségterületeket, majd a terv szerinti új helyiségeket B01–B18 kóddal egységesítettem.
2. A helyiségekhez alsó és felső hőhatárolót rendeltem. Külső/pincefal csak azokhoz került, amelyek a rajz külső kontúrját érintik; a belső válaszfalakat nem rögzítettem hamisan külső hőhatárolóként.
3. A szerkezeteket az AutoWinWatt által feltárt WinWatt XML-mezőkbe generáltam. Az A01 régi szerkezeteit a meglévő tanúsítvány értékeihez kötöttem; az új részekhez R1B, R5, R6, R7, R14, R15 és R16 kódú szerkezeteket használtam.
4. Helyi, 32 bites Python-folyamat indított üres WinWatt projektet, importálta az XML-t, mentette, bezárta, újraindította, majd natív XML-be visszaexportálta.
5. A visszaexport alapján összevetettem a generált és a WinWatt által ténylegesen megőrzött modellt.

Az automatikus feldolgozás és a WinWatt-vezérlés helyben futott; ehhez a projekthez nem történt külső LLM-hívás.

## Visszaellenőrzés

| Ellenőrzés | Eredmény |
|---|---:|
| Épületek | 2 |
| Zónák / helyiségek | 29 / 29 |
| Szerkezettípusok | 12 |
| Hőhatárolók | 78 |
| Fűtött alapterület | 383,52 m² |
| Területeltérés | 0,00 m² |
| Térfogateltérés | 0,0094 m³ (0,000893%) |
| Transzmissziós eltérés | 0,00512 W/K (0,002405%) |

## Jelölések és szerkezeti logika

A vizuális ellenőrző PDF-ben a kék címke első sora a helyiségkódot, a WinWattba rögzített alapterületet (`A`) és belmagasságot (`h`) mutatja. A további sorok szerkezetenként a WinWatt natív XML-be rögzített `X×Y` értéket adják meg: `X` a szerkezet felülete m²-ben, `Y` a darabszám (ebben a modellben 1,00). A lejtős tetőnél ezért az R7 felülete eltérhet a helyiség vízszintes alapterületétől.

- R14: talajon fekvő padló
- R1B: új tető
- R7: ferde tető
- R5: új külső fal
- R6: födém / terasz feletti elválasztás
- R15, R16: pincefal

A01 a 2018-as tanúsítvány egyetlen aggregált meglévő zónája. Részletes felmérési alaprajz hiányában ezt nem bontottam fel mesterségesen kisebb helyiségekre.

## Nyitott szakmai ellenőrzési pontok

Az R1B/R5/R6/R7/R14/R15/R16 szerkezetek jelenleg előzetes U-értékes energetikai szerkezetek. A WinWatt anyagkatalógusával összevezetett, tényleges anyagréteges felépítés és a nyílászáró-termékadatok még külön ellenőrzést igényelnek. A mostani rajzi címkék azt mutatják, mi került ténylegesen a WWP-be, nem helyettesítik ezt a szakértői felülvizsgálatot.

## B10a korrekció (2026-09-14)

A korábbi modell tévesen egyetlen, 8,00 m²-es R5 külső falat rendelt a B10a gardróbhoz. Az É-02 tervi méretlánca alapján sarokhelyiség: `1,92 × 4,02 m` méretű, ezért két eltérő tájolású R5 falat kapott:

- felső tervi falszakasz: `1,92 × 2,84 = 5,45 m²`, azimut 36°;
- jobb oldali tervi falszakasz: `4,02 × 2,84 = 11,42 m²`, azimut 126°.

Ezeknél a WinWatt import XML-ben `X` a tervi falhossz, `Y` a helyiség belmagassága, `A` pedig az `X × Y` felület. A korábbi, nem részletezett falaknál a régi `X=felület; Y=1` átmeneti reprezentáció látható; ezeket a falszakasz-audit feloldásáig nem szabad véglegesnek tekinteni.

Ez a modellben 79 határolót eredményez. A korábbi 8,00 m²-es összesített falat a generátor eltávolítja.
