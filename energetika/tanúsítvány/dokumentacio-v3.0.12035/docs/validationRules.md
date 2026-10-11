# e-tanúsítás validációs szabályok
## Hibaüzenetek visszafejtése
Ez a dokumentum elsősorban a tanúsító szoftverek fejlesztőinek szól. Ha Tanúsítóként jött ide, akkor valószínűleg az előnézet létrehozásakor tapasztalt hibaüzenetet próbálja kinyomozni.

Ez nem lehetetlen, és nem is könnyű. Megpróbálunk az alábbiakban segíteni. 
## Áttekintés
Az alapvető folyamat az lesz, hogy ki kell másoljuk a hibaüzenetben kapott angol kifejezés különböző részeit, és rá kell keresnünk ebben a dokumentumban. Ha sikerül azonosítani, hogy a tanúsítvány mely részét érinti a hibaüzenet, akkor vissza kell térni a tanúsító szoftverbe, ott javítani a megfelelő részt, majd az új fájlt feltölteni az e-tanúsítás alkalmazásba.

A továbbiakban két konkrét példán mutatjuk be a teendőket.
## Egyszerűbb példa
Ha a hibaüzenet pl. „BuildingData.MajorRenovationYear: Kérjük, 1000 és 2023 közötti értéket adjon meg!”

Másolja ki az utolsó pont utáni részt, azaz ebben az esetben a „MajorRenovationYear” szövegrészt.

Majd ezen az oldalon keressen (Ctrl+F) rá erre a kifejezésre.

Az oldalon egy találat lesz! Az angol kifejezés után látja a tanúsítványon is használatos magyar kifejezést, és utána a szabályt, aminek meg kell feleljen ez az érték!

majorRenovationYear (jelentős felújítás éve) max 5 db évszám, vesszővel elválasztva, >=1000 és <=aktuális év

Vissza kell térnie a tanúsító programba, megtalálni a hivatkozott értéket, és ellenőrizni azt.

Önnek kell rájönnie, hogy ebben az esetben i) több, mint öt évszámot adott meg, vagy ii) az egyik évszám nem felel meg a szabálynak.

A tanúsító programban javítva az értéket, és újra elmentve a fájlt, kell újra feltöltenie az e-tanúsítás alkalmazásba a fájlt.

## Nehezebb példa
Ha a hibaüzenet pl.
„ModernisationProposalsOfBuildingServicesSystems[2].ActualEnergeticQuality.Note: Az érték hossza nem haladhatja meg a 150 karaktert!”

Ha a pont utáni részt „Note” másoljuk ki és keresünk rá, akkor 5 találatot fogunk kapni.

Ilyen esetben érdemes a legelső tagot másolni, és arra is rákeresni: „ModernisationProposalsOfBuildingServicesSystems”

Ez a hosszú kifejezés ebben a dokumentumban a releváns fejezetet adja meg! Tehát most már tudjuk, hogy ezen a fejezeten belül kell keresnünk.

Ezen belül a következő tag az „ActualEnergeticQuality”, amin belül a „Note” érték nem felel meg a szabálynak.

Épülettechnikai rendszerek korszerűsítési javaslataihoz több blokk is tartozhat. Pl. a fűtési rendszerhez tartozó, vagy a beépített világításhoz tartozó, stb. Azaz Önnek még rá kell jönnie, hogy melyik blokkban van a 150 karaktert meghaladó érték.

A tanúsító programban javítva az értéket, és újra elmentve a fájlt, kell újra feltöltenie az e-tanúsítás alkalmazásba a fájlt.

## Validációs szabályok gyűjteménye

[TOC]

# Energetikai tanúsítvány json és xml fájlok validációja

A csillaggal megjelölt és vastagon szedett mezők kötelezőek.

## 1. header (fejléc)

   1. **energyClassification*** (energetikai besorolás): `A+++, A++, A+, A, B, C, D, E, F, G, H, I`

   2. **co2Emission*** (CO<sub>2</sub> kibocsátás): `A+++, A++, A+, A, B, C, D, E, F, G, H, I`

