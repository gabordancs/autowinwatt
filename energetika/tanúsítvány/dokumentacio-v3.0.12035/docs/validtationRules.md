[TOC]

# Energetikai tanúsítvány json és xml fájlok validációja

## 1. header: fejléc

   1. energyClassification: energetikai besorolás, kötelező mező. Értékkészlet: A+++, A++, A+, A, B, C, D, E, F, G, H, I
   2. co2Emission: Co2 kibocsátás: string, 12-es értékkészlet: A+++, A++, A+, A, B, C, D, E, F, G, H, I

## 2. buildingData: az épület adatai

   1. clientName: megrendelő neve, kötelező mező. Szabadszöveges, min 3, max 50 karakter.
   2. buildingAddress: cím

      1. zipCode: irányítószám, kötelező mező. Értéke: 1000<>9999
      2. settlementName: település neve, kötelező mező, szabadszavas, min 2, max 30
      3. streetName: közterület neve, nem kötelező, szabadszavas, min 1, max 40
      4. streetType: közterület típusa, nem kötelező, szabadszavas, min 2, max 20
      5. houseNumber: házszám, nem kötelező, szabadszavas, min 1, max 20
      6. building: épület, nem kötelező, szabadszavas, min 1, max 20
      7. floor: emelet, nem kötelező, szabadszavas, min 1, max 20
      8. doorNumber: ajtó, nem kötelező, szabadszavas, max 20
      9. staircase: lépcsőház, nem kötelező, szabadszavas, max 20

   3. topographicalNumber: helyrajzi szám, kötelező szabadszavas min 1, max 50, az alábbi karaktereket fogadjuk el: 123456789ABCDFGHJKLMNPRSTVABCDFGHJKLMNPRSTV/
   4. certIssueReason: tanúsítvány kiállításának oka, kötelező mező. Értékkészlet: PurchaseAndSale, NewBuilding, RentingOut, PublicBuilding, Tender, Other
   5. buildingPurpose: épület rendeltetése, kötelező mező, Értékkészlet: ResidentialBuilding, Cottage, AccomodationFacility, HelathCareFacility, EducationalFacility, CulturalFacility, SportsFacility, Office, CommercialBuildings, TransportationAndCommunicationBuildings, IndustrialAndWareHouseBuildings, AgriculturalBuilding, ReligiousAndFuneralPurposeBuilding, LawEnforcementAndDefenseBuilding, OtherShortTermStayBuilding, OtherUnclassifiedBuilding
   6. yearOfConstruct: építési év, kötelező mező, >=1000 és <=aktuális év
   7. majorRenovationYear: jelentős felújítás éve, nem kötelező mező. Max 5 db évszám, vesszővel elválasztva, >=1000 és <=aktuális év.
   8. heritageOrLocalProtection: műemléki vagy helyi védettség, kötelező mező, Értékkészlet: NotProtected, Protected, ArchaeologicalProtection, WorldHeritageProtection, LocalProtection, VariousProtections
   9. usefulFloorArea: hasznos alapterület, kötelező mező, csak pozitív szám lehet, két tizedesjegy megengedett
   10. conditionedVolume: kondicionált térfogat, kötelező mező, nem lehet negatív, de nulla lehet, két tizedesjegy megengedett
   11. numberOfFloors: épület szintjeinek száma, kötelező mező, csak pozitív egész szám, max 100.
   12. buildingAreaToVolumeRatio: épület felület-térfogat aránya, nem kötelező, csak pozitív szám, max 2 tizedesjegy
   13. hasPublicTraffic: közforgalom van-e benne?, kötelező mező, boolean, nem jelenik meg a pdf tanúsítványon
   14. isPublicProperty: köztulajdon-e?, kötelező mező, boolean, nem jelenik meg a pdf tanúsítványon
   15. isFunctionalUnit: rendeltetési egység-e?, kötelező mező, boolean

