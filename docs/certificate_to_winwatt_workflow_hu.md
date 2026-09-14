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

A kimenet `certificate_build_manifest.json`. A következő, natív WinWatt-lépés kizárólag jóváhagyott, strukturált geometriai mappingből készíthet XML-t, majd a meglévő `NativeXmlService` importja és a `WinWattService.save_project_as` mentése állít elő `.wwp` fájlt. Nyers `.wwp` bináris írás tiltott.
# Tanúsítvány → natív WinWatt projekt

Az `certificate-native-project` a feltárt AutoWinWatt-mappinget használja:
`MainForm.NewProjekt` egy új, még nem létező célfájlra, majd natív XML-import,
végül `MainForm.SaveProjekt`. Az XML-import összevonó művelet, ezért a folyamat
szándékosan nem meglévő vagy sablon `.wwp`-be importál.

Réteganyag esetén a helyi WinWatt-katalógus az elsődleges. A matcher név,
anyagcsalád, hővezetési tényező, sűrűség és fajhő alapján rangsorol. Hiányos vagy
ellentmondó fizikai adat `review`; új anyag nem keletkezik automatikusan. Zárt
légrés külön `special` döntés, nem katalógusanyag.

Az integrációs Kerepesi-visszaolvasás kontrollértéke: 1 épület, 2 helyiség,
21 szerkezet, 61 határoló elem, 2970,5 m² és 12189 m³.
