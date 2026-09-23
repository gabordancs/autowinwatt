# Energetikai tanúsítás - end-to-end folyamatváz

> Cél: a WebWatt/AutoWinWatt rendszerben a megkereséstől a hiteles tanúsítvány átadásán és a számlázáson át a lezárásig követhető, ellenőrizhető munkafolyamat legyen. Ez folyamat- és rendszerterv, nem helyettesíti a tanúsító mérnök szakmai felelősségét vagy a kiállítás napján végzendő jogszabály-ellenőrzést.

## 1. Jogszabályi és szakmai keret

| Forrás | Szerep a folyamatban |
|---|---|
| 176/2008. (VI. 30.) Korm. rendelet | Meghatározza, mikor kell tanúsítani, a tanúsítvány/alátámasztó munkarész tartalmát és a besorolás keretét. A kiállítási feladat jogosult tanúsítóé. |
| 9/2023. (V. 25.) ÉKM rendelet és függelékei | A számítási módszer, referenciaépület, követelmények és műszaki adatok forrása. |
| 266/2013. (VII. 11.) Korm. rendelet | A tanúsítói szakmagyakorlás jogosultsági kerete. |
| Alkalmazott épületenergetika (2024) | A felmérés, szerkezet- és gépészetazonosítás, zónázás, számítás és korszerűsítési javaslatok szakmai segédlete. Nem jogszabály, de a mérnöki adatfelvétel elsődleges kézikönyve. |
| OÉNY e-tanúsítás | A hiteles nyilvántartás; a szakmailag kész XML/adataiból keletkezik a hiteles, HET-azonosítós tanúsítvány. |

**Kiadási szabály:** a jogszabályi státuszt és az OÉNY aktuális XML-validációját minden végleges beküldés előtt ellenőrizni kell. A modell, a PDF-ből kinyert adat vagy az LLM csak bizonyítékkal alátámasztott előkészítő adatot adhat; nem minősül helyszíni szemlének.

## 2. Folyamatkép

```text
Lead → kvalifikálás → ajánlat → ügyfél-elfogadás → projekt
  → adatbekérés + helyszíni szemle → bizonyítékcsomag
  → épületmodell + WinWatt számítás → mérnöki QA
  → tanúsítvány XML + OÉNY előnézet → végleges OÉNY rögzítés
  → HET-tanúsítvány átadás → számla → fizetés → archiválás
```

Minden nyíl egy átadási pont: csak sikeres minőségkapu után léphet tovább az ügy.

## 3. Üzemi szakaszok és minőségkapuk

### A. Lead és kvalifikálás

**WebWatt entitás:** `crm_leads` (üzleti CRM) vagy átmenetileg `pipeline_leads`.

**Rögzítendő:** kapcsolattartó, ingatlan címe/helyrajzi száma ha rendelkezésre áll, szolgáltatási cél (adásvétel, bérbeadás, használatbavétel, pályázat, felújítás), épülettípus, becsült alapterület, határidő, forrás, meglévő terv/tanúsítvány/fotó.

**Kvalifikáló kérdések:**

- Tanúsítandó épület vagy önálló rendeltetési egység pontosan mi?
- Van-e érvényes tanúsítvány, és mi a kiállítás oka?
- Milyen tervek, műszaki dokumentumok, korábbi számlák és gépészeti adattáblák állnak rendelkezésre?
- Kell-e helyszíni szemle, milyen hozzáférés biztosított, és ki az információforrás?

**Kapuk:** cím és tanúsítási tárgy azonosított; a feladat nem esik nyilvánvaló kivétel alá; a szükséges szakági jogosultság és kapacitás rendelkezésre áll. A rendszer *nem* állíthatja automatikusan, hogy a tanúsítás kötelező vagy nem kötelező: ezt a tanúsító hagyja jóvá.

### B. Ajánlat és megrendelés

**WebWatt entitás:** `crm_offers`, `crm_offer_versions`; pipeline-ban `lead_submitted → quoted → approved/rejected`.

