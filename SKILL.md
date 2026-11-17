---
name: windows-native
license: MIT
description: Design, architect, build, interop, package, sign, test, and profile native Windows 10/11 desktop applications in C#, XAML, and C++ (WPF on .NET 9/10, WinUI 3 / Windows App SDK, C++/WinRT, modern Win32/DWM/CsWin32, CommunityToolkit.Mvvm). Use whenever building or reviewing Windows desktop apps from scratch or updating existing views—covering Generic Host DI, single-instance IPC, URI protocols, DPAPI/Credential Manager security, global hotkeys, audio/power events, NativeAOT/ReadyToRun, MSIX/Sparse Packages, WiX v5/Inno Setup 6 installers, Velopack auto-updates, Azure Artifact Signing, SmartScreen, Fluent 2 tokens, WindowChrome Snap Layouts, PerMonitorV2 DPI, iGPU-safe animations, UI virtualization, accessibility, FlaUI E2E tests, crash dumps, or WPA/dotnet-dump profiling.
---

# Windows Native App Engineering (`windows-native`)

End-to-end engineering guide for **native Windows 10/11 desktop applications** across **WPF (`.NET 9/10`)**, **WinUI 3 (`Windows App SDK` + NativeAOT)**, **C++/WinRT**, and **Win32/DWM/CsWin32**—from app architecture, OS security, and Fluent 2 UI/motion through MSIX/installer packaging, code signing, auto-updates, automated testing, and live profiling.

---

## Quick Reference Routing

Load **only** the reference file(s) required for the active task rather than loading everything upfront:

