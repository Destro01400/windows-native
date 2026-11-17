# Windows App Architecture, Configuration, IPC & Lifecycle (.NET 9/10)

> **Scope:** `.NET 9/10` Generic Host DI in WPF and WinUI 3, `CultureInfo` `XmlLanguage` overrides, `IOptionsMonitor` vs. `%LocalAppData%` atomic persistence, SQLite WAL mode on Windows, `Mutex` (`Local\` vs. `Global\`) + `NamedPipeServerStream` (`CurrentUserOnly`) single-instance IPC, custom URI protocols (`HKCU\Software\Classes` vs. MSIX) with command-injection defense, crash/session handlers, WER Restart/Recovery, and non-blocking structured logging.

## Table of Contents

1. [App Startup & Generic Host DI (WPF & WinUI 3)](#1-app-startup--generic-host-di-wpf--winui-3)
2. [Configuration & Crash-Safe Local Persistence](#2-configuration--crash-safe-local-persistence)
3. [Single-Instance, Activation & Secure Named-Pipe IPC](#3-single-instance-activation--secure-named-pipe-ipc)
4. [Custom URI Protocols & File Associations (`HKCU` vs. MSIX)](#4-custom-uri-protocols--file-associations-hkcu-vs-msix)
5. [Crash Recovery, Shutdown, Session Ending & Structured Logging](#5-crash-recovery-shutdown-session-ending--structured-logging)

---

## 1. App Startup & Generic Host DI (WPF & WinUI 3)

### 1.1 WPF: Remove `StartupUri` and Wire `Host.CreateApplicationBuilder`

Leaving `StartupUri` in `App.xaml` forces WPF to instantiate `MainWindow` via its parameterless constructor before DI or async services start. **Remove `StartupUri`**, resolve `MainWindow` from `IHost.Services` in `Startup`, and override `FrameworkElement.LanguageProperty` **before** any UI element is constructed.

```xml
<!-- App.xaml: NO StartupUri when using DI -->
<Application x:Class="MyApp.App"
             xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
             xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
             ShutdownMode="OnMainWindowClose"
             Startup="OnApplicationStartup"
             Exit="OnApplicationExit">
    <Application.Resources />
</Application>
```

```csharp
using System.Globalization;
using System.IO;
using System.Windows;
using System.Windows.Documents;
using System.Windows.Markup;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace MyApp;

public partial class App : Application
{
    private IHost? _host;

    private async void OnApplicationStartup(object sender, StartupEventArgs e)
    {
        // Must run BEFORE any Window/FrameworkElement is created (metadata seals after first use).
        // Override both FrameworkElement and TextElement (Run/Span/Paragraph do not inherit FrameworkElement).
        var xmlLang = XmlLanguage.GetLanguage(CultureInfo.CurrentCulture.IetfLanguageTag);
        FrameworkElement.LanguageProperty.OverrideMetadata(typeof(FrameworkElement), new FrameworkPropertyMetadata(xmlLang));
        FrameworkContentElement.LanguageProperty.OverrideMetadata(typeof(TextElement), new FrameworkPropertyMetadata(xmlLang));

        var appDataDir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "MyCompany", "MyApp");
        Directory.CreateDirectory(appDataDir);

        var builder = Host.CreateApplicationBuilder(e.Args);
        builder.Configuration.AddJsonFile(Path.Combine(appDataDir, "user-settings.json"), optional: true, reloadOnChange: true);
        builder.Services.Configure<AppUserSettings>(builder.Configuration.GetSection("UserSettings"));
        builder.Services.AddSingleton<MainWindow>();
        builder.Services.AddSingleton<MainViewModel>();
        builder.Services.AddHostedService<SyncWorkerService>();

        _host = builder.Build();
        await _host.StartAsync();

        var mainWindow = _host.Services.GetRequiredService<MainWindow>();
        MainWindow = mainWindow;
        mainWindow.Show();
    }

    private async void OnApplicationExit(object sender, ExitEventArgs e)
    {
        if (_host is null) return;
        using (_host) { await _host.StopAsync(TimeSpan.FromSeconds(5)); }
    }
}
```

> **Pitfalls (`ShutdownMode` & `XmlLanguage`):**
> - For tray-resident apps that hide when closed, use `ShutdownMode="OnExplicitShutdown"` and call `Current.Shutdown()` from the tray Exit action.
> - `XmlLanguage` override fixes WPF's `en-US` default binding format (`$12.34` / `MM/dd/yyyy`) so `StringFormat` follows OS locale; custom user overrides in Windows Regional Settings still require explicit `CultureInfo.CurrentCulture` formatting.

### 1.2 WinUI 3: Custom Entry Point (`DISABLE_XAML_GENERATED_MAIN`)

To initialize single-instance IPC or Generic Host before WinUI 3 boots, define `DISABLE_XAML_GENERATED_MAIN` and `<StartupObject>MyWinUIApp.Program</StartupObject>` in `.csproj`, then set `DispatcherQueueSynchronizationContext` inside `Application.Start`:

```csharp
using System;
using System.Threading;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using WinRT;

