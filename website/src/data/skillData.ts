export type Lang = 'en' | 'pt';

export interface TrapCase {
  id: string;
  code: string;
  title: string;
  broken: string;
  fixed: string;
  why: { en: string; pt: string };
}

export const COMPILER_TRAPS: TrapCase[] = [
  {
    id: 'mc3072',
    code: 'MC3072',
    title: 'AccessibilityView="Raw"',
    broken: `<Button AutomationProperties.Name="Close">\n  <TextBlock Text="&#xE8BB;"\n    AutomationProperties.AccessibilityView="Raw" />\n</Button>`,
    fixed: `<Button AutomationProperties.Name="Close"\n        ToolTip="Close">\n  <TextBlock Text="&#xE8BB;" IsHitTestVisible="False" />\n</Button>`,
    why: {
      en: 'AccessibilityView="Raw" exists only in WinUI 3 / UWP and crashes WPF XAML builds (MC3072). Use ControlTemplate glyphs or IsHitTestVisible="False".',
      pt: 'AccessibilityView="Raw" só existe no WinUI 3/UWP e quebra o build XAML no WPF (MC3072). Use ControlTemplate ou IsHitTestVisible="False".',
    },
  },
  {
    id: 'netsdk1168',
    code: 'NETSDK1168',
    title: 'PublishAot on WPF',
    broken: `<PropertyGroup>\n  <UseWPF>true</UseWPF>\n  <PublishAot>true</PublishAot>\n</PropertyGroup>`,
    fixed: `<PropertyGroup>\n  <UseWPF>true</UseWPF>\n  <PublishReadyToRun Condition="'$(Configuration)' == 'Release'">true</PublishReadyToRun>\n</PropertyGroup>`,
    why: {
      en: 'WPF does not support NativeAOT or PublishTrimmed (NETSDK1168). Use ReadyToRun for WPF, and reserve PublishAot for WinUI 3 (CsWinRT 2.2+) or Win32.',
      pt: 'WPF não suporta NativeAOT nem PublishTrimmed (NETSDK1168). Use PublishReadyToRun no WPF e deixe PublishAot para WinUI 3 ou Win32.',
    },
  },
  {
    id: 'cs0115',
    code: 'CS0115',
    title: 'OnIsEnabledChanged',
    broken: `protected override void OnIsEnabledChanged(\n  DependencyPropertyChangedEventArgs e)\n{\n  base.OnIsEnabledChanged(e);\n}`,
    fixed: `public ToolCard()\n{\n  IsEnabledChanged += (_, _) => UpdateVisualStates(true);\n}`,
    why: {
      en: 'UIElement.IsEnabledChanged is a CLR event in WPF—there is no virtual OnIsEnabledChanged method to override.',
      pt: 'No WPF, IsEnabledChanged é um evento CLR — não existe método virtual OnIsEnabledChanged para sobrescrever.',
    },
  },
  {
    id: 'cs9248',
    code: 'CS9248',
    title: 'Mvvm 8.4.0 vs 8.4.2',
    broken: `<!-- PackageReference CommunityToolkit.Mvvm 8.4.0 -->\n[ObservableProperty]\npublic partial string Query { get; set; }`,
    fixed: `<!-- Upgrade to >= 8.4.2 on .NET 10 -->\n[ObservableProperty]\npublic partial string Query { get; set; } = string.Empty;`,
    why: {
      en: 'Mvvm 8.4.0 triggers CS9248 on partial properties unless LangVersion=preview is forced; 8.4.2+ compiles cleanly on stock .NET 10.',
      pt: 'Mvvm 8.4.0 gera erro CS9248 em partial properties no .NET 10 padrão; a versão 8.4.2+ compila nativamente sem preview.',
    },
  },
  {
    id: 'pinvoke',
    code: 'PInvoke001',
    title: 'CsWin32 Comments',
    broken: `# NativeMethods.txt\nRegisterHotKey\nUnregisterHotKey`,
    fixed: `// NativeMethods.txt\nRegisterHotKey\nUnregisterHotKey`,
    why: {
      en: 'CsWin32 0.3.x rejects "#" comments inside NativeMethods.txt with PInvoke001—comments must use "//".',
      pt: 'O CsWin32 0.3.x rejeita comentários com "#" dentro do NativeMethods.txt (PInvoke001) — use "//".',
    },
  },
];

