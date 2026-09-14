# Tanúsítvány → WinWatt projekt

A `winwatt certificate-build` az első, bizonyítékos előállítási lépés. A PDF-et helyben olvassa (`pypdf`), a forrásfájl SHA-256 azonosítóját, oldal- és szövegrészlet-hivatkozását eltárolja, majd a helyi WinWatt-anyagkatalógusban keres.

```powershell
cd winwatt_automation
python -m winwatt_automation.cli.main certificate-build `
  C:\projekt\tanusitvany.pdf `
  --catalog-xml C:\helyi\anyagok.xml `
  --output-dir data\certificate_builds\pelda
```

A ChatGPT CLI alapértelmezésben nem fut. Csak `--allow-llm` kapcsolóval kapja meg a helyi kivonás felülvizsgálandó részleteit; nem küldi fel a teljes tanúsítványt, és nem találhat ki hiányzó geometriát vagy anyagtulajdonságot.

A helyi kivonó külön kiszűri az önmagukban álló méretsorokat (például
`77.000 m` vagy `szélesség = 70 mm`): ezek geometriai bizonyítékok, nem
anyagmegnevezések, ezért sem a katalóguskeresést, sem az esetleges LLM-reviewt
nem szennyezhetik.

A kimenet `certificate_build_manifest.json`. A következő, natív WinWatt-lépés kizárólag jóváhagyott, strukturált geometriai mappingből készíthet XML-t, majd a meglévő `NativeXmlService` importja és a `MainForm.SaveProjekt` mentése állít elő `.wwp` fájlt. Nyers `.wwp` bináris írás tiltott.
# Tanúsítvány → natív WinWatt projekt

Az `certificate-native-project` a feltárt AutoWinWatt-mappinget használja:
`MainForm.NewProjekt` egy új, még nem létező célfájlra, majd natív XML-import,
végül `MainForm.SaveProjekt`. Az XML-import összevonó művelet, ezért a folyamat
szándékosan nem meglévő vagy sablon `.wwp`-be importál.

Réteganyag esetén a helyi WinWatt-katalógus az elsődleges. A matcher név,
anyagcsalád, hővezetési tényező, sűrűség és fajhő alapján rangsorol. Hiányos vagy
ellentmondó fizikai adat `review`; új anyag nem keletkezik automatikusan. Zárt
légrés külön `special` döntés, nem katalógusanyag.

A Kerepesi-v3 helyi auditja a 1460 elemű WinWatt-katalógus ellen 67 rétegsorból
26 `catalog_match`, 2 `special` zárt légrés és 39 `manual_review` döntést adott.
A `review` nem hibásan kitalált anyag: a projekt a tanúsítványból származó,
megadott rétegfizikát őrzi meg, míg a jelölt katalógusanyag és az indoklás a
visszakövethető felülvizsgálati nyomban marad.

Az integrációs Kerepesi-visszaolvasás kontrollértéke: 1 épület, 2 energetikai
zóna, 2 helyiség, 21 szerkezet, 67 rétegsor, 61 határoló elem, 2970,5 m² és
12189 m³. A transzmissziós hőveszteség eltérése 0,121675 W/K (−0,003823%).
Minden szerkezettípus felülete egyezik a felülvizsgált forrásmodellel.

Az ezen a gépen lévő régi WinWatt kiadásban a külső tető (`Type=5`) importált
`Compass` értékét megnyitás–mentés után 0°-ra normalizálja; a 45°-os dőlés,
felület, U-érték és transzmisszió megmarad. A visszaolvasási riport ezt valódi
tájolási eltérésként jelöli, nem maszkolja forrásbeli feltételezéssel.