namespace MyWinUIApp;

public static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        ComWrappersSupport.InitializeComWrappers();
        Application.Start(_ =>
        {
            SynchronizationContext.SetSynchronizationContext(
                new DispatcherQueueSynchronizationContext(DispatcherQueue.GetForCurrentThread()));
            new App();
        });
    }
}
```

### 1.3 `IHostedService` / `BackgroundService` vs. UI Dispatcher

| Concern | Rule | Why |
|---|---|---|
| **Cold start** | Keep `IHostedService.StartAsync` non-blocking; begin `BackgroundService.ExecuteAsync` with `await Task.Yield();`. | `Host.StartAsync` runs `StartAsync` sequentially **before** `MainWindow.Show()` — blocking loops stall startup. |
| **UI updates** | Never mutate `DependencyObject` or bound `ObservableCollection<T>` from background threads. | Marshal via `Application.Current.Dispatcher.InvokeAsync(...)` (WPF) or `dispatcherQueue.TryEnqueue(...)` (WinUI 3). |
| **Shutdown** | Pass `stoppingToken` (`IHostApplicationLifetime.ApplicationStopping`) to every delay, pipe wait, and I/O call. | Prevents background loops from hanging past `Host.StopAsync(TimeSpan.FromSeconds(5))`. |

---

## 2. Configuration & Crash-Safe Local Persistence

### 2.1 `appsettings.json` vs. `%LocalAppData%` User State

Never write mutable files into `AppContext.BaseDirectory` (`Program Files` is read-only for `asInvoker` users; MSIX virtualizes writes inconsistently across upgrades).

| Data Kind | Location | API / Pattern |
|---|---|---|
| **Read-only defaults** | `appsettings.json` beside `.exe` | `IConfiguration` / `IOptions<T>` |
| **Mutable user settings** | `%LocalAppData%\<Company>\<App>\user-settings.json` | `IOptionsMonitor<T>` (`reloadOnChange: true`) + atomic writer |
| **SQLite DB & rolling logs** | `%LocalAppData%\<Company>\<App>\data.db`, `Logs\` | Keep in **`LocalApplicationData`** (never `%AppData%` roaming profiles, which corrupt locked WAL DBs) |

- **`IOptions<T>`**: singleton, never reloads. **`IOptionsSnapshot<T>`**: scoped (useless for long-lived UI singletons). **`IOptionsMonitor<T>`**: singleton-safe, fires `OnChange(Action<T, string?>)` on file updates (dispose subscription on exit).

### 2.2 Crash-Safe Atomic File Writes (Temp-File + Flush + `File.Replace` / `File.Move`)

`File.WriteAllText` truncates the target first — a crash mid-write leaves a **0-byte or half-written JSON**. Write to a temp file **in the same directory** (guaranteed same NTFS volume), flush to physical disk, and swap atomically:

```csharp
using System.IO;
using System.Text.Json;

namespace MyApp.Persistence;