export interface StackSpec {
  id: string;
  name: string;
  badge: string;
  summary: { en: string; pt: string };
  metrics: { label: { en: string; pt: string }; value: string }[];
  snippetTitle: string;
  snippet: string;
}

export const STACK_SPECS: StackSpec[] = [
  {
    id: 'wpf',
    name: 'WPF (.NET 9 / 10)',
    badge: 'Desktop Standard',
    summary: {
      en: 'Best balance of mature ecosystem, custom WindowChrome Snap Layouts, DynamicResource brand themes, and fast development.',
      pt: 'Melhor equilíbrio entre ecossistema maduro, WindowChrome com Snap Layouts, temas dinâmicos de marca e produtividade.',
    },
    metrics: [
      { label: { en: 'Compilation', pt: 'Compilação' }, value: 'PublishReadyToRun' },
      { label: { en: 'AOT / Trim', pt: 'AOT / Trim' }, value: 'Not supported (NETSDK1168)' },
      { label: { en: 'Win11 Chrome', pt: 'Chrome Win11' }, value: 'WindowChrome + DWM Interop' },
      { label: { en: 'MVVM Stack', pt: 'Stack MVVM' }, value: 'CommunityToolkit.Mvvm >= 8.4.2' },
    ],
    snippetTitle: 'CustomChromeWindow.xaml.cs — Snap Layouts',
    snippet: `case WM_NCHITTEST:\n  long lp = lParam.ToInt64();\n  var pt = new Point((short)(lp & 0xFFFF), (short)((lp >> 16) & 0xFFFF));\n  if (IsOverElement(MaxBtn, pt)) {\n    SetMaxHover(true);\n    handled = true;\n    return HTMAXBUTTON; // Triggers Win11 Snap Layouts\n  }`,
  },
  {
    id: 'winui3',
    name: 'WinUI 3 + NativeAOT',
    badge: 'Windows App SDK 1.7+',
    summary: {
      en: 'Modern Fluent 2 system controls, compiled x:Bind bindings, native MicaBackdrop, and full C# NativeAOT publishing via CsWinRT 2.2+.',
      pt: 'Controles nativos Fluent 2, x:Bind compilado, MicaBackdrop nativo e publicação real com PublishAot=true via CsWinRT 2.2+.',
    },
    metrics: [
      { label: { en: 'Compilation', pt: 'Compilação' }, value: 'PublishAot=true (CsWinRT 2.2+)' },
      { label: { en: 'Packaging', pt: 'Empacotamento' }, value: 'MSIX or WindowsPackageType=None' },
      { label: { en: 'Bindings', pt: 'Bindings' }, value: 'Compiled x:Bind + [GeneratedBindableCustomProperty]' },
      { label: { en: 'Threading', pt: 'Threading' }, value: 'DispatcherQueue.TryEnqueue' },
    ],
    snippetTitle: 'Program.cs — Single-Instance Redirection',
    snippet: `// Requires <DefineConstants>$(DefineConstants);DISABLE_XAML_GENERATED_MAIN</DefineConstants>\nvar key = AppInstance.FindOrRegisterForKey("main");\nif (!key.IsCurrent) {\n  await key.RedirectActivationToAsync(AppInstance.GetCurrent().GetActivatedEventArgs());\n  return;\n}\nApplication.Start(p => { new App(); });`,
  },
  {
    id: 'cswin32',
    name: 'Win32 via CsWin32',
    badge: 'Zero-Guess P/Invoke',
    summary: {
      en: 'Compile-time source-generated Win32 and COM projections using Microsoft.Windows.CsWin32 with SafeHandles and zero manual marshaling bugs.',
      pt: 'Bindings Win32 e COM gerados na compilação via Microsoft.Windows.CsWin32, com SafeHandles e sem DllImport frágil.',
    },
    metrics: [
      { label: { en: 'Generator', pt: 'Gerador' }, value: 'Microsoft.Windows.CsWin32 0.3.371+' },
      { label: { en: 'Input File', pt: 'Entrada' }, value: 'NativeMethods.txt (// comments only)' },
      { label: { en: 'Lifetime', pt: 'Ciclo de vida' }, value: 'SafeFileHandle + PInvoke017 Lease()' },
      { label: { en: 'Build Flag', pt: 'Flag de build' }, value: '<AllowUnsafeBlocks>true</AllowUnsafeBlocks>' },
    ],
    snippetTitle: 'NativeMethods.json — Safe & Modern Projections',
    snippet: `{\n  "$schema": "https://aka.ms/CsWin32.schema.json",\n  "allowMarshaling": false,\n  "useSafeHandles": true,\n  "friendlyOverloads": true\n}`,
  },
  {
    id: 'cppwinrt',
    name: 'C++/WinRT & Direct2D',
    badge: 'Zero .NET Runtime (< 2 MB)',
    summary: {
      en: 'Ultra-lean native C++20 desktop utilities and high-frequency overlays using WIL RAII wrappers, safe coroutines, and DirectComposition.',
      pt: 'Utilitários nativos em C++20 abaixo de 2 MB sem runtime .NET, usando WIL RAII, corrotinas seguras e DirectComposition.',
    },
    metrics: [
      { label: { en: 'Language', pt: 'Linguagem' }, value: 'C++20 /MSVC /permissive- /W4 /WX' },
      { label: { en: 'RAII Layer', pt: 'Camada RAII' }, value: 'Microsoft.Windows.ImplementationLibrary (WIL)' },
      { label: { en: 'Coroutines', pt: 'Corrotinas' }, value: 'get_weak() + wil::resume_foreground' },
      { label: { en: 'Rendering', pt: 'Renderização' }, value: 'WS_EX_NOREDIRECTIONBITMAP + DComp' },
    ],
    snippetTitle: 'MainPage.cpp — Leak-Safe Coroutine Resume',
    snippet: `winrt::fire_and_forget MainPage::OnLoadClicked()\n{\n  auto weak = get_weak();\n  co_await winrt::resume_background();\n  auto result = LoadFromRegistry();\n  co_await wil::resume_foreground(DispatcherQueue());\n  if (auto self = weak.get()) { self->Label(result); }\n}`,
  },
];

