# Windows Native App Engineering (`windows-native`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Target: .NET 9 / 10 WPF, WinUI 3 & C++/WinRT](https://img.shields.io/badge/Target-.NET%209%2F10%20WPF%20%7C%20WinUI%203%20%7C%20C%2B%2B%2FWinRT-512BD4.svg)](#)

An agent skill for full-lifecycle **native Windows 10/11 desktop application engineering** across **WPF (`.NET 9/10`)**, **WinUI 3 (`Windows App SDK` + NativeAOT)**, **C++/WinRT**, and **modern Win32/DWM/CsWin32**—covering architecture, OS interop, security, packaging, code signing, auto-updates, Fluent 2 UI/motion, diagnostics, and a zero-dependency Python static auditor.

*(Versão em Português abaixo / [Portuguese README](#versão-em-português-br))*

---

## What This Skill Covers

- **App Architecture, DI, IPC & Lifecycle ([`references/app-architecture-and-lifecycle.md`](references/app-architecture-and-lifecycle.md))**
  - `.NET 9/10` Generic Host (`Host.CreateApplicationBuilder`) in WPF (`StartupUri` removal) and WinUI 3 (`DISABLE_XAML_GENERATED_MAIN`), `CultureInfo`/`XmlLanguage` overrides, `IOptionsMonitor` vs. atomic `%LocalAppData%` JSON (`Flush(true)` + `File.Replace`) and SQLite WAL mode, `Local\`/`Global\` `Mutex` + `GC.KeepAlive` + `CurrentUserOnly` Named Pipes, custom URI protocol handlers (`HKCU\Software\Classes` vs. MSIX) with command-injection defense, global exception handlers, WER `RegisterApplicationRestart`/`Recovery`, and async `Serilog`.
- **Windows OS Interop, CsWin32 & Security ([`references/windows-os-and-cswin32.md`](references/windows-os-and-cswin32.md))**
  - `Microsoft.Windows.CsWin32` (`NativeMethods.txt`/`.json`, `SafeHandle`/`Lease()`, `AllowUnsafeBlocks` vs. `[LibraryImport]`), `.NET 8–10` Shell pickers (`OpenFileDialog`, `OpenFolderDialog`, WinUI 3 `InitializeWithWindow`, COM `IFileOpenDialog`), Drag-Drop UIPI rules, `RegisterHotKey`/`UnregisterHotKey` vs. `WH_KEYBOARD_LL` caveats, DPAPI (`CurrentUser` + entropy), Windows Credential Manager vs. `PasswordVault`, UAC/`app.manifest` (`PerMonitorV2`, `longPathAware`, UTF-8 `activeCodePage`), Registry `Run` + `StartupApproved`, `WM_DEVICECHANGE`, WASAPI/`NAudio` device traps, and leak-free `SystemEvents.PowerModeChanged`.
- **WinUI 3, C# NativeAOT & C++/WinRT / Modern Win32 ([`references/winui3-and-cppwinrt-native.md`](references/winui3-and-cppwinrt-native.md))**
  - **Part A (WinUI 3):** Packaged (MSIX) vs. unpackaged (`WindowsPackageType=None`) vs. `WindowsAppSDKSelfContained`, `AppInstance.FindOrRegisterForKey` single-instance redirection, `AppWindow`/TitleBar passthrough rects, `x:Bind`/`x:DefaultBindMode`/function bindings/`x:Phase`, `NavigationView`/`Frame.CacheSize`/`ConnectedAnimation`/`Composition`, `DispatcherQueue`, `ApplicationData` vs. `System.IO`, and **NativeAOT** (`PublishAot=true`, `CsWinRT >= 2.1.6`, `[GeneratedBindableCustomProperty]`).
  - **Part B (C++/WinRT & Win32):** WPF vs. WinUI 3 NativeAOT vs. C++/WinRT decision matrix, C++20/CMake/vcpkg/`WIL`, C++/WinRT apartments/coroutines/`wil::resume_foreground`/`get_weak()`/MIDL 3.0, and pure Win32 `PerMonitorV2` + Direct2D/DirectComposition skeletons for `< 2 MB` utilities.
- **Packaging, NativeAOT, Signing & Auto-Updates ([`references/packaging-signing-and-updates.md`](references/packaging-signing-and-updates.md))**
  - Unpackaged vs. self-contained vs. single-file (`IncludeNativeLibrariesForSelfExtract`, `%TEMP%\.net` extraction, `AppContext.BaseDirectory` vs. `IL3000`), `PublishReadyToRun` vs. `PublishAot` (and why WPF fails `NETSDK1168`), MSIX vs. External Location **Sparse Packages** (`uap10:AllowExternalContent`), **WiX Toolset v5** (`<Files>`, `<netfx:DotNetCompatibilityCheck>`) vs. **Inno Setup 6** (per-user `{autopf}` + WebView2/`.NET` bootstrappers), **Velopack** (`VelopackApp.Build().Run()`, `UpdateManager`, delta `.nupkg`, `vpk pack`) vs. `.appinstaller`, and **Azure Artifact Signing** + RFC 3161 timestamping / SmartScreen engineering.
- **Testing, Crash Dumps & Profiling ([`references/diagnostics-testing-and-profiling.md`](references/diagnostics-testing-and-profiling.md))**
  - Headless `xUnit` ViewModel testing (`IDialogService`/`IDispatcherService`), `Xunit.StaFact` `[WpfFact]` & STA `Dispatcher` teardown, `FlaUI.UIA3` E2E tests (plus `windows-latest` CI session caveats), `RenderTargetBitmap` / `Verify.Wpf` visual snapshots, recursive-safe unhandled exception capture, WER `LocalDumps`, `Serilog.Sinks.Async` + `OpenTelemetry` flushing, `dotnet-counters`, `dotnet-gcdump`, `dotnet-dump`, `dotnet-trace`/PerfView, `WPR`/`WPA` UI delays, VS XAML Binding Failures, and Snoop.
- **Windows 11 & Fluent 2 Design System ([`references/fluent-design-tokens-and-ux.md`](references/fluent-design-tokens-and-ux.md))**
  - `4 epx` grid alignment across 10 DPI scaling plateaus (`100%`–`400%`), spacing ramp, breakpoints, Windows 11 type ramp, Light/Dark/High-Contrast tokens, WCAG 2.1 contrast math, concentric radii, Mica/Acrylic/Smoke layering, `Segoe Fluent Icons`, Wait UX, `InfoBar`/`ContentDialog`/`SettingsCard`, and dual-stroke focus visuals.
- **Native Windows 11 Integration & DWM ([`references/window-chrome-and-win11.md`](references/window-chrome-and-win11.md))**
  - `WindowChrome` custom title bars without `AllowsTransparency="True"`, `dwmapi.dll` (`DWMWA_USE_IMMERSIVE_DARK_MODE`, `DWMWA_WINDOW_CORNER_PREFERENCE`, `DWMWA_BORDER_COLOR`, `DWMWA_SYSTEMBACKDROP_TYPE`), complete **Snap Layouts (`HTMAXBUTTON`)**, DPI-scaled maximized bounds + auto-hide taskbar fix, live theme/accent/`TextScaleFactor` sync, `.NET 9/10` `ThemeMode`, and Windows Shell extras.
- **Motion Design & WPF Animations ([`references/motion-and-animations.md`](references/motion-and-animations.md))**
  - Fluent 2 timing (`83/167/250/333 ms`) & `KeySpline`s, `VisualStateManager`, `FillBehavior.HoldEnd` traps, frozen-brush hover crossfades, iGPU optimization, reduced motion (`SystemParameters.ClientAreaAnimation`), and `dt`-normalized `CompositionTarget.Rendering` visualizers.
- **XAML Architecture, Performance & Accessibility ([`references/xaml-architecture-and-quality.md`](references/xaml-architecture-and-quality.md))**
  - Layered `ResourceDictionary` tokens, `StaticResource` vs. `DynamicResource`, `CommunityToolkit.Mvvm` 8.4 (`partial` properties), `20–30 Hz` streaming batching, `VirtualizingStackPanel`, `Markdig` vs. `FlowDocument` cost, memory leaks, UI Automation (`AutomationProperties`, `LiveRegionChanged`, `AutomationPeer`), and localization.
- **Custom Brand Theming ([`references/custom-brand-theming.md`](references/custom-brand-theming.md))**
  - Adapting Windows 11 standards to distinct custom brand palettes (embedded fonts + fallback chains, WCAG badge fixes, styling all built-in controls, opaque vs. translucent chrome, frozen resource caching).
- **Automated Static Windows App Auditor ([`scripts/audit_windows_app.py`](scripts/audit_windows_app.py) & [`scripts/audit_wpf_ui.py`](scripts/audit_wpf_ui.py))**
  - Scans `.csproj`, `*.manifest`, `*.xaml`, and `*.cs` for packaging traps (`NETSDK1168`, `AllowUnsafeBlocks`, `Mvvm < 8.4.2`), manifest issues (`PerMonitorV2`, `supportedOS`, `requireAdministrator`), C# lifecycle/security bugs (`Mutex` `GC.KeepAlive`, `SystemEvents` `-=`, `HttpClient`, `async void`, `LocalMachine` DPAPI, unvalidated `UseShellExecute`, unmatched `RegisterHotKey`), WCAG contrast, `po:Freeze`, virtualization blockers, animation leaks, and UIA gaps. Supports `--ui-only`, `--strict`, and `--json`. (`audit_wpf_ui.py` remains as a backwards-compatible UI-only CLI wrapper.)

---

## Repository Structure

```text
windows-native/
├── SKILL.md                                         # Core instructions & progressive-disclosure routing
├── README.md                                        # Documentation (EN / PT-BR)
├── LICENSE                                          # MIT License
├── .gitignore
├── references/
│   ├── app-architecture-and-lifecycle.md            # Generic Host DI, persistence, IPC, URI protocols, crash recovery
│   ├── windows-os-and-cswin32.md                    # CsWin32, Shell pickers, hotkeys, DPAPI/CredMan, manifest, hardware/power
│   ├── winui3-and-cppwinrt-native.md                # WinUI 3 (.NET + NativeAOT) & C++/WinRT / modern Win32 + Direct2D
│   ├── packaging-signing-and-updates.md             # Publish/SingleFile/R2R/AOT, MSIX/Sparse, WiX v5/Inno 6, Velopack, signing
│   ├── diagnostics-testing-and-profiling.md         # xUnit/StaFact/FlaUI, WER LocalDumps, Serilog/OTel, dotnet-dump/WPR/WPA
│   ├── fluent-design-tokens-and-ux.md               # Windows 11 / Fluent 2 tokens, 4px grid, typography, contrast, UX
│   ├── window-chrome-and-win11.md                   # WindowChrome, DWM, Snap Layouts (HTMAXBUTTON), DPI, ThemeMode
│   ├── motion-and-animations.md                     # Fluent curves, KeySpline, VSM, CompositionTarget, iGPU perf
│   ├── xaml-architecture-and-quality.md             # Layered tokens, Mvvm 8.4, virtualization, streaming, UIA
│   └── custom-brand-theming.md                      # Custom palettes, embedded fonts, control coverage, frozen cache
└── scripts/
    ├── audit_windows_app.py                         # Zero-dependency Python auditor (.csproj, manifest, C#, XAML/UI)
    └── audit_wpf_ui.py                              # Backwards-compatible UI-only CLI wrapper (--ui-only mode)
```

---

## Installation

### Skills CLI / Antigravity / Claude Code / Codex / OpenCode

```bash
# Skills CLI
npx skills add Destro01400/windows-native

# Project-scoped (Antigravity)
git clone https://github.com/Destro01400/windows-native.git .agent/skills/windows-native

# Project-scoped (Claude Code)
git clone https://github.com/Destro01400/windows-native.git .claude/skills/windows-native

# Project-scoped (Codex)
git clone https://github.com/Destro01400/windows-native.git .agents/skills/windows-native

# Project-scoped (OpenCode)
git clone https://github.com/Destro01400/windows-native.git .opencode/skills/windows-native
```

### Running the Static Windows App Auditor

```bash
# Full audit (.csproj + app.manifest + C# lifecycle/security + XAML/UI)
python scripts/audit_windows_app.py path/to/YourWindowsApp

# UI/XAML-only mode, JSON output, or CI strict mode (exits 1 on ERROR/WARN)
python scripts/audit_windows_app.py path/to/YourWindowsApp --ui-only
python scripts/audit_windows_app.py path/to/YourWindowsApp --json
python scripts/audit_windows_app.py path/to/YourWindowsApp --strict

# Legacy backwards-compatible WPF UI entrypoint (delegates to audit_windows_app.py --ui-only)
python scripts/audit_wpf_ui.py path/to/YourWpfApp --strict
```

---

<a id="versão-em-português-br"></a>

## Versão em Português (BR)

Skill completa de engenharia para **aplicativos nativos do Windows 10/11** em **C#, XAML e C++** (**WPF no .NET 9/10**, **WinUI 3 / Windows App SDK + NativeAOT**, **C++/WinRT** e **Win32/DWM/CsWin32**), acompanhada de um auditor estático em Python sem dependências externas.

### O que esta Skill inclui

- **Arquitetura, DI, IPC e ciclo de vida ([`app-architecture-and-lifecycle.md`](references/app-architecture-and-lifecycle.md)):** Generic Host no WPF e WinUI 3, remoção de `StartupUri`, escrita atômica em `%LocalAppData%` + SQLite WAL, instância única com `Mutex` + `GC.KeepAlive` + Named Pipes (`CurrentUserOnly`), protocolos URI (`HKCU` vs. MSIX) protegidos contra injeção, captura de falhas, WER Restart/Recovery e logs `Serilog` assíncronos.
- **Interop de SO, CsWin32 e segurança ([`windows-os-and-cswin32.md`](references/windows-os-and-cswin32.md)):** `Microsoft.Windows.CsWin32` (`NativeMethods.txt`/`.json`, `SafeHandle`/`Lease()`, `[LibraryImport]`), seletores nativos (`OpenFolderDialog`, `IFileOpenDialog`), `RegisterHotKey` vs. `WH_KEYBOARD_LL`, DPAPI `CurrentUser`, Credential Manager vs. `PasswordVault`, UAC/`app.manifest` (`PerMonitorV2`, `longPathAware`, UTF-8), eventos de hardware/áudio/energia sem vazamentos.
- **WinUI 3, C# NativeAOT e C++/WinRT / Win32 moderno ([`winui3-and-cppwinrt-native.md`](references/winui3-and-cppwinrt-native.md)):** empacotado vs. desempacotado (`WindowsPackageType=None`), redirecionamento de instância única, `AppWindow` e barra de título, `x:Bind`/`x:Phase`, `DispatcherQueue`, NativeAOT com `CsWinRT >= 2.1.6`, C++20 + WIL + corrotinas (`get_weak()`), e esqueletos Win32 + Direct2D/DirectComposition (`< 2 MB`).
- **Empacotamento, NativeAOT, assinatura e atualizações ([`packaging-signing-and-updates.md`](references/packaging-signing-and-updates.md)):** single-file WPF (`IncludeNativeLibrariesForSelfExtract`, `AppContext.BaseDirectory`), ReadyToRun vs. NativeAOT (`NETSDK1168` no WPF), MSIX e **Sparse Packages** (`uap10:AllowExternalContent`), **WiX v5** vs. **Inno Setup 6** (por usuário + bootstrapper WebView2/`.NET`), **Velopack** vs. `.appinstaller`, **Azure Artifact Signing** + timestamp RFC 3161 e mitigação de SmartScreen.
- **Testes, crash dumps e profiling ([`diagnostics-testing-and-profiling.md`](references/diagnostics-testing-and-profiling.md)):** pirâmide de testes (`xUnit`, `Xunit.StaFact` `[WpfFact]`, `FlaUI.UIA3` e ressalvas de CI), snapshots `RenderTargetBitmap`, WER `LocalDumps`, `Serilog.Sinks.Async`/`OpenTelemetry`, `dotnet-counters`, `dotnet-gcdump`, `dotnet-dump`, PerfView, `WPR`/`WPA` e Snoop.
- **Design Windows 11 / Fluent 2 ([`fluent-design-tokens-and-ux.md`](references/fluent-design-tokens-and-ux.md)):** grade de `4 px`, escala tipográfica, contraste WCAG AA (`4,5:1`), raios concêntricos, Mica/Acrylic/Smoke, ícones, diálogos/`InfoBar`, telas de espera e foco por teclado.
- **Integração nativa Windows 11 e DWM ([`window-chrome-and-win11.md`](references/window-chrome-and-win11.md)):** `WindowChrome` sem `AllowsTransparency="True"`, `DwmSetWindowAttribute`, **Snap Layouts (`HTMAXBUTTON`)**, janela maximizada com DPI, troca de tema em tempo real e `ThemeMode` (.NET 9/10).
- **Movimento e animações ([`motion-and-animations.md`](references/motion-and-animations.md)):** durações (`83/167/250/333 ms`) e `KeySpline`s Fluent, `VisualStateManager`, prevenção de travamentos em iGPU, redução de movimento e `CompositionTarget.Rendering` com `dt` real.
- **Arquitetura XAML, desempenho e acessibilidade ([`xaml-architecture-and-quality.md`](references/xaml-architecture-and-quality.md)):** `ResourceDictionary` em camadas, `CommunityToolkit.Mvvm` 8.4, virtualização de listas, streaming sem reconstrução `O(N²)`, vazamentos de memória e leitores de tela (`AutomationProperties` e `LiveRegionChanged`).
- **Temas próprios de marca ([`custom-brand-theming.md`](references/custom-brand-theming.md)):** personalidade visual própria mantendo contraste WCAG, controles nativos sem estilo Aero, fontes embutidas e cache congelado.
- **Auditor estático ([`scripts/audit_windows_app.py`](scripts/audit_windows_app.py) e [`scripts/audit_wpf_ui.py`](scripts/audit_wpf_ui.py)):** audita `.csproj`, `app.manifest`, ciclo de vida/segurança em C# e regras WPF/XAML (`--ui-only`, `--strict`, `--json`).

### Como instalar no seu projeto

```bash
# Via Skills CLI
npx skills add Destro01400/windows-native

# No Antigravity (dentro da pasta do projeto)
git clone https://github.com/Destro01400/windows-native.git .agent/skills/windows-native

# No Claude Code (dentro da pasta do projeto)
git clone https://github.com/Destro01400/windows-native.git .claude/skills/windows-native

# No Codex (dentro da pasta do projeto)
git clone https://github.com/Destro01400/windows-native.git .agents/skills/windows-native

# No OpenCode (dentro da pasta do projeto)
git clone https://github.com/Destro01400/windows-native.git .opencode/skills/windows-native
```

Para auditar qualquer projeto Windows localmente:

```bash
python scripts/audit_windows_app.py caminho/do/seu-app-windows --strict
```

---

## License

Released under the [MIT License](LICENSE).
