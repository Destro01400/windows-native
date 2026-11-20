# Windows Compiler Traps, Runtime Pitfalls & OS Build Compatibility

> **Scope:** Fast lookup for verified `.NET 9/10`, WPF, WinUI 3, `CsWin32`, `CommunityToolkit.Mvvm`, MSIX, WebView2, and Win32 compiler/runtime traps, plus a Windows 10/11 minimum OS build compatibility matrix (`19041` through `26100`).

## Table of Contents

1. [Verified Compiler & Analyzer Traps](#1-verified-compiler--analyzer-traps)
2. [Verified Runtime & Windows Architecture Traps](#2-verified-runtime--windows-architecture-traps)
3. [Before / After Remediation Snippets](#3-before--after-remediation-snippets)
4. [Windows 10 / 11 Minimum Build Compatibility Matrix](#4-windows-10--11-minimum-build-compatibility-matrix)
5. [Safe Runtime OS, Hardware & Policy Guard Patterns](#5-safe-runtime-os-hardware--policy-guard-patterns)

---

## 1. Verified Compiler & Analyzer Traps

| Code | Tool / Layer | Exact Trigger | Verified Fix & Reference |
|---|---|---|---|
| **`MC3072`** | WPF Markup Compiler | Using WinUI/UWP-only attached properties in WPF XAML (`AutomationProperties.AccessibilityView="Raw"`), or non-DP / `internal` / mismatched `clr-namespace` properties. | Remove `AccessibilityView` in WPF. Place decorative icon `TextBlock`s inside a `ControlTemplate` (`TextBlockAutomationPeer` hides them) or use a custom decorative `AutomationPeer`. See [xaml-architecture-and-quality.md](xaml-architecture-and-quality.md#5-accessibility-ui-automation-keyboard-live-regions-high-contrast). |
| **`NETSDK1168`** | .NET SDK / MSBuild | Setting `<PublishTrimmed>true</PublishTrimmed>` or `<PublishAot>true</PublishAot>` on a project with `<UseWPF>true</UseWPF>`. | WPF BAML, `DynamicResource`, `TypeConverter`s, and runtime bindings require full metadata. Remove trimming/AOT and use `<PublishReadyToRun>true</PublishReadyToRun>` for WPF; pick WinUI 3 (`CsWinRT >= 2.2`) or C++/WinRT for NativeAOT. See [packaging-signing-and-updates.md](packaging-signing-and-updates.md#31-why-wpf-fails-publishtrimmed-and-publishaot-netsdk1168). |
| **`CS0115`** | C# Compiler | `'...': no suitable method found to override`—commonly when overriding `OnLaunched` in WinUI 3 `App` without `Microsoft.UI.Xaml.Application`, mixing `Windows.UI.Xaml`, or overriding `SelectTemplateCore` on WPF's `DataTemplateSelector`. | Ensure `Microsoft.UI.Xaml.*` (not `System.Windows.*` or `Windows.UI.Xaml.*`), mark WinUI subclasses `partial`, and use `SelectTemplateCore(object item, DependencyObject container)`. See [winui3-and-cppwinrt-native.md](winui3-and-cppwinrt-native.md). |
| **`CS9248`** | C# / Roslyn Compiler | `Partial property must have an implementation part` when decorating `public partial string Name { get; set; }` with `[ObservableProperty]` under `CommunityToolkit.Mvvm 8.4.0` (or pre-C# 14 `<LangVersion>`). | Upgrade to **`CommunityToolkit.Mvvm >= 8.4.2`** on `.NET 10` for native `partial` property generation, or use field-backed `[ObservableProperty] private string _name = "";` on non-AOT WPF (WinUI 3 NativeAOT requires `partial` properties). See [xaml-architecture-and-quality.md](xaml-architecture-and-quality.md#31-modern-net-10-c-14-source-generators). |
| **`SYSLIB1062`** | .NET Interop Generator | Using `[LibraryImport]` (`.NET 7+` source-generated P/Invoke) without enabling unsafe blocks in `.csproj`. | Add `<AllowUnsafeBlocks>true</AllowUnsafeBlocks>` to `.csproj` (also required by `CsWin32` and `CsWinRT` NativeAOT). See [windows-os-and-cswin32.md](windows-os-and-cswin32.md#12-safehandle-lifecycle-vs-libraryimport-vs-dllimport). |
| **`PInvoke001`** | `Microsoft.Windows.CsWin32` | `Method, type or constant "..." not found` in `NativeMethods.txt`. Triggered by `#` comments (invalid!), CRT names (`memcmp`), WinRT types (`Windows.*`), header macros (`EnumProcesses`), or enum members (`PInvoke004`). | Use `//` comments only in `NativeMethods.txt`, specify exact win32metadata exports (`K32EnumProcesses`, `CredWriteW`), and list parent enum names (`DEV_BROADCAST_HDR_DEVICE_TYPE`). See [windows-os-and-cswin32.md](windows-os-and-cswin32.md#11-csproj-nativemethodstxt--nativemethodsjson-setup). |
| **`PInvoke017`** | `Microsoft.Windows.CsWin32` | Analyzer lifetime-safety diagnostic when unwrapping or storing `SafeHandle` raw pointers / `DangerousValue` outside a bounded `using` / `Lease()` scope. | Keep `CsWin32` current (`0.3.371+`), wrap handles in `using`, acquire `using var lease = handle.Lease();`, and pass `lease.Value` directly into a helper call instead of caching `DangerousValue`. See [windows-os-and-cswin32.md](windows-os-and-cswin32.md#12-safehandle-lifecycle-vs-libraryimport-vs-dllimport). |
| **`C00CE014`** | Appx / MSIX Schema | `Package.appxmanifest` XML schema validation failure (`APPX0501`/`DEP0700`): missing `xmlns` / `IgnorableNamespaces`, `<uap10:AllowExternalContent>` outside `<Properties>`, wrong child tag order, or unprefixed `runFullTrust`. | Declare `uap`, `uap10`, `desktop`, `com`, `rescap` namespaces on `<Package>` + `IgnorableNamespaces`, use `<rescap:Capability Name="runFullTrust" />`, and keep strict schema child ordering. See [packaging-signing-and-updates.md](packaging-signing-and-updates.md#43-external-location-sparse-packages-identity-for-traditional-installers). |
| **`IL3000`** | Single-File / Trim Analyzer | Calling `Assembly.Location` or `Assembly.CodeBase`—returns `""` in `PublishSingleFile=true` and NativeAOT binaries, causing runtime `ArgumentException` / missing asset crashes. | Use `AppContext.BaseDirectory` for bundled assets and `Environment.ProcessPath` for the running `.exe`. See [packaging-signing-and-updates.md](packaging-signing-and-updates.md#22-wpf-single-file-pitfalls--temporary-extraction). |
| **`WPF0001`** | WPF .NET 9/10 Analyzer | Experimental API warning raised when using `ThemeMode` / `Application.Current.ThemeMode` (`PresentationFramework.Fluent`). | Opt in explicitly via `<NoWarn>$(NoWarn);WPF0001</NoWarn>` in `.csproj` (or `#pragma warning disable WPF0001`), and override `*Brush` keys directly after `Fluent.xaml`. See [window-chrome-and-win11.md](window-chrome-and-win11.md#7-net-9--net-10-presentationframeworkfluent-thememode--brand-overrides). |

> **Inspecting Source-Generated Code:** Add `<EmitCompilerGeneratedFiles>true</EmitCompilerGeneratedFiles>` temporarily in `.csproj` to inspect generated `CsWin32`, `LibraryImport`, `CommunityToolkit.Mvvm`, and `CsWinRT` files under `obj/`.

---

## 2. Verified Runtime & Windows Architecture Traps

| Trap | Affected Stack | Why It Breaks in Production | Verified Fix & Reference |
|---|---|---|---|
| **WinUI 3 `Window.Current == null`** | WinUI 3 Desktop | WinUI 3 supports multiple `Window`s per thread without a UWP `CoreWindow`, so `Window.Current` and `CoreWindow.GetForCurrentThread()` always return `null` at runtime. | Store `MainWindow` on `App`, pass `element.XamlRoot` to `ContentDialog` / `TeachingTip` / `Flyout`, and use `AppWindow` + `Microsoft.UI.Dispatching.DispatcherQueue`. See [winui3-and-cppwinrt-native.md](winui3-and-cppwinrt-native.md#22-appwindow-overlappedpresenter--close-confirmation). |
| **`EnsureCoreWebView2Async()` Program Files Lock** | WPF / WinUI 3 + WebView2 | Parameterless `EnsureCoreWebView2Async()` defaults `UserDataFolder` to `<ExeDir>\<App>.exe.WebView2`, throwing `UnauthorizedAccessException` (`0x80070005`) under read-only `C:\Program Files` when running `asInvoker`. | Always pass a `CoreWebView2Environment` created with an explicit `%LocalAppData%\<Company>\<App>\WebView2` folder, and guard against concurrent init calls. See [webview2-and-hybrid-apps.md](webview2-and-hybrid-apps.md). |
| **`Mutex` Premature GC** | Single-Instance Apps | A local `Mutex` inside `Main` or `OnStartup` becomes eligible for Release-mode JIT garbage collection as soon as `createdNew` is read, closing the OS kernel handle so a second launch starts anyway. | Store `_mutex` in a long-lived field, call `GC.KeepAlive(_mutex)` in shutdown/dispose, pick `Local\` (per-session) vs `Global\` intentionally, and handle `AbandonedMutexException`. See [app-architecture-and-lifecycle.md](app-architecture-and-lifecycle.md#31-mutex-traps-local-vs-global-and-gckeepalive). |
| **Session 0 Service Isolation** | Windows Services (`SCM`) | Windows Services execute in non-interactive Session 0—they cannot display `HWND`s, tray icons, `MessageBox`, or interactive user UI, and fail user-desktop shell actions. | Keep the service headless (`AddWindowsService`) and bridge to an interactive user-session Tray/UI companion over `NamedPipeServerStream` (`PipeSecurity` ACLs) or gRPC over Named Pipes. See [background-services-and-ipc.md](background-services-and-ipc.md). |
| **`AllowsTransparency="True"` DWM Break** | WPF Windows | Sets `UsesPerPixelOpacity = true`, telling DWM to drop the non-client frame—breaking native shadows, `DWMWA_WINDOW_CORNER_PREFERENCE`, Aero Snap / Snap Layouts, and Mica/Acrylic. | Keep `AllowsTransparency="False"` on main windows; use `WindowChrome` (`GlassFrameThickness="-1"` or `"1"` for opaque frames) + `DwmSetWindowAttribute`. Reserve `AllowsTransparency` strictly for small irregular splash/popups. See [window-chrome-and-win11.md](window-chrome-and-win11.md#13-why-allowstransparencytrue-is-an-anti-pattern). |

---

## 3. Before / After Remediation Snippets

### 3.1 `.csproj` Interop, WPF R2R & Single-File (`SYSLIB1062`, `NETSDK1168`, `WPF0001`)

```xml
<!-- WPF (.NET 10): PublishReadyToRun (never PublishTrimmed/PublishAot -> NETSDK1168) -->
<PropertyGroup>
  <TargetFramework>net10.0-windows10.0.19041.0</TargetFramework>
  <UseWPF>true</UseWPF>
  <AllowUnsafeBlocks>true</AllowUnsafeBlocks> <!-- Fixes SYSLIB1062 & enables CsWin32 -->
  <PublishReadyToRun Condition="'$(Configuration)' == 'Release'">true</PublishReadyToRun>
  <IncludeNativeLibrariesForSelfExtract>true</IncludeNativeLibrariesForSelfExtract>
  <NoWarn>$(NoWarn);WPF0001</NoWarn> <!-- Only if opting into .NET 9/10 ThemeMode -->
</PropertyGroup>
```

### 3.2 `NativeMethods.txt` Comment & Enum Trap (`PInvoke001`, `PInvoke004`)

```text
// GOOD: CsWin32 requires // comments (never # comments, which trigger PInvoke001)
// GOOD: List parent enum names rather than individual enum members (avoids PInvoke004)
DEV_BROADCAST_HDR_DEVICE_TYPE
REGISTER_NOTIFICATION_FLAGS
CredWriteW
CredReadW
```

### 3.3 `MC3072` (WPF Decorative Icons) & `CS9248` (`Mvvm >= 8.4.2`)

```xml
<!-- BAD (throws MC3072 in WPF): AutomationProperties.AccessibilityView="Raw" -->
<!-- GOOD (WPF): Place decorative glyphs inside a ControlTemplate or set IsHitTestVisible="False" -->
<Button AutomationProperties.Name="Settings" ToolTip="Settings">
    <TextBlock FontFamily="{StaticResource SymbolFont}" Text="&#xE713;" IsHitTestVisible="False" />
</Button>
```

```csharp
// Requires CommunityToolkit.Mvvm >= 8.4.2 on .NET 10 (prevents CS9248 on partial properties)
public sealed partial class SettingsViewModel : CommunityToolkit.Mvvm.ComponentModel.ObservableObject
{
    [CommunityToolkit.Mvvm.ComponentModel.ObservableProperty]
    public partial string StatusText { get; set; } = "Ready";
}
```

### 3.4 `SafeHandle` Lease (`PInvoke017`), `IL3000`, `Mutex` GC & `WebView2` UDF

```csharp
// IL3000-safe path resolution (works identically in loose, single-file, and NativeAOT builds)
string configPath = System.IO.Path.Combine(AppContext.BaseDirectory, "appsettings.json");
string exePath = Environment.ProcessPath ?? throw new InvalidOperationException("ProcessPath unavailable.");
```

```csharp
// Mutex Premature GC Fix: store in a long-lived field + keep alive through Shutdown/Dispose
private Mutex? _instanceMutex;

public bool TryAcquireSingleInstance(string appId)
{
    _instanceMutex = new Mutex(initiallyOwned: false, $@"Local\{appId}.InstanceMutex", out bool createdNew);
    return createdNew;
}

public void ReleaseSingleInstance()
{
    GC.KeepAlive(_instanceMutex);
    _instanceMutex?.Dispose();
    _instanceMutex = null;
}
```

```csharp
// EnsureCoreWebView2Async Program Files Fix: always supply writable %LocalAppData% UDF
string udf = System.IO.Path.Combine(
    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
    "MyCompany", "MyApp", "WebView2");
System.IO.Directory.CreateDirectory(udf);
var env = await Microsoft.Web.WebView2.Core.CoreWebView2Environment.CreateAsync(userDataFolder: udf);
await webView.EnsureCoreWebView2Async(env);
```

### 3.5 WinUI 3 `Window.Current == null` & `CS0115` Template Selectors

```csharp
// BAD in WinUI 3 Desktop: Window.Current (always null!)
// GOOD in WinUI 3: track MainWindow on App, pass element.XamlRoot, and mark selectors partial
public sealed partial class StatusTemplateSelector : Microsoft.UI.Xaml.Controls.DataTemplateSelector
{
    public required Microsoft.UI.Xaml.DataTemplate DefaultTemplate { get; set; }
    protected override Microsoft.UI.Xaml.DataTemplate SelectTemplateCore(
        object item, Microsoft.UI.Xaml.DependencyObject container) => DefaultTemplate;
}
```

> **Rule for `PInvoke017`:** Acquire `using var lease = handle.Lease();` inside `using (handle)` and pass `lease.Value` directly into a dedicated reader method (`ReadCredentialBlob(lease.Value)`), rather than storing `handle.DangerousValue` in a local variable or field.

---

## 4. Windows 10 / 11 Minimum Build Compatibility Matrix

Verify target OS capabilities before invoking build-dependent DWM attributes, shell chrome, packaging, WebView2, or Windows AI APIs:

| Feature / API | `19041` (Win10 2004) | `22000` (Win11 21H2) | `22621` (Win11 22H2) | `26100` (Win11 24H2) | Guard & Behavior Notes |
|---|---|---|---|---|---|
| **`DWMWA_USE_IMMERSIVE_DARK_MODE` (`20`)** | **Min Build** | Supported | Supported | Supported | Pre-2004 Insider Win10 builds used undocumented ID `19`; use `20` on `19041+`. Match app theme so Snap menus match. |
| **`DWMWA_WINDOW_CORNER_PREFERENCE` (`33`)** | No-op (`E_INVALIDARG`) | **Min Build** | Supported | Supported | Guard with `IsWindowsVersionAtLeast(10, 0, 22000)`. `DWMWCP_ROUND` (`2`) gives `8px` corners and auto-squares when maximized. |
| **`DWMWA_BORDER_COLOR` (`34`)** | No-op (`E_INVALIDARG`) | **Min Build** | Supported | Supported | Guard with `22000`. Must be updated manually on `Activated`/`Deactivated`—DWM does not dim custom border colors automatically. |
| **`DWMWA_SYSTEMBACKDROP_TYPE` (`38`)** | Unsupported | Unsupported* | **Min Build** | Supported | Sets Mica (`2`), Desktop Acrylic (`3`), or Mica Alt (`4`). Requires `DwmExtendFrameIntoClientArea(-1)` + transparent window background (`*22000` lacked official ID `38`). |
| **Snap Layouts (`HTMAXBUTTON`)** | Safe (acts as Max btn) | **Min Build** | Supported (enhanced) | Supported | Returning `HTMAXBUTTON (9)` on `WM_NCHITTEST` degrades cleanly on Win10 and triggers Snap Layouts on Win11+. Keep `MinWidth <= 500` (`<= 330` ideal). |
| **Windows App SDK (WinUI 3)** | Supported (`net*-windows10.0.19041.0`) | Supported | Supported | **Full SDK + AI align** | Runtime OS baseline is `17763` (Win10 1809); Sparse Packages (`uap10:AllowExternalContent`) require **`19041+`**. Unpackaged dynamic bootstrapper fails when elevated (`Admin`). |
| **WebView2 (Evergreen Runtime)** | Supported (needs runtime install) | Supported | Supported | **OS-inbuilt core** | Supported on `1709+`. Check/bundle the Evergreen Bootstrapper in Win10 (`19041`) installers; always pass an explicit `%LocalAppData%` `UserDataFolder` on all builds. |
| **DirectML (`OnnxRuntime.DirectML`)** | **Min practical DX12** | Supported | Supported | Supported (maintenance) | Runs on any DX12 GPU across Win10/11 (`19041+`), now in sustained maintenance—ideal universal GPU fallback (pair with CPU fallback for headless/RDP). |
| **Windows AI / Windows ML (`Microsoft.Windows.AI`)** | Unsupported | Unsupported | Unsupported | **Min Build** (+ NPU/Copilot+ PC for SLMs) | Dynamic EP catalog (QNN/OpenVINO/VitisAI NPUs) & Windows AI (`Phi Silica`, Imaging, OCR) require **`26100+`**, compatible drivers, and readiness checks (`GetReadyState()`/`EnsureReadyAsync()`). |

---

## 5. Safe Runtime OS, Hardware & Policy Guard Patterns

Never assume an API succeeds across all Windows editions, RDP sessions, or restricted corporate endpoints. Combine compile-time TFM bounds with runtime OS, WinRT metadata, and policy guards:

```csharp
using System;
using System.Runtime.InteropServices;

namespace MyApp.Compat;

public static class WindowsBuildGuards
{
    public static bool SupportsDarkTitleBar => OperatingSystem.IsWindowsVersionAtLeast(10, 0, 19041);
    public static bool SupportsWin11CornersAndBorder => OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22000);
    public static bool SupportsSystemBackdrop => OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22621);
    public static bool SupportsWindows24H2Ai => OperatingSystem.IsWindowsVersionAtLeast(10, 0, 26100);
    public static bool IsArm64Process => RuntimeInformation.ProcessArchitecture == Architecture.Arm64;
}
```

### Runtime Defensive Checklist

1. **Lower `TargetPlatformMinVersion` than `TargetFramework`:** When targeting `net10.0-windows10.0.26100.0` with `TargetPlatformMinVersion` `10.0.19041.0` (or `17763.0`), guard newer WinRT APIs with `Windows.Foundation.Metadata.ApiInformation.IsTypePresent(...)` before instantiating them.
2. **WebView2 availability:** Probe `CoreWebView2Environment.GetAvailableBrowserVersionString()` inside a `try/catch` (`WebView2RuntimeNotFoundException`) and offer an inline fallback/installer prompt ([webview2-and-hybrid-apps.md](webview2-and-hybrid-apps.md)).
3. **AI & GPU capability:** Even on Build `26100+`, verify `GetReadyState()` / `EnsureReadyAsync()` for `Microsoft.Windows.AI` and fall back cleanly to DirectML or CPU ([graphics-media-and-windows-ai.md](graphics-media-and-windows-ai.md)).
4. **High Contrast & Software Rendering:** Disable Mica/Acrylic and translucent overlays whenever `SystemParameters.HighContrast` or `RenderCapability.Tier >> 16 == 0` (RDP / VM / driver reset) is active ([window-chrome-and-win11.md](window-chrome-and-win11.md#6-system-theme-accent-color-high-contrast--text-scale-sync)).
5. **Pre-Release Static Audit:** Run `python scripts/audit_windows_app.py <app-dir> --strict` (and `--sarif` in CI) to catch `NETSDK1168`, missing `AllowUnsafeBlocks`, `Window.Current`, parameterless `EnsureCoreWebView2Async()`, `AllowsTransparency`, and manifest gaps automatically.