## 2. buildingData (épület adatai)

   1. **clientName*** (megrendelő neve): `min 3, max 45 UTF-8 karakter`
   2. buildingAddress (az épület címe):

      1. **zipCode*** (irányítószám): `1000-9999, azonban vannak érvénytelen számok a Magyar Posta hivatalos irányítószám adatbázisa az irányadó ez esetben` <https://www.posta.hu/szolgaltatasok/iranyitoszam-kereso>
      2. **settlementName*** (település neve): `min 2, max 30 UTF-8 karakterek`
      3. streetName (közterület neve): `min 1, max 40 UTF-8 karakterek`
      4. streetType (közterület típusa): `min 2, max 20 UTF-8 karakterek`
      5. houseNumber (házszám): `min 1, max 20 UTF-8 karakterek`
      6. building (épület): `min 1, max 20 UTF-8 karakterek`
      7. floor (emelet): `min 1, max 20 UTF-8 karakterek`
      8. doorNumber (ajtó): `min 1, max 20 UTF-8 karakterek`
      9. staircase (lépcsőház): `min 1, max 20 UTF-8 karakterek`

   3. **topographicalNumber*** (helyrajzi szám): `min 1, max 50, az alábbi karaktereket fogadjuk el: 1234567890ABCDEFGHIJKLMNOPRSTVXYZ/`
   4. **certIssueReason*** (tanúsítvány kiállításának oka): `PurchaseAndSale, NewBuilding, RentingOut, PublicBuilding, Tender, Other`
   5. **buildingPurpose*** (épület rendeltetése): `ResidentialBuilding, Cottage, AccomodationFacility, HealthCareFacility, EducationalFacility, CulturalFacility, SportsFacility, Office, CommercialBuildings, TransportationAndCommunicationBuildings, IndustrialAndWareHouseBuildings, AgriculturalBuilding, ReligiousAndFuneralPurposeBuilding, LawEnforcementAndDefenseBuilding, OtherShortTermStayBuilding, OtherUnclassifiedBuilding`
   6. **yearOfConstruct*** (építési év): `>=1000 és <=aktuális év`
   7. majorRenovationYear (jelentős felújítás éve) `max 5 db évszám, vesszővel elválasztva, >=1000 és <=aktuális év`
   8. **heritageOrLocalProtection*** (műemléki vagy helyi védettség): `NotProtected, Protected, ArchaeologicalProtection, WorldHeritageProtection, LocalProtection, VariousProtections`
   9. **usefulFloorArea*** (hasznos alapterület): `csak pozitív két tizedesjegy pontosságú törtszám megengedett`
   10. **conditionedVolume*** (kondicionált térfogat): `0 vagy pozitív két tizedesjegy pontosságú törszám megengedett`
   11. **numberOfFloors*** (épület szintjeinek száma): `csak pozitív egész szám, min 1, max 100`
   12. buildingAreaToVolumeRatio (épület felület-térfogat aránya): `csak pozitív szám, max 3 tizedesjegy`
   13. **hasPublicTraffic*** (közforgalom van-e benne?): `boolean, nem jelenik meg a pdf tanúsítványon`
   14. **isPublicProperty*** (köztulajdon-e?): `boolean, nem jelenik meg a pdf tanúsítványon`
   15. **isFunctionalUnit*** (rendeltetési egység-e?): `boolean`