public static class AtomicJsonStore
{
    public static void Save<T>(string targetPath, T value, JsonSerializerOptions? options = null)
    {
        var dir = Path.GetDirectoryName(Path.GetFullPath(targetPath))
            ?? throw new ArgumentException("Invalid target path.", nameof(targetPath));
        Directory.CreateDirectory(dir);

        // Same directory => same NTFS volume => atomic metadata rename/replace
        var tempPath = Path.Combine(dir, $".{Path.GetFileName(targetPath)}.{Guid.NewGuid():N}.tmp");
        var backupPath = Path.Combine(dir, $".{Path.GetFileName(targetPath)}.bak");

        try
        {
            using (var fs = new FileStream(tempPath, FileMode.CreateNew, FileAccess.Write, FileShare.None, 4096, FileOptions.WriteThrough))
            {
                JsonSerializer.Serialize(fs, value, options);
                fs.Flush(flushToDisk: true);
            }

            // Brief retry for transient Windows Defender / Search Indexer read locks
            for (int attempt = 0; attempt < 3; attempt++)
            {
                try
                {
                    if (File.Exists(targetPath))
                        File.Replace(tempPath, targetPath, backupPath, ignoreMetadataErrors: true);
                    else
                        File.Move(tempPath, targetPath, overwrite: true);
                    return;
                }
                catch (IOException) when (attempt < 2)
                {
                    Thread.Sleep(25 * (attempt + 1));
                }
            }
        }
        finally
        {
            if (File.Exists(tempPath))
            {
                try { File.Delete(tempPath); } catch { }
            }
        }
    }
}
```

### 2.3 SQLite WAL Mode on Windows (`Microsoft.Data.Sqlite`)

Default `DELETE` journal mode blocks concurrent readers during writes and triggers `SQLITE_BUSY` across UI + background sync tasks. Enable **WAL mode**:

```csharp
using System.IO;
using Microsoft.Data.Sqlite;

namespace MyApp.Persistence;

public static class SqliteConnectionFactory
{
    public static SqliteConnection OpenConfigured(string dbPath)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(dbPath))!);

        var connStr = new SqliteConnectionStringBuilder
        {
            DataSource = dbPath,
            Mode = SqliteOpenMode.ReadWriteCreate,
            Pooling = true
        }.ToString();

        var connection = new SqliteConnection(connStr);
        connection.Open();

        using var pragma = connection.CreateCommand();
        pragma.CommandText = """
            PRAGMA journal_mode = WAL;
            PRAGMA synchronous = NORMAL;
            PRAGMA busy_timeout = 5000;
            PRAGMA foreign_keys = ON;
            """;
        pragma.ExecuteNonQuery();
        return connection;
    }

    public static void CheckpointAndReleasePools(string dbPath)
    {
        using (var conn = new SqliteConnection(new SqliteConnectionStringBuilder { DataSource = dbPath }.ToString()))
        {
            conn.Open();
            using var cmd = conn.CreateCommand();
            cmd.CommandText = "PRAGMA wal_checkpoint(TRUNCATE);";
            cmd.ExecuteNonQuery();
        }
        // Releases Windows file locks held by connection pooling before backup/delete
        SqliteConnection.ClearAllPools();
    }
}
```

> **WAL Rules:** `WAL + synchronous = NORMAL` prevents database corruption on process crashes (the last pre-power-loss commit may roll back; use `synchronous = FULL` for strict per-commit power-loss durability). Never copy `.db` alone while `-wal`/`-shm` exist — call `BackupDatabase(...)` or `wal_checkpoint(TRUNCATE)` + `ClearAllPools()`.

---

## 3. Single-Instance, Activation & Secure Named-Pipe IPC

### 3.1 `Mutex` Traps: `Local\` vs. `Global\` and `GC.KeepAlive`

- **Terminal Services (`Local\` vs. `Global\`):** Windows isolates kernel objects per RDP / Fast User Switching session.
  - **`Local\`** (default when unprefixed): one instance **per interactive user session** — standard for desktop GUI apps so User A and User B on the same machine do not block each other.
  - **`Global\`**: machine-wide across all sessions; fails with `UnauthorizedAccessException` across mismatched user/service privilege boundaries unless custom security ACLs are supplied.
- **`GC.KeepAlive` Trap:** In Release JIT builds, an unreferenced local `Mutex` is eligible for GC immediately after checking `createdNew`, closing the OS kernel handle while the app runs! Store the `Mutex` in a field, call **`GC.KeepAlive(_mutex)`**, and dispose only on exit.
- **`AbandonedMutexException`:** Calling `mutex.WaitOne(0)` after the prior holder crashed throws `AbandonedMutexException` *after* granting ownership — catch it, verify/recover shared state, and proceed.

### 3.2 `NamedPipeServerStream` / `NamedPipeClientStream` (`PipeOptions.CurrentUserOnly`)

Always set **`PipeOptions.CurrentUserOnly | PipeOptions.Asynchronous`**. Without `CurrentUserOnly`, any local user or lower-integrity process on the machine can connect to the pipe and inject activation arguments.

```csharp
using System.IO;
using System.IO.Pipes;
using System.Text.Json;
using System.Windows;

