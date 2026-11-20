# Windows App Packaging, NativeAOT, Code Signing & Auto-Updates (.NET 9/10)

> **Scope:** Unpackaged vs. self-contained vs. single-file publishing, ReadyToRun vs. NativeAOT (`NETSDK1168` in WPF vs. WinUI 3 / CsWinRT), MSIX & External Location Sparse Packages, WiX Toolset v5 vs. Inno Setup 6 (per-user vs. per-machine + WebView2 / .NET bootstrappers), Velopack vs. MSIX AppInstaller auto-updates, and Azure Artifact Signing / SmartScreen engineering.
>
> **Related:** See [compiler-traps-and-compat.md](compiler-traps-and-compat.md) for `NETSDK1168`, `IL3000`, `C00CE014`, and Windows `19041`/`26100` requirements, [webview2-and-hybrid-apps.md](webview2-and-hybrid-apps.md) for Evergreen vs. Fixed Version WebView2 deployment, [background-services-and-ipc.md](background-services-and-ipc.md) for WiX v5 `<ServiceInstall>` & `sc.exe failure` service recovery, and [security-hardening-and-enterprise.md](security-hardening-and-enterprise.md) for AppLocker/WDAC compatibility, SBOMs, and deterministic CI builds.

## Table of Contents

1. [Deployment Mode Decision Matrix](#1-deployment-mode-decision-matrix)
2. [Unpackaged .NET Publishing](#2-unpackaged-net-publishing-framework-dependent-self-contained--single-file)
3. [ReadyToRun vs. NativeAOT](#3-readytorun-publishreadytorun-vs-nativeaot-publishaot)
4. [MSIX & External Location Sparse Packages](#4-msix-package-identity--external-location-sparse-packages)
5. [WiX Toolset v5 vs. Inno Setup 6](#5-traditional-installers-wix-toolset-v5-vs-inno-setup-6)
6. [Velopack vs. MSIX AppInstaller](#6-auto-update-engineering-velopack-vs-msix-appinstaller)
7. [Code Signing & SmartScreen](#7-code-signing--windows-smartscreen-engineering)

---

## 1. Deployment Mode Decision Matrix

| Mode | Typical Size | Cold Start | Target Prerequisites | Package Identity APIs | Default Update Path |
|---|---|---|---|---|---|
| **Framework-Dependent** | ~1–15 MB | Fast (shared cache) | `.NET Desktop Runtime` | No (unless Sparse Package) | External installer / Velopack |
| **Self-Contained (Loose)** | ~130–180 MB | Fast (`R2R`) | None | No (unless Sparse Package) | Velopack / Inno / WiX |
| **Self-Contained Single-File** | ~65–160 MB (1 EXE) | Slower first run (extraction) | None | No | External replace / Velopack |
| **NativeAOT (`PublishAot`)** | ~3–25 MB (Win32) / ~25–60 MB (WinUI 3) | Fastest (no JIT) | None (WinUI 3: Windows App SDK or self-contained) | Optional (MSIX or unpackaged) | Velopack / Inno / MSIX |
| **MSIX (Full Package)** | ~15–180 MB | Fast | Win10/11; trusted cert or Store | **Yes** (`Toast`, `StartupTask`, `ShareTarget`, AI) | Store or `.appinstaller` |
| **Installer + Sparse Package** | Installer + ~50 KB `.msix` | Fast | Win10 2004+ (`19041+`); signed `.msix` | **Yes** (attached to unpackaged EXE) | Velopack / Inno / WiX |

**Rule of Thumb:** Consumer WPF/WinUI 3 app with delta updates -> Self-contained loose + **Velopack** + **Azure Artifact Signing**. Enterprise GPO/Intune rollout -> **WiX Toolset v5** `.msi` or signed **MSIX** `.appinstaller`. Tiny tray/helper (< 10 MB, sub-50 ms cold start) -> C# **`PublishAot=true`** + `CsWin32` (or C++/WinRT).

---

## 2. Unpackaged .NET Publishing: Framework-Dependent, Self-Contained & Single-File

### 2.1 `.csproj` Publish Profiles (`net9.0-windows` / `net10.0-windows`)

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net10.0-windows</TargetFramework>
    <UseWPF>true</UseWPF>
    <RuntimeIdentifier>win-x64</RuntimeIdentifier>
    <ApplicationManifest>app.manifest</ApplicationManifest>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <SelfContained>true</SelfContained>
    <!-- Gate single-file packing to Release/publish so Debug/Snoop stays unpackaged -->
    <PublishSingleFile Condition="'$(Configuration)' == 'Release'">true</PublishSingleFile>
    <!-- CRITICAL FOR WPF: Bundles wpfgfx_cor3.dll, PresentationNative_cor3.dll, PenImc_cor3.dll, D3DCompiler_47_cor3.dll -->
    <IncludeNativeLibrariesForSelfExtract>true</IncludeNativeLibrariesForSelfExtract>
    <EnableCompressionInSingleFile>true</EnableCompressionInSingleFile>
    <PublishReadyToRun>true</PublishReadyToRun>
    <!-- Never set PublishTrimmed=true or PublishAot=true with UseWPF=true (NETSDK1168) -->
  </PropertyGroup>
</Project>
```

CLI publish commands for multi-channel builds:

```powershell
# Framework-dependent (requires .NET 10 Desktop Runtime)
dotnet publish -c Release -r win-x64 --self-contained false -o ./publish/fdd
# Self-contained loose files (best input for Velopack, Inno Setup, or WiX v5)
dotnet publish -c Release -r win-x64 --self-contained true -p:PublishReadyToRun=true -o ./publish/win-x64
# Self-contained portable single-file EXE
dotnet publish -c Release -r win-x64 --self-contained true `
  -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:PublishReadyToRun=true -o ./publish/single
```

### 2.2 WPF Single-File Pitfalls & Temporary Extraction

1. **Loose native DLL surprise:** Omitting `<IncludeNativeLibrariesForSelfExtract>true</IncludeNativeLibrariesForSelfExtract>` leaves WPF native binaries (`wpfgfx_cor3.dll`, `PresentationNative_cor3.dll`, `PenImc_cor3.dll`, `D3DCompiler_47_cor3.dll`) outside the `.exe`. Copying only the `.exe` crashes on startup.
2. **Temp extraction & AV tax:** On launch, `.NET` extracts bundled native libraries into `%TEMP%\.net\<AppName>\<hash>\` (overridable via `DOTNET_BUNDLE_EXTRACT_BASE_DIR`). Antivirus scans and restricted `%TEMP%` policies slow cold start. Avoid `<IncludeAllContentForSelfExtract>true</IncludeAllContentForSelfExtract>`, which forces legacy extraction of *every* managed `.dll` to disk instead of loading them from memory.
3. **`Assembly.Location` returns `""` (`IL3000`):** Bundled managed assemblies have no physical path. Always resolve adjacent files via `AppContext.BaseDirectory` and executable path via `Environment.ProcessPath`:

```csharp
using System;
using System.IO;

namespace MyApp.Packaging;

public static class AppPaths
{
    public static string GetPackagedAssetPath(string relativePath) =>
        Path.Combine(AppContext.BaseDirectory, relativePath);

    public static string GetExecutablePath() =>
        Environment.ProcessPath
        ?? throw new InvalidOperationException("Process executable path is unavailable.");
}
```

> **Installer / Velopack rule:** Prefer **loose self-contained** (`PublishSingleFile=false`) + `PublishReadyToRun=true` when shipping via **Velopack**, **Inno Setup**, or **WiX** — zero `%TEMP%\.net` extraction, per-DLL binary delta patches, and cleaner AV scanning.

---

## 3. ReadyToRun (`PublishReadyToRun`) vs. NativeAOT (`PublishAot`)

| Dimension | ReadyToRun (`PublishReadyToRun=true`) | NativeAOT (`PublishAot=true`) |
|---|---|---|
| **Runtime model** | Ships CLR + JIT + pre-compiled R2R images + IL | Compiles IL directly to native code (`ILCompiler`); no JIT |
| **Tiered Compilation** | Active (`TieredCompilation=true`): R2R/Tier-0 startup + Tier-1 PGO re-JIT | N/A — tuned at publish via `OptimizationPreference` (`Speed` / `Size`) |
| **Binary size** | ~1.5×–3× larger than pure IL | Smallest self-contained footprint (full IL trimming) |
| **WPF (`UseWPF=true`)** | **Supported** (recommended) | **Unsupported (`NETSDK1168`)** |
| **WinUI 3 (`WindowsAppSDK`)** | Supported | **Supported** (`CsWinRT >= 2.1.6` / `2.2+` + trim-safe code) |
| **C# Win32 (`CsWin32`) / Console** | Supported | **Supported** (smallest EXE, fastest startup) |
| **Reflection & `Assembly.Load`** | Full dynamic reflection, BAML, XAML `Binding` | Restricted (`IL2026`/`IL3053`; requires `[JsonSerializable]` source gen) |

### 3.1 Why WPF Fails `PublishTrimmed` and `PublishAot` (`NETSDK1168`)

Setting `<PublishTrimmed>true</PublishTrimmed>` or `<PublishAot>true</PublishAot>` with `<UseWPF>true</UseWPF>` fails compilation with **`NETSDK1168: WPF is not supported or recommended with trimming enabled`**. WPF relies on runtime BAML decoding, `TypeConverter` discovery, `DynamicResource` resolution, reflection-driven `Binding`, `UIAutomation` peers, and built-in COM interop that static IL trimming breaks. Use **`PublishReadyToRun=true`** with default **`TieredCompilation=true`** for WPF.

### 3.2 NativeAOT `.csproj` for Win32 / Console & WinUI 3

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net10.0-windows10.0.19041.0</TargetFramework>
    <RuntimeIdentifier>win-x64</RuntimeIdentifier>
    <ApplicationManifest>app.manifest</ApplicationManifest>
    <PublishAot>true</PublishAot>
    <OptimizationPreference>Speed</OptimizationPreference> <!-- or Size -->
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <DebugType>pdbonly</DebugType> <!-- Keep PDB separate for crash symbolication -->
  </PropertyGroup>
</Project>
```

For **WinUI 3 NativeAOT**: require **`Microsoft.Windows.CsWinRT >= 2.1.6` (or `2.2+`)**, replace reflection `JsonSerializer` calls with `[JsonSerializable]` source generators, prefer compiled `x:Bind` over `{Binding}`, and add `<WindowsAppSDKSelfContained>true</WindowsAppSDKSelfContained>` for unpackaged distribution without requiring a separate Windows App Runtime installer.

---

## 4. MSIX, Package Identity & External Location Sparse Packages

### 4.1 What Package Identity Unlocks

| Capability | Unpackaged EXE | Full MSIX | EXE + Sparse Package |
|---|---|---|---|
| Interactive Toasts (`AppNotificationManager` + COM activation) | Manual AUMID/COM setup | Native | **Native** |
| Windows Settings Startup (`windows.startupTask`) | Legacy HKCU `Run` key | Native | **Native** |
| Share Target (`windows.shareTarget`) & Background Tasks | No / Restricted | Native | **Native** |
| Windows AI local APIs | Restricted | Native | **Native** |
| Clean OS uninstall & VFS isolation | Manual uninstaller | **Guaranteed** | App keeps traditional installer |
| Arbitrary install path (`Program Files` / custom folder) | Yes | VFS redirected | **Yes** |

### 4.2 Store vs. Sideloading

- **Microsoft Store:** Store certification re-signs your `.msix` / `.msixbundle` and handles delta updates automatically.
- **Sideloading (`Add-AppxPackage` / `.appinstaller`):** Installs cleanly without Developer Mode **only** when signed by a certificate chaining to a machine-trusted Root CA (public CA / Azure Artifact Signing, or enterprise GPO-pushed root CA).

### 4.3 External Location Sparse Packages (Identity for Traditional Installers)

On **Windows 10 2004 (Build 19041)+**, attach an identity-only `.msix` (`AppxManifest.xml` + `Assets/`) to binaries installed by Inno Setup, WiX, or Velopack. Note `<uap10:AllowExternalContent>true</uap10:AllowExternalContent>` sits inside `<Properties>`, and `Identity.Publisher` must match your signing certificate's `Subject` character-for-character.

```xml
<?xml version="1.0" encoding="utf-8"?>
<Package
    xmlns="http://schemas.microsoft.com/appx/manifest/foundation/windows10"
    xmlns:uap="http://schemas.microsoft.com/appx/manifest/uap/windows10"
    xmlns:uap10="http://schemas.microsoft.com/appx/manifest/uap/windows10/10"
    xmlns:desktop="http://schemas.microsoft.com/appx/manifest/desktop/windows10"
    xmlns:com="http://schemas.microsoft.com/appx/manifest/com/windows10"
    xmlns:rescap="http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities"
    IgnorableNamespaces="uap uap10 desktop com rescap">
  <Identity Name="MyCompany.MyApp" Publisher="CN=MyCompany LLC, O=MyCompany LLC, C=US"
            Version="1.0.0.0" ProcessorArchitecture="x64" />
  <Properties>
    <uap10:AllowExternalContent>true</uap10:AllowExternalContent>
    <DisplayName>MyApp</DisplayName>
    <PublisherDisplayName>MyCompany LLC</PublisherDisplayName>
    <Logo>Assets\StoreLogo.png</Logo>
  </Properties>
  <Dependencies>
    <TargetDeviceFamily Name="Windows.Desktop" MinVersion="10.0.19041.0" MaxVersionTested="10.0.26100.0" />
  </Dependencies>
  <Capabilities>
    <rescap:Capability Name="runFullTrust" />
  </Capabilities>
  <Applications>
    <Application Id="MyApp" Executable="MyApp.exe" uap10:TrustLevel="mediumIL" uap10:RuntimeBehavior="win32App">
      <uap:VisualElements DisplayName="MyApp" Description="Native Windows desktop app"
                          Square150x150Logo="Assets\Square150x150Logo.png"
                          Square44x44Logo="Assets\Square44x44Logo.png" BackgroundColor="transparent" />
      <Extensions>
        <desktop:Extension Category="windows.startupTask" Executable="MyApp.exe" EntryPoint="Windows.FullTrustApplication">
          <desktop:StartupTask TaskId="MyAppStartup" Enabled="false" DisplayName="MyApp" />
        </desktop:Extension>
        <desktop:Extension Category="windows.toastNotificationActivation">
          <desktop:ToastNotificationActivation ToastActivatorCLSID="B4A8B2E4-3F4B-4F0F-9D6E-8C2C1A9A7701" />
        </desktop:Extension>
        <com:Extension Category="windows.comServer">
          <com:ComServer>
            <com:ExeServer Executable="MyApp.exe" Arguments="--toast-activated" DisplayName="MyApp Toast Activator">
              <com:Class Id="B4A8B2E4-3F4B-4F0F-9D6E-8C2C1A9A7701" />
            </com:ExeServer>
          </com:ComServer>
        </com:Extension>
      </Extensions>
    </Application>
  </Applications>
</Package>
```

```powershell
# /nv skips package payload file validation (MyApp.exe lives in the external install directory)
MakeAppx.exe pack /d ".\SparsePackageContent" /p ".\MyApp.identity.msix" /nv /o
signtool.exe sign /fd SHA256 /tr "http://timestamp.acs.microsoft.com" /td SHA256 ... ".\MyApp.identity.msix"
```

```csharp
using System;
using System.Threading.Tasks;
using Windows.Management.Deployment;

namespace MyApp.Packaging;

public static class SparsePackageRegistrar
{
    // Requires TargetFramework >= net9.0-windows10.0.19041.0 (or net10.0-windows10.0.19041.0)
    public static async Task RegisterExternalIdentityAsync(string sparseMsixPath, string installDirectory)
    {
        var packageManager = new PackageManager();
        var options = new AddPackageOptions
        {
            ExternalLocationUri = new Uri(installDirectory, UriKind.Absolute)
        };

        DeploymentResult result = await packageManager.AddPackageByUriAsync(
            new Uri(sparseMsixPath, UriKind.Absolute),
            options);

        if (!result.IsRegistered)
        {
            int hr = result.ExtendedErrorCode?.HResult ?? unchecked((int)0x80004005);
            throw new InvalidOperationException(
                $"Sparse package registration failed (0x{hr:X8}): {result.ErrorText}");
        }
    }
}
```

> **CsWinRT note:** `DeploymentResult.ExtendedErrorCode` is projected as `System.Exception?`, not an integer. Always check `result.IsRegistered` and read `result.ExtendedErrorCode?.HResult`.

---

## 5. Traditional Installers: WiX Toolset v5 vs. Inno Setup 6

| Criterion | WiX Toolset v5 (`.msi` / Burn `.exe`) | Inno Setup 6 (`setup.exe`) |
|---|---|---|
| **Output** | Windows Installer `.msi` or Burn bootstrapper `.exe` | Single compressed `.exe` |
| **Enterprise IT / Intune** | **Native** (GPO, `msiexec`, MST transforms, rollback) | Silent CLI flags wrapped in `.intunewin` |
| **Scope control** | `Scope="perUser"`, `"perMachine"`, or `"perUserOrMachine"` | `PrivilegesRequired=lowest` + `PrivilegesRequiredOverridesAllowed=dialog` (`{autopf}`) |
| **File harvesting** | Native **`<Files Include="..." />`** (no `heat.exe`) | `[Files]` `recursesubdirs` |
| **Runtime checks** | `WixToolset.Netfx.wixext` (`<netfx:DotNetCompatibilityCheck>`) | `[Code]` Pascal Script + `[Run]` |
| **Silent command** | `msiexec /i MyApp.msi /qn /norestart` | `MyApp-Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART` |

**Per-User (`%LocalAppData%\Programs\MyApp`) vs. Per-Machine (`C:\Program Files\MyApp`):** Prefer **per-user** for consumer/auto-updating apps (zero UAC prompt, silent updates without elevation, avoids UIPI drag-drop breaks from launching unelevated GUIs out of an elevated setup). Choose **per-machine** only for shared multi-user tools, Windows Services, or admin-locked enterprise policies.

### 5.1 WiX Toolset v5 (`.wixproj` + `Package.wxs`)

```xml
<!-- MyApp.Installer.wixproj -->
<Project Sdk="WixToolset.Sdk/5.0.2">
  <PropertyGroup><InstallerPlatform>x64</InstallerPlatform></PropertyGroup>
  <ItemGroup>
    <PackageReference Include="WixToolset.UI.wixext" Version="5.0.2" />
    <PackageReference Include="WixToolset.Netfx.wixext" Version="5.0.2" />
    <ProjectReference Include="..\MyApp\MyApp.csproj" />
  </ItemGroup>
</Project>
```

```xml
<!-- Package.wxs (Per-user MSI + .NET Desktop Runtime check) -->
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs"
     xmlns:ui="http://wixtoolset.org/schemas/v4/wxs/ui"
     xmlns:netfx="http://wixtoolset.org/schemas/v4/wxs/netfx">
  <Package Name="MyApp" Manufacturer="MyCompany" Version="1.0.0.0" Scope="perUser"
           UpgradeCode="E214F93A-6E7D-4D3E-8B29-1E56C4790A12">
    <MajorUpgrade DowngradeErrorMessage="A newer version of [ProductName] is already installed." />
    <!-- Omit if publishing SelfContained=true -->
    <netfx:DotNetCompatibilityCheck Id="DotNetDesktop10Check" Property="DOTNETDESKTOP10"
        RuntimeType="desktop" Platform="x64" Version="10.0.0" RollForward="major" />
    <Launch Condition="Installed OR DOTNETDESKTOP10 = 0"
            Message="[ProductName] requires .NET 10 Desktop Runtime (x64)." />
    <StandardDirectory Id="LocalAppDataFolder">
      <Directory Name="Programs">
        <Directory Id="INSTALLFOLDER" Name="MyApp" />
      </Directory>
    </StandardDirectory>
    <Feature Id="MainFeature" Title="MyApp" Level="1">
      <ComponentGroupRef Id="AppPublishedFiles" />
    </Feature>
    <ui:WixUI Id="WixUI_InstallDir" InstallDirectory="INSTALLFOLDER" />
  </Package>
  <Fragment>
    <ComponentGroup Id="AppPublishedFiles" Directory="INSTALLFOLDER">
      <Files Include="..\MyApp\bin\Release\net10.0-windows\win-x64\publish\**" />
    </ComponentGroup>
  </Fragment>
</Wix>
```

> **Dual-scope MSI (`Scope="perUserOrMachine"`):** Pass `MSIINSTALLPERUSER=1` for per-user silent install or `ALLUSERS=1` (elevated) for machine-wide silent install alongside `msiexec /i MyApp.msi /qn /norestart`.

### 5.2 Inno Setup 6 (Per-User/Dual-Scope + WebView2 & .NET Bootstrapper)

```ini
; installer.iss
[Setup]
AppId={{8E9B7D6A-5120-4C81-9E12-A3B4C5D6E7F8}
AppName=MyApp
AppVersion=1.0.0
AppPublisher=MyCompany
DefaultDirName={autopf}\MyApp
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
OutputBaseFilename=MyApp-Setup-1.0.0

[Files]
Source: "publish\win-x64\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "prereqs\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: IsWebView2RuntimeNeeded

[Icons]
Name: "{autoprograms}\MyApp"; Filename: "{app}\MyApp.exe"
Name: "{autodesktop}\MyApp"; Filename: "{app}\MyApp.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing WebView2 Runtime..."; Check: IsWebView2RuntimeNeeded; Flags: waituntilterminated
; For framework-dependent apps, similarly bundle & run windowsdesktop-runtime-10.0.x-win-x64.exe with: /install /quiet /norestart
Filename: "{app}\MyApp.exe"; Description: "{cm:LaunchProgram,MyApp}"; Flags: nowait postinstall skipifsilent

[Code]
function IsWebView2RuntimeNeeded(): Boolean;
var
  Version: string;
begin
  Result := True;
  if RegQueryStringValue(HKEY_LOCAL_MACHINE,
       'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
     or RegQueryStringValue(HKEY_LOCAL_MACHINE,
       'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
     or RegQueryStringValue(HKEY_CURRENT_USER,
       'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version) then
  begin
    if (Version <> '') and (Version <> '0.0.0.0') then
      Result := False;
  end;
end;
```

Silent overrides: `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CURRENTUSER` (or `/ALLUSERS`). With `PrivilegesRequired=lowest`, post-install launch runs at standard `mediumIL`. If using `PrivilegesRequired=admin`, avoid launching an elevated GUI from `[Run]` (`runasoriginaluser` drops elevation).

---

## 6. Auto-Update Engineering: Velopack vs. MSIX AppInstaller

### 6.1 Velopack (Full Replacement for Squirrel.Windows / Clowd.Squirrel)

Velopack uses a native Rust bootstrapper/updater (no `.NET Framework 4.8` dependency), atomic side-by-side swaps, and binary delta `.nupkg` patches.

**1. WPF `.csproj` (replaces auto-generated `Main` to prevent `CS0017`):**

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net10.0-windows</TargetFramework>
    <UseWPF>true</UseWPF>
    <ApplicationManifest>app.manifest</ApplicationManifest>
    <PublishReadyToRun Condition="'$(Configuration)' == 'Release'">true</PublishReadyToRun>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <StartupObject>MyApp.App</StartupObject>
  </PropertyGroup>
  <ItemGroup>
    <ApplicationDefinition Remove="App.xaml" />
    <Page Include="App.xaml" />
    <PackageReference Include="Velopack" Version="0.0.1298" />
  </ItemGroup>
</Project>
```

**2. Initialize `VelopackApp` at the very start of `Main` (before WPF loads XAML or locks files):**

```csharp
using System;
using System.Windows;
using Velopack;

namespace MyApp
{
    public partial class App : Application
    {
        [STAThread]
        public static void Main(string[] args)
        {
            VelopackApp.Build().OnFirstRun(v => { /* Optional onboarding */ }).Run();
            var app = new App();
            app.InitializeComponent();
            app.Run();
        }
    }
}
```

**3. Update manager (`UpdateManager` does NOT implement `IDisposable` — never wrap in `using`):**

```csharp
using System;
using System.Threading;
using System.Threading.Tasks;
using Velopack;
using Velopack.Exceptions;
using Velopack.Sources;

namespace MyApp.Updates;

public sealed class AppUpdateService
{
    private readonly UpdateManager _updateManager;

    public AppUpdateService(string githubRepoUrl, bool includePrerelease = false)
    {
        // Use SimpleWebSource("https://updates.example.com/") for S3/CDN/static web feeds
        var source = new GithubSource(githubRepoUrl, accessToken: null, prerelease: includePrerelease);
        _updateManager = new UpdateManager(source);
    }

    public async Task<bool> CheckAndInstallUpdateAsync(
        Action<int>? onProgress = null, CancellationToken cancellationToken = default)
    {
        if (!_updateManager.IsInstalled) return false;
        try
        {
            UpdateInfo? newVersion = await _updateManager.CheckForUpdatesAsync();
            if (newVersion is null) return false;

            await _updateManager.DownloadUpdatesAsync(newVersion, onProgress, cancellationToken);
            _updateManager.ApplyUpdatesAndRestart(newVersion);
            return true;
        }
        catch (NotInstalledException)
        {
            return false;
        }
    }
}
```

**4. Pack & upload release assets:**

```powershell
dotnet tool update -g vpk
dotnet publish -c Release -r win-x64 --self-contained true -p:PublishReadyToRun=true -o ./publish/win-x64

# Generates releases.win.json, *-full.nupkg, *-delta.nupkg, and MyApp-win-Setup.exe
vpk pack --packId "MyApp" --packVersion "1.2.0" --packDir "./publish/win-x64" --mainExe "MyApp.exe" --outputDir "./releases"
```

Upload **all** files in `./releases` to GitHub Releases or your HTTPS feed. Keep prior `releases.win.json` + `-full.nupkg` available during CI builds so `vpk pack` computes small delta `.nupkg` patches.

### 6.2 MSIX `.appinstaller` (2021 Schema)

```xml
<?xml version="1.0" encoding="utf-8"?>
<AppInstaller
    xmlns="http://schemas.microsoft.com/appx/appinstaller/2021"
    Version="1.2.0.0"
    Uri="https://downloads.example.com/myapp/MyApp.appinstaller">
  <MainPackage
      Name="MyCompany.MyApp"
      Publisher="CN=MyCompany LLC, O=MyCompany LLC, C=US"
      Version="1.2.0.0"
      ProcessorArchitecture="x64"
      Uri="https://downloads.example.com/myapp/MyApp_1.2.0.0_x64.msix" />
  <UpdateSettings>
    <!-- 2021 schema adds ShowPrompt and UpdateBlocksActivation -->
    <OnLaunch HoursBetweenUpdateChecks="0" ShowPrompt="true" UpdateBlocksActivation="true" />
    <AutomaticBackgroundTask />
    <ForceUpdateFromAnyVersion>true</ForceUpdateFromAnyVersion>
  </UpdateSettings>
</AppInstaller>
```

---

## 7. Code Signing & Windows SmartScreen Engineering

### 7.1 EV vs. OV vs. Azure Artifact Signing

1. **Hardware HSM Mandate (June 2023):** CA/Browser Forum rules require **all** publicly trusted OV and EV private keys to reside in certified hardware modules (FIPS 140-2 Level 2+ USB tokens or cloud HSMs). Exportable `.pfx` files for public trust are obsolete.
2. **460-Day Max Validity (March 2026, Ballot CSC-31):** Shortened cert lifespans favor cloud-managed rotation over physical USB tokens.
3. **No EV SmartScreen shortcut:** Microsoft decoupled automatic SmartScreen reputation bypass from EV certificates; **both OV and EV** build SmartScreen trust via publisher continuity and download/execution telemetry.
4. **Azure Artifact Signing (formerly Trusted Signing):** Cloud HSM service issuing **3-day short-lived certs** bound to your verified legal entity. **RFC 3161 SHA-256 timestamping is mandatory** (`http://timestamp.acs.microsoft.com`) so signatures outlive the 3-day signing cert.

### 7.2 Signing Order, `SignTool` & GitHub Actions OIDC

Sign **inside-out**: (1) app `.exe`/`.dll` payloads -> (2) pack `.nupkg`/`.msi`/`.msix`/`Setup.exe` -> (3) sign installer/package containers (and Inno uninstaller via `SignTool=` in `[Setup]`).

**`metadata.json` for `Azure.CodeSigning.Dlib.dll`:**

```json
{
  "Endpoint": "https://eus.codesigning.azure.net/",
  "CodeSigningAccountName": "mycompany-signing-account",
  "CertificateProfileName": "mycompany-public-trust"
}
```

```powershell
signtool.exe sign /v /fd SHA256 `
  /tr "http://timestamp.acs.microsoft.com" /td SHA256 `
  /dlib "C:\Tools\AzureSigning\x64\Azure.CodeSigning.Dlib.dll" `
  /dmdf "C:\Tools\AzureSigning\metadata.json" ".\releases\MyApp-win-Setup.exe"
```

```yaml
# GitHub Actions OIDC signing step (id-token: write, contents: read)
- name: Azure Login (OIDC)
  uses: azure/login@v3
  with:
    client-id: ${{ secrets.AZURE_CLIENT_ID }}
    tenant-id: ${{ secrets.AZURE_TENANT_ID }}
    subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
- name: Sign binaries with Azure Artifact Signing
  uses: azure/artifact-signing-action@v2
  with:
    endpoint: https://eus.codesigning.azure.net/
    signing-account-name: mycompany-signing-account
    certificate-profile-name: mycompany-public-trust
    files-folder: ${{ github.workspace }}/releases
    files-folder-filter: exe,dll,msi,msix
    file-digest: SHA256
    timestamp-rfc3161: http://timestamp.acs.microsoft.com
    timestamp-digest: SHA256
```

### 7.3 SmartScreen Mitigation Checklist

- **Sign & SHA-256 timestamp every executable:** Browsers attach Mark of the Web (`Zone.Identifier`), causing SmartScreen blocks on unsigned installers. Never use deprecated `/t` SHA-1 timestamps; use `/tr ... /td SHA256`.
- **Keep one stable Publisher `Subject`:** Switching CAs or rotating legal subject strings resets accumulated publisher reputation.
- **Never edit PE resources after signing:** Stamping version info or icons (`rcedit`) post-signing breaks Authenticode (`TRUST_E_BAD_DIGEST`).
- **Pre-submit major installers:** Upload fresh major release installers to Microsoft Defender Security Intelligence (*Submit a file for malware analysis* -> Software developer) to clear heuristic false positives early.