## 3. efficiencyCategories: hatékonysági kategóriák

    1. buildingCategory: épület típusa, kötelező mező, Értékkészlet: SingleFamilyDetachedHome, TwinHouse, TwinHouseHalf, TerracedHouse, TerracedHouseEnd, TerracedHouseIntermediate, ApartmentBuilding, FlatEndLower, FlatEndIntermediate, FlatEndUpper, FlatGeneralLower, FlatGeneralIntermediate, FlatGeneralUpper, OtherBuilding
    2. isMajorRenovationFulfilled: teljesül a jelentős felújítás követelményszintje?, kötelező mező, boolean
    3. isZeroEmissionFulfilled: teljesül a közel nulla energiaigényű épületek követelményszintje?, kötelező mező, boolean
    4. isSummerHeatProtectionFulfilled: nyári hővédelmi követelményeknek megfelel?, kötelező mező, boolean
    5. renewableEnergyUsage: hasznosított megújuló energia mennyisége, kötelező mező, nem negatív számok, két tizedesjegy megengedett
    6. currentValues: jelenlegi érték

        1. summariesEnergyRating: összesített energetikai jellemző

           1. percentage: pozitív egész szám, kötelező
           2. value: szám: nulla vagy pozitív szám, max 2 tizedesjegy.

        2. co2: co2 kibocsátás

           1. percentage: pozitív egész szám, kötelező
           2. value: nulla vagy pozitív szám, max 2 tizedesjegy

        3.  heatLossFactor: fajlagos hőveszteségtényező

            1. percentage: mindig null értékkel szerepel.
            2. value: nulla vagy pozitív szám, max 2 tizedesjegy

    7. majorRenovationRequirementLevel: jelentős felújítás követelményszintje
       1. summariesEnergyRating: összesített energetikai jellemző
          1. percentage: mindig null értékkel szerepel.
          2. value: nulla vagy pozitív szám, max 2 tizedesjegy
       2. co2: co2 kibocsátás
          1. percentage: mindig null értékkel szerepel.
          2. value: mindig null értékkel szerepel
       3. heatLossFactor: fajlagos hőveszteségtényező
           1. percentage: mindig null értékkel szerepel.
           2. value: nulla vagy pozitív szám, max 2 tizedesjegy
    8. nearZeroEnergyBuildingRequirementLevel:
       1. summariesEnergyRating: összesített energetikai jellemző
          1. percentage: mindig null értékkel szerepel.
          2. value: nulla vagy pozitív szám, max 2 tizedesjegy
       2. co2: co2 kibocsátás
          1. percentage:mindig null értékkel szerepel.
          2. value: nulla vagy pozitív szám, max 2 tizedesjegy
       3. heatLossFactor: fajlagos hőveszteségtényező
          1. percentage: mindig null értékkel szerepel.
          2.  value: nulla vagy pozitív szám, max 2 tizedesjegy


## 4. certifierDetails: tanúsító adatai

   1. name: név, kötelező mező. Szabadszöveges, max 50 karakter.
   2. address:

      1. zipCode: irányítószám, kötelező mező. Éréke: 1000<>9999
      2. settlementName: település neve, kötelező mező, szabadszavas, max 30
      3. streetName: közterület neve, nem kötelező, de ha nem adja meg akkor kötelezően kitöltendő a **topographicalNumber** adat, szabadszavas, max 40
      4. streetType: közterület típusa, nem kötelező, szabadszavas, min 2, max 20
      5. houseNumber: házszám, nem kötelező, szabadszavas, min 1 max 20
      6. building: épület, nem kötelező, szabadszavas, min 1, max 20
      7. floor: emelet, nem kötelező, szabadszavas, min 1, max 20
      8. doorNumber: ajtó, nem kötelező, szabadszavas, min 1, max 20
      9. staircase: lépcsőház, nem kötelező, szabadszavas, min 1, max 20

   3. topographicalNumber: helyrajzi szám, csak akkor kötelező ha nem adott meg **streetName** adatot, szabadszavas max 50, az alábbi karaktereket fogadjuk el: 123456789ABCDFGHJKLMNPRSTVABCDFGHJKLMNPRSTV/,
   4. phoneNumber: telefon, kötelező mező, max 20, csak egyetlen telefonszám szerepelhet benne, számok és karakterek szerepelhetnek benne de betű nem "+36 20 432 67 89",
   5. email: e-mail, kötelező mező, szabadszavas, min 5, max 50, és szintaktikailag érvényesnek kell lennie
   6. eligibilityNumber: jogosultsági szám, kötelező mező, formátum: “TÉ {megyekód}-{tagszám}”. fix tag: TÉ, megye szám: 01-21, csak szám, tagszám: min 4 , max 5 karakter, csak szám. pl TÉ 06-0366 , TÉ 16-50658
   7. softwareAndVersion: szoftver és verzió, kötelező mező, min 1 max 40

## 5. validity: érvényesség

    1. siteInspectionDate: helyszíni szemle dátuma, kötelező mező, európai dátum forma: éééé.hh.nn.

