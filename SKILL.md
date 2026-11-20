---
name: windows-native
license: MIT
description: Design, scaffold, build, harden, package, sign, test, and audit native Windows 10/11 desktop apps in C#, XAML, and C++ (WPF on .NET 9/10, WinUI 3 with Windows App SDK and NativeAOT, C++/WinRT, Win32/DWM/CsWin32). Use for new apps or reviews of existing ones. Covers compile-verified starter templates, a SARIF static auditor, Generic Host DI, single-instance IPC, Windows Services and named pipes, WebView2 hybrid apps, DirectML and Windows AI, WASAPI and graphics capture, DLL hijack defense, Windows Hello, OAuth PKCE, WDAC, MSIX and Sparse Packages, WiX v5, Inno Setup, Velopack, Azure Artifact Signing, Fluent 2 tokens, Snap Layouts, PerMonitorV2 DPI, motion, accessibility, FlaUI tests, crash dumps, and compiler trap lookups such as NETSDK1168, MC3072, and CS9248.
---

# Windows Native App Engineering (`windows-native`)

End-to-end guide for **native Windows 10/11 desktop apps**: **WPF (`.NET 9/10`)**, **WinUI 3 (`Windows App SDK` + NativeAOT)**, **C++/WinRT / pure Win32**, and **CsWin32 interop**. Covers scaffolding, architecture, OS security, Fluent 2 UI/motion, hybrid web, background services, graphics/AI, packaging/signing/updates, testing, and static auditing.

> Load **only** the reference file(s) the active task needs. Paths below are relative to this folder.

---

## 1-Hop Decision Tree

| If the task is... | Template (`scripts/scaffold_windows_app.py --template`) | Read first | Then |
|---|---|---|---|
| Rich LOB / branded desktop app, custom chrome, fast iteration | `wpf-modern` | [window-chrome-and-win11.md](references/window-chrome-and-win11.md) | UI: [fluent-design-tokens-and-ux.md](references/fluent-design-tokens-and-ux.md), [xaml-architecture-and-quality.md](references/xaml-architecture-and-quality.md); Arch: [app-architecture-and-lifecycle.md](references/app-architecture-and-lifecycle.md); Ship: [packaging-signing-and-updates.md](references/packaging-signing-and-updates.md) (`PublishReadyToRun`, never `PublishAot`) |
| Modern Fluent 2 app, smallest/fastest managed binary | `winui3-aot` | [winui3-and-cppwinrt-native.md](references/winui3-and-cppwinrt-native.md) | [app-architecture-and-lifecycle.md](references/app-architecture-and-lifecycle.md), [compiler-traps-and-compat.md](references/compiler-traps-and-compat.md), [packaging-signing-and-updates.md](references/packaging-signing-and-updates.md) (`PublishAot`, `CsWinRT 2.2`) |
| Tray tool / HUD / launcher, zero .NET runtime, under 2 MB | `cppwinrt-dcomp` | [winui3-and-cppwinrt-native.md](references/winui3-and-cppwinrt-native.md) (Part B) | [security-hardening-and-enterprise.md](references/security-hardening-and-enterprise.md) (DLL hijack), [graphics-media-and-windows-ai.md](references/graphics-media-and-windows-ai.md) |
| Embedded web UI (SPA, Markdown, OAuth pages) | `wpf-modern` or `winui3-aot` | [webview2-and-hybrid-apps.md](references/webview2-and-hybrid-apps.md) | [security-hardening-and-enterprise.md](references/security-hardening-and-enterprise.md) |
| Windows Service + tray/UI companion | any (service project separate) | [background-services-and-ipc.md](references/background-services-and-ipc.md) | [packaging-signing-and-updates.md](references/packaging-signing-and-updates.md) (WiX `ServiceInstall`) |
| Build error, analyzer warning, or OS-version question | n/a | [compiler-traps-and-compat.md](references/compiler-traps-and-compat.md) | Owning guide linked in each row |
| Existing codebase review | n/a | Run `scripts/audit_windows_app.py` | Fix by finding category using the routing table below |

Scaffold example: `python scripts/scaffold_windows_app.py --template wpf-modern --name Contoso --out ./Contoso` (`--list`, `--namespace`, `--force` also supported).

---

## Quick Reference Routing