**Ajánlat tartalma:** tárgy és cím, vizsgált egység, helyszíni szemle és dokumentumigény, vállalási határidő, ár/ÁFA/fizetési feltétel, mit tartalmaz az átadás (HET tanúsítvány, alátámasztó számítás, javaslatok), kizárások, ügyfél felelőssége az adatszolgáltatásért.

**Kapuk:** az ügyfél elfogadta; a megrendelő és a számlázási adatok elkülönítve rögzítettek; a projekt a jóváhagyott ajánlatverzióhoz kötött. Elfogadáskor `survey_projects` és - ahol munkaelosztás kell - `pipeline_projects` jön létre. Egy leadhez a pipeline modellben legfeljebb egy projekt tartozik.

### C. Projektindítás és adatbekérés

**WebWatt hierarchia:** projekt → épület → szint → helyiség → fal → nyílászáró; PDF-alaprajz a Draftsman háttere lehet.

**Kötelező bizonyítékcsomag:**

1. megrendelői adatok és nyilatkozatok;
2. tervrajzok, korábbi tanúsítványok és rendelkezésre álló műszaki dokumentumok;
3. helyszíni szemle fényképei, méretei, megfigyelései és dátuma;
4. szerkezetenként a bizonyíték forrása és bizonyossági szintje;
5. gépészetenként gyártó/típus/adattábla, szabályozás, hőleadó, HMV, szellőzés, hűtés és megújuló adat.

**Kapuk:** a szemle dátuma és a források rögzítve; ellentmondó adat megjelölve; a hiányzó adat nem kap automatikus, látszólag hiteles értéket.

### D. Mérnöki felmérés és geometriai modell

**Eszközök:** helyszíni felmérés + WebWatt Draftsman + AutoWinWatt PDF→modell előkészítés + WinWatt.

**Kötelező modell:** épületek, szintek, helyiségek, fűtött/nem fűtött terek, termikus zónák, minden energetikailag releváns határoló és nyílászáró, rétegrend, tájolás, hőhíd-/talajkapcsolati adat.

**Falgeometriai szerződés az AutoWinWattban:** minden külső vagy lábazati fal-szegmenshez `X = tervből/felmérésből feltárt hossz`, `Y = falmagasság`, `A = X × Y`. A PDF-címkén ugyanennek kell látszania. Hiányos X/Y esetén a fal `ELLENŐRZENDŐ`, és a szigorú WinWatt-fordítás nem készíthet végleges XML/WWP-t.

**Kapuk:**

- a helyiség-alapterületek és belmagasságok összevetve a tervvel/felméréssel;
- egy több külső fallal bíró helyiség minden fala külön szegmens (nem összevont R5);
- nyílászárók mérete és elhelyezése falhoz kapcsolva;
- a rétegrend katalógusanyagból választott vagy saját anyagként dokumentált;
- a tervre rajzolt ellenőrző PDF-et mérnök átnézte.

### E. Szerkezet- és gépészetazonosítás

Az *Alkalmazott épületenergetika* 22. fejezete szerinti logikával azonosítandók a homlokzati falak, tetők, födémek, talajjal érintkező szerkezetek és nyílászárók; a 23. fejezet szerint a fűtés, HMV, szellőzés, hűtés és világítás.

**Gépészeti felvételi minimum:** hőtermelő típusa/életkora/teljesítménye és adatlapja, energiaforrás, hőleadók, elosztás/tárolás/szabályozás, HMV, szellőzés, hűtés, PV/napkollektor. Ismeretlen berendezésnél a választott egyszerűsített paraméter és annak oka auditálható legyen.

**Kapuk:** a rendszeradatok és a szerkezetadatok nem keverednek; minden feltételezéshez forrás vagy tanúsítói megjegyzés tartozik.

### F. Számítás, WinWatt és szakmai ellenőrzés

**Számítási lánc:** zónázás → transzmisszió/szellőzési veszteség és nyereségek → fűtési/hűtési nettó igény → gépészeti rendszerek végső- és primerenergia-igénye → CO2 és referenciaépülethez viszonyított besorolás → korszerűsítési javaslatok.

**WinWatt feladat:** a hitelesen ellenőrzött modell felvétele/importja, a számítási eredmények és a tanúsítvány-előkészítés. A PDF→WinWatt automatizmus csak adatbeviteli gyorsító; a WinWatt eredménye és az alátámasztó munkarész a mérnöki kiadás alapja.