## 3. efficiencyCategories (hatékonysági kategóriák)

   1. **buildingCategory*** (épület típusa): `SingleFamilyDetachedHome, TwinHouse, TwinHouseHalf, TerracedHouse, TerracedHouseEnd, TerracedHouseIntermediate, ApartmentBuilding, FlatEndLower, FlatEndIntermediate, FlatEndUpper, FlatGeneralLower, FlatGeneralIntermediate, FlatGeneralUpper, OtherBuilding`
   2. **isMajorRenovationFulfilled*** (teljesül a jelentős felújítás követelményszintje?): `boolean`
   3. **isZeroEmissionFulfilled*** (teljesül a közel nulla energiaigényű épületek követelményszintje?): `boolean`
   4. **isSummerHeatProtectionFulfilled*** (nyári hővédelmi követelményeknek megfelel?): `boolean`
   5. **renewableEnergyUsage*** (hasznosított megújuló energia mennyisége): `nem negatív számok, két tizedesjegy megengedett`
   6. currentValues (jelenlegi értékek):
      1. summariesEnergyRating: összesített energetikai jellemző
         1. **percentage*** (százalék): `egész szám`
         2. value (értéke): `Szám, max 2 tizedesjegy pontossággal`

      2. co2 (CO<sub>2</sub> kibocsátás):
           1. **percentage*** (százalék): `egész szám`
           2. value (értéke): `Szám, max 2 tizedesjegy pontossággal`

      3. heatLossFactor: fajlagos hőveszteségtényező
            1. percentage (százalék): `mindig null`
            2. value (értéke): `Szám, max 2 tizedesjegy pontossággal`

   7. majorRenovationRequirementLevel (jelentős felújítás követelményszintje):
      1. summariesEnergyRating (összesített energetikai jellemző):
         1. percentage (százalék): `mindig null`
         2. value (értéke): `Szám, max 2 tizedesjegy pontossággal`
      2. co2: co2 kibocsátás
         1. percentage (százalék): `mindig null`
         2. value (értéke): `mindig null`
      3. heatLossFactor: fajlagos hőveszteségtényező
          1. percentage (százalék): `mindig null`
          2. value (értéke): `Szám, max 2 tizedesjegy pontossággal`
   8. nearZeroEnergyBuildingRequirementLevel:
      1. summariesEnergyRating: összesített energetikai jellemző
         1. percentage (százalék): `mindig null`
         2. value (értéke): `Szám, max 2 tizedesjegy pontossággal`
      2. co2: co2 kibocsátás
         1. percentage (százalék): `mindig null`
         2. value (értéke): `Szám, max 2 tizedesjegy pontossággal`
      3. heatLossFactor: fajlagos hőveszteségtényező
         1. percentage (százalék): `mindig null`
         2. value (értéke): `Szám, max 2 tizedesjegy pontossággal`

## 4. certifierDetails: tanúsító adatai

   1. **name*** (név): `max 50 UTF-8 karakter`
   2. address (cím):
      1. **zipCode*** (irányítószám): `1000-9999, azonban vannak érvénytelen számok a Magyar Posta hivatalos irányítószám adatbázisa az irányadó ez esetben` <https://www.posta.hu/szolgaltatasok/iranyitoszam-kereso>
      2. **settlementName*** (település neve): `min 2, max 30 UTF-8 karakterek`
      3. streetName (közterület neve): `min 1, max 40 UTF-8 karakterek, de ha nem adja meg akkor kötelezően kitöltendő a topographicalNumber adat`
      4. streetType (közterület típusa): `min 2, max 20 UTF-8 karakterek`
      5. houseNumber (házszám): `min 1, max 20 UTF-8 karakterek`
      6. building (épület): `min 1, max 20 UTF-8 karakterek`
      7. floor (emelet): `min 1, max 20 UTF-8 karakterek`
      8. doorNumber (ajtó): `min 1, max 20 UTF-8 karakterek`
      9. staircase (lépcsőház): `min 1, max 20 UTF-8 karakterek`

   3. topographicalNumber (helyrajzi szám): `csak akkor kötelező ha nem adott meg **streetName** adatot, szabadszavas max 50, az alábbi karaktereket fogadjuk el: 1234567890ABCDEFGHIJKLMNOPRSTVXYZ/`
   4. **phoneNumber*** (telefon): `max 20, csak egyetlen telefonszám szerepelhet benne, számok, szóköz és plusz karaktereket tartalmazhat pl.:"+36 20 432 67 89"`
   5. **email*** (e-mail): `min 5, max 50, és e-mail cím szabályainak meg kell feleljen`
   6. **eligibilityNumber*** (jogosultsági szám):`formátum: “TÉ {megyekód}-{tagszám}”. fix tag: TÉ, megye szám: 01-21, csak szám, tagszám: min 4 , max 5 karakter, csak szám. pl TÉ 06-0366 , TÉ 16-50658`
   7. **softwareAndVersion*** (szoftver neve és verziója): `min 1 max 40`

## 5. validity (érvényesség)

    1. **siteInspectionDate*** (helyszíni szemle dátuma): `európai dátum formátum: json esetében: éééé.hh.nn. és xml esetében éééé-hh-nn`