namespace MyApp.SingleInstance;

public sealed class SingleInstanceCoordinator : IDisposable
{
    private readonly string _pipeName;
    private readonly Mutex _mutex;
    private readonly bool _isPrimary;
    private CancellationTokenSource? _cts;
    private Task? _listenTask;

    public SingleInstanceCoordinator(string appId)
    {
        _pipeName = $"{appId}.ActivationPipe";
        _mutex = new Mutex(initiallyOwned: false, $@"Local\{appId}.InstanceMutex", out _isPrimary);
    }

    public bool IsPrimaryInstance => _isPrimary;

    public async Task<bool> TryForwardArgsToPrimaryAsync(string[] args, CancellationToken ct = default)
    {
        if (_isPrimary) return false;
        try
        {
            using var client = new NamedPipeClientStream(".", _pipeName, PipeDirection.Out, PipeOptions.CurrentUserOnly | PipeOptions.Asynchronous);
            await client.ConnectAsync(timeout: 1500, ct);
            await client.WriteAsync(JsonSerializer.SerializeToUtf8Bytes(args), ct);
            await client.FlushAsync(ct);
            return true;
        }
        catch (Exception ex) when (ex is TimeoutException or IOException or UnauthorizedAccessException)
        {
            return false;
        }
    }

    public void StartListening(Action<string[]> onSecondaryActivation)
    {
        if (!_isPrimary) return;
        _cts = new CancellationTokenSource();
        _listenTask = ListenLoopAsync(onSecondaryActivation, _cts.Token);
    }

    private async Task ListenLoopAsync(Action<string[]> onSecondaryActivation, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                using var server = new NamedPipeServerStream(
                    _pipeName, PipeDirection.In, maxNumberOfServerInstances: 1,
                    PipeTransmissionMode.Byte, PipeOptions.CurrentUserOnly | PipeOptions.Asynchronous);

                await server.WaitForConnectionAsync(ct);

                using var ms = new MemoryStream();
                await server.CopyToAsync(ms, ct);
                if (ms.Length is > 0 and <= 64 * 1024)
                {
                    onSecondaryActivation(JsonSerializer.Deserialize<string[]>(ms.ToArray()) ?? []);
                }
            }
            catch (OperationCanceledException) when (ct.IsCancellationRequested) { break; }
            catch (IOException) { /* Recycle pipe after client disconnect */ }
        }
    }

    public static void ActivateExistingWindow(Window? window)
    {
        window?.Dispatcher.InvokeAsync(() =>
        {
            if (!window.IsVisible) window.Show();
            if (window.WindowState == WindowState.Minimized) window.WindowState = WindowState.Normal;
            window.Activate();
            window.Topmost = true;
            window.Topmost = false;
            window.Focus();
        });
    }

    public void Dispose()
    {
        _cts?.Cancel();
        try { _listenTask?.Wait(TimeSpan.FromMilliseconds(500)); } catch { }
        _cts?.Dispose();
        GC.KeepAlive(_mutex);
        _mutex.Dispose();
    }
}
```

> **Foreground Activation Tip:** Windows restricts background apps from stealing focus (`SetForegroundWindow` flashes the taskbar). Before writing to the pipe, the foreground secondary instance can call Win32 `AllowSetForegroundWindow(primaryPid)` so `Activate()` brings the primary window forward cleanly.

---

## 4. Custom URI Protocols & File Associations (`HKCU` vs. MSIX)

### 4.1 Unpackaged `HKCU\Software\Classes` vs. MSIX Declarations

Write unpackaged per-user schemes under **`HKCU\Software\Classes\`** (no Admin UAC required). For **MSIX-packaged** apps, declare `<uap:Protocol Name="myapp">` and `<uap:FileTypeAssociation>` in `Package.appxmanifest` so Windows routes structured `ProtocolActivatedEventArgs` / `FileActivatedEventArgs` via `AppInstance.GetCurrent().GetActivatedEventArgs()`, bypassing raw shell command strings entirely.

```xml
<!-- Package.appxmanifest (MSIX): eliminates shell command-string parsing -->
<Extensions>
  <uap:Extension Category="windows.protocol">
    <uap:Protocol Name="myapp"><uap:DisplayName>MyApp Link</uap:DisplayName></uap:Protocol>
  </uap:Extension>
  <uap:Extension Category="windows.fileTypeAssociation">
    <uap:FileTypeAssociation Name="myproject">
      <uap:SupportedFileTypes><uap:FileType>.myproj</uap:FileType></uap:SupportedFileTypes>
    </uap:FileTypeAssociation>
  </uap:Extension>