export interface GuideDoc {
  file: string;
  category: 'arch' | 'ui' | 'native' | 'ship';
  lines: number;
  title: { en: string; pt: string };
  desc: { en: string; pt: string };
  tags: string[];
}

export const GUIDE_DOCS: GuideDoc[] = [
  {
    file: 'app-architecture-and-lifecycle.md',
    category: 'arch',
    lines: 543,
    title: { en: 'App Architecture & Lifecycle', pt: 'Arquitetura & Ciclo de Vida' },
    desc: {
      en: 'Generic Host DI, StartupUri removal, atomic %LocalAppData% JSON, SQLite WAL, Mutex + GC.KeepAlive, Named Pipes ACLs, URI handlers, WER Restart/Recovery.',
      pt: 'Generic Host DI, remoção de StartupUri, escrita atômica em %LocalAppData%, SQLite WAL, Mutex com GC.KeepAlive, Named Pipes, URI myapp:// e WER.',
    },
    tags: ['Generic Host', 'Named Pipes', 'SQLite WAL', 'WER'],
  },
  {
    file: 'windows-os-and-cswin32.md',
    category: 'arch',
    lines: 526,
    title: { en: 'Windows OS & CsWin32 Interop', pt: 'Interop Windows & CsWin32' },
    desc: {
      en: 'CsWin32 projections, OpenFolderDialog & IFileOpenDialog, RegisterHotKey, DPAPI CurrentUser, Credential Manager, UAC manifest, WASAPI & PowerModeChanged.',
      pt: 'Projeções CsWin32, diálogos nativos, atalhos globais, DPAPI CurrentUser, Credential Manager, manifesto UAC, WASAPI e eventos de energia.',
    },
    tags: ['CsWin32', 'DPAPI', 'RegisterHotKey', 'app.manifest'],
  },
  {
    file: 'winui3-and-cppwinrt-native.md',
    category: 'native',
    lines: 648,
    title: { en: 'WinUI 3, NativeAOT & C++/WinRT', pt: 'WinUI 3, NativeAOT & C++/WinRT' },
    desc: {
      en: 'Packaged vs. unpackaged WinUI 3, AppWindow & TitleBar, x:Bind/x:Phase, PublishAot + CsWinRT 2.2, C++20/WIL coroutines, MIDL 3.0, and Direct2D/DirectComposition.',
      pt: 'WinUI 3 empacotado/desempacotado, AppWindow, x:Bind, NativeAOT com CsWinRT 2.2, C++20/WIL, MIDL 3.0 e Direct2D/DirectComposition.',
    },
    tags: ['WinUI 3', 'PublishAot', 'C++/WinRT', 'WIL'],
  },
  {
    file: 'packaging-signing-and-updates.md',
    category: 'ship',
    lines: 554,
    title: { en: 'Packaging, Signing & Auto-Update', pt: 'Empacotamento, Assinatura & Updates' },
    desc: {
      en: 'Single-File WPF pitfalls, ReadyToRun vs. NativeAOT, MSIX & Sparse Packages (ComServer + MakeAppx /nv), WiX v5 vs. Inno Setup 6, Velopack, Azure Artifact Signing.',
      pt: 'Single-File WPF, ReadyToRun vs. NativeAOT, MSIX e Sparse Packages, WiX v5 vs. Inno Setup 6, Velopack e Azure Artifact Signing + SmartScreen.',
    },
    tags: ['MSIX', 'Sparse Package', 'Velopack', 'Signing'],
  },
  {
    file: 'diagnostics-testing-and-profiling.md',
    category: 'ship',
    lines: 485,
    title: { en: 'Testing, Crash Dumps & Profiling', pt: 'Testes, Crash Dumps & Profiling' },
    desc: {
      en: 'Headless xUnit pyramid, Xunit.StaFact [WpfFact], FlaUI.UIA3 E2E, RenderTargetBitmap snapshots, WER LocalDumps, OpenTelemetry, dotnet-dump & WPR/WPA.',
      pt: 'Pirâmide xUnit sem interface, [WpfFact], FlaUI.UIA3, snapshots visuais, WER LocalDumps, OpenTelemetry, dotnet-dump e WPR/WPA.',
    },
    tags: ['FlaUI.UIA3', 'WER LocalDumps', 'dotnet-dump', 'WPA'],
  },
  {
    file: 'fluent-design-tokens-and-ux.md',
    category: 'ui',
    lines: 337,
    title: { en: 'Fluent 2 Design Tokens & UX', pt: 'Tokens Fluent 2 & UX Windows 11' },
    desc: {
      en: '4 epx grid, DPI plateaus, Win11 type ramp, OKLCH/WCAG AA contrast math, concentric corners, Mica/Acrylic/Smoke layering, dialogs, InfoBar, SettingsCard.',
      pt: 'Grade 4 epx, escala tipográfica, contraste WCAG AA, raios concêntricos, Mica/Acrylic/Smoke, diálogos, InfoBar, Wait UX e SettingsCard.',
    },
    tags: ['4px Grid', 'WCAG AA', 'Mica', 'SettingsCard'],
  },
  {
    file: 'window-chrome-and-win11.md',
    category: 'ui',
    lines: 458,
    title: { en: 'WindowChrome, DWM & Snap Layouts', pt: 'WindowChrome, DWM & Snap Layouts' },
    desc: {
      en: 'AllowsTransparency pitfalls, dwmapi.dll attributes, compile-verified HTMAXBUTTON Snap Layouts, DPI-scaled maximized bounds, PerMonitorV2, ThemeMode (.NET 10).',
      pt: 'Alternativa segura a AllowsTransparency, dwmapi.dll, Snap Layouts (HTMAXBUTTON) compilável, janela maximizada com DPI e ThemeMode.',
    },
    tags: ['WindowChrome', 'HTMAXBUTTON', 'DWM', 'PerMonitorV2'],
  },
  {
    file: 'motion-and-animations.md',
    category: 'ui',
    lines: 581,
    title: { en: 'Motion Design & iGPU Performance', pt: 'Movimento & GPU Integrada' },
    desc: {
      en: 'Fluent 83/167/250ms KeySplines, VisualStateManager, frozen-brush hover crossfades, TransitioningContentControl, Skeleton shimmer, dt-normalized visualizers.',
      pt: 'Curvas Fluent em KeySpline, VisualStateManager, hover sem pincel congelado quebrado, Skeleton 30 fps e CompositionTarget.Rendering com dt.',
    },
    tags: ['KeySpline', 'VSM', 'po:Freeze', 'Reduced Motion'],
  },
  {
    file: 'xaml-architecture-and-quality.md',
    category: 'ui',
    lines: 322,
    title: { en: 'XAML Architecture & UI Automation', pt: 'Arquitetura XAML & Acessibilidade' },
    desc: {
      en: 'Layered ResourceDictionaries, CommunityToolkit.Mvvm 8.4.2+, VirtualizingStackPanel traps, 20–30 Hz streaming batching, memory leaks, UIA & LiveRegionChanged.',
      pt: 'ResourceDictionary em camadas, Mvvm 8.4.2+, VirtualizingStackPanel, batching 20–30 Hz, vazamentos de memória e leitores de tela UIA.',
    },
    tags: ['Mvvm 8.4.2', 'Virtualization', 'UIA', 'Memory Leaks'],
  },
  {
    file: 'custom-brand-theming.md',
    category: 'ui',
    lines: 122,
    title: { en: 'Custom Brand Theming', pt: 'Temas Próprios de Marca' },
    desc: {
      en: 'Distinct brand palettes without Aero control leaks, embedded pack:// font fallback chains, badge contrast fixes (*Dim ink), and frozen resource caching.',
      pt: 'Paletas próprias sem controles Aero padrão, fontes embutidas com fallback, contraste de badges e cache congelado de pincéis.',
    },
    tags: ['Brand Palette', 'Fonts', 'Frozen Cache', 'Zero Aero'],
  },
];