## 6. boundaryAndOpeningStructures (határoló és nyílászáró szerkezetek)

   1. typeOfStructure (szerkezet típusa):

   ```text
      curtainWall
      doorBetweenFacadeOrHeatedAndUnheatedSpaces
      facadeOpeningsWithMetalFrames
      facadeOpeningsWithWoodenOrPvcFrames
      facadeWall
      flatRoof
      floorStructureAboveArchesAndPassages
      floorStructureBelowAtticAndCrawlSpace
      foundationWall
      gateBetweenFacadeOrHeatedAndUnheatedSpaces
      glassRoof
      glazing
      groundLevelFloorInNewBuildings
      industrialAndFireResistantDoorsAndGates
      lowerCeilingStructureAboveUnheatedSpaces
      roofPlaneWindow
      roofSkylightSmokeVentDome
      specialGlazingWithHighAcousticOrSecurityRequirements
      structureBetweenAdjacentHeatedBuildingsAndBuildingSections
      structuresEnclosingHeatedAtticSpace
      traditionalEnergyCollectingWalls
      wallBetweenHeatedAndUnheatedSpaces
      wallInContactWithTheGroundInNewBuildings
   ```

   2. energeticQualities (energetikai minőség)

      1. quality (minősítés): `bad, poor, average, good, excellent`

## 7. buildingServicesSystemEnergeticQuality (épülettechnikai rendszerek)

   1. heatingSystem (fűtési rendszer): `bad, poor, average, good, excellent`
   2. heatingAndVentilationSystem (fűtési és légtechnikai rendszer): `bad, poor, average, good, excellent`
   3. hotWaterSupplySystem (használati melegvíz ellátó rendszer): `bad, poor, average, good, excellent`
   4. coolingSystem (hűtési rendszer): `bad, poor, average, good, excellent`
   5. integratedLighting (beépített világítás): `bad, poor, average, good, excellent`

## 8. usingAlternativeEnergy (alternatív energiák használata)

   1. alternativeEnergies (alternatív energiák):

   ```text
      SolarPanels
      SolarCollectors
      BiomassHeatPump
      ConnectedEnergyProduction
      DistrictHeatingOrCooling
   ```

## 9. modernisationProposalDetails (korszerűsítési javaslatok részletezése)

   1. structureType (szerkezet típusa):

   ```text
      curtainWall
      doorBetweenFacadeOrHeatedAndUnheatedSpaces
      facadeOpeningsWithMetalFrames
      facadeOpeningsWithWoodenOrPvcFrames
      facadeWall
      flatRoof
      floorStructureAboveArchesAndPassages
      floorStructureBelowAtticAndCrawlSpace
      foundationWall
      gateBetweenFacadeOrHeatedAndUnheatedSpaces
      glassRoof
      glazing
      groundLevelFloorInNewBuildings
      industrialAndFireResistantDoorsAndGates
      lowerCeilingStructureAboveUnheatedSpaces
      roofPlaneWindow
      roofSkylightSmokeVentDome
      specialGlazingWithHighAcousticOrSecurityRequirements
      structureBetweenAdjacentHeatedBuildingsAndBuildingSections
      structuresEnclosingHeatedAtticSpace
      traditionalEnergyCollectingWalls
      wallBetweenHeatedAndUnheatedSpaces
      wallInContactWithTheGroundInNewBuildings
   ```

   3. structureNote (szerkezet rövid leírása): `max. 20 UTF-8 karakter`
   4. airTightness (légtömörség): `nyílászáró esetében kötelező mező, értékkészlet: poor, average, good, excellent`
   5. note (megjegyzés): `max. 150 UTF-8 karakter`
   6. proposalEnergeticQualities (javaslat energetikai minőségre)
      1. quality (minősítés): `good, excellent`