</Extensions>
```

### 4.2 Quoting `"%1"` & Defending Against Command-Line Injection

Unquoted `%1` in `shell\open\command` lets spaces inside a browser link (`myapp://open --admin`) split into separate `args[]` switches! Always quote **both** the EXE path and `"%1"`, prepend an explicit `--uri` / `--open` switch, and validate the parsed `Uri`:

```csharp
using Microsoft.Win32;

namespace MyApp.ShellRegistration;

public static class ProtocolRegistrar
{
    public static void RegisterUriProtocolForCurrentUser(string scheme, string displayName, string exePath)
    {
        using var root = Registry.CurrentUser.CreateSubKey($@"Software\Classes\{scheme}");
        root.SetValue(null, $"URL:{displayName}");
        root.SetValue("URL Protocol", string.Empty); // Mandatory empty marker for URI protocols

        using var icon = root.CreateSubKey("DefaultIcon");
        icon.SetValue(null, $"\"{exePath}\",0");

        // CRITICAL: Quote BOTH exePath AND "%1", and bind to an explicit --uri switch
        using var cmd = root.CreateSubKey(@"shell\open\command");
        cmd.SetValue(null, $"\"{exePath}\" --uri \"%1\"");
    }

    public static void RegisterFileAssociationForCurrentUser(string extension, string progId, string description, string exePath)
    {
        using (var extKey = Registry.CurrentUser.CreateSubKey($@"Software\Classes\{extension}"))
            extKey.SetValue(null, progId);

        using var progKey = Registry.CurrentUser.CreateSubKey($@"Software\Classes\{progId}");
        progKey.SetValue(null, description);
        using var cmd = progKey.CreateSubKey(@"shell\open\command");
        cmd.SetValue(null, $"\"{exePath}\" --open \"%1\"");
    }

    public static bool TryParseDeepLink(string[] args, out Uri? uri)
    {
        uri = null;
        for (int i = 0; i < args.Length - 1; i++)
        {
            if (!string.Equals(args[i], "--uri", StringComparison.Ordinal)) continue;
            string raw = args[i + 1];
            if (raw.IndexOfAny(['"', '\r', '\n', '\0']) >= 0) return false;
            if (!Uri.TryCreate(raw, UriKind.Absolute, out var parsed)) return false;
            if (!string.Equals(parsed.Scheme, "myapp", StringComparison.OrdinalIgnoreCase)) return false;
            if (parsed.Host is not ("open" or "settings" or "auth")) return false;
            uri = parsed;
            return true;
        }
        return false;
    }
}
```

---

## 5. Crash Recovery, Shutdown, Session Ending & Structured Logging

### 5.1 Global Exception Triad & Session Ending

| Hook | Scope & Behavior | Rule |
|---|---|---|
| `Application.DispatcherUnhandledException` | WPF UI thread (and `async void` UI handlers) | Never blindly set `e.Handled = true` on corrupted state; log, flush, notify, and shut down unless known transient. |
| `TaskScheduler.UnobservedTaskException` | Unawaited `Task` faults on GC finalizer | Modern `.NET` swallows these silently by default — hook, log `e.Exception`, and call `e.SetObserved()`. |
| `AppDomain.CurrentDomain.UnhandledException` | Any thread (`IsTerminating == true` on fatal) | Cannot stop termination; synchronously call `Log.CloseAndFlush()`. |
| `Application.SessionEnding` vs. `SystemEvents.SessionEnding` | OS logoff/shutdown (`WM_QUERYENDSESSION`) | Prefer `Application.SessionEnding` in WPF (`e.Cancel = true` vetoes unsaved work; inspect `e.ReasonSessionEnding`). If using `SystemEvents.SessionEnding`, always unsubscribe (`-=`) in `OnExit`. |