## 6. boundaryAndOpeningStructures: határoló és nyílászáró szerkezetek

   1. typeOfStructure: szerkezet típusa, nem kötelező, értékkészlet: facadeWall, flatRoof, structuresEnclosingHeatedAtticSpace, floorStructureBelowAtticAndCrawlSpace, floorStructureAboveArchesAndPassages, lowerCeilingStructureAboveUnheatedSpaces, glazing, flatRoof, structuresEnclosingHeatedAtticSpace, specialGlazingWithHighAcousticOrSecurityRequirements, facadeOpeningsWithWoodenOrPvcFrames, facadeOpeningsWithMetalFrames, curtainWall, glassRoof, roofSkylightSmokeVentDome, roofPlaneWindow, industrialAndFireResistantDoorsAndGates, doorBetweenFacadeOrHeatedAndUnheatedSpaces, gateBetweenFacadeOrHeatedAndUnheatedSpaces, wallBetweenHeatedAndUnheatedSpaces, structureBetweenAdjacentHeatedBuildingsAndBuildingSections, foundationWall, wallInContactWithTheGroundInNewBuildings, groundLevelFloorInNewBuildings, traditionalEnergyCollectingWalls
   2. energeticQualities: energetikai minőség

      1. quality: minősítés, értékkészlet: bad, poor, average, good, excellent

## 7. buildingServicesSystemEnergeticQuality: épülettechnikai rendszerek

   1. heatingSystem: fűtési rendszer, nem kötelező, értékkészlet: bad, poor, average, good, excellent
   2. heatingAndVentilationSystem: fűtési és légtechnikai renszer, nem kötelező, értékkészlet: bad, poor, average, good, excellent
   3. hotWaterSupplySystem: használati melegvíz ellátó rendszer, nem kötelező, értékkészlet: bad, poor, average, good, excellent
   4. coolingSystem: hűtési rendszer, nem kötelező, értékkészlet: bad, poor, average, good, excellent
   5. integratedLighting: beépített világítás, nem kötelező, értékkészlet: bad, poor, average, good, excellent

## 8. usingAlternativeEnergy: alternatív energiák használata

   1. alternativeEnergies: alternatív energiák, nem kötelező, értékkészlet: SolarPanels, SolarCollectors, Biomass, HeatPump, CombinedHeatAndPower, DistrictHeatingOrCooling

## 9. modernisationProposalDetails: korszerűsítési javaslatok (részletezése)

   1. structureType: szerkezet típusa, értékkészlet: facadeWall, flatRoof, structuresEnclosingHeatedAtticSpace, floorStructureBelowAtticAndCrawlSpace, floorStructureAboveArchesAndPassages, lowerCeilingStructureAboveUnheatedSpaces, glazing, flatRoof, structuresEnclosingHeatedAtticSpace, floorStructureBelowAtticAndCrawlSpace, floorStructureAboveArchesAndPassages, lowerCeilingStructureAboveUnheatedSpaces, glazing, specialGlazingWithHighAcousticOrSecurityRequirements, facadeOpeningsWithWoodenOrPvcFrames, facadeOpeningsWithMetalFrames, curtainWall, glassRoof, roofSkylightSmokeVentDome, roofPlaneWindow, industrialAndFireResistantDoorsAndGates, doorBetweenFacadeOrHeatedAndUnheatedSpaces, gateBetweenFacadeOrHeatedAndUnheatedSpaces, wallBetweenHeatedAndUnheatedSpaces, structureBetweenAdjacentHeatedBuildingsAndBuildingSections, foundationWall, wallInContactWithTheGroundInNewBuildings, groundLevelFloorInNewBuildings, traditionalEnergyCollectingWalls 
   2. structureNote: szerkezet rövid leírása, nem kötelező, max. 20 karakter
   3. airTightness: légtömörség, nyílászáró esetében kötelező mező, értékkészlet: poor, average, good, excellent
   4. note: megjegyzés, nem kötelező, max. 150 karakter
   5. proposalEnergeticQualities: javaslat energetikai minőségre, nem kötelező

      1. quality: minősítés, értékkészlet: good, excellent