## 10. modernisationProposalsOfBuildingServicesSystems (korszerűsítési javaslatok épülettechnikai rendszerekhez)

   1. **buildingServiceSystemType*** (épülettechnikai rendszer típusa): `HeatingSystem, HeatingAndVentilationSystem, HotWaterSupplySystem, CoolingSystem, IntegratedLighting, Other`
   2. note (megjegyzés): `max 20 UTF-8 karakter`
   3. actualEnergeticQuality (jelenlegi energetikai minőség):
      1. quality (minőség): `bad, poor, average, good, excellent`
      2. note (megjegyzés): `max 150 UTF-8 karakter`
   4. recommendedModernisations (javasolt korszerűsítések):
      1. modernisationCategory (javasolt korszerűsítési kategória): `HeatGeneratorReplacement, HeatDistributionStorageControlEmitter, HeatRecoveryDistributionStorageControlEmitter, HeatDistributionStorageControl`
      2. systemElements (rendszerelemek):
         1. name (név):

         ```text
            Adjustment
            AirCooledFanCoil
            AirDuctNetworkModernisation
            AirPreHeatingWithGroundSourceHeatExchanger
            AirToAirHeatPump
            AirToWaterHeatPump
            Anemostat
            AutomaticOnAndOff
            AutomaticOnDimmable
            AutomationOfNaturalVentilation
            BuildingManagementSystem
            CeilingCoolingPipelines
            ChilledBeam
            CondenserHeatUtilization
            CondensingBoiler
            ControllingSunshades
            DepartingAirToWaterHeatPump
            DesigningSunshades
            DistrictHeating
            ElectricBoilerWithHeatPump
            EmergencyLighting
            FanCoilUnits
            FanReplacement
            FreeCooling
            GasPoweredHeatPump
            GasPoweredHeatPumpUtilizingWasteHeat
            GroundSourceHeatExchanger
            GroundSourceHeatToWaterElectricHeatPump
            GroundSourceHeatToWaterHeatPump
            HeatExchangers
            HeatRecoveryInstallation
            ImprovingNaturalLighting
            IndirectHeatedWaterTank
            InsulationOfAirDucts
            InsulationOfPipelines
            LightSourcesReplacement
            ManualOnAndAutomaticOffSwitching
            ManualOnSwitchingDimmable
            ModernRegulatedConvector
            Other
            PassiveSolarSolutions
            PelletBurningBoiler
            PumpReplacement
            Recirculation
            Regulation
            ReplacementOfCirculationPump
            ReplacementOfLightFixtures
            SmartMetering
            SolarCollector
            SolarPanelSystem
            SplitAC
            SurfaceCooling
            WaterCooledChillerWithScrewCompressor
            WaterCooledChillerWithScrollCompressor
            WaterCooledChillerWithTurboCompressor
            WaterSavingFixtures
            WaterToWaterHeatPump
            WoodBurningBoiler
         ```

         2. description (leírás): `max. 150 UTF-8 karakter`
         3. **isExcellentLevel*** (kiváló szint-e?): `boolean, true érték esetén "kiváló" szintű,  false érték esetén pedig "jó" szintű`

## 11. modernisationProposals (korszerűsítési javaslatok)

   1. Good/ExcellentLevel (jó/kiváló szint):
      1. energyClassification (energetikai besorolás): `A+++, A++, A+, A, B, C, D, E, F, G, H, I`
      2. co2Emission (CO<sub>2</sub> kibocsátás): `A+++, A++, A+, A, B, C, D, E, F, G, H, I`
   2. renovationPassport (felújítási útlevél): `egyik mezője sem kötelező, a három mező összesen (sortörésekkel együtt) max 2500 UTF-8 karakter lehet. Elfogadott sortörések: json-ban: \n, \r, \r\n, xml-ben: &#10;, &#13;, &#13;&#10;`

## 12. photos (fotódokumentáció)

   1. category (fényképek kategóriái): `a fényképeknél az elfogadott fájltípusok: jpg, png, méretük egyenként max 1MB lehet, összesen max 12 fotót lehet feltölteni, melynek a mérete max 4 MB lehet, base64-ben kódolva`

      1. **coverPhoto*** (borítókép): `1db, a homlokzati kép kategóriába tartozik, ez fog a tanúsítvány elő oldalán is megjelenni`
      2. facade (homlokzat): `min 0db, max 2db kép`
      3. **characteristicHeatExchanger*** (jellemző hőleadó és annak szabályozása): `min 1db max 3db kép`
      4. **characteristicOpeningStructure*** (jellemző nyílászáró): `min 1db, max 3db`
      5. heatGeneratorAndHeatStorageSituation (hőtermelő és a hőtároló helyzete): `min 0db`
      6. renewableEnergyUtilizerSystem (megújuló energiát hasznosító rendszer): `min 0db`
      7. other (egyéb): `min 0db`

   2. note (fényképekhez tartozó megjegyzés mezők): `mezőnként max 150 UTF-8 karater`
   3. content (a fénykép base64 tartalma): `base64 karaktersor`

## 13. calculationsPdfFileContent (számítások PDF fájl)

   1. `A számítások pdf fájl base64 enkódolással, kötelező, max 15 MB. Nem a tanúsítvány pdf tartalmaként, hanem annak csatolmányaként jelenik meg. Ennek megjelenítéséhez ezt támogató megjelenítőre van szükség, pl. Adobe Acrobat Reader.`