**Kapuk:**

- natív XML/WWP visszaolvasás: helyiség, szerkezet, X/Y/A, rétegrend és rendszeradat egyezik a forrásmodellel;
- a tanúsító ellenőrzi a fajlagos mutatókat, besorolást és a javaslatok műszaki realitását;
- javítás után új számítás és verziózott audit készül;
- csak `engineer_approved` állapotból készülhet OÉNY-be küldendő XML.

### G. E-tanúsítás és átadás

**Hivatalos cél:** az OÉNY e-tanúsítási rendszerében történő rögzítés és a hiteles tanúsítvány/HET-azonosító keletkezése.

**Technikai váz:**

1. WinWattból vagy a jóváhagyott exportból az aktuális sémának megfelelő XML készül;
2. XML-séma és üzleti validáció; OÉNY előnézet;
3. a tanúsító a végleges beküldést jóváhagyja;
4. az OÉNY válasza, HET-azonosítója és a generált dokumentum a projekthez archiválódik;
5. az ügyfél az elfogadott átadási csatornán megkapja a tanúsítványt és a vállalt mellékleteket.

Az `oeny_uploader.py` feltárt működése szerint az OÉNY-sor előnézetet tud kérni, feltöltéskor számlázási adatot ad át, és a végleges feltöltést nem ismétli automatikusan, mert hálózati hiba esetén a befogadás bizonytalan. Ezt a védelmet meg kell tartani: bizonytalan státusznál előbb az OÉNY-ben kell ellenőrizni, csak utána szabad újból beküldeni.

**Kapuk:** XML előnézet hibamentes; helyes számlázási adat kiválasztva; végleges feltöltés tanúsítói jóváhagyással; HET és kiadott dokumentum archiválva; ügyfélátadás naplózva.

### H. Számlázás, fizetés, lezárás

**WebWatt entitás:** `project_invoices`, státusz: `draft → issued → paid`; a projekt-, ajánlat- és számlakapcsolat visszakereshető.

**Számlázási minimum:** számlázási név, irányítószám, település, cím, e-mail és adószám ellenőrzése; ajánlat-/megrendelés-hivatkozás; bruttó összeg, pénznem, fizetési határidő, számlaszám/külső számlaazonosító.

**Kapuk:** a számla csak átadásra kész vagy átadott eredményhez kapcsolható; a kiállítás és a fizetés dátuma rögzített; lejárt számla a kintlévőség-listára kerül, de a tanúsítvány szakmai tartalmát már nem módosíthatja.

## 4. Ajánlott, végrehajtható workflow-sablon

| Sorrend | Fázis | Felelős | Kimenet | Kilépési feltétel |
|---:|---|---|---|---|
| 1 | Lead kvalifikálás | ügyfélkapcsolat / tanúsító | minősített lead | tárgy, cím, határidő tiszta |
| 2 | Ajánlat | ügyfélkapcsolat | verziózott ajánlat | elfogadva vagy elutasítva |
| 3 | Projekt és adatbekérés | admin | projekt, kérdőív, dokumentumtár | szemle szervezhető |
| 4 | Helyszíni szemle | jogosult tanúsító | fotó- és mérési napló | bizonyítékcsomag elégséges |
| 5 | Geometria és szerkezet | energetikus | ellenőrző PDF, rétegrendek | X/Y/A audit rendben |
| 6 | Gépészet | energetikus | rendszerlapok | forrás/feltételezés dokumentált |
| 7 | WinWatt számítás | energetikus | WWP, számítás, export | műszaki QA jóváhagyta |
| 8 | E-tanúsítás | jogosult tanúsító | XML, OÉNY előnézet, HET | hiteles rögzítés kész |
| 9 | Átadás | admin / tanúsító | átadási napló | ügyfélnek elküldve |
| 10 | Számla és lezárás | admin | számla, fizetési állapot | fizetve vagy kintlévőségben |

## 5. Adat- és jogosultsági határok