| Task / Area | Reference File |
|---|---|
| Generic Host DI (`StartupUri` removal, `CultureInfo` `XmlLanguage`, `IHostedService`), `IOptionsMonitor` vs. atomic `%LocalAppData%` JSON + SQLite WAL, `Mutex` (`Local\`/`Global\`) + `NamedPipeServerStream` IPC, URI protocols, crash recovery, WER Restart/Recovery, async `Serilog` | [app-architecture-and-lifecycle.md](references/app-architecture-and-lifecycle.md) |
| `Microsoft.Windows.CsWin32` (`NativeMethods.txt`/`.json`, `SafeHandle`/`Lease()`, `[LibraryImport]`/`AllowUnsafeBlocks`), Shell pickers (`OpenFolderDialog`, `IFileOpenDialog`), Drag-Drop UIPI, `RegisterHotKey`/`WH_KEYBOARD_LL`, DPAPI `CurrentUser`, Credential Manager/`PasswordVault`, UAC/`app.manifest`, Registry `Run`, `WM_DEVICECHANGE`, WASAPI/`NAudio`, `SystemEvents.PowerModeChanged` | [windows-os-and-cswin32.md](references/windows-os-and-cswin32.md) |
| **WinUI 3** (Packaged vs. `WindowsPackageType=None`, `AppInstance` redirection, `AppWindow`/TitleBar passthrough, `x:Bind`/`x:Phase`, `DispatcherQueue`, `ApplicationData`, NativeAOT + `CsWinRT >= 2.1.6`) and **C++/WinRT / Modern Win32** (decision matrix, C++20/WIL, coroutines/`get_weak()`, MIDL 3.0, Direct2D/DirectComposition) | [winui3-and-cppwinrt-native.md](references/winui3-and-cppwinrt-native.md) |
| Unpackaged/Single-File (`IncludeNativeLibrariesForSelfExtract`, `AppContext.BaseDirectory`), `PublishReadyToRun` vs. `PublishAot` (WPF `NETSDK1168`), MSIX & External Location **Sparse Packages**, WiX v5 vs. Inno Setup 6 (WebView2/`.NET` bootstrappers), **Velopack** vs. `.appinstaller`, **Azure Artifact Signing** & SmartScreen | [packaging-signing-and-updates.md](references/packaging-signing-and-updates.md) |
| Testing pyramid (`IDialogService`/`IDispatcherService`, `Xunit.StaFact` `[WpfFact]`, `FlaUI.UIA3` + CI session caveats, `RenderTargetBitmap` snapshots), WER `LocalDumps`, crash capture, `Serilog.Sinks.Async`/`OpenTelemetry`, `dotnet-counters`/`gcdump`/`dump`/`trace`, PerfView, WPR/WPA, Snoop | [diagnostics-testing-and-profiling.md](references/diagnostics-testing-and-profiling.md) |
| Layout grid (`4px`), breakpoints, Windows 11 type ramp, color tokens, WCAG contrast, concentric radii, Mica/Acrylic/Smoke layering, icons, dialogs/`InfoBar`, Wait UX, Settings, copy | [fluent-design-tokens-and-ux.md](references/fluent-design-tokens-and-ux.md) |
| Custom `WindowChrome`, `DwmSetWindowAttribute` (Mica/Acrylic/corners/dark mode), **Snap Layouts (`HTMAXBUTTON`)**, maximized bounds, `PerMonitorV2` DPI, crisp text, `.NET 9/10` `ThemeMode`, Shell extras | [window-chrome-and-win11.md](references/window-chrome-and-win11.md) |
| Fluent 2 motion curves -> WPF `KeySpline`, `VisualStateManager`, `TransitioningContentControl`, hover/expand/shimmer/stagger recipes, `CompositionTarget.Rendering`, reduced motion, iGPU perf | [motion-and-animations.md](references/motion-and-animations.md) |
| Layered `ResourceDictionary` tokens, `StaticResource` vs. `DynamicResource`, `CommunityToolkit.Mvvm` 8.4 (`partial` properties), virtualized lists, streaming Markdown perf, memory leaks, UIA/`LiveSetting` | [xaml-architecture-and-quality.md](references/xaml-architecture-and-quality.md) |
| Custom brand theme adaptation (embedded fonts, badge WCAG contrast fixes, styling all built-in controls without Aero leaks, frozen resource caching, opaque vs. translucent chrome) | [custom-brand-theming.md](references/custom-brand-theming.md) |
| Automated static audit across `.csproj`, `*.manifest`, `*.xaml`, and `*.cs` (lifecycle/security, packaging flags, WCAG contrast, `po:Freeze`, virtualization, animation leaks, UIA) | Run `python scripts/audit_windows_app.py <app-dir>` (or `scripts/audit_wpf_ui.py <wpf-dir>` for UI-only legacy CLI) |

---

## Core Windows App Engineering Workflow

### 1. Audit & Stack Selection First

Before editing an existing codebase or scaffolding a new app:
1. **Static Audit:** Run `python <skill-dir>/scripts/audit_windows_app.py <project-dir>` (`--ui-only` for XAML/UI checks only, `--strict` in CI, `--json` for tooling) to surface `.csproj` pitfalls (`NETSDK1168`, missing `AllowUnsafeBlocks`), manifest gaps, lifecycle/security bugs, contrast failures, and UIA gaps.
2. **Choose the Native Stack Deliberately** (details in [winui3-and-cppwinrt-native.md](references/winui3-and-cppwinrt-native.md)):
   - **WPF (`.NET 9/10`):** Mature ecosystem, rich `ControlTemplate`/`WindowChrome` customization, fast iteration (`PublishReadyToRun=true`, no `PublishAot`).
   - **WinUI 3 (`Windows App SDK`):** Modern Fluent 2 controls, `Microsoft.UI.Composition`, `x:Bind`, supports **`PublishAot=true`** (`CsWinRT >= 2.1.6`).
   - **C++/WinRT or Pure Win32 + Direct2D/DirectComposition:** Zero `.NET` runtime, sub-2 MB–10 MB binaries, lowest idle RAM for always-on utilities.

### 2. App Architecture, Startup, Persistence & IPC

Follow [app-architecture-and-lifecycle.md](references/app-architecture-and-lifecycle.md):
- **Generic Host DI:** Remove `StartupUri` in WPF `App.xaml` (resolve `MainWindow` from `IHost.Services` in `Startup`); in WinUI 3 or Velopack WPF apps requiring custom `Main`, disable auto-generated `Main` (`DISABLE_XAML_GENERATED_MAIN` or `Page` build action on `App.xaml` + `StartupObject`). Override `FrameworkElement.LanguageProperty` with `CultureInfo.CurrentCulture` **before** building UI.
- **Crash-Safe Local Storage:** Separate read-only `IOptionsMonitor` `appsettings.json` from `%LocalAppData%\<App>\` user state. Write JSON atomically (`temp` + `Flush(true)` + `File.Replace`/`Move`) and enable **WAL mode** on SQLite.
- **Single-Instance & Secure IPC:** Keep the `Mutex` alive past app shutdown with `GC.KeepAlive(mutex)` (choose `Local\` vs. `Global\` intentionally and handle `AbandonedMutexException`). Pass second-instance CLI arguments / deep links over `NamedPipeServerStream` with `PipeOptions.CurrentUserOnly`. Quote `"%1"` cleanly in `HKCU\Software\Classes` custom URI handlers and validate schemes/arguments against injection.
- **Resilient Shutdown & Crash Capture:** Wire `DispatcherUnhandledException`, `TaskScheduler.UnobservedTaskException`, and `AppDomain.UnhandledException` with an `Interlocked` anti-recursion guard; distinguish `Application.SessionEnding` from `SystemEvents.SessionEnding`; flush buffered `Serilog.Sinks.Async` / `OpenTelemetry` sinks on exit.

### 3. OS Interop (`CsWin32`), Input, Security & Hardware Events

Follow [windows-os-and-cswin32.md](references/windows-os-and-cswin32.md):
- **Modern Win32 Interop:** Prefer `Microsoft.Windows.CsWin32` (`NativeMethods.txt` + `NativeMethods.json` with `SafeHandle`s) over manual P/Invokes. Enable `<AllowUnsafeBlocks>true</AllowUnsafeBlocks>` whenever using `[LibraryImport]` (`SYSLIB1062`) or `CsWin32` pointers.
- **Shell Pickers & Global Hotkeys:** Use built-in `.NET 8+` WPF `OpenFileDialog` / `OpenFolderDialog` (or `InitializeWithWindow` in WinUI 3). Pair `RegisterHotKey` with guaranteed `UnregisterHotKey` cleanup; avoid global `WH_KEYBOARD_LL` hooks unless required (timeout/EDR/UIPI isolation pitfalls).
- **Windows Security & Manifest Hygiene:** Encrypt per-user secrets with DPAPI `DataProtectionScope.CurrentUser` + entropy (never `LocalMachine` for user tokens) or Windows Credential Manager (`CredWrite`/`CredRead` / `PasswordVault`). Always ship an `app.manifest` declaring `<dpiAwareness>PerMonitorV2</dpiAwareness>`, Windows 10/11 `<supportedOS>` GUIDs, `<longPathAware>true</longPathAware>`, and `requestedExecutionLevel level="asInvoker"` unless elevation is strictly mandatory.
- **Hardware, Audio & Power:** Unsubscribe `SystemEvents.PowerModeChanged` (`-=`) to prevent static event leaks; handle WASAPI / audio endpoint changes gracefully; quote executable paths in `HKCU\...\Run`.

### 4. Visual Polish, WindowChrome, Motion & Accessibility

Follow [fluent-design-tokens-and-ux.md](references/fluent-design-tokens-and-ux.md), [window-chrome-and-win11.md](references/window-chrome-and-win11.md), [motion-and-animations.md](references/motion-and-animations.md), [xaml-architecture-and-quality.md](references/xaml-architecture-and-quality.md), and [custom-brand-theming.md](references/custom-brand-theming.md):
- **Geometry & WCAG:** Stick to the `4 epx` grid (`UseLayoutRounding="True"`, `SnapsToDevicePixels="True"`), keep normal text **`>= 4.5:1`** contrast (use dark `*-Dim` ink on pastel badges), style **every** control used (zero unstyled Aero leaks), and freeze static resources (`po:Freeze="True"`).
- **Native Win11 Frame:** Never set `AllowsTransparency="True"` on main windows. Use `WindowChrome` (`GlassFrameThickness="-1"` or `1` for opaque brand frames), `WindowChrome.IsHitTestVisibleInChrome="True"` on interactive caption controls, `DWMWA_USE_IMMERSIVE_DARK_MODE (20)`, `DWMWA_WINDOW_CORNER_PREFERENCE (33)`, and full `HTMAXBUTTON` (`WM_NCHITTEST` with signed `(short)` coords + `StateChanged` glyph sync) for Snap Layouts.
- **iGPU-Safe Motion & Virtualization:** Animate `RenderTransform` and `Opacity` only (`83/167/250 ms`), honor `SystemParameters.ClientAreaAnimation`, guard `RepeatBehavior="Forever"` loops with `IsVisible`, dedupe/sleep `CompositionTarget.Rendering` loops, preserve `VirtualizingStackPanel` (no `<ScrollViewer>` wrapping `ItemsControl`, no `CanContentScroll="False"`), batch streaming updates at `20–30 Hz`, and use `CommunityToolkit.Mvvm >= 8.4.2` for native `.NET 10` `partial` properties.
- **UIA Parity:** Label icon-only buttons with `AutomationProperties.Name` + `ToolTip`, never use WPF-invalid `AutomationProperties.AccessibilityView="Raw"` (`MC3072`), and reveal hover actions on `IsKeyboardFocusWithin` too.

### 5. Packaging, Signing, Auto-Updates & Diagnostics

Follow [packaging-signing-and-updates.md](references/packaging-signing-and-updates.md) and [diagnostics-testing-and-profiling.md](references/diagnostics-testing-and-profiling.md):
- **Publish & AOT Rules:** For single-file WPF, always set `<IncludeNativeLibrariesForSelfExtract>true</IncludeNativeLibrariesForSelfExtract>` and resolve files via `AppContext.BaseDirectory` (not `Assembly.Location`). Never set `PublishTrimmed`/`PublishAot` on WPF (`NETSDK1168`); use `PublishReadyToRun=true`. Use `PublishAot=true` on pure Win32 (`CsWin32`) or WinUI 3 (`CsWinRT >= 2.1.6` + source-gen JSON).
- **Installers, Package Identity & Updates:** Prefer **per-user** installs (`%LocalAppData%\Programs`) unless shared machine scope is required. Use **WiX Toolset v5** (`<Files>`, `<netfx:DotNetCompatibilityCheck>`) for MSI/Enterprise or **Inno Setup 6** (`PrivilegesRequired=lowest`, `PrivilegesRequiredOverridesAllowed=dialog`, `{autopf}`) + WebView2 bootstrapper. Add an **External Location Sparse Package** (`<uap10:AllowExternalContent>true</uap10:AllowExternalContent>`) when an unpackaged app needs Toasts/StartupTask/ShareTarget. Ship delta auto-updates via **Velopack** (`VelopackApp.Build().Run()` first in `Main`; note `UpdateManager` is not `IDisposable`) or MSIX `.appinstaller`.
- **Signing & SmartScreen:** Sign inside-out (payloads -> installer/MSIX) using **Azure Artifact Signing** (`Azure.CodeSigning.Dlib.dll`) or hardware HSM certs with mandatory **RFC 3161 SHA-256 timestamping** (`/tr http://timestamp.acs.microsoft.com /td SHA256`) and one stable publisher `Subject`.
- **Testing & Profiling:** Keep 80% of logic in headless `xUnit` tests behind `IDialogService`/`IDispatcherService`, use `Xunit.StaFact` (`[WpfFact]`) for `DependencyProperty`/`RenderTargetBitmap` tests, run `FlaUI.UIA3` E2E tests in interactive desktop sessions, configure WER `LocalDumps`, and diagnose leaks/stutters with `dotnet-counters`, `dotnet-gcdump`, `dotnet-dump`, and `WPR`/`WPA`.

---

## Pre-Delivery Checklist

1. **Static Audit:** Run `python scripts/audit_windows_app.py <project-dir> --strict` and resolve all `ERROR` and `WARN` findings.
2. **Clean Build & Binding Check:** Verify `dotnet build` produces `0 warnings, 0 errors` (and 0 *XAML Binding Failures* at runtime).
3. **Interactive & Packaging Check:** Test `PerMonitorV2` DPI scaling (`100%`/`125%`/`150%`), Snap Layouts (`HTMAXBUTTON`), keyboard-only navigation (`Tab`/`F6`/`Esc`), Contrast themes, reduced motion, single-instance handoff, clean uninstall, and Authenticode signature + RFC 3161 timestamp verification (`signtool verify /pa`).
