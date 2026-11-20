# Windows App Testing, Crash Dumps, Observability & Profiling (.NET 9/10)

> **Scope:** Testing pyramid for WPF & WinUI 3 (`xUnit`/`NUnit`, `Xunit.StaFact`, `FlaUI.UIA3`, `RenderTargetBitmap` snapshots, GitHub Actions caveats), Windows Error Reporting (`LocalDumps`), recursive-safe crash capture, `Serilog.Sinks.Async` + `OpenTelemetry` flushing, and live CPU/memory/GPU diagnostics (`dotnet-counters`, `dotnet-gcdump`, `dotnet-dump`, `dotnet-trace`, PerfView, WPR/WPA, VS XAML Binding Failures, Snoop).
>
> **Related:** See [compiler-traps-and-compat.md](compiler-traps-and-compat.md) for compiler/runtime trap lookup, [webview2-and-hybrid-apps.md](webview2-and-hybrid-apps.md) for WebView2 `TrySuspendAsync` memory control, and [graphics-media-and-windows-ai.md](graphics-media-and-windows-ai.md) for Direct2D/SkiaSharp/Win2D/DirectComposition rendering paths.

## Table of Contents

1. [Testing Pyramid for Windows Desktop Apps](#1-testing-pyramid-for-windows-desktop-apps)
2. [Headless Unit & STA Dispatcher Testing](#2-headless-unit--sta-dispatcher-testing)
3. [Automated UI E2E with `FlaUI.UIA3` & CI Caveats](#3-automated-ui-e2e-with-flauiuia3--ci-caveats)
4. [Visual Regression Snapshots (`RenderTargetBitmap` & `Verify.Wpf`)](#4-visual-regression-snapshots-rendertargetbitmap--verifywpf)
5. [Unhandled Exceptions, WER `LocalDumps` & Observability](#5-unhandled-exceptions-wer-localdumps--observability)
6. [Live Memory, CPU & Rendering Profiling on Windows](#6-live-memory-cpu--rendering-profiling-on-windows)

---

## 1. Testing Pyramid for Windows Desktop Apps

| Layer | Share | Context | What It Proves | Speed & Reliability |
|---|---|---|---|---|
| **1. Headless Unit Tests** | ~80% | `dotnet test` (`xUnit`/`NUnit`, MTA) | ViewModels, commands, validation, streaming buffers, IPC | `< 10 ms`/test; runs anywhere |
| **2. STA & Snapshot Tests** | ~15% | `Xunit.StaFact` (`[WpfFact]`) / `RenderTargetBitmap` | `DependencyProperty` callbacks, `ControlTemplate` parts, visual layout | `20–200 ms`/test; Windows Desktop SDK |
| **3. UI E2E (`FlaUI.UIA3`)** | ~5% | Real EXE via Windows UIA3 COM | Window launch, `AutomationId` tree, modal focus trapping, persistence | `1–5 s`/test; needs interactive session |

> **Legacy Note:** `microsoft/WinAppDriver` has been unmaintained since 2020. Use **`FlaUI.UIA3`** for desktop UI automation across WPF, WinUI 3, and Win32.

---

## 2. Headless Unit & STA Dispatcher Testing

### 2.1 Decouple ViewModels with `IDialogService` & `IDispatcherService`

ViewModels must never construct `Window`, call `MessageBox.Show`, or touch `Application.Current.Dispatcher` directly. Inject thin abstractions so 80%+ of app logic runs headless without an STA message pump:

```csharp
// Requires NuGet: CommunityToolkit.Mvvm (>= 8.4.2), xunit
using System;
using System.Threading.Tasks;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;
using Xunit;

namespace MyApp.Testing;

public interface IDispatcherService
{
    void Invoke(Action action);
    Task InvokeAsync(Action action);
}

public interface IDialogService
{
    Task<bool> ConfirmAsync(string title, string message);
}

public sealed partial class ProfileEditorViewModel(
    IDialogService dialogs,
    IDispatcherService dispatcher) : ObservableObject
{
    [ObservableProperty]
    public partial string DisplayName { get; set; } = string.Empty;

    [ObservableProperty]
    public partial string StatusMessage { get; private set; } = "Ready";

    [RelayCommand]
    private async Task ResetAsync()
    {
        if (!await dialogs.ConfirmAsync("Reset profile", "Discard unsaved edits?")) return;
        await dispatcher.InvokeAsync(() =>
        {
            DisplayName = string.Empty;
            StatusMessage = "Reset complete";
        });
    }
}

public sealed class ImmediateDispatcherService : IDispatcherService
{
    public void Invoke(Action action) => action();
    public Task InvokeAsync(Action action) { action(); return Task.CompletedTask; }
}

public sealed class StubDialogService(bool answer) : IDialogService
{
    public Task<bool> ConfirmAsync(string title, string message) => Task.FromResult(answer);
}

public sealed class ProfileEditorViewModelTests
{
    [Fact]
    public async Task ResetCommand_ClearsDisplayName_WhenConfirmed()
    {
        var vm = new ProfileEditorViewModel(new StubDialogService(true), new ImmediateDispatcherService())
        {
            DisplayName = "Ada Lovelace"
        };
        await vm.ResetCommand.ExecuteAsync(null);
        Assert.Equal(string.Empty, vm.DisplayName);
        Assert.Equal("Reset complete", vm.StatusMessage);
    }
}
```

### 2.2 STA Dispatcher Tests (`Xunit.StaFact` vs. Manual STA Thread)

Use an STA thread with a live `Dispatcher` only when testing `Window`/`UserControl` visual behavior, `DependencyProperty` coercion, `BindingOperations`, or `HwndSource` hooks:

- **Preferred (`Xunit.StaFact` NuGet):** Use `[WpfFact]` (or `[UIFact]`). It creates a fresh STA thread with `DispatcherSynchronizationContext` per test and tears it down automatically.
- **The `ShutdownFinished` Trap:** Once `Dispatcher.InvokeShutdown()` executes on a thread, that thread's `Dispatcher` enters `ShutdownFinished` **permanently** and cannot restart. Never reuse a shared STA thread after shutdown—spawn and join a dedicated `Thread` per test:

```csharp
using System;
using System.Runtime.ExceptionServices;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Threading;

namespace MyApp.Testing;

public static class StaTestRunner
{
    public static void RunWpf(Func<Dispatcher, Task> body)
    {
        ExceptionDispatchInfo? captured = null;
        var thread = new Thread(() =>
        {
            var dispatcher = Dispatcher.CurrentDispatcher;
            SynchronizationContext.SetSynchronizationContext(new DispatcherSynchronizationContext(dispatcher));
            dispatcher.InvokeAsync(async () =>
            {
                try { await body(dispatcher); }
                catch (Exception ex) { captured = ExceptionDispatchInfo.Capture(ex); }
                finally { dispatcher.InvokeShutdown(); }
            });
            Dispatcher.Run();
        });
        thread.SetApartmentState(ApartmentState.STA);
        thread.IsBackground = true;
        thread.Start();
        thread.Join();
        captured?.Throw();
    }
}
```

> **Test `Application` Rule:** Avoid instantiating `new System.Windows.Application()` repeatedly (`Application.Current` is an `AppDomain` singleton). If one is initialized once in a fixture, set `ShutdownMode = ShutdownMode.OnExplicitShutdown` so closing a test `Window` never kills the host `Application`.

---

## 3. Automated UI E2E with `FlaUI.UIA3` & CI Caveats

### 3.1 Resilient Querying, Modal Checks & Focus Verification

- **Query by `AutomationProperties.AutomationId`:** Stable across localization and visual layout refactors (unlike localized `Name` or tree indexes).
- **Never use `Thread.Sleep`:** Wait for windows, controls, and dialogs using `Retry.WhileNull(...)` or `Retry.WhileTrue(...)`.
- **Verify Modals & Focus Return:** Assert `mainWindow.ModalWindows` shows the dialog (`AutomationProperties.IsDialog="True"`), confirm `automation.FocusedElement()` sits inside it, press `Esc`, and assert keyboard focus returns to the invoking trigger button.

```csharp
// Requires NuGet: FlaUI.UIA3, xunit
using System;
using FlaUI.Core;
using FlaUI.Core.AutomationElements;
using FlaUI.Core.Input;
using FlaUI.Core.Tools;
using FlaUI.Core.WindowsAPI;
using FlaUI.UIA3;
using Xunit;

namespace MyApp.UiTests;

public static class SmokeUiTests
{
    public static void VerifySettingsModalFocusFlow(string exePath, int? attachPid = null)
    {
        using var app = attachPid is int pid ? Application.Attach(pid) : Application.Launch(exePath);
        try
        {
            using var automation = new UIA3Automation();
            var mainWindow = Retry.WhileNull(
                () => app.GetMainWindow(automation),
                timeout: TimeSpan.FromSeconds(10),
                interval: TimeSpan.FromMilliseconds(200)).Result;
            Assert.NotNull(mainWindow);

            var openBtn = Retry.WhileNull(
                () => mainWindow.FindFirstDescendant(cf => cf.ByAutomationId("OpenSettingsButton"))?.AsButton(),
                timeout: TimeSpan.FromSeconds(5)).Result;
            Assert.NotNull(openBtn);
            openBtn.Invoke(); // Prefer UIA InvokePattern over raw mouse coordinates

            var modal = Retry.WhileNull(
                () => mainWindow.ModalWindows.Length > 0 ? mainWindow.ModalWindows[0] : null,
                timeout: TimeSpan.FromSeconds(5)).Result;
            Assert.NotNull(modal);

            Keyboard.Type(VirtualKeyShort.ESCAPE);
            bool stillOpen = Retry.WhileTrue(
                () => mainWindow.ModalWindows.Length > 0,
                timeout: TimeSpan.FromSeconds(3)).Result;

            Assert.False(stillOpen);
            Assert.Equal("OpenSettingsButton", automation.FocusedElement()?.Properties.AutomationId.ValueOrDefault);
        }
        finally
        {
            if (!app.HasExited) app.Close();
        }
    }
}
```

### 3.2 GitHub Actions (`windows-latest`) Headless & Interactive Session Caveats

1. **No Interactive Desktop Session (`WinSta0`):** Hosted `windows-latest` runners execute under a non-interactive service/agent session without an unlocked console desktop. Hardware mouse/keyboard injection (`Mouse.Click(x, y)`, `SendInput`) and foreground focus assertions frequently fail with `ErrorCode: 5 (Access Denied)` or `NullReferenceException` on `GetMainWindow`.
2. **No Physical GPU:** Hosted VMs lack hardware GPUs; DirectX/WebView2 or hardware-accelerated composition may stall or draw blank frames unless software rendering is enabled (`RenderOptions.ProcessRenderMode = RenderMode.SoftwareOnly` in WPF test mode).
3. **Recommended CI Split:** Run Layer 1 (headless unit), Layer 2 (`[WpfFact]` + offscreen `RenderTargetBitmap`), and [`audit_windows_app.py`](../scripts/audit_windows_app.py) (`--strict` or `--sarif` for GitHub Code Scanning) on `windows-latest`. Inside UIA tests, prefer pattern calls (`Invoke()`, `ValuePattern`, `Toggle()`) over physical cursor clicks, and run full interactive FlaUI suites on a **self-hosted Windows runner** with an active auto-logon desktop session.

---

## 4. Visual Regression Snapshots (`RenderTargetBitmap` & `Verify.Wpf`)

Four pitfalls cause flaky visual snapshot tests:

1. **Offscreen / Unmeasured Visuals Render Blank:** `RenderTargetBitmap.Render` outputs `0x0` or empty frames unless `Measure`, `Arrange`, `UpdateLayout`, and a `Dispatcher` flush run first.
2. **Host DPI Drift:** Passing live monitor DPI causes `150%` laptops to diverge from `96` DPI CI baselines. Pin snapshot bitmaps to `96.0` DPI (`PixelFormats.Pbgra32`).
3. **Blinking `TextBox` Carets & 60 FPS Loops:** Active caret pulses, `CompositionTarget.Rendering` loops, and `RepeatBehavior="Forever"` shimmers cause random pixel diffs. Gate animations behind a test flag and set `CaretBrush = Brushes.Transparent` before capture.
4. **`ApplicationIdle` Hang Trap:** Never pass `DispatcherPriority.ApplicationIdle` to `Dispatcher.PushFrame` if any timer/render loop runs—flush with `DispatcherPriority.Background` or `Loaded`.

```csharp
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;

namespace MyApp.Testing;

public static class SnapshotTestOptions
{
    public static bool DisableAnimationsForTests { get; set; }
}

public static class SnapshotRenderer
{
    public static byte[] RenderControlToPng(FrameworkElement element, double width, double height)
    {
        SnapshotTestOptions.DisableAnimationsForTests = true;
        try
        {
            if (element is TextBox tb) tb.CaretBrush = Brushes.Transparent;

            element.Width = width;
            element.Height = height;
            element.Measure(new Size(width, height));
            element.Arrange(new Rect(0, 0, width, height));
            element.UpdateLayout();
            FlushDispatcher(DispatcherPriority.Background);

            var rtb = new RenderTargetBitmap((int)width, (int)height, 96.0, 96.0, PixelFormats.Pbgra32);
            rtb.Render(element);

            var encoder = new PngBitmapEncoder();
            encoder.Frames.Add(BitmapFrame.Create(rtb));
            using var ms = new MemoryStream();
            encoder.Save(ms);
            return ms.ToArray();
        }
        finally
        {
            SnapshotTestOptions.DisableAnimationsForTests = false;
        }
    }

    private static void FlushDispatcher(DispatcherPriority priority)
    {
        var frame = new DispatcherFrame();
        Dispatcher.CurrentDispatcher.BeginInvoke(
            priority,
            new DispatcherOperationCallback(static state =>
            {
                ((DispatcherFrame)state!).Continue = false;
                return null;
            }),
            frame);
        Dispatcher.PushFrame(frame);
    }
}
```

> **Snapshot Diffing (`Verify.Wpf`):** Pair deterministic layout flushing with **`Verify.Wpf`** (`await Verifier.Verify(control);`) to store `.verified.png` baselines and highlight pixel diffs in CI.

---

## 5. Unhandled Exceptions, WER `LocalDumps` & Observability

### 5.1 Unhandled Exception Capture Without Recursive Crash Loops

Wire all three desktop exception boundaries and protect crash logging with `Interlocked.Exchange` so secondary I/O or dispatcher errors never trigger infinite recursion:

- **`Application.DispatcherUnhandledException` (WPF) / `Application.Current.UnhandledException` (WinUI 3):** UI thread faults (WinUI 3 also catches `async void` errors on `DispatcherQueue`). Set `e.Handled = true` **only** for known-recoverable UI errors; leave fatal crashes unhandled so WER captures the real stack.
- **`AppDomain.CurrentDomain.UnhandledException`:** Fatal background-thread faults (`IsTerminating == true`). Never show WPF dialogs/windows here—the dispatcher may already be deadlocked.
- **`TaskScheduler.UnobservedTaskException`:** Forgotten `Task` faults collected on the finalizer thread; log and call `e.SetObserved()`.

```csharp
using System;
using System.IO;
using System.Threading;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Threading;

namespace MyApp.Diagnostics;

public static class CrashGuard
{
    private static int _isCrashing;
    private static Action? _flushTelemetry;

    public static void Install(Application app, Action? flushTelemetry = null)
    {
        _flushTelemetry = flushTelemetry;
        app.DispatcherUnhandledException += OnDispatcherUnhandledException;
        AppDomain.CurrentDomain.UnhandledException += OnAppDomainUnhandledException;
        TaskScheduler.UnobservedTaskException += OnUnobservedTaskException;
    }

    public static void Uninstall(Application app)
    {
        app.DispatcherUnhandledException -= OnDispatcherUnhandledException;
        AppDomain.CurrentDomain.UnhandledException -= OnAppDomainUnhandledException;
        TaskScheduler.UnobservedTaskException -= OnUnobservedTaskException;
    }

    private static void OnDispatcherUnhandledException(object sender, DispatcherUnhandledExceptionEventArgs e) =>
        HandleFatal("DispatcherUnhandledException", e.Exception);

    private static void OnAppDomainUnhandledException(object sender, UnhandledExceptionEventArgs e)
    {
        var ex = e.ExceptionObject as Exception ?? new Exception($"Non-CLS crash: {e.ExceptionObject}");
        HandleFatal("AppDomainUnhandledException", ex);
    }

    private static void OnUnobservedTaskException(object? sender, UnobservedTaskExceptionEventArgs e)
    {
        WriteEmergencyLog("UnobservedTaskException", e.Exception);
        e.SetObserved();
    }

    private static void HandleFatal(string boundary, Exception ex)
    {
        if (Interlocked.Exchange(ref _isCrashing, 1) != 0) return; // Stop recursive crash loops
        WriteEmergencyLog(boundary, ex);
        try { _flushTelemetry?.Invoke(); } catch { }
    }

    private static void WriteEmergencyLog(string boundary, Exception ex)
    {
        try
        {
            var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MyApp", "logs");
            Directory.CreateDirectory(dir);
            File.AppendAllText(Path.Combine(dir, "crash.log"),
                $"[{DateTimeOffset.UtcNow:O}] [{boundary}] {ex}{Environment.NewLine}{Environment.NewLine}");
        }
        catch { }
    }
}
```

### 5.2 Windows Error Reporting (`WER`) `LocalDumps`

Enable OS-level `.dmp` capture for native crashes (`0xC0000005`, `StackOverflowException`, GPU faults) and fatal managed crashes (`DumpType = 2` captures full managed heaps for SOS `dumpheap`/`gcroot`; `DumpFolder` **must** be `REG_EXPAND_SZ` for `%LocalAppData%`):

```powershell
$exe = "MyApp.exe"
$key = "HKLM:\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps\$exe" # Or HKCU:\... for per-user
New-Item -Path $key -Force | Out-Null
Set-ItemProperty -Path $key -Name "DumpFolder" -Value "%LocalAppData%\CrashDumps" -Type ExpandString
Set-ItemProperty -Path $key -Name "DumpCount"  -Value 10 -Type DWord
Set-ItemProperty -Path $key -Name "DumpType"   -Value 2  -Type DWord # 1 = Mini, 2 = Full
```

### 5.3 Desktop Observability (`Serilog.Sinks.Async`, `OpenTelemetry` & Event Log)

- **Async File Sink:** Wrap `WriteTo.File(...)` in `WriteTo.Async(...)` (`Serilog.Sinks.Async`) so disk I/O never blocks UI frames.
- **OpenTelemetry Batching:** `TracerProvider` and `MeterProvider` use `BatchExportProcessor` queues that vanish on desktop window close unless explicitly flushed. Call `ForceFlush(2000)`, `Log.CloseAndFlush()`, and `.Dispose()` on `OnExit` and inside `CrashGuard`.
- **Event Viewer Caveat:** `EventLog.WriteEntry` with a custom source throws `SecurityException` for non-admin users unless the installer pre-registers the source under `HKLM\SYSTEM\CurrentControlSet\Services\EventLog\Application`. Prefer `%LocalAppData%\<MyApp>\logs\` + OpenTelemetry OTLP.

```csharp
// Requires NuGet: Serilog, Serilog.Sinks.Async, Serilog.Sinks.File, OpenTelemetry, OpenTelemetry.Exporter.OpenTelemetryProtocol
using System;
using System.IO;
using OpenTelemetry;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using Serilog;

namespace MyApp.Diagnostics;

public sealed class TelemetryBootstrap : IDisposable
{
    public TracerProvider TracerProvider { get; }
    public MeterProvider MeterProvider { get; }

    public TelemetryBootstrap(string serviceName, string version, Uri otlpEndpoint)
    {
        var logDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MyApp", "logs");
        Log.Logger = new LoggerConfiguration()
            .MinimumLevel.Information()
            .WriteTo.Async(a => a.File(Path.Combine(logDir, "app-.log"), rollingInterval: RollingInterval.Day, retainedFileCountLimit: 7))
            .CreateLogger();

        var resource = ResourceBuilder.CreateDefault().AddService(serviceName, serviceVersion: version);
        TracerProvider = Sdk.CreateTracerProviderBuilder().SetResourceBuilder(resource).AddSource(serviceName)
            .AddOtlpExporter(o => o.Endpoint = otlpEndpoint).Build();
        MeterProvider = Sdk.CreateMeterProviderBuilder().SetResourceBuilder(resource).AddMeter(serviceName)
            .AddOtlpExporter(o => o.Endpoint = otlpEndpoint).Build();
    }

    public void FlushAndClose()
    {
        TracerProvider.ForceFlush(2000);
        MeterProvider.ForceFlush(2000);
        Log.CloseAndFlush();
    }

    public void Dispose()
    {
        FlushAndClose();
        TracerProvider.Dispose();
        MeterProvider.Dispose();
    }
}
```

---

## 6. Live Memory, CPU & Rendering Profiling on Windows

### 6.1 `.NET` CLI Diagnostics (`dotnet-counters`, `dotnet-gcdump`, `dotnet-dump`, `dotnet-trace`)

```powershell
dotnet-counters ps
dotnet-counters monitor -p <PID> --counters `
  System.Runtime[gc-heap-size,gen-0-gc-count,gen-1-gc-count,gen-2-gc-count,alloc-rate,threadpool-queue-length]

# Diff managed heap before/after opening & closing a view 5x
dotnet-gcdump collect -p <PID> -o baseline.gcdump
dotnet-gcdump collect -p <PID> -o after.gcdump

# Full dump + SOS root analysis for retained WPF visual trees
dotnet-dump collect -p <PID> --type Full -o app_leak.dmp
dotnet-dump analyze app_leak.dmp
# SOS prompt:  dumpheap -stat   ->   dumpheap -mt <MethodTable>   ->   gcroot <ObjectAddress>

# CPU sampling trace -> PerfView / Speedscope flamegraph
dotnet-trace collect -p <PID> --profile cpu-sampling -o cpu.nettrace
dotnet-trace convert --format speedscope cpu.nettrace
```

- **Typical WPF `gcroot` Leak Roots:** `SystemEvents` static handler list (missing `-=`), `ValueChangedEventManager` / `PropertyDescriptor` (unremoved `DependencyPropertyDescriptor.AddValueChanged` or plain CLR binding missing `INotifyPropertyChanged`), `DispatcherTimer` / `CompositionTarget`, and unremoved `HwndSource` hooks.
- **PerfView:** Open `.nettrace` for `CPU Stacks` / `GC Heap`, or record an ETW trace in **PerfView** with `Thread Time` enabled to expose synchronous locks/I/O stalling the UI thread at near-`0%` CPU.

### 6.2 WPR & WPA for UI Delays, DWM & MilCore Frame Drops

```cmd
wpr -start GeneralProfile -start DesktopComposition -start XAMLAppResponsiveness -filemode
:: Reproduce scroll/animation stutter or drag lag for 5-15s
wpr -stop C:\Temp\ui_perf.etl
```

*(GUI equivalent: `WPRUI.exe` -> **First level triage**, **Desktop composition activity**, **XAML App Responsiveness analysis**.)*

- **System Activity -> UI Delays:** Inspect `MsgCheck Delay` (`> 200 ms`) to pinpoint the frozen `PID`/`TID`, then drill into **CPU Usage (Precise) / Wait Analysis** for the blocking stack.
- **DWM & MilCore (`dwm.exe`, `dwmcore.dll`, `wpfgfx_cor3.dll`) + `VSync-DwmFrame`:** Diagnoses dropped frames caused by oversized `BlurEffect`/`DropShadowEffect` shader passes, excessive `UIElement.Opacity` isolation surfaces, or accidental software rendering (`RenderCapability.Tier == 0`).

### 6.3 VS XAML Binding Failures & Snoop (`snoopwpf`)

| Tool | Use Case | Crucial Rules & Caveats |
|---|---|---|
| **VS XAML Binding Failures** | *View -> Other Windows -> XAML Binding Failures* (`Ctrl+Q`) | Target **0** binding errors before release; silent fallbacks burn reflection CPU and hide broken bindings. |
| **`PresentationTraceSources.TraceLevel`** | Per-binding trace (`diag:PresentationTraceSources.TraceLevel=High` via `clr-namespace:System.Diagnostics;assembly=WindowsBase`) | Logs `DataContext` resolution step-by-step in VS Output; **remove before shipping**. |
| **Snoop (`snoopwpf`)** | Live visual tree, `DataContext`, *"Visuals with binding errors"* filter | Uses `ManagedInjector`—**cannot attach to `PublishSingleFile=true` / self-contained single-file EXEs**. Keep Debug/QA profiling builds unpacked. |
