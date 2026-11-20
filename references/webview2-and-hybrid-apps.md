# WebView2 & Hybrid Desktop App Engineering (.NET 9/10)

> **Scope:** Evergreen vs. Fixed Version WebView2 runtime distribution and bootstrapper patterns, mandatory `%LocalAppData%` `CoreWebView2Environment` UserDataFolder isolation, single-flight initialization free of `EnsureCoreWebView2Async` deadlocks and races, offline SPAs/Markdown via `SetVirtualHostNameToFolderMapping`, source-generated typed JSON messaging (`WebMessageReceived` / `PostWebMessageAsJson`) vs. `AddHostObjectToScript` COM surface risks, WPF airspace/focus/DPI (`WebView2` `HwndHost` vs. `WebView2CompositionControl`) vs. WinUI 3 `WebView2`, release lockdown + origin allowlisting, and `TrySuspendAsync` memory control.
>
> **Related:** See [packaging-signing-and-updates.md](packaging-signing-and-updates.md#52-inno-setup-6-per-userdual-scope--webview2--net-bootstrapper) for Inno Setup 6 / WiX v5 WebView2 bootstrapper integration, [winui3-and-cppwinrt-native.md](winui3-and-cppwinrt-native.md) for WinUI 3 NativeAOT rules, and [compiler-traps-and-compat.md](compiler-traps-and-compat.md) for OS build compatibility.

## Table of Contents

1. [Runtime Distribution: Evergreen vs. Fixed Version](#1-runtime-distribution-evergreen-vs-fixed-version)
2. [Explicit `UserDataFolder` & Deadlock-Free Initialization](#2-explicit-userdatafolder--deadlock-free-initialization)
3. [Offline SPAs & Assets via `SetVirtualHostNameToFolderMapping`](#3-offline-spas--assets-via-setvirtualhostnametofoldermapping)
4. [Typed JSON Messaging (`WebMessageReceived` / `PostWebMessageAsJson`) vs. Host Objects](#4-typed-json-messaging-webmessagereceived--postwebmessageasjson-vs-host-objects)
5. [WPF Airspace, Focus & DPI vs. WinUI 3 Composition](#5-wpf-airspace-focus--dpi-vs-winui-3-composition)
6. [Release Lockdown & Origin Allowlisting](#6-release-lockdown--origin-allowlisting)
7. [Memory & Lifecycle Control (`TrySuspendAsync`, Process Failures & Cleanup)](#7-memory--lifecycle-control-trysuspendasync-process-failures--cleanup)

---

## 1. Runtime Distribution: Evergreen vs. Fixed Version

| Mode | Installer Overhead | Patching & Security | Target Scenarios | `CoreWebView2Environment` Arg |
|---|---|---|---|---|
| **Evergreen (Shared)** | ~0 MB (or ~2 MB online bootstrapper; ~160 MB standalone offline `.exe`) | Automatic Microsoft Edge Update patching | Consumer & enterprise Windows 10/11 apps | `browserExecutableFolder: null` (WPF) / `""` (WinUI 3) |
| **Fixed Version (`.cab`)** | ~150–250 MB uncompressed beside app | **Your responsibility** (must ship updates for Chromium CVEs) | Air-gapped kiosks, strict industrial certification, pinned DOM engines | Path to extracted folder containing `msedgewebview2.exe` |

### 1.1 Evergreen Bootstrapper & Runtime Probing

Windows 11 ships with Evergreen WebView2 pre-installed; Windows 10 (`19041+`) or stripped corporate images may lack it. Probe availability via `CoreWebView2Environment.GetAvailableBrowserVersionString()` before creating browser views:

```csharp
// Requires NuGet: Microsoft.Web.WebView2 (>= 1.0.2957.106 for public WebView2CompositionControl)
using System.Diagnostics;
using System.IO;
using Microsoft.Web.WebView2.Core;

namespace MyApp.WebView;

public static class WebView2RuntimeHelper
{
    public static string? TryGetInstalledVersion(string? fixedVersionFolder = null)
    {
        try
        {
            string version = string.IsNullOrEmpty(fixedVersionFolder)
                ? CoreWebView2Environment.GetAvailableBrowserVersionString()
                : CoreWebView2Environment.GetAvailableBrowserVersionString(fixedVersionFolder);
            return string.IsNullOrWhiteSpace(version) ? null : version;
        }
        catch (WebView2RuntimeNotFoundException) { return null; }
        catch (FileNotFoundException) { return null; }
    }

    public static async Task<bool> RunSilentBootstrapperAsync(string bootstrapperPath, CancellationToken ct = default)
    {
        string fullPath = Path.GetFullPath(bootstrapperPath);
        if (!File.Exists(fullPath)) throw new FileNotFoundException("Bootstrapper not found.", fullPath);

        // Installs per-machine when elevated; per-user when running standard mediumIL
        var psi = new ProcessStartInfo { FileName = fullPath, UseShellExecute = false, CreateNoWindow = true };
        psi.ArgumentList.Add("/silent");
        psi.ArgumentList.Add("/install");
        using Process? process = Process.Start(psi);
        if (process is null) return false;
        await process.WaitForExitAsync(ct).ConfigureAwait(false);
        return process.ExitCode == 0;
    }
}
```

### 1.2 Bootstrapper & Fixed Version Deployment Rules

1. **Installers:** Run `MicrosoftEdgeWebview2Setup.exe /silent /install` (online) or `MicrosoftEdgeWebView2RuntimeInstallerX64.exe /silent /install` (offline) when registry `pv` under `EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}` is missing (see [packaging-signing-and-updates.md](packaging-signing-and-updates.md#52-inno-setup-6-per-userdual-scope--webview2--net-bootstrapper)).
2. **Elevation & Auto-Upgrade:** Launching `MicrosoftEdgeWebview2Setup.exe` elevated installs per-machine; non-elevated installs per-user. If a machine-wide Edge Updater exists, existing per-user runtimes are replaced by the per-machine channel automatically.
3. **Fixed Version traps:** Extract the `.cab` (`expand.exe` or `tar`) into e.g. `Path.Combine(AppContext.BaseDirectory, "WebView2Runtime")` and pass that directory as `browserExecutableFolder`. Never point at an installed `\Edge\Application\` folder (`ERROR_NOT_SUPPORTED`), and grant `ALL APPLICATION PACKAGES` Read & Execute permissions on MSIX-bundled fixed runtimes.

---

## 2. Explicit `UserDataFolder` & Deadlock-Free Initialization

### 2.1 Why Default `UserDataFolder` Fails in Production

Calling parameterless `EnsureCoreWebView2Async()`—or setting `Source="..."` in XAML before initializing an environment—defaults the Chromium User Data Folder (UDF) to `<ExeDir>\<App>.exe.WebView2\`:

| Failure Mode | Production Impact | Fix |
|---|---|---|
| **Installed in `C:\Program Files\` or MSIX** | Standard `asInvoker` users lack write permission to `ExeDir` -> `UnauthorizedAccessException` (`0x80070005`). | Pass an explicit writable UDF under `%LocalAppData%\<Company>\<App>\WebView2`. |
| **Per-user updaters (Velopack / Inno)** | `msedgewebview2.exe` locks `EBWebView\`, blocking clean folder replacement during updates. | Keep mutable browser cache (`%LocalAppData%\<Company>\<App>\WebView2`) separate from immutable app binaries. |
| **Multiple WebView2 controls, mismatched options** | Calling `CreateAsync` twice on the same UDF with different `CoreWebView2EnvironmentOptions` throws `COMException` (`0x8007139F`). | Share **one cached `CoreWebView2Environment`** across the process via a singleton provider. |

### 2.2 Single-Flight Environment Cache & Race-Free Initializer

Never mix XAML `Source="..."` (implicit init) with `EnsureCoreWebView2Async(env)`, never mix `CreationProperties` with a custom `CoreWebView2Environment`, and never block the UI thread via `.GetAwaiter().GetResult()`. Defer initialization until the WPF control's `Loaded` event fires (ensuring `HwndHost` has an HWND) and guard concurrent callers with a single-flight `Task`:

```csharp
// Requires NuGet: Microsoft.Web.WebView2 (>= 1.0.2957.106)
using System.IO;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;

namespace MyApp.WebView;

public sealed class SharedWebView2EnvironmentProvider : IDisposable
{
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly string _userDataFolder;
    private readonly string? _fixedBrowserFolder;
    private Task<CoreWebView2Environment>? _cachedTask;

    public SharedWebView2EnvironmentProvider(string company, string appName, string? fixedBrowserFolder = null)
    {
        _userDataFolder = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), company, appName, "WebView2");
        _fixedBrowserFolder = fixedBrowserFolder;
    }

    public Task<CoreWebView2Environment> GetEnvironmentAsync(CancellationToken ct = default) =>
        _cachedTask is { IsFaulted: false, IsCanceled: false } ? _cachedTask : CreateOnceAsync(ct);

    private async Task<CoreWebView2Environment> CreateOnceAsync(CancellationToken ct)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            if (_cachedTask is { IsFaulted: false, IsCanceled: false }) return await _cachedTask.ConfigureAwait(false);
            Directory.CreateDirectory(_userDataFolder);
            var options = new CoreWebView2EnvironmentOptions
            {
                EnableTrackingPrevention = true,
                AreBrowserExtensionsEnabled = false
                // Optional: ExclusiveUserDataFolderAccess = true blocks concurrent access from another process
            };
            _cachedTask = CoreWebView2Environment.CreateAsync(_fixedBrowserFolder, _userDataFolder, options);
            return await _cachedTask.ConfigureAwait(false);
        }
        catch { _cachedTask = null; throw; }
        finally { _gate.Release(); }
    }

    public void Dispose() => _gate.Dispose();
}

public sealed class SingleFlightWebViewInitializer(SharedWebView2EnvironmentProvider envProvider)
{
    private Task? _initTask;

    public Task InitializeAsync(IWebView2 webView, Action<CoreWebView2> configureBeforeNavigate) =>
        _initTask is { IsFaulted: false, IsCanceled: false }
            ? _initTask
            : (_initTask = InitializeCoreAsync(webView, configureBeforeNavigate));

    private async Task InitializeCoreAsync(IWebView2 webView, Action<CoreWebView2> configureBeforeNavigate)
    {
        try
        {
            CoreWebView2Environment env = await envProvider.GetEnvironmentAsync();
            await webView.EnsureCoreWebView2Async(env);
            CoreWebView2 core = webView.CoreWebView2 ?? throw new InvalidOperationException("CoreWebView2 null.");
            configureBeforeNavigate(core);
        }
        catch { _initTask = null; throw; }
    }
}
```

> **Multi-Profile Apps:** Partition separate user profiles under `...\WebView2\<ProfileId>` and allocate one `SharedWebView2EnvironmentProvider` per profile.

---

## 3. Offline SPAs & Assets via `SetVirtualHostNameToFolderMapping`

Loading local bundles over `file://` breaks ES modules (`<script type="module">`), `fetch()`, Web Workers, local fonts, and `localStorage` because Chromium treats `file://` origins as opaque (`null`) under strict CORS. Map a synthetic `.local` hostname to disk via `SetVirtualHostNameToFolderMapping`:

| `CoreWebView2HostResourceAccessKind` | Behavior | Best For |
|---|---|---|
| `Allow` | Full same-origin access + permits cross-origin requests from virtual host | Offline SPA calling trusted HTTPS APIs, ES modules, Web Workers |
| `DenyCors` | Serves mapped assets while blocking cross-origin XHR/`fetch` | Offline Markdown/docs viewers that must not exfiltrate data |
| `Deny` | Blocks all access to that virtual host | Revoking a previously mapped folder (`ClearVirtualHostNameToFolderMapping`) |

```csharp
using System;
using System.IO;
using Microsoft.Web.WebView2.Core;

namespace MyApp.WebView;

public static class WebView2AssetHost
{
    public const string VirtualHostName = "appassets.local";
    public static readonly Uri BaseOrigin = new($"https://{VirtualHostName}/", UriKind.Absolute);

    public static void MountOfflineAssets(CoreWebView2 core, string assetsDirectory, string spaFallbackFile = "index.html")
    {
        string fullAssetsDir = Path.GetFullPath(assetsDirectory);
        if (!Directory.Exists(fullAssetsDir))
            throw new DirectoryNotFoundException($"Web assets directory not found: {fullAssetsDir}");

        core.SetVirtualHostNameToFolderMapping(VirtualHostName, fullAssetsDir, CoreWebView2HostResourceAccessKind.Allow);

        // Optional SPA history-routing fallback for extensionless routes (/settings, /guide/intro)
        core.AddWebResourceRequestedFilter($"https://{VirtualHostName}/*", CoreWebView2WebResourceContext.Document);
        core.WebResourceRequested += (_, args) =>
        {
            if (!Uri.TryCreate(args.Request.Uri, UriKind.Absolute, out Uri? uri)) return;
            string relPath = uri.AbsolutePath.TrimStart('/').Replace('/', Path.DirectorySeparatorChar);
            if (string.IsNullOrEmpty(relPath) || Path.HasExtension(relPath)) return;

            string fallbackPath = Path.Combine(fullAssetsDir, spaFallbackFile);
            if (!File.Exists(fallbackPath)) return;

            FileStream stream = File.OpenRead(fallbackPath);
            args.Response = core.Environment.CreateWebResourceResponse(
                stream, 200, "OK", "Content-Type: text/html; charset=utf-8\r\nCache-Control: no-store");
        };
    }
}
```

> **Path-Traversal & WinUI 3 Stream Note:** `SetVirtualHostNameToFolderMapping` sandboxes reads inside `folderPath` (`../` cannot escape above `fullAssetsDir`), and always use a synthetic non-routable hostname (`appassets.local`) instead of hijacking real domains. On WinUI 3, call `.AsRandomAccessStream()` on managed streams passed to `CreateWebResourceResponse`.

---

## 4. Typed JSON Messaging (`WebMessageReceived` / `PostWebMessageAsJson`) vs. Host Objects

| Criterion | `PostWebMessageAsJson` + `WebMessageReceived` | `AddHostObjectToScript` (COM `IDispatch` Proxy) |
|---|---|---|
| **Attack surface** | Narrow: explicit discriminated DTOs parsed defensively | Broad: exposes every public method/property (and returned objects!) on `chrome.webview.hostObjects` |
| **Origin enforcement** | Strict `args.Source` scheme + host check per message | Exposed across subsequent navigations unless revoked and `AreHostObjectsAllowed = false` |
| **NativeAOT / Trimming** | **100% AOT-safe** with `[JsonSerializable]` source generation | Fragile: relies on COM `IDispatch` reflection/interop marshaling |
| **Concurrency** | Clean async message queue; zero COM re-entrancy | Synchronous proxy calls risk UI blocking or nested re-entrancy deadlocks |

Prefer **source-generated typed JSON envelopes** with strict `args.Source` origin checks, disabling host objects (`AreHostObjectsAllowed = false`):

```csharp
using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Web.WebView2.Core;

namespace MyApp.WebView;

public sealed record WebBridgeEnvelope(
    [property: JsonPropertyName("type")] string Type,
    [property: JsonPropertyName("requestId")] string? RequestId,
    [property: JsonPropertyName("payload")] JsonElement Payload);

public sealed record StatusUpdatePayload(
    [property: JsonPropertyName("state")] string State,
    [property: JsonPropertyName("progress")] double Progress);

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
[JsonSerializable(typeof(WebBridgeEnvelope))]
[JsonSerializable(typeof(StatusUpdatePayload))]
internal partial class WebBridgeJsonContext : JsonSerializerContext { }

public sealed class TypedWebMessageBridge(string allowedHost = WebView2AssetHost.VirtualHostName)
{
    private const int MaxInboundJsonChars = 512 * 1024;

    public void Attach(CoreWebView2 core, Action<WebBridgeEnvelope> onTrustedMessage)
    {
        core.Settings.IsWebMessageEnabled = true;
        core.Settings.AreHostObjectsAllowed = false;

        core.WebMessageReceived += (_, args) =>
        {
            if (!IsTrustedOrigin(args.Source)) return;
            string rawJson = args.WebMessageAsJson;
            if (string.IsNullOrWhiteSpace(rawJson) || rawJson.Length > MaxInboundJsonChars) return;

            try
            {
                WebBridgeEnvelope? envelope = JsonSerializer.Deserialize(rawJson, WebBridgeJsonContext.Default.WebBridgeEnvelope);
                if (envelope is not null && !string.IsNullOrWhiteSpace(envelope.Type))
                    onTrustedMessage(envelope);
            }
            catch (JsonException) { /* Reject malformed payloads without crashing UI */ }
        };
    }

    public static void SendStatus(CoreWebView2 core, string requestId, string state, double progress)
    {
        JsonElement payload = JsonSerializer.SerializeToElement(
            new StatusUpdatePayload(state, progress), WebBridgeJsonContext.Default.StatusUpdatePayload);
        string json = JsonSerializer.Serialize(
            new WebBridgeEnvelope("statusUpdate", requestId, payload), WebBridgeJsonContext.Default.WebBridgeEnvelope);
        core.PostWebMessageAsJson(json);
    }

    private bool IsTrustedOrigin(string? sourceUri) =>
        Uri.TryCreate(sourceUri, UriKind.Absolute, out Uri? uri)
        && uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
        && uri.Host.Equals(allowedHost, StringComparison.OrdinalIgnoreCase)
        && uri.IsDefaultPort;
}
```

> **JS Contract:** Send `{ type, requestId, payload }` via `window.chrome.webview.postMessage(msg)` and listen via `window.chrome.webview.addEventListener("message", e => ...)`. Never pass untrusted payloads into `ExecuteScriptAsync` string interpolation.

---

## 5. WPF Airspace, Focus & DPI vs. WinUI 3 Composition

### 5.1 Hosting Comparison

| Control | Base Class | Rendering Path | Overlays / Popups Above WebView | Performance & DRM Tradeoffs |
|---|---|---|---|---|
| **WPF `WebView2`** | `HwndHost` | Dedicated Win32 child `HWND` | **Airspace conflict:** child `HWND` paints on top of WPF overlays, titlebar menus, and rounded clips. | Highest FPS (60/120+ Hz), lowest idle overhead, supports hardware DRM. |
| **WPF `WebView2CompositionControl`** (`>= 1.0.2957.106`) | `Control` | Composition visual integrated into WPF visual tree | **No airspace conflict:** WPF popups, `ToolTip`, shadows, and rounded clips render cleanly on top. | Higher GPU/surface copy cost; potential FPS ceiling on 4K WebGL/video; no hardware DRM. |
| **WinUI 3 `WebView2`** (`Microsoft.UI.Xaml.Controls`) | `Control` (`Microsoft.UI.Composition`) | Native Windows App SDK visual composition host | **No airspace conflict:** XAML `TeachingTip`, `MenuFlyout`, and acrylic overlays sit above WebView2 natively. | Native `PerMonitorV2` DPI scaling and composition without a separate control class. |

### 5.2 WPF XAML, Focus & Per-Monitor DPI Rules

Leave `Source` unset in XAML, set `AllowExternalDrop="False"` so dragging `.html`/`.url` files onto the surface cannot hijack navigation, and match `DefaultBackgroundColor` (`System.Drawing.Color.Transparent` in WPF; `Microsoft.UI.Colors.Transparent` in WinUI 3) to eliminate white pre-paint flashes on dark themes:

```xml
<Grid xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
      xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
      xmlns:wv2="clr-namespace:Microsoft.Web.WebView2.Wpf;assembly=Microsoft.Web.WebView2.Wpf">
    <!-- Swap wv2:WebView2 for wv2:WebView2CompositionControl (>= 1.0.2957.106) when WPF overlays must sit above it -->
    <wv2:WebView2CompositionControl x:Name="HybridBrowser"
                                    AllowExternalDrop="False"
                                    DefaultBackgroundColor="Transparent"
                                    Visibility="Visible" />
</Grid>
```

1. **Keyboard & Accelerator Forwarding (WPF):** WPF `WebView2` wraps its internal `CoreWebView2Controller` (no public `CoreWebView2Controller` property is exposed) and bubbles Chromium accelerator keys as WPF `PreviewKeyDown`/`KeyDown`. Intercept app shortcuts (`Ctrl+K`, `Esc`, `F1`) in `PreviewKeyDown` (`e.Handled = true`). In raw Win32/custom `CoreWebView2Controller.AcceleratorKeyPressed` handlers, never run synchronous blocking COM/JS calls (`RPC_E_CANTCALLOUT_ININPUTSYNCCALL`)—queue onto `Dispatcher.BeginInvoke` / `DispatcherQueue.TryEnqueue`.
2. **Per-Monitor DPI:** Declare `<dpiAwareness>PerMonitorV2</dpiAwareness>` in `app.manifest` and scale layout pixel calculations using `VisualTreeHelper.GetDpi(webView)`.
3. **WinUI 3 `WebView2` Nuances:** In Windows App SDK (`1.5+`), `CoreWebView2Environment.CreateWithOptionsAsync(string, string, CoreWebView2EnvironmentOptions)` expects `string.Empty` (not `null`) for Evergreen, `EnsureCoreWebView2Async(env)` returns `IAsyncAction`, and teardown uses `.Close()` (not `.Dispose()`):

```csharp
// WinUI 3 (Windows App SDK >= 1.5) explicit environment init + suspend + Close()
using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.Web.WebView2.Core;

namespace MyApp.WinUIWebView;

public sealed class WinUIWebView2Host
{
    private const int ErrorInvalidStateHResult = unchecked((int)0x8007139F);
    private Task? _initTask;

    public Task EnsureInitializedAsync(WebView2 webView, string company, string appName) =>
        _initTask is { IsFaulted: false, IsCanceled: false } ? _initTask : (_initTask = InitCoreAsync(webView, company, appName));

    private async Task InitCoreAsync(WebView2 webView, string company, string appName)
    {
        try
        {
            string udf = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), company, appName, "WebView2");
            Directory.CreateDirectory(udf);
            CoreWebView2Environment env = await CoreWebView2Environment.CreateWithOptionsAsync(
                string.Empty, udf, new CoreWebView2EnvironmentOptions());
            await webView.EnsureCoreWebView2Async(env);

            CoreWebView2 core = webView.CoreWebView2 ?? throw new InvalidOperationException("CoreWebView2 null.");
            core.SetVirtualHostNameToFolderMapping(
                "appassets.local", Path.Combine(AppContext.BaseDirectory, "Assets"), CoreWebView2HostResourceAccessKind.Allow);
        }
        catch { _initTask = null; throw; }
    }

    public static async Task SuspendWhenHiddenAsync(WebView2 webView)
    {
        if (webView.CoreWebView2 is not { IsSuspended: false } core) return;
        webView.Visibility = Visibility.Collapsed;
        try { await core.TrySuspendAsync(); }
        catch (COMException ex) when (ex.HResult == ErrorInvalidStateHResult) { }
    }

    public static void ResumeAndCleanupOnClose(WebView2 webView, Window hostWindow)
    {
        hostWindow.Activated += (_, args) =>
        {
            if (args.WindowActivationState == WindowActivationState.Deactivated) return;
            webView.Visibility = Visibility.Visible;
            if (webView.CoreWebView2 is { IsSuspended: true } core) core.Resume();
        };
        hostWindow.Closed += (_, _) => webView.Close();
    }
}
```

---

## 6. Release Lockdown & Origin Allowlisting

Most `CoreWebView2Settings` flags apply on the **next** top-level navigation—always configure lockdown and origin allowlists immediately after `EnsureCoreWebView2Async(env)` completes and **before** calling `Navigate(...)`:

```csharp
using System;
using System.Collections.Generic;
using System.Diagnostics;
using Microsoft.Web.WebView2.Core;

namespace MyApp.WebView;

public static class WebView2SecurityHardening
{
    public static void ApplyLockdownAndAllowlist(
        CoreWebView2 core, IReadOnlySet<string> allowedHttpsHosts, Action<Uri>? openExternalBrowser = null)
    {
        CoreWebView2Settings s = core.Settings;
#if DEBUG
        s.AreDevToolsEnabled = true;
#else
        s.AreDevToolsEnabled = false;
#endif
        s.AreDefaultContextMenusEnabled = false;
        s.IsStatusBarEnabled = false;
        s.AreHostObjectsAllowed = false;
        s.AreBrowserAcceleratorKeysEnabled = false;
        s.IsGeneralAutofillEnabled = false;
        s.IsPasswordAutosaveEnabled = false;
        s.IsBuiltInErrorPageEnabled = false;
        s.IsSwipeNavigationEnabled = false;

        bool IsAllowed(string? rawUri) =>
            Uri.TryCreate(rawUri, UriKind.Absolute, out Uri? uri)
            && uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)
            && allowedHttpsHosts.Contains(uri.Host);

        core.NavigationStarting += (_, args) => { if (!IsAllowed(args.Uri)) args.Cancel = true; };
        core.FrameNavigationStarting += (_, args) => { if (!IsAllowed(args.Uri)) args.Cancel = true; };
        core.NewWindowRequested += (_, args) =>
        {
            args.Handled = true;
            if (Uri.TryCreate(args.Uri, UriKind.Absolute, out Uri? uri)
                && uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
                openExternalBrowser?.Invoke(uri);
        };
    }

    public static void LaunchVerifiedHttpsUrl(Uri safeHttpsUri)
    {
        if (!safeHttpsUri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("Only HTTPS URLs are permitted.", nameof(safeHttpsUri));
        Process.Start(new ProcessStartInfo(safeHttpsUri.AbsoluteUri) { UseShellExecute = true });
    }
}
```

> **Allowlist Coverage:** Requiring `Uri.UriSchemeHttps` inside both `NavigationStarting` and `FrameNavigationStarting` blocks `file://`, `javascript:`, `data:`, and unencrypted `http://` pivots inside main frames and nested iframes alike.

---

## 7. Memory & Lifecycle Control (`TrySuspendAsync`, Process Failures & Cleanup)

Each live WebView2 spawns multiple Chromium sub-processes (`msedgewebview2.exe` browser, GPU, network, renderer) totaling **~80–250+ MB RAM**. Suspend inactive tabs or tray-minimized windows safely:

1. **Visibility Prerequisite (`0x8007139F`):** `TrySuspendAsync()` **throws `COMException` (`ERROR_INVALID_STATE`)** unless the controller is hidden (`IsVisible == false`). Minimizing a WPF `Window` (`WindowState.Minimized`) does **not** set `webView.IsVisible` to `false` automatically—set `webView.Visibility = Visibility.Collapsed` and yield one `DispatcherPriority.Render` tick first.
2. **Best-Effort & Auto-Resume:** `TrySuspendAsync()` returns `false` if audio/WebRTC locks prevent suspension. Avoid calling `Navigate()` or `ExecuteScriptAsync()` while suspended because they auto-resume the renderer.
3. **Crash Recovery & Lock Release:** Guard `CoreWebView2.ProcessFailed` with bounded retries to prevent crash-reload loops, and call `webView.Dispose()` (WPF) or `webView.Close()` (WinUI 3) on close so Chromium processes release UDF file locks cleanly.

```csharp
using System;
using System.Runtime.InteropServices;
using System.Threading.Tasks;
using System.Windows;
using System.Windows.Threading;
using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.Wpf;

namespace MyApp.WebView;

public sealed class WebView2LifecycleController(WebView2 webView)
{
    private const int ErrorInvalidStateHResult = unchecked((int)0x8007139F);
    private int _crashRecoveryCount;

    public void AttachFailureHandlers(CoreWebView2 core, Func<Task> recreateWebViewAsync)
    {
        core.ProcessFailed += async (_, args) =>
        {
            if (args.ProcessFailedKind == CoreWebView2ProcessFailedKind.RenderProcessExited && _crashRecoveryCount < 3)
            {
                _crashRecoveryCount++;
                await Task.Delay(250 * _crashRecoveryCount);
                webView.Reload();
            }
            else if (args.ProcessFailedKind == CoreWebView2ProcessFailedKind.BrowserProcessExited && _crashRecoveryCount < 2)
            {
                _crashRecoveryCount++;
                await recreateWebViewAsync();
            }
        };
    }

    public async Task SuspendWhenHiddenAsync()
    {
        CoreWebView2? core = webView.CoreWebView2;
        if (core is null || core.IsSuspended) return;

        // Controller IsVisible MUST be false before TrySuspendAsync(), otherwise COMException (0x8007139F)
        webView.Visibility = Visibility.Collapsed;
        await webView.Dispatcher.InvokeAsync(() => { }, DispatcherPriority.Render);
        if (webView.IsVisible) return;

        try { await core.TrySuspendAsync(); }
        catch (COMException ex) when (ex.HResult == ErrorInvalidStateHResult) { /* Became visible concurrently */ }
    }

    public void ResumeWhenRestored()
    {
        webView.Visibility = Visibility.Visible;
        if (webView.CoreWebView2 is { IsSuspended: true } core) core.Resume();
    }
}
```