## 10. modernisationProposalsOfBuildingServicesSystems: korszerűsítési javaslatok épülettechnikai rendszerekhez

   1. buildingServiceSystemType: épülettechnikai rendszer típusa, kötelező mező, értékkészlet: HeatingSystem, HeatingAndVentilationSystem, HotWaterSupplySystem, CoolingSystem, IntegratedLighting, Other
   2. note: megjegyzés, nem kötelező, max 20 karakter
   3. actualEnergeticQuality: jelenlegi energetikai minőség, nem kötelező

      1. quality: minőség, értékkészlet: bad, poor, average, good, excellent
      2. note: megjegyzés, max 150 karakter

   4. recommendedModernisations: javasolt korszerűsítések

      1. modernisationCategory: javasolt korszerűsítési kategória, nem kötelező, értékkészlet: HeatGeneratorReplacement, HeatDistributionStorageControlEmitter, HeatRecoveryDistributionStorageControlEmitter, HeatDistributionStorageControl
      2. systemElements: rendszerelemek

         1. name: név, értékkészlet: CondensingBoiler, AirToWaterHeatPump, DepartingAirToWaterHeatPump, AirToAirHeatPump, WaterToWaterHeatPump, GroundSourceHeatToWaterHeatPump, WoodBurningBoiler, PelletBurningBoiler, ModernRegulatedConvector, Other, InsulationOfPipelines, PumpReplacement, Regulation, Adjustment, HeatExchangers, Anemostat, DesigningSunshades, ControllingSunshades, AutomaticOnAndOff, AutomaticOnDimmable, ReplacementOfCirculationPump, BuildingManagementSystem, FanCoilUnits, SurfaceCooling, LightSourcesReplacement, GasPoweredHeatPumpUtilizingWasteHeat, GasPoweredHeatPump, ElectricBoilerWithHeatPump, HeatRecoveryInstallation, CeilingCoolingPipelines, IndirectHeatedWaterTank, ManualOnAndAutomaticOffSwitching, ManualOnSwitchingDimmable, ChilledBeam, SplitAC, CondenserHeatUtilization, ReplacementOfLightFixtures, AirDuctNetworkModernisation, InsulationOfAirDucts, AirCooledFanCoil, SolarPanelSystem, SolarCollector, SmartMetering, PassiveSolarSolutions, Recirculation, FreeCooling, GroundSourceHeatToWaterElectricHeatPump, GroundSourceHeatExchanger, AirPreHeatingWithGroundSourceHeatExchanger, DistrictHeating, AutomationOfNaturalVentilation, ImprovingNaturalLighting, FanReplacement, EmergencyLighting, WaterCooledChillerWithScrewCompressor, WaterCooledChillerWithScrollCompressor, WaterCooledChillerWithTurboCompressor, WaterSavingFixtures
         2. description: leírás, nem kötelező, max. 150 karakter
         3. isExcellentLevel: kiváló szint-e?, kötelező mező, boolean, true érték esetén "kiváló" szintű,  false érték esetén pedig "jó" szintű

## 11. modernisationProposals: korszerűsítési javaslatok

   1. Good/ExcellentLevel: jó/kiváló szint

      1. energyClassification: energetikai besorolás, nem kötelező, értékkészlet: A+++, A++, A+, A, B, C, D, E, F, G, H, I
      2. co2Emission: co2 kibocsátás, nem kötelező, értékkészlet: A+++, A++, A+, A, B, C, D, E, F, G, H, I

   2. renovationPassport: felújítási útlevél, egyik mezője sem kötelező, a három mező összesen (sortörésekkel együtt) max 2500 karakter lehet. Elfogadott sortörések: jnos-ban: \n, \r, \r\n, xml-ben: &#10;, &#13;, &#13;&#10;

## 12. photos: fotódokumentáció

   1. category: fényképek kategóriái a fényképeknél az elfogadott fájltípusok: jpg, png, méretük egyenként max 1MB lehet, összesen max 12 fotót lehet feltölteni, melynek a mérete max 4 MB lehet.

      1. coverPhoto: borítókép, kötelező mező, homlokzati kép kategóriába tartozik
      2. facade: homlokzat, nem kötelező
      3. characteristicHeatExchanger: jellemző hőleadó és annak szabályozása, kötelező mező
      4. characteristicOpeningStructure: jellemző nyílászáró, kötelező mező
      5. heatGeneratorAndHeatStorageSituation: hőtermelő és a hőtároló helyzete, nem kötelező
      6. renewableEnergyUtilizerSystem: megújuló energiát hasznosító rendszer, nem kötelező
      7. other: egyéb, nem kötelező

   2. note: fényképekhez tartozó megjegyzés mezők, nem kötelező, mezőnként max 150 karater
   3. content: a fénykép base64 tartalma

## 13. calculationsPdfFileContent: számítások PDF fájl

   1. A számítások pdf fájl base64 enkódolással, kötelező, max 15 MB. Nem a tanúsítvány pdf tartalmaként, hanem annak csatolmányaként jelenik meg. Ennek megjelenítéséhez ezt támogató megjelenítőre van szükség pl. Adobe Acrobat Reader.
