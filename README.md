# Windows Native App Engineering (`windows-native`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Target: .NET 9 / 10 WPF, WinUI 3 & C++/WinRT](https://img.shields.io/badge/Target-.NET%209%2F10%20WPF%20%7C%20WinUI%203%20%7C%20C%2B%2B%2FWinRT-512BD4.svg)](#)

An agent skill for full-lifecycle **native Windows 10/11 desktop application engineering** across **WPF (`.NET 9/10`)**, **WinUI 3 (`Windows App SDK` + NativeAOT)**, **C++/WinRT**, and **modern Win32/DWM/CsWin32**. It ships **15 reference guides**, **3 compile-verified starter templates** with a CLI scaffolder, and a zero-dependency **Python static auditor with SARIF 2.1.0 output** for GitHub Code Scanning.

*(Versão em Português abaixo / [Portuguese README](#versão-em-português-br))*

---

## What This Skill Covers

| Area | Guide |
|---|---|
| App architecture, Generic Host DI, atomic persistence, single-instance IPC, URI protocols, crash recovery | [`app-architecture-and-lifecycle.md`](references/app-architecture-and-lifecycle.md) |
| CsWin32, Shell pickers, hotkeys, DPAPI / Credential Manager, UAC manifests, hardware/audio/power events | [`windows-os-and-cswin32.md`](references/windows-os-and-cswin32.md) |
| WinUI 3 (packaged/unpackaged, `AppWindow`, `x:Bind`, NativeAOT) and C++/WinRT / Win32 + Direct2D/DirectComposition | [`winui3-and-cppwinrt-native.md`](references/winui3-and-cppwinrt-native.md) |
| Publishing (R2R/AOT/single-file), MSIX + Sparse Packages, WiX v5, Inno Setup 6, Velopack, Azure Artifact Signing, SmartScreen | [`packaging-signing-and-updates.md`](references/packaging-signing-and-updates.md) |
| Testing pyramid, FlaUI, snapshots, WER `LocalDumps`, OpenTelemetry, `dotnet-counters`/`gcdump`/`dump`, WPR/WPA | [`diagnostics-testing-and-profiling.md`](references/diagnostics-testing-and-profiling.md) |
| WebView2 hybrid apps: Evergreen vs Fixed runtime, `UserDataFolder`, virtual host mapping, typed messaging, lockdown, `TrySuspendAsync` | [`webview2-and-hybrid-apps.md`](references/webview2-and-hybrid-apps.md) |
| Windows Services (Session 0), gRPC over Named Pipes, `PipeSecurity` ACLs, framing, ring buffers, `sc.exe failure`, tray watchdog | [`background-services-and-ipc.md`](references/background-services-and-ipc.md) |
| GPU rendering ladder, Windows Graphics Capture, WASAPI, HID/Serial/BLE, DirectML, `Microsoft.Windows.AI` | [`graphics-media-and-windows-ai.md`](references/graphics-media-and-windows-ai.md) |
| DLL hijack defense, Windows Hello, OAuth 2.0 PKCE, proxy/TLS hygiene, AppLocker/WDAC, SBOM, deterministic builds | [`security-hardening-and-enterprise.md`](references/security-hardening-and-enterprise.md) |
| Verified compiler/runtime traps (`MC3072`, `NETSDK1168`, `CS9248`, `SYSLIB1062`, `PInvoke001/017`, `C00CE014`, ...) + Windows build matrix (`19041`-`26100`) | [`compiler-traps-and-compat.md`](references/compiler-traps-and-compat.md) |
| Fluent 2 grid, type ramp, color tokens, WCAG contrast, materials, Wait UX | [`fluent-design-tokens-and-ux.md`](references/fluent-design-tokens-and-ux.md) |
| `WindowChrome`, DWM, Snap Layouts (`HTMAXBUTTON`), `PerMonitorV2` DPI, `ThemeMode` | [`window-chrome-and-win11.md`](references/window-chrome-and-win11.md) |
| Motion curves, `KeySpline`, `VisualStateManager`, `CompositionTarget.Rendering`, iGPU performance | [`motion-and-animations.md`](references/motion-and-animations.md) |
| Layered XAML tokens, `CommunityToolkit.Mvvm` 8.4, virtualization, streaming perf, UI Automation | [`xaml-architecture-and-quality.md`](references/xaml-architecture-and-quality.md) |
| Custom brand themes without Aero leaks, WCAG-safe badges, frozen resource caching | [`custom-brand-theming.md`](references/custom-brand-theming.md) |

### Starter Templates (`assets/templates/`)

| Template | Stack |
|---|---|
| `wpf-modern` | `.NET 10` WPF, Generic Host DI, `WindowChrome` + Snap Layouts (`HTMAXBUTTON`), CsWin32, `MotionSettings`, WCAG AA tokens, `PublishReadyToRun` |
| `winui3-aot` | `.NET 10` WinUI 3, Windows App SDK 1.7, `PublishAot`, `AppInstance` single-instance, custom `TitleBar` + Mica, compiled `x:Bind` |
| `cppwinrt-dcomp` | C++20 + CMake, C++/WinRT, Direct2D + DirectComposition, `PerMonitorV2`, `SetDefaultDllDirectories` |

---

## Repository Structure

```text
windows-native/
├── SKILL.md                                         # Core instructions, decision tree & routing table
├── README.md                                        # Documentation (EN / PT-BR)
├── LICENSE                                          # MIT License
├── .gitignore
├── assets/
│   └── templates/
│       ├── wpf-modern/                              # WPF .NET 10 starter (manifest, chrome, tokens, motion, CsWin32)
│       ├── winui3-aot/                              # WinUI 3 + NativeAOT starter (Program.cs, TitleBar, Mica)
│       └── cppwinrt-dcomp/                          # C++/WinRT + Direct2D/DirectComposition starter (CMake)
├── references/
│   ├── app-architecture-and-lifecycle.md            # Generic Host DI, persistence, IPC, URI protocols, crash recovery
│   ├── windows-os-and-cswin32.md                    # CsWin32, Shell pickers, hotkeys, DPAPI/CredMan, manifest, hardware/power
│   ├── winui3-and-cppwinrt-native.md                # WinUI 3 (.NET + NativeAOT) & C++/WinRT / modern Win32
│   ├── packaging-signing-and-updates.md             # Publish/SingleFile/R2R/AOT, MSIX/Sparse, WiX v5/Inno 6, Velopack, signing
│   ├── diagnostics-testing-and-profiling.md         # xUnit/StaFact/FlaUI, WER LocalDumps, Serilog/OTel, dotnet-dump/WPR/WPA
│   ├── webview2-and-hybrid-apps.md                  # WebView2 runtime, UserDataFolder, messaging, lockdown, lifecycle
│   ├── background-services-and-ipc.md               # Session 0, WindowsServices, gRPC over pipes, PipeSecurity, watchdog
│   ├── graphics-media-and-windows-ai.md             # GPU ladder, Graphics Capture, WASAPI, devices, DirectML/Windows AI
│   ├── security-hardening-and-enterprise.md         # DLL hijack, Hello, PKCE, proxy/TLS, WDAC, SBOM
│   ├── compiler-traps-and-compat.md                 # Compiler/runtime trap lookup + Windows 10/11 build matrix
│   ├── fluent-design-tokens-and-ux.md               # Windows 11 / Fluent 2 tokens, 4px grid, typography, contrast, UX
│   ├── window-chrome-and-win11.md                   # WindowChrome, DWM, Snap Layouts, DPI, ThemeMode
│   ├── motion-and-animations.md                     # Fluent curves, KeySpline, VSM, CompositionTarget, iGPU perf
│   ├── xaml-architecture-and-quality.md             # Layered tokens, Mvvm 8.4, virtualization, streaming, UIA
│   └── custom-brand-theming.md                      # Custom palettes, embedded fonts, control coverage, frozen cache
└── scripts/
    ├── scaffold_windows_app.py                      # Template scaffolder (--list/--template/--name/--out/--namespace/--force)
    ├── audit_windows_app.py                         # Static auditor (--ui-only/--strict/--json/--sarif)
    ├── audit_wpf_ui.py                              # Backwards-compatible UI-only wrapper
    ├── test_audit_windows_app.py                    # Auditor unit tests (unittest)
    └── test_scaffold.py                             # Scaffolder unit tests (unittest)
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

## Usage

### Scaffold a starter app

```bash
python scripts/scaffold_windows_app.py --list
python scripts/scaffold_windows_app.py --template wpf-modern --name Contoso --out ./Contoso
python scripts/scaffold_windows_app.py --template winui3-aot --name Contoso --namespace Contoso.App --out ./ContosoWinUI
python scripts/scaffold_windows_app.py --template cppwinrt-dcomp --name ContosoTool --out ./ContosoTool
```

### Audit an app

```bash
python scripts/audit_windows_app.py path/to/YourWindowsApp                # human-readable findings
python scripts/audit_windows_app.py path/to/YourWindowsApp --ui-only      # XAML/UI checks only
python scripts/audit_windows_app.py path/to/YourWindowsApp --json         # tooling output
python scripts/audit_windows_app.py path/to/YourWindowsApp --strict       # exit 1 on ERROR/WARN
python scripts/audit_windows_app.py path/to/YourWindowsApp --sarif        # SARIF 2.1.0 (excludes --json)
```

### GitHub Code Scanning (CI)

```yaml
# .github/workflows/windows-native-audit.yml
name: windows-native-audit
on: [push, pull_request]
jobs:
  audit:
    runs-on: windows-latest
    permissions:
      contents: read
      security-events: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - name: Audit (SARIF)
        run: python .agent/skills/windows-native/scripts/audit_windows_app.py . --sarif > audit.sarif
      - uses: github/codeql-action/upload-sarif@v3
        with: { sarif_file: audit.sarif }
```

### Run the unit tests

```bash
python -B -m unittest discover -s scripts -p "test_*.py" -v
```

---

<a id="versão-em-português-br"></a>

## Versão em Português (BR)

Skill completa de engenharia para **aplicativos nativos do Windows 10/11** em **C#, XAML e C++** (**WPF no .NET 9/10**, **WinUI 3 / Windows App SDK + NativeAOT**, **C++/WinRT** e **Win32/DWM/CsWin32**). Inclui **15 guias de referência**, **3 templates iniciais com compilação verificada** + gerador por linha de comando, e um **auditor estático em Python** (sem dependências externas) com saída **SARIF 2.1.0** para o GitHub Code Scanning.

### O que esta Skill inclui

- **Arquitetura, DI, IPC e ciclo de vida ([`app-architecture-and-lifecycle.md`](references/app-architecture-and-lifecycle.md)):** Generic Host, escrita atômica em `%LocalAppData%`, SQLite WAL, instância única (`Mutex` + `GC.KeepAlive` + Named Pipes `CurrentUserOnly`), protocolos URI, captura de falhas e logs assíncronos.
- **Interop de SO, CsWin32 e segurança ([`windows-os-and-cswin32.md`](references/windows-os-and-cswin32.md)):** `CsWin32` com `SafeHandle`, seletores nativos, `RegisterHotKey`, DPAPI `CurrentUser`, Credential Manager, `app.manifest`, eventos de hardware/áudio/energia.
- **WinUI 3, NativeAOT e C++/WinRT ([`winui3-and-cppwinrt-native.md`](references/winui3-and-cppwinrt-native.md)):** empacotado vs. desempacotado, `AppWindow`, `x:Bind`, `PublishAot`, C++20 + WIL, Direct2D/DirectComposition.
- **Empacotamento, assinatura e atualizações ([`packaging-signing-and-updates.md`](references/packaging-signing-and-updates.md)):** single-file, ReadyToRun vs. NativeAOT, MSIX e Sparse Packages, WiX v5, Inno Setup 6, Velopack, Azure Artifact Signing, SmartScreen.
- **Testes e diagnóstico ([`diagnostics-testing-and-profiling.md`](references/diagnostics-testing-and-profiling.md)):** xUnit, `Xunit.StaFact`, FlaUI, WER `LocalDumps`, OpenTelemetry, `dotnet-counters`/`gcdump`, WPR/WPA.
- **WebView2 e apps híbridos ([`webview2-and-hybrid-apps.md`](references/webview2-and-hybrid-apps.md)):** runtime Evergreen vs. Fixed, `UserDataFolder` explícita, mapeamento de host virtual, mensagens JSON tipadas, bloqueio em Release, `TrySuspendAsync`.
- **Serviços em segundo plano e IPC ([`background-services-and-ipc.md`](references/background-services-and-ipc.md)):** isolamento da Sessão 0, `AddWindowsService`, gRPC sobre Named Pipes, ACLs `PipeSecurity`, `MemoryMappedFile`, `sc.exe failure`, watchdog na bandeja.
- **Gráficos, mídia e IA do Windows ([`graphics-media-and-windows-ai.md`](references/graphics-media-and-windows-ai.md)):** escada de renderização GPU, captura de tela, WASAPI, HID/Serial/BLE, DirectML, `Microsoft.Windows.AI`.
- **Segurança e ambiente corporativo ([`security-hardening-and-enterprise.md`](references/security-hardening-and-enterprise.md)):** defesa contra DLL hijacking, Windows Hello, OAuth 2.0 PKCE, proxy/TLS, AppLocker/WDAC, SBOM, builds determinísticos.
- **Erros de compilador e compatibilidade ([`compiler-traps-and-compat.md`](references/compiler-traps-and-compat.md)):** tabela rápida (`MC3072`, `NETSDK1168`, `CS9248`, `SYSLIB1062`, `PInvoke001/017`, `C00CE014`, `IL3000`, `WPF0001`) e matriz de builds do Windows (`19041` a `26100`).
- **Design e UI ([`fluent-design-tokens-and-ux.md`](references/fluent-design-tokens-and-ux.md), [`window-chrome-and-win11.md`](references/window-chrome-and-win11.md), [`motion-and-animations.md`](references/motion-and-animations.md), [`xaml-architecture-and-quality.md`](references/xaml-architecture-and-quality.md), [`custom-brand-theming.md`](references/custom-brand-theming.md)):** grade de 4 px, contraste WCAG, `WindowChrome` + Snap Layouts, DPI `PerMonitorV2`, animações Fluent, virtualização, acessibilidade e temas de marca.
- **Templates e scripts:** `assets/templates/` (`wpf-modern`, `winui3-aot`, `cppwinrt-dcomp`), [`scaffold_windows_app.py`](scripts/scaffold_windows_app.py), [`audit_windows_app.py`](scripts/audit_windows_app.py), [`audit_wpf_ui.py`](scripts/audit_wpf_ui.py) e testes `test_*.py`.

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

### Como usar

```bash
# Criar um app inicial a partir de um template
python scripts/scaffold_windows_app.py --template wpf-modern --name MeuApp --out ./MeuApp

# Auditar um projeto (use --strict no CI e --sarif para o GitHub Code Scanning)
python scripts/audit_windows_app.py caminho/do/seu-app-windows --strict
python scripts/audit_windows_app.py caminho/do/seu-app-windows --sarif > audit.sarif
```

O exemplo de workflow do GitHub Actions acima (seção *GitHub Code Scanning*) funciona igualmente para projetos em português.

---

## License

Released under the [MIT License](LICENSE).