### 5.2 WER Restart & Recovery (`RegisterApplicationRestart` / `RegisterApplicationRecoveryCallback`)

```csharp
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using Windows.Win32;
using Windows.Win32.Foundation;
using Windows.Win32.System.Recovery;

namespace MyApp.Lifecycle;

// CsWin32 NativeMethods.txt: RegisterApplicationRestart, RegisterApplicationRecoveryCallback,
// ApplicationRecoveryInProgress, ApplicationRecoveryFinished, REGISTER_APPLICATION_RESTART_FLAGS
public static unsafe class WerRestartRecovery
{
    public static void Register()
    {
        // Do NOT include the .exe path (Windows prepends it automatically).
        // WER triggers recovery/restart only if the process ran >= 60 seconds before crashing/hanging.
        _ = PInvoke.RegisterApplicationRestart("--recovered", default);

        // [UnmanagedCallersOnly] keeps a fixed native pointer (if using [DllImport] + delegate, root delegate in a static field!)
        _ = PInvoke.RegisterApplicationRecoveryCallback(&OnApplicationRecovery, null, dwPingInterval: 5000, dwFlags: 0);
    }

    [UnmanagedCallersOnly(CallConvs = [typeof(CallConvStdcall)])]
    private static uint OnApplicationRecovery(void* pvParameter)
    {
        try
        {
            _ = PInvoke.ApplicationRecoveryInProgress(out BOOL canceled);
            if (!canceled) EmergencyCrashState.FlushPendingWork();
            PInvoke.ApplicationRecoveryFinished(true);
        }
        catch { PInvoke.ApplicationRecoveryFinished(false); }
        return 0;
    }
}

internal static class EmergencyCrashState { public static void FlushPendingWork() { } }
```

### 5.3 Non-Blocking Structured Logging (`Serilog` Rolling File + `EventLog`)

Never write logs synchronously on the UI thread. Use **`Serilog.Extensions.Hosting`** + **`Serilog.Sinks.File`** (`buffered: true`, `flushToDiskInterval`) into `%LocalAppData%`, and route `Error`/`Fatal` to **`Serilog.Sinks.EventLog`** (`source: "Application"`, `manageEventSource: false` — creating custom EventLog sources in `HKLM` requires Admin privileges!):

```csharp
using System.IO;
using System.Threading.Tasks;
using System.Windows;
using Microsoft.Extensions.Hosting;
using Serilog;
using Serilog.Events;

namespace MyApp.Diagnostics;

public static class AppTelemetryBootstrap
{
    public static void ConfigureSerilog(HostApplicationBuilder builder, string appLogDir)
    {
        Directory.CreateDirectory(appLogDir);
        builder.Services.AddSerilog((_, cfg) => cfg
            .MinimumLevel.Information()
            .MinimumLevel.Override("Microsoft", LogEventLevel.Warning)
            .Enrich.FromLogContext()
            .WriteTo.File(
                Path.Combine(appLogDir, "app-.log"),
                rollingInterval: RollingInterval.Day,
                retainedFileCountLimit: 14,
                fileSizeLimitBytes: 10 * 1024 * 1024,
                rollOnFileSizeLimit: true,
                buffered: true,
                flushToDiskInterval: TimeSpan.FromSeconds(5))
            .WriteTo.EventLog(source: "Application", manageEventSource: false, restrictedToMinimumLevel: LogEventLevel.Error));
    }

    public static void AttachGlobalCrashHandlers(Application app)
    {
        app.DispatcherUnhandledException += (_, e) => { Log.Fatal(e.Exception, "Unhandled UI exception"); Log.CloseAndFlush(); };
        TaskScheduler.UnobservedTaskException += (_, e) => { Log.Error(e.Exception, "Unobserved task exception"); e.SetObserved(); };
        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            Log.Fatal(e.ExceptionObject as Exception, "AppDomain unhandled (Terminating={Terminating})", e.IsTerminating);
            if (e.IsTerminating) Log.CloseAndFlush();
        };
    }
}
```