- **LLM/PDF-feldolgozás:** javaslatot, kiolvasott jelölést és bizonyítékhivatkozást ad; nem hoz létre végleges szakmai tényt bizonyíték nélkül.
- **Automata import:** felvehet helyiséget, szerkezetet és katalogizált anyagot, de a `review_required` adat nem mehet automatikusan kiadásra.
- **Mérnök/tanúsító:** dönt a zónázásról, szerkezetazonosításról, gépészeti feltételezésről, számítási módról, javaslatokról és végleges beküldésről.
- **Admin:** lead, ajánlat, ügyfélkommunikáció, számla és feladatok; nem módosíthat jóváhagyott szakmai számítási adatot új felülvizsgálat nélkül.
- **Audit:** minden forrásfájl, modellverzió, WinWatt-export, OÉNY-válasz és átadási/számlázási esemény dátummal és felelőssel archiválandó.

## 6. Rendszerfejlesztési prioritás

1. `certification_case` összekötő rekord: CRM lead, `survey_project`, ajánlat, WinWatt modell, OÉNY-feltöltés és számla egy ügyazonosítón.
2. Kötelező ellenőrzőlista és állapotgép a 4. fejezet minőségkapuihoz; a jelenlegi CRM- és pipeline-státuszok ne legyenek a mérnöki jóváhagyás helyettesítői.
3. Bizonyítéktár: minden adatnál `source_type`, `source_file`, oldal/fotó, megfigyelő, bizonyosság és felülvizsgálati állapot.
4. AutoWinWatt audit integráció: a címkézett alaprajz és az X/Y/A eltéréslista legyen a projekt kiadási csomagjának kötelező melléklete.
5. OÉNY integráció csak előnézet → tanúsítói jóváhagyás → egyszeri végleges feltöltés állapotgéppel; bizonytalan válasz esetén kézi OÉNY-ellenőrzés.
6. Számlázási integráció a hiteles átadási eseményből induljon, ne pusztán egy projektstátuszból.

## 7. Feltárt helyi források

- `magyar-mentor/external/energetika/Alkalmazott_Epuletenergetika.pdf` - 2024-es kézikönyv; különösen 21-24. fejezet (tanúsítás, szerkezet- és gépészetazonosítás, korszerűsítés) és 27.1. esettanulmány.
- `magyar-mentor/external/energetika/176_2008. (VI. 30.) Korm. rendelet.pdf` - helyi példány; hatályosságát kiadáskor online kell újraellenőrizni.
- `magyar-mentor/external/energetika/ÉKM rendelet 1. függelék.pdf` és `ÉKM rendelet 2. függelék.pdf` - helyi számítási mellékletek.
- `magyar-mentor/external/energetika/tanúsítvány/dokumentacio-v3.0.12035/` - e-tanúsítás XML, szótár és validációs dokumentáció.
- `Programt-red-kek/tanusitvany_upload/oeny_uploader.py` - a feltárt előnézeti/feltöltési és számlázási adatfolyam.
- `magyar-mentor/docs/felhasznaloi-kezikonyv.md`, `pipeline-lead-projekt-osszerendeles-utmutato.md`, `contractor-lead-project-beepitesi-terv.md` - WebWatt CRM-, projekt-, pipeline- és számlázási modell.
- `autowinwatt/winwatt_automation/docs/PDF_TO_WINWATT_XY_GEOMETRY.md` - a geometriai import és az X/Y/A kiadási tilalom részletes specifikációja.

## 8. Külső, kiadáskor ellenőrizendő források

- [176/2008. (VI. 30.) Korm. rendelet - Hatályos Jogszabályok Gyűjteménye](https://net.jogtar.hu/jogszabaly?docid=a0800176.kor)
- [9/2023. (V. 25.) ÉKM rendelet - Hatályos Jogszabályok Gyűjteménye](https://net.jogtar.hu/jogszabaly?docid=a2300009.eko)
- [266/2013. (VII. 11.) Korm. rendelet - Hatályos Jogszabályok Gyűjteménye](https://net.jogtar.hu/jogszabaly?docid=a1300266.kor)
- [OÉNY e-tanúsítás ügyintézési leírás](https://www.magyarorszag.hu/szuf_ugyleiras?id=81731df4-ab80-4ca6-89b9-9c9dcb32c695)