export const AUDITOR_OUTPUTS = {
  full: {
    cmd: 'python scripts/audit_windows_app.py ./MyWindowsApp --strict',
    lines: [
      { kind: 'dim', text: 'Scanned 9 XAML, 46 C#, 1 .csproj, 1 .manifest files' },
      { kind: 'err', text: '[ERROR:CSPROJ]    MyApp.csproj: <PublishAot>true</PublishAot> unsupported with UseWPF (NETSDK1168)' },
      { kind: 'err', text: '[ERROR:WPF-BUG]   Views/Modal.xaml:42 AccessibilityView="Raw" fails WPF XAML build (MC3072)' },
      { kind: 'warn', text: '[WARN:LIFECYCLE]  Program.cs:19 new Mutex(...) lacks GC.KeepAlive(mutex)' },
      { kind: 'warn', text: '[WARN:SECURITY]   Browser.cs:64 ProcessStartInfo($"https://{host}/{slug}") with UseShellExecute=true' },
      { kind: 'warn', text: '[WARN:MANIFEST]   app.manifest missing <dpiAwareness>PerMonitorV2</dpiAwareness>' },
      { kind: 'warn', text: '[WARN:CONTRAST]   Theme/Colors.xaml:18 Coral (#E85D66) on CoralSoft (#FDE7E9) = 3.08:1 (< 4.5:1 AA)' },
      { kind: 'dim', text: 'Summary: 2 errors · 4 warnings · 0 info (exit 1 under --strict)' },
    ],
  },
  clean: {
    cmd: 'python scripts/audit_windows_app.py ./VerifiedApp --strict --json',
    lines: [
      { kind: 'dim', text: 'Scanned 4 XAML, 14 C#, 1 .csproj, 1 .manifest files' },
      { kind: 'ok', text: '{' },
      { kind: 'ok', text: '  "mode": "full",' },
      { kind: 'ok', text: '  "counts": { "error": 0, "warn": 0, "info": 0 },' },
      { kind: 'ok', text: '  "findings": []' },
      { kind: 'ok', text: '}' },
      { kind: 'ok', text: '✓ Clean pass — zero unresolved Windows build, manifest, lifecycle, or UI issues (exit 0)' },
    ],
  },
};
