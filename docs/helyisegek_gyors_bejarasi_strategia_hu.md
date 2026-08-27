# Helyiségek gyors, mégis visszaállítható bejárási stratégiája

## Kiinduló mérés

A korábbi futás 127 rögzített UI-állapotot, 3926 élet és 1272 hibabejegyzést tartalmaz. Az állapotok között 48 lépés mélységű utak is vannak. Ez nem a helyiségek valódi funkcionális mélységét jelenti: a vezérlőjelöltek összetétele a következő.

| Jelölt | Darab |
| --- | ---: |
| Gomb | 2314 |
| Listaelem | 868 |
| Tab | 724 |
| Kombinált lista | 485 |
| Faelem | 156 |

A leggyakoribb hibák ugyanazon ideiglenes listaelemekre (`Étterem`, `vízszintes`, `90° (K)`) mutatnak. Ezek egy korábban megnyitott ComboBox felugró listaelemei: a következő teljes újrajátszáskor már nincs önálló vezérlőként jelen. Emiatt a jelenlegi stratégia sok nem reprodukálható, nem funkcionális ágat próbál meg újra és újra.

## Cél

Az új bejárás célja nem minden UIA-gyerekablak-kontroll megnyomása, hanem minden **funkcionális állapotátmenet** rögzítése. A lista minden eleme továbbra is dokumentált érték marad, de nem válik önálló, koordináta-alapú útvonallá.

## Új modell: szemantikus akciók

### 1. Akcióosztályozás a várólistára kerülés előtt

| Vezérlő | Bejárási szabály |
| --- | --- |
| Tab | Minden tab egyszer, az állapotváltozás ellenőrzésével. |
| Funkcionális gomb | Bejárható: `Szerkezetek`, `Felvesz`, `Módosít`, `Választék`, `Radiátorok`, `Határoló szerkezetek` stb. |
| Bezárás/OK/Elvetés/Súgó és oldalléptetés | Rögzítendő, de nem új állapotághoz vezető akció. |
| ComboBox | Egyetlen `select_value(combo_locator, érték)` akcióvá alakul. Az értékek a megnyitott listából olvashatók ki, de a felugró `ListItem` nem kerül közvetlenül a várólistára. |
| Táblázat/lista sorai | Alapból dokumentálandók; csak akkor bejárhatók, ha a lista első kiválasztása kimutathatóan új párbeszédet vagy vezérlőkészletet nyit. Azonos szerkezetű sorokból reprezentatív mintát kell venni. |
| Faelem | Kinyitás/kijelölés egyszer elem-azonosító szerint; a gyermekek csak ténylegesen megjelenő új faágként kerülnek sorra. |

Ez várhatóan azonnal eltávolítja a több száz ismétlődő felugró listaelem- és navigációs ágat.

### 2. „Munkamenet-sziget” ugyanazon szülőállapotra

A jelenlegi teljes gyökér–cél újrajátszás stabil, de egy testvér-akcióhoz is ismét megnyitja a projektet, a Helyiségek jegyzéket és a helyiségablakot. Az új egység egy **ellenőrzött munkamenet-sziget**:

1. A helyiség gyökeréből egyszer eljut a már hitelesített szülőállapotba.
2. Ugyanabban az ablakban végrehajtja a szülő összes, priorizált gyermekakcióját.
3. Minden akció után kizárólag ismert `Mégse`/`Esc`/Bezárás útvonalon állítja vissza a szülőt.
4. Visszaálláskor újra számolja a szülő UI-hashét és felsőmenü-hashét.
5. Eltérés vagy sikertelen visszaállás esetén azonnal eldobja a munkamenetet, és csak annál az ágnál visszatér a jelenlegi teljes gyökér–cél újrajátszásra.

Így nem az egész bejárás kockáztat stabilitást: csak egy sikertelen sziget esik vissza a lassú, bizonyított módszerre.

### 3. Ágprioritás és lezárási feltétel

Elsőbbséget kapnak a szerkezetet nyitó ágak: `Határoló szerkezetek → Szerkezetek`, felvétel/módosítás, választékok, fák és új tabok. A bezáró, súgó- és lapozógombok csak a jelenlétük bizonyítékát kapják.

Egy ág lezárt, ha:

- az akció új állapotot adott és annak gyermekei már feldolgozottak;
- az akció azonos UI-hashhez tért vissza;
- a szemantikus akció háromszor reprodukálhatóan sikertelen volt;
- a lista reprezentatív mintája nem nyitott új funkcionális szerkezetet.

## Tartós mentés és folytatás

Az eseménynaplós checkpoint megmarad: minden átmenet kis, fsync-elt esemény, a teljes gráf 50 átmenetenként tömörül. A munkamenet-sziget minden akciója is külön esemény, ezért áramszünet vagy WinWatt-hiba után legfeljebb az aktuális akció ismétlődik meg.

## Bevezetési terv

1. Külön `semantic_hybrid` futás indítása, a jelenlegi `20260826T154506_merged` változatlan megőrzésével.
2. ComboBox- és átmeneti-lista felismerő bevezetése; a régi futásból az ilyen hibautak megjelölése `legacy_transient_list` kategóriával.
3. Tabok és a `Határoló szerkezetek` ág munkamenet-szigetes pilotja.
4. A pilotnál mérés: átmenet/perc, visszaállási arány, új UI-hash/100 akció.
5. Csak akkor terjesztés minden helyiség-ágra, ha a visszaállási ellenőrzés hibaaránya alacsony; különben az érintett párbeszéd marad teljes újrajátszásos.

## Várható eredmény

Nem a párhuzamos WinWatt-példány a fő gyorsítás, hanem a hibás akciótér eltávolítása és a testvér-ágak egy helyiség-munkamenetben való feldolgozása. A 9 ág / 5 perc érték helyett a funkcionális átmeneteknél nagyságrendi javulás várható; a pontos célértéket a pilot első 100 akciója után kell rögzíteni.

## Fontos korlát

Ezt a stratégiát nem szabad a régi, koordináta-alapú várólistára közvetlenül ráengedni, mert annak jelentős része már eleve átmeneti listaelem. A meglévő állapotképek és menüsnapshotok bizonyítékként felhasználhatók, de a gyors bejárás saját, szemantikus várólistával induljon.
