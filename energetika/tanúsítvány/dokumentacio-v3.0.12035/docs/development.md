#Fejlesztőknák szánt konfiguráció
## Nuget repository elérése

A Nuget.Config fájl tartalmazza a szükséges repositoryt. A belépéshez szükséges egy felhasználónév/jelszó (ez az AD jelszó)
A legegyszerűbb módja a konfigurációnak, ha az `%APPDATA%/Nuget/Nuget.config` fájl kiegészítjük a következő tartalommal:
```
  <packageSourceCredentials>
    <Lechner_x0020_NuGet_x0020_proxy>
        <add key="Username" value="USERNAME" />
        <add key="ClearTextPassword" value="PASSWOR>" />
      </Lechner_x0020_NuGet_x0020_proxy>
  </packageSourceCredentials>
```