| Area | File |
|---|---|
| Generic Host DI (`StartupUri` removal, `XmlLanguage`), atomic `%LocalAppData%` JSON + SQLite WAL, `Mutex` (`Local\`/`Global\`) + `GC.KeepAlive` + `NamedPipeServerStream` IPC, URI protocols, WER Restart/Recovery, async `Serilog` | [app-architecture-and-lifecycle.md](references/app-architecture-and-lifecycle.md) |
| `Microsoft.Windows.CsWin32` (`NativeMethods.txt`/`.json`, `SafeHandle`/`Lease()`), `[LibraryImport]`, Shell pickers, Drag-Drop UIPI, `RegisterHotKey`, DPAPI `CurrentUser`, Credential Manager, UAC/`app.manifest`, `WM_DEVICECHANGE`, `SystemEvents` leaks | [windows-os-and-cswin32.md](references/windows-os-and-cswin32.md) |
| **WinUI 3** (packaged vs `WindowsPackageType=None`, `AppInstance`, `AppWindow`/TitleBar, `x:Bind`, `DispatcherQueue`, NativeAOT) and **C++/WinRT / Win32** (decision matrix, WIL, coroutines, Direct2D/DirectComposition) | [winui3-and-cppwinrt-native.md](references/winui3-and-cppwinrt-native.md) |
| Single-file/R2R/AOT publishing, MSIX + Sparse Packages, WiX v5 vs Inno Setup 6, Velopack vs `.appinstaller`, Azure Artifact Signing, SmartScreen | [packaging-signing-and-updates.md](references/packaging-signing-and-updates.md) |
| Testing pyramid (`Xunit.StaFact`, `FlaUI.UIA3`, snapshots), WER `LocalDumps`, `Serilog`/OpenTelemetry flush, `dotnet-counters`/`gcdump`/`dump`, WPR/WPA | [diagnostics-testing-and-profiling.md](references/diagnostics-testing-and-profiling.md) |
| **WebView2**: Evergreen vs Fixed runtime, explicit `UserDataFolder`, virtual host mapping, typed JSON messaging, lockdown, `TrySuspendAsync`, WPF/WinUI 3 differences | [webview2-and-hybrid-apps.md](references/webview2-and-hybrid-apps.md) |
| **Session 0** services (`AddWindowsService`), gRPC over Named Pipes, `PipeSecurity` ACLs, length-prefixed framing, `MemoryMappedFile` ring buffer, `sc.exe failure`, tray watchdog | [background-services-and-ipc.md](references/background-services-and-ipc.md) |
| Rendering ladder (`DrawingContext` to `D3DImage`/`SwapChainPanel`), Graphics Capture, WASAPI/loopback, HID/Serial/BLE, `OnnxRuntime.DirectML`, `Microsoft.Windows.AI` | [graphics-media-and-windows-ai.md](references/graphics-media-and-windows-ai.md) |
| DLL hijack defense, Windows Hello, OAuth 2.0 PKCE loopback, proxy/PAC/TLS hygiene, AppLocker/WDAC, SBOM, deterministic builds | [security-hardening-and-enterprise.md](references/security-hardening-and-enterprise.md) |
| Verified compiler/runtime traps (`MC3072`, `NETSDK1168`, `CS0115`, `CS9248`, `SYSLIB1062`, `PInvoke001/017`, `C00CE014`, `IL3000`, `WPF0001`, `Window.Current`) + OS build matrix (`19041`/`22000`/`22621`/`26100`) | [compiler-traps-and-compat.md](references/compiler-traps-and-compat.md) |
| 4 px grid, type ramp, color tokens, WCAG, radii, Mica/Acrylic/Smoke, icons, dialogs, Wait UX, Settings | [fluent-design-tokens-and-ux.md](references/fluent-design-tokens-and-ux.md) |
| `WindowChrome`, `DwmSetWindowAttribute`, Snap Layouts (`HTMAXBUTTON`), maximized bounds, `PerMonitorV2` DPI, `ThemeMode` | [window-chrome-and-win11.md](references/window-chrome-and-win11.md) |
| Fluent motion curves to `KeySpline`, `VisualStateManager`, hover/expand/shimmer recipes, `CompositionTarget.Rendering`, reduced motion | [motion-and-animations.md](references/motion-and-animations.md) |
| Layered `ResourceDictionary` tokens, `CommunityToolkit.Mvvm` 8.4, virtualization, streaming Markdown perf, memory leaks, UIA | [xaml-architecture-and-quality.md](references/xaml-architecture-and-quality.md) |
| Custom brand themes (embedded fonts, badge WCAG fixes, styled built-in controls, opaque vs Mica chrome) | [custom-brand-theming.md](references/custom-brand-theming.md) |

### Scripts and Assets

| Tool | Usage |
|---|---|
| [scripts/scaffold_windows_app.py](scripts/scaffold_windows_app.py) | `--list`, `--template {wpf-modern,winui3-aot,cppwinrt-dcomp}`, `--name`, `--out`, `--namespace`, `--force`. Templates live in `assets/templates/` and are compile-verified (`TreatWarningsAsErrors`, MSVC `/W4 /WX`). |
| [scripts/audit_windows_app.py](scripts/audit_windows_app.py) | `python scripts/audit_windows_app.py APP_DIR` plus `--ui-only` (XAML/UI only), `--strict` (exit 1 on ERROR/WARN, for CI), `--json` (tooling), `--sarif` (SARIF 2.1.0 for GitHub Code Scanning; mutually exclusive with `--json`). Scans `.csproj`, manifests, XAML, C#, and C++. |
| [scripts/audit_wpf_ui.py](scripts/audit_wpf_ui.py) | Backwards-compatible UI-only wrapper (`--json`, `--sarif`, `--strict`). |
| `scripts/test_audit_windows_app.py`, `scripts/test_scaffold.py` | Zero-dependency suites: `python -B -m unittest discover -s scripts -p "test_*.py" -v`. |

---

## Core Workflow

1. **Audit first (existing code):** run the auditor with `--strict` to surface `.csproj` pitfalls (`NETSDK1168`, missing `AllowUnsafeBlocks`), manifest gaps, lifecycle/security bugs (`Mutex` GC, `SystemEvents` leaks, DPAPI `LocalMachine`, unvalidated `UseShellExecute`), WebView2/WinUI 3/C++ traps, contrast and UIA gaps.
2. **Pick the stack deliberately:** WPF for mature ecosystem and custom chrome (`PublishReadyToRun`, no `PublishAot`); WinUI 3 for Fluent 2 + NativeAOT; C++/WinRT or Win32 + DirectComposition for sub-2 MB, zero-runtime tools.
3. **Scaffold, don't improvise:** start from `scaffold_windows_app.py` so manifest (`PerMonitorV2`, `longPathAware`, `asInvoker`), Snap Layouts, `Mutex` + `GC.KeepAlive`, and token dictionaries are already correct.
4. **Architect:** Generic Host DI, atomic `%LocalAppData%` persistence, `CurrentUserOnly` pipes, crash guards ([app-architecture-and-lifecycle.md](references/app-architecture-and-lifecycle.md)). Keep services headless and use a tray companion ([background-services-and-ipc.md](references/background-services-and-ipc.md)).
5. **Interop and harden:** prefer CsWin32 `SafeHandle`s, `SetDefaultDllDirectories`, DPAPI `CurrentUser`, explicit WebView2 `UserDataFolder`, release lockdown ([windows-os-and-cswin32.md](references/windows-os-and-cswin32.md), [security-hardening-and-enterprise.md](references/security-hardening-and-enterprise.md), [webview2-and-hybrid-apps.md](references/webview2-and-hybrid-apps.md)).
6. **Polish UI:** 4 epx grid, WCAG contrast of 4.5:1 for text, never `AllowsTransparency="True"` on main windows, animate `RenderTransform`/`Opacity` only, honor `SystemParameters.ClientAreaAnimation`, preserve virtualization, label icon-only buttons (`AutomationProperties.Name` + `ToolTip`).
7. **Guard OS versions:** wrap build-specific APIs with `OperatingSystem.IsWindowsVersionAtLeast` (`19041`/`22000`/`22621`/`26100`) ([compiler-traps-and-compat.md](references/compiler-traps-and-compat.md)).
8. **Package, sign, update:** loose self-contained + `PublishReadyToRun` + Velopack for consumer apps; WiX v5 or MSIX for enterprise; sign inside-out with RFC 3161 timestamps ([packaging-signing-and-updates.md](references/packaging-signing-and-updates.md)).
9. **Test and profile:** 80% headless xUnit, `[WpfFact]` for STA, FlaUI on interactive sessions, WER `LocalDumps`, `dotnet-counters`/`gcdump` ([diagnostics-testing-and-profiling.md](references/diagnostics-testing-and-profiling.md)).

---

## Pre-Delivery Checklist

1. **Static audit:** `python scripts/audit_windows_app.py APP_DIR --strict` exits 0 (use `--sarif` in CI for Code Scanning).
2. **Clean build:** `dotnet build -p:TreatWarningsAsErrors=true` yields 0 warnings and 0 errors (and 0 XAML binding failures at runtime); C++ compiles with `/std:c++20 /permissive- /utf-8 /EHsc /W4 /WX`.
3. **Platform checks:** `PerMonitorV2` at 100%/125%/150%, Snap Layouts, keyboard-only flow (`Tab`/`F6`/`Esc`), Contrast themes, reduced motion, single-instance handoff, OS-build guards for DWM/AI APIs.
4. **Security checks:** `asInvoker` manifest, named pipes `CurrentUserOnly` or explicit `PipeSecurity`, no TLS validation bypass outside `#if DEBUG`, WebView2 DevTools off in Release, DLL search paths locked.
5. **Release checks:** Authenticode signature + RFC 3161 timestamp (`signtool verify /pa`), clean uninstall, update path tested.
