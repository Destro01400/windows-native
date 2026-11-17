# WinUI 3 (Windows App SDK), C# NativeAOT & C++/WinRT / Modern Win32 Native Apps

> **Scope:** Full-lifecycle engineering for **WinUI 3** (`Microsoft.WindowsAppSDK` on `.NET 9/10`), **C# NativeAOT**, and zero-.NET-runtime **C++/WinRT** or **pure Win32 + Direct2D / DirectComposition** Windows 11 apps. APIs are tagged with origin (`Windows App SDK`, `WinRT`, `.NET BCL`, `C++/WinRT`, `WIL`, or `Win32/DXGI/D2D/DComp`).

## Table of Contents
**Part A — WinUI 3 (Windows App SDK) Full App Engineering (C# .NET 9/10)**
1. [Project Setup & Deployment Modes](#1-project-setup--deployment-modes)
2. [App Lifecycle, Single-Instance Redirection & `AppWindow` API](#2-app-lifecycle-single-instance-redirection--appwindow-api)
3. [Custom Title Bar, Icons & Passthrough Hit-Testing](#3-custom-title-bar-icons--passthrough-hit-testing)
4. [Performance & Binding (`x:Bind`, `x:DefaultBindMode`, Functions, `x:Phase`)](#4-performance--binding-xbind-xdefaultbindmode-functions-xphase)
5. [Navigation, Page Caching, `ConnectedAnimation` & `Microsoft.UI.Composition`](#5-navigation-page-caching-connectedanimation--microsoftuicomposition)
6. [Threading (`DispatcherQueue`) & Storage (`ApplicationData` vs `System.IO`)](#6-threading-dispatcherqueue--storage-applicationdata-vs-systemio)
7. [C# NativeAOT in WinUI 3 (`PublishAot`, `CsWinRT`, Trimming Pitfalls)](#7-c-nativeaot-in-winui-3-publishaot-cswinrt-trimming-pitfalls)

**Part B — C++/WinRT & Modern Win32 C++ (Zero-.NET Runtime Native Apps)**
8. [Architecture Decision Matrix](#8-architecture-decision-matrix)
9. [Modern C++20/23 Windows Toolchain & WIL](#9-modern-c2023-windows-toolchain--wil)
10. [C++/WinRT Essentials (Apartments, Coroutines, `get_weak()`, MIDL 3.0)](#10-cwinrt-essentials-apartments-coroutines-get_weak-midl-30)
11. [Pure Modern Win32 + DirectComposition / Direct2D Skeleton (< 2 MB Utilities)](#11-pure-modern-win32--directcomposition--direct2d-skeleton--2-mb-utilities)

---

## Part A — WinUI 3 (Windows App SDK) Full App Engineering (C# .NET 9/10)

## 1. Project Setup & Deployment Modes

*(Origin: `Microsoft.WindowsAppSDK` MSBuild targets, `Microsoft.Windows.ApplicationModel.DynamicDependency`, `Microsoft.Windows.ApplicationModel.WindowsAppRuntime`.)*

| Mode | `.csproj` Properties | Target Machine Requirements | Key Tradeoffs |
|---|---|---|---|
| **Packaged (MSIX)** *(default)* | `<WindowsPackageType>MSIX</WindowsPackageType>` (or omitted) | Windows App Runtime MSIX framework package (auto-resolved by Store/AppInstaller) | Full **Package Identity** (Toasts, `StartupTask`, Share target, clean uninstall), container storage virtualization. |
| **Unpackaged (Framework-Dependent)** | `<WindowsPackageType>None</WindowsPackageType>` | Matching Windows App Runtime + `.NET` (unless `<SelfContained>true</SelfContained>`) | Traditional installer (`Inno`/`WiX`/ZIP). Auto-initializer runs bootstrapper. **Fails if launched elevated (Admin)** via dynamic dependency. |
| **Unpackaged (Self-Contained)** | `<WindowsPackageType>None</WindowsPackageType>` + `<WindowsAppSDKSelfContained>true</WindowsAppSDKSelfContained>` | Zero external Windows App Runtime install (add `<SelfContained>true</SelfContained>` for zero `.NET` install) | Larger uncompressed footprint (~100–150 MB before NativeAOT), works when elevated, zero shared-runtime version skew. |

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net10.0-windows10.0.26100.0</TargetFramework>
    <TargetPlatformMinVersion>10.0.19041.0</TargetPlatformMinVersion>
    <UseWinUI>true</UseWinUI>
    <EnableMsixTooling>true</EnableMsixTooling>
    <WindowsPackageType>None</WindowsPackageType>
    <WindowsAppSDKSelfContained>false</WindowsAppSDKSelfContained>
    <Platforms>x64;ARM64</Platforms>
    <RuntimeIdentifiers>win-x64;win-arm64</RuntimeIdentifiers>
    <ApplicationManifest>app.manifest</ApplicationManifest>
    <Nullable>enable</Nullable>
  </PropertyGroup>
  <ItemGroup><PackageReference Include="Microsoft.WindowsAppSDK" Version="1.7.*" /></ItemGroup>
</Project>
```

### 1.1 Bootstrapper Quirks & Manual Initialization

- **Auto-initializer (`WindowsAppSdkBootstrapInitialize`):** For unpackaged framework-dependent `Exe`/`WinExe` builds, Windows App SDK injects a `[ModuleInitializer]` calling native `MddBootstrapInitialize` before `Main`. With `WindowsAppSDKSelfContained=true`, the auto-initializer is omitted because SDK binaries sit alongside the `.exe`.
- **Manual opt-out (`<WindowsAppSdkBootstrapInitialize>false</WindowsAppSdkBootstrapInitialize>`):** Necessary when you want custom missing-runtime UI or `DeploymentManager.GetStatus()` / `Initialize()` / `Repair()` before XAML loads. **Critical rule:** Call `Bootstrap.TryInitialize` in `Main` **before** JIT touches any method referencing `Microsoft.UI.Xaml.*` (referencing XAML types first throws `COMException` / `TypeLoadException`), and avoid running dynamic-dependency bootstrapper calls in elevated Admin processes.

```csharp
using System;
using Microsoft.Windows.ApplicationModel.DynamicDependency; // Windows App SDK (Bootstrap)

namespace MyApp;

public static class Program
{
    [STAThread]
    public static int Main(string[] args)
    {
        if (!Bootstrap.TryInitialize(0x00010007, out int hr))
            return hr; // Show native Win32 MessageBoxW here (do NOT touch Microsoft.UI.Xaml.*)
        try { LaunchApp(); return 0; }
        finally { Bootstrap.Shutdown(); }
    }

    private static void LaunchApp()
    {
        WinRT.ComWrappersSupport.InitializeComWrappers();
        Microsoft.UI.Xaml.Application.Start(p =>
        {
            var dq = Microsoft.UI.Dispatching.DispatcherQueue.GetForCurrentThread();
            System.Threading.SynchronizationContext.SetSynchronizationContext(
                new Microsoft.UI.Dispatching.DispatcherQueueSynchronizationContext(dq));
            new App();
        });
    }
}
```

---

## 2. App Lifecycle, Single-Instance Redirection & `AppWindow` API

*(Origin: `Microsoft.Windows.AppLifecycle.AppInstance`, `Microsoft.UI.Windowing.AppWindow`, `OverlappedPresenter` — Windows App SDK.)*

### 2.1 Single-Instance Redirection (`DISABLE_XAML_GENERATED_MAIN`)

WinUI 3 apps are **multi-instanced by default**. Define `DISABLE_XAML_GENERATED_MAIN` in `.csproj` (`<DefineConstants>$(DefineConstants);DISABLE_XAML_GENERATED_MAIN</DefineConstants>`) and redirect in `Program.Main` **before** `Application.Start` so secondary launches exit cleanly without flashing a window or spinning up XAML.

```csharp
using System;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.UI.Dispatching;       // Windows App SDK
using Microsoft.UI.Xaml;              // Windows App SDK
using Microsoft.Windows.AppLifecycle; // Windows App SDK

namespace MyApp;

public static class Program
{
    private static DispatcherQueue? _uiQueue;
    private static App? _app;

    [STAThread]
    public static int Main(string[] args)
    {
        WinRT.ComWrappersSupport.InitializeComWrappers();
        AppActivationArguments activationArgs = AppInstance.GetCurrent().GetActivatedEventArgs();
        AppInstance primary = AppInstance.FindOrRegisterForKey("com.example.myapp.main");

        if (!primary.IsCurrent)
        {
            // Offload RedirectActivationToAsync onto threadpool to avoid STA COM deadlock
            using var done = new AutoResetEvent(false);
            _ = Task.Run(async () => { await primary.RedirectActivationToAsync(activationArgs); done.Set(); });
            done.WaitOne();
            return 0;
        }

        primary.Activated += OnPrimaryActivated;
        Application.Start(p =>
        {
            _uiQueue = DispatcherQueue.GetForCurrentThread();
            SynchronizationContext.SetSynchronizationContext(new DispatcherQueueSynchronizationContext(_uiQueue));
            _app = new App();
        });
        return 0;
    }

    private static void OnPrimaryActivated(object? sender, AppActivationArguments args)
    {
        // CRITICAL: Activated fires on an RPC/threadpool thread (DispatcherQueue.GetForCurrentThread() is null here).
        _uiQueue?.TryEnqueue(() => _app?.BringMainWindowToFront(args));
    }
}
```

### 2.2 `AppWindow`, `OverlappedPresenter` & Close Confirmation

Since Windows App SDK 1.3, `Window.AppWindow` is built in (earlier versions used `Win32Interop.GetWindowIdFromWindow(WindowNative.GetWindowHandle(this))` + `AppWindow.GetFromWindowId`). Unlike `Window.Closed` (not cancelable), `AppWindow.Closing` supports async close confirmation:

```csharp
using System;
using Microsoft.UI.Windowing;     // Windows App SDK
using Microsoft.UI.Xaml;          // Windows App SDK
using Microsoft.UI.Xaml.Controls; // Windows App SDK
using Windows.Graphics;           // WinRT

namespace MyApp;

public sealed partial class MainWindow : Window
{
    private bool _allowClose;

    public MainWindow()
    {
        InitializeComponent();
        AppWindow.Resize(new SizeInt32(1280, 800));
        AppWindow.Move(new PointInt32(120, 80));

        if (AppWindow.Presenter is OverlappedPresenter p)
        {
            p.IsResizable = p.IsMaximizable = p.IsMinimizable = true;
            p.IsAlwaysOnTop = false;
            p.PreferredMinimumWidth = 640;
            p.PreferredMinimumHeight = 480;
            p.SetBorderAndTitleBar(hasBorder: true, hasTitleBar: true);
            // p.State (OverlappedPresenterState) is read-only; call Maximize() / Minimize() / Restore().
        }
        AppWindow.Closing += OnAppWindowClosing;
    }

    private async void OnAppWindowClosing(AppWindow sender, AppWindowClosingEventArgs args)
    {
        if (_allowClose || !HasUnsavedWork()) return;
        args.Cancel = true; // Cancel synchronously before awaiting

        var dialog = new ContentDialog
        {
            Title = "Unsaved changes", Content = "Discard unsaved changes and close?",
            PrimaryButtonText = "Close anyway", CloseButtonText = "Cancel",
            DefaultButton = ContentDialogButton.Close, XamlRoot = Content.XamlRoot
        };
        if (await dialog.ShowAsync() == ContentDialogResult.Primary) { _allowClose = true; Close(); }
    }

    private bool HasUnsavedWork() => false;
}
```

---

## 3. Custom Title Bar, Icons & Passthrough Hit-Testing

*(Origin: `Window.ExtendsContentIntoTitleBar`, `Window.SetTitleBar`, `AppWindowTitleBar`, `Microsoft.UI.Input.InputNonClientPointerSource` — Windows App SDK.)*

- **High-level path (recommended):** Set `ExtendsContentIntoTitleBar = true; SetTitleBar(CustomTitleBarGrid);` (or use the Windows App SDK 1.7+ `<TitleBar>` control). WinUI computes drag and interactive child cutouts automatically.
- **Low-level path (`AppWindow.TitleBar` + `InputNonClientPointerSource`):** When customizing drag regions manually without `Window.SetTitleBar`, specify `SetDragRectangles(RectInt32[])` or punch interactive holes via `NonClientRegionKind.Passthrough` in **physical pixels** (`DIPs * XamlRoot.RasterizationScale`), refreshed on `SizeChanged` and `XamlRoot.Changed`:

```csharp
using System;
using Microsoft.UI;           // Windows App SDK
using Microsoft.UI.Input;     // Windows App SDK
using Microsoft.UI.Windowing; // Windows App SDK
using Microsoft.UI.Xaml;
using Windows.Foundation;
using Windows.Graphics;

private void ConfigureTitleBar()
{
    if (!AppWindowTitleBar.IsCustomizationSupported()) return;

    ExtendsContentIntoTitleBar = true;
    SetTitleBar(CustomTitleBarGrid);

    AppWindowTitleBar titleBar = AppWindow.TitleBar;
    titleBar.PreferredHeightOption = TitleBarHeightOption.Tall; // Standard | Tall | Collapsed
    titleBar.IconShowOptions = IconShowOptions.HideIconAndSystemMenu;
    titleBar.ButtonBackgroundColor = Colors.Transparent;
    titleBar.ButtonInactiveBackgroundColor = Colors.Transparent;
}

private void UpdateNonClientPassthrough(FrameworkElement interactiveControl)
{
    if (interactiveControl.XamlRoot is null) return;
    double scale = interactiveControl.XamlRoot.RasterizationScale;
    Rect dip = interactiveControl.TransformToVisual(null)
        .TransformBounds(new Rect(0, 0, interactiveControl.ActualWidth, interactiveControl.ActualHeight));

    var rect = new RectInt32
    {
        X = (int)Math.Round(dip.X * scale), Y = (int)Math.Round(dip.Y * scale),
        Width = (int)Math.Round(dip.Width * scale), Height = (int)Math.Round(dip.Height * scale)
    };
    InputNonClientPointerSource.GetForWindowId(AppWindow.Id)
        .SetRegionRects(NonClientRegionKind.Passthrough, [rect]);
}
```

---

## 4. Performance & Binding (`x:Bind`, `x:DefaultBindMode`, Functions, `x:Phase`)

*(Origin: WinUI 3 XAML compiler `{x:Bind}`, `x:DefaultBindMode`, `x:Phase`, `ListViewBase.ContainerContentChanging`, `ItemsRepeater`.)*

| Feature | `{x:Bind}` (Compiled) | `{Binding}` (Classic / Runtime) |
|---|---|---|
| **Default `Mode`** | **`OneTime`** (override subtree with `x:DefaultBindMode="OneWay"`) | **`OneWay`** |
| **Resolution** | Compile-time strongly typed C# codegen | Runtime reflection (`DataContext`) |
| **NativeAOT** | **100% AOT-safe** | Requires `partial` + `[WinRT.GeneratedBindableCustomProperty]` |
| **Function paths** | Supported directly (zero `IValueConverter` allocation) | Unsupported |
| **Root scope** | Page/UserControl code-behind or `x:DataType` in `DataTemplate` | `FrameworkElement.DataContext` |

```xml
<Page x:Class="MyApp.Views.CatalogPage"
      xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
      xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
      xmlns:vm="using:MyApp.ViewModels"
      x:DefaultBindMode="OneWay">
    <ListView ItemsSource="{x:Bind ViewModel.Items}">
        <ListView.ItemTemplate>
            <DataTemplate x:DataType="vm:CatalogItem" x:DefaultBindMode="OneTime">
                <Grid Height="64" ColumnSpacing="12">
                    <Grid.ColumnDefinitions>
                        <ColumnDefinition Width="48"/>
                        <ColumnDefinition Width="*"/>
                    </Grid.ColumnDefinitions>
                    <!-- Phase 0 (implicit): primary title renders on first layout frame -->
                    <TextBlock Grid.Column="1" Text="{x:Bind Title}" FontWeight="SemiBold"/>
                    <!-- Phase 1: static/instance function binding without IValueConverter -->
                    <TextBlock Grid.Column="1" Margin="0,22,0,0" x:Phase="1"
                               Text="{x:Bind vm:Formatters.FormatPrice(Price, Currency)}"/>
                    <!-- Phase 2: heavier image decode deferred to idle frames -->
                    <Image Grid.Column="0" Width="44" Height="44" x:Phase="2"
                           Source="{x:Bind Thumbnail}"/>
                </Grid>
            </DataTemplate>
        </ListView.ItemTemplate>
    </ListView>
</Page>
```

- **Function binding rules:** Method overloads resolve strictly by **argument count** (not type), with no implicit narrowing conversions. Two-way function bindings supply `BindBack`: `Text="{x:Bind ViewModel.Format(Val), BindBack=ViewModel.Parse, Mode=TwoWay}"`. `TargetNullValue` applies to the function's **return value**.
- **`x:Phase` incremental rendering:** Works in `ListViewBase` (`ListView` / `GridView`) templates with `{x:Bind}`. Elements with `x:Phase > 0` start at `Opacity = 0` (preserving layout slot), evaluate progressively as frame budget permits, reset automatically on container recycle, and behave as `OneTime` per binding cycle. For imperative control, handle `ListViewBase.ContainerContentChanging` (`args.Phase`, `args.RegisterUpdateCallback`).
- **`ItemsRepeater` contrast:** Lightweight data-driven panel without `ContainerContentChanging`; uses `VirtualizingLayout` (`StackLayout`, `UniformGridLayout`) and `ElementPrepared` / `ElementClearing` / `ElementIndexChanged`.

---

## 5. Navigation, Page Caching, `ConnectedAnimation` & `Microsoft.UI.Composition`

*(Origin: `NavigationView`, `Frame`, `Page.NavigationCacheMode`, `ConnectedAnimationService`, `Microsoft.UI.Composition`, `ElementCompositionPreview` — Windows App SDK.)*

### 5.1 `NavigationView` + `Frame.CacheSize` & `NavigationCacheMode`

- Set `ContentFrame.CacheSize = 5;` on the host `Frame`, and set `NavigationCacheMode` on each `Page` in XAML or **strictly in the `Page` constructor**: `Disabled` (default, recreated every visit), `Enabled` (LRU cached up to `Frame.CacheSize`), or `Required` (never evicted).
- **Leak rule:** Cached pages remain alive off-screen; unsubscribe external event handlers/timers in `OnNavigatedFrom` and re-attach in `OnNavigatedTo`.

### 5.2 `ConnectedAnimation` Across Pages

```csharp
using Microsoft.UI.Xaml.Media.Animation; // Windows App SDK
using Microsoft.UI.Xaml.Navigation;

// Source page: suppress overlapping Frame transition
ConnectedAnimationService.GetForCurrentView().PrepareToAnimate("HeroImage", SourceCardImage);
Frame.Navigate(typeof(DetailPage), item, new SuppressNavigationTransitionInfo());

// Destination page OnNavigatedTo:
protected override void OnNavigatedTo(NavigationEventArgs e)
{
    base.OnNavigatedTo(e);
    if (ConnectedAnimationService.GetForCurrentView().GetAnimation("HeroImage") is { } anim)
    {
        anim.Configuration = new GravityConnectedAnimationConfiguration();
        anim.TryStart(DestinationHeroImage, [DetailTitlePanel]); // Coordinated entrance
    }
}
```
*(In `ListViewBase`, use `PrepareConnectedAnimation` before navigating out and `await listView.TryStartConnectedAnimationAsync(anim, item, "ImgName")` when navigating back.)*

### 5.3 `Microsoft.UI.Composition`: `ExpressionAnimation` & `CompositionBackdropBrush`

```csharp
using Microsoft.UI.Composition;  // Windows App SDK
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Hosting; // ElementCompositionPreview

private void AttachScrollParallax(ScrollViewer scroller, UIElement headerBanner)
{
    CompositionPropertySet scrollerProps =
        ElementCompositionPreview.GetScrollViewerManipulationPropertySet(scroller);

    // WARNING: Never mix ElementCompositionPreview.SetIsTranslationEnabled / GetElementVisual
    // with WinUI 3 UIElement.Translation / Scale / Rotation on the same element (throws at runtime).
    ElementCompositionPreview.SetIsTranslationEnabled(headerBanner, true);
    Visual headerVisual = ElementCompositionPreview.GetElementVisual(headerBanner);
    Compositor compositor = headerVisual.Compositor; // or CompositionTarget.GetCompositorForCurrentThread()

    ExpressionAnimation parallax = compositor.CreateExpressionAnimation(
        "Vector3(0, Clamp(-scroller.Translation.Y * 0.4, 0, 180), 0)");
    parallax.SetReferenceParameter("scroller", scrollerProps);
    headerVisual.StartAnimation("Translation", parallax);
}
```

- **`CompositionBackdropBrush` vs System Backdrops:** Use `Window.SystemBackdrop = new MicaBackdrop()` or `new DesktopAcrylicBackdrop()` (`Microsoft.UI.Xaml.Media`) for OS wallpaper/desktop-sampled **Mica** / **Acrylic**. Use `compositor.CreateBackdropBrush()` (`CompositionBackdropBrush`) inside a `CompositionEffectBrush` (e.g., Win2D `GaussianBlurEffect`) attached via `ElementCompositionPreview.SetElementChildVisual(host, spriteVisual)` to blur **in-app XAML content** behind a visual.

---

## 6. Threading (`DispatcherQueue`) & Storage (`ApplicationData` vs `System.IO`)

*(Origin: `Microsoft.UI.Dispatching.DispatcherQueue`, `Microsoft.Windows.Storage.ApplicationData`, WinRT `Windows.Storage.ApplicationData`, `.NET BCL`.)*

### 6.1 `DispatcherQueue` (WinUI 3) vs `CoreDispatcher` (WinUI 2 / UWP)

WinUI 3 replaces `Windows.UI.Core.CoreDispatcher.RunAsync` with **`Microsoft.UI.Dispatching.DispatcherQueue`** (do not confuse with `Windows.System.DispatcherQueue`):

```csharp
using System;
using System.Threading.Tasks;
using Microsoft.UI.Dispatching; // Windows App SDK

public static class DispatcherHelpers
{
    public static void RunOnUi(DispatcherQueue q, Action action)
    {
        if (q.HasThreadAccess) action();
        else _ = q.TryEnqueue(DispatcherQueuePriority.Normal, () => action());
    }

    public static Task<T> EnqueueAsync<T>(DispatcherQueue q, Func<T> work)
    {
        if (q.HasThreadAccess) return Task.FromResult(work());
        var tcs = new TaskCompletionSource<T>(TaskCreationOptions.RunContinuationsAsynchronously);
        if (!q.TryEnqueue(() => { try { tcs.SetResult(work()); } catch (Exception ex) { tcs.SetException(ex); } }))
            tcs.SetCanceled();
        return tcs.Task;
    }
}
```

### 6.2 `ApplicationData` vs `System.IO`

| Storage API | Packaged (MSIX) | Unpackaged (`WindowsPackageType=None`) | Guidance |
|---|---|---|---|
| `Windows.Storage.ApplicationData.Current` *(WinRT)* | Works (AppContainer store) | **Throws** (`APPMODEL_ERROR_NO_PACKAGE` `0x80073D54`) | Avoid in code targeting unpackaged builds. |
| `Microsoft.Windows.Storage.ApplicationData.GetDefault()` *(WinAppSDK)* | Works | **Fails** (requires package identity) | Packaged-only paths. |
| `Microsoft.Windows.Storage.ApplicationData.GetForUnpackaged(pub, app)` *(WinAppSDK)* | Not intended | Maps structured store under `%LOCALAPPDATA%\<pub>\<app>` | Use when unpackaged code needs `StorageFolder`/`LocalSettings`. |
| `Environment.GetFolderPath(SpecialFolder.LocalApplicationData)` + `System.IO` *(.NET BCL)* | Works (MSIX-redirected) | Works natively under `%LOCALAPPDATA%` | **Most portable** across packaged, unpackaged, WPF, and NativeAOT. |

---

## 7. C# NativeAOT in WinUI 3 (`PublishAot`, `CsWinRT`, Trimming Pitfalls)

*(Origin: Windows App SDK 1.6+ NativeAOT docs, `Microsoft.Windows.CsWinRT` >= 2.1.1 / 2.2+.)*

Microsoft's Windows App SDK 1.6 NativeAOT benchmark (*Contoso Camera*) measured ~**50% faster cold startup**, ~**8x smaller framework-dependent MSIX**, and ~**2x smaller self-contained package**.

```xml
<PropertyGroup>
  <PublishAot>true</PublishAot>
  <!-- CsWinRT >= 2.1.1 (2.2.x+ recommended) enables CsWinRTAotOptimizerEnabled when PublishAot=true -->
  <CsWinRTAotWarningLevel>2</CsWinRTAotWarningLevel>
  <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
</PropertyGroup>
<ItemGroup>
  <PackageReference Include="Microsoft.WindowsAppSDK" Version="1.7.*" />
  <PackageReference Include="Microsoft.Windows.CsWinRT" Version="2.2.*" />
</ItemGroup>
```

- **Eliminate runtime reflection:** Use `{x:Bind}` with `x:DataType` everywhere. Legacy `{Binding}` and `DisplayMemberPath` silently fail unless models are declared `partial` with **`[WinRT.GeneratedBindableCustomProperty]`**.
- **MVVM Toolkit + AOT conflict (`MVVMTK0047`/`MVVMTK0048`):** Use C# `partial` properties (`CommunityToolkit.Mvvm >= 8.4`) with `[GeneratedBindableCustomProperty]` rather than field-backed `[ObservableProperty]` attributes:

```csharp
using CommunityToolkit.Mvvm.ComponentModel;
using WinRT; // CsWinRT >= 2.1.1

[GeneratedBindableCustomProperty]
public sealed partial class DeviceSummary : ObservableObject
{
    [ObservableProperty]
    public partial string DisplayName { get; set; } = string.Empty;
}
```

- **Templates & JSON:** Replace reflection in `DataTemplateSelector` (`GetType().GetProperty(...)`) with sealed pattern matching (`item switch { HeaderItem => HeaderTemplate, _ => RowTemplate }`), and use `System.Text.Json` `[JsonSerializable]` `JsonSerializerContext` source generation.

---

## Part B — C++/WinRT & Modern Win32 C++ (Zero-.NET Runtime Native Apps)

## 8. Architecture Decision Matrix

*(Representative ranges for desktop utilities; actual metrics depend on view complexity, GPU driver heap, and self-contained packaging.)*

| Dimension | WPF (`.NET 9/10`) | WinUI 3 (C# JIT/R2R) | WinUI 3 (C# + `PublishAot`) | C++/WinRT (WinUI 3) | Pure Win32 + D2D / DirectComposition |
|---|---|---|---|---|---|
| **Runtime Dependencies** | `.NET Desktop` (or self-contained) | `.NET` + `WindowsAppSDK` | Native code + `WindowsAppSDK` | Zero `.NET`; `VC++ CRT` + `WindowsAppSDK` | **Zero external frameworks** (inbox OS DLLs only) |
| **Idle Working Set (RAM)** | ~60–140 MB | ~90–180 MB | ~55–120 MB | ~45–95 MB | **~5–20 MB** |
| **Release Size (Self-Contained)** | ~65–150 MB | ~110–180 MB | ~50–95 MB *(~2x smaller than JIT)* | ~15–35 MB *(+WASDK if self-contained)* | **< 0.5–2 MB** *(0.2–1.5 MB typical)* |
| **Cold Start (SSD)** | ~350–800 ms | ~500–1100 ms | ~250–550 ms *(~50% faster than JIT)* | ~180–400 ms | **< 30–100 ms** |
| **Designer / Hot Reload** | XAML Hot Reload + VS Designer | XAML Hot Reload | XAML Hot Reload (Debug) | Limited XAML Hot Reload | **None** (100% code-driven) |
| **OS / COM / C++ Interop** | `[LibraryImport]` / P/Invoke | `[LibraryImport]` / CsWinRT | `[LibraryImport]` / CsWinRT | **Direct C++20 headers** | **Direct Win32 / COM** |
| **Best Fit** | Rich LOB apps, custom chrome | Modern Fluent 2 C# apps | Distribution-sensitive C# WinUI 3 | Strict RAM/startup WinUI 3 + C++ core | Tray tools, HUDs, launchers, monitors |

---

## 9. Modern C++20/23 Windows Toolchain & WIL

*(Origin: MSVC `/std:c++20`, `vcpkg` manifest targets, Microsoft Windows Implementation Libraries (`WIL`).)*

- **MSVC flags:** `/std:c++20` (or `/std:c++latest`), `/permissive-`, `/utf-8`, `/EHsc`, `/W4` (standard `<coroutine>` works without `/await`).
- **MSBuild + NuGet** (for WinUI 3 XAML + MIDL targets): `Microsoft.WindowsAppSDK`, `Microsoft.Windows.CppWinRT`, `Microsoft.Windows.ImplementationLibrary`.
- **CMake + vcpkg** (for pure Win32, Direct2D, services, and non-XAML WinRT tools):

```json
// vcpkg.json -> { "name": "native-win-tool", "version-string": "1.0.0", "dependencies": [ "cppwinrt", "wil" ] }
```
```cmake
cmake_minimum_required(VERSION 3.24)
project(NativeWinTool LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
find_package(wil CONFIG REQUIRED)
find_package(cppwinrt CONFIG REQUIRED)
add_executable(NativeWinTool WIN32 main.cpp)
target_compile_options(NativeWinTool PRIVATE /permissive- /utf-8 /W4)
target_link_libraries(NativeWinTool PRIVATE WIL::WIL)
```

| WIL Symbol | Header | Role |
|---|---|---|
| `wil::unique_hkey`, `wil::unique_handle` | `<wil/resource.h>` | RAII handle closing (`RegCloseKey`, `CloseHandle`) |
| `THROW_IF_FAILED(hr)`, `RETURN_IF_FAILED(hr)` | `<wil/result.h>` | Deterministic `HRESULT` checks (`THROW_*` maps cleanly to `winrt::hresult_error`) |
| `wil::scope_exit([&] { ... })` | `<wil/common.h>` | Scope guard cleanup (`.release()` cancels on success) |
| `wil::resume_foreground(dispatcherQueue)` | `<wil/cppwinrt_helpers.h>` | `co_await` bridge onto WinUI 3 `Microsoft::UI::Dispatching::DispatcherQueue` |

```cpp
#include <windows.h>
#include <wil/resource.h>
#include <wil/result.h>
#include <wil/common.h>

HRESULT ReadSettingDword(DWORD& outValue) noexcept
{
    wil::unique_hkey key;
    RETURN_IF_WIN32_ERROR(RegOpenKeyExW(
        HKEY_CURRENT_USER, L"Software\\Example\\MyTool", 0, KEY_READ, key.put()));
    auto cleanupGuard = wil::scope_exit([&] { /* runs on early error exit */ });

    DWORD size = sizeof(DWORD), type = 0;
    RETURN_IF_WIN32_ERROR(RegQueryValueExW(
        key.get(), L"RefreshHz", nullptr, &type, reinterpret_cast<BYTE*>(&outValue), &size));
    RETURN_HR_IF(E_UNEXPECTED, type != REG_DWORD);
    cleanupGuard.release();
    return S_OK;
}
```

---

## 10. C++/WinRT Essentials (Apartments, Coroutines, `get_weak()`, MIDL 3.0)

*(Origin: C++/WinRT `winrt::*`, WIL `<wil/cppwinrt_helpers.h>`, MIDL 3.0 `midlrt`.)*

### 10.1 Apartments, Coroutines & `get_weak()` Safety

- **Apartments:** Call `winrt::init_apartment(winrt::apartment_type::single_threaded)` in STA Win32 entry points (`wWinMain`), or `winrt::init_apartment()` (MTA) in console/worker processes (`Application::Start` initializes STA for WinUI 3).
- **`IAsyncAction` / `winrt::fire_and_forget`:** Return `IAsyncAction` / `IAsyncOperation<T>` for awaitable methods; reserve `winrt::fire_and_forget` for top-level event handlers (unhandled exceptions terminate immediately).
- **Thread switching & dangling `this`:** Use `co_await winrt::resume_background()` for threadpool work, then `co_await wil::resume_foreground(uiQueue)` (`<wil/cppwinrt_helpers.h>`) — C++/WinRT's `winrt::resume_foreground` supports legacy `CoreDispatcher` / `Windows::System::DispatcherQueue`, **not** WinUI 3's `Microsoft::UI::Dispatching::DispatcherQueue` (or capture `winrt::apartment_context ui_thread;` and `co_await ui_thread;`). Always capture `auto weak_this{ get_weak() };` **before** the first `co_await`, because a `Page` or control can close and reach refcount 0 while background work is suspended:

```cpp
winrt::fire_and_forget MainPage::OnLoadClicked(
    winrt::Windows::Foundation::IInspectable const&, winrt::Microsoft::UI::Xaml::RoutedEventArgs const&)
{
    auto weak_this{ get_weak() };
    auto uiQueue = DispatcherQueue(); // Microsoft::UI::Dispatching::DispatcherQueue

    co_await winrt::resume_background();
    winrt::hstring payload = LoadHeavyDataFromDisk();

    co_await wil::resume_foreground(uiQueue); // from <wil/cppwinrt_helpers.h>
    if (auto strong_this{ weak_this.get() }) strong_this->StatusText().Text(payload); // Safe if unloaded mid-I/O
}
```

### 10.2 MIDL 3.0 (`.idl`) `runtimeclass` Authoring for XAML `{x:Bind}`

```idl
// StatusItem.idl
namespace NativeApp
{
    runtimeclass StatusItem : Microsoft.UI.Xaml.Data.INotifyPropertyChanged { StatusItem(String label); String Label; }
}
// MainPage.idl
import "StatusItem.idl";
namespace NativeApp
{
    [default_interface]
    runtimeclass MainPage : Microsoft.UI.Xaml.Controls.Page
    {
        MainPage();
        StatusItem CurrentStatus { get; };
        Windows.Foundation.Collections.IObservableVector<StatusItem> Items { get; };
    }
}
```
```cpp
void StatusItem::Label(winrt::hstring const& value) // inherits StatusItemT<StatusItem>
{
    if (m_label != value) { m_label = value; m_propertyChanged(*this, winrt::Microsoft::UI::Xaml::Data::PropertyChangedEventArgs{ L"Label" }); }
}
// In MainPage ctor: m_items = winrt::single_threaded_observable_vector<NativeApp::StatusItem>();
```

---

## 11. Pure Modern Win32 + DirectComposition / Direct2D Skeleton (< 2 MB Utilities)

*(Origin: Win32 `PerMonitorV2` DPI, `dwmapi.h`, `d3d11_1.h`, `dxgi1_3.h`, `d2d1_2.h` + `d2d1_1helper.h`, `dcomp.h`.)*

For sub-2 MB zero-framework utilities (`d3d11.lib dxgi.lib d2d1.lib dcomp.lib dwmapi.lib user32.lib`):
- **DPI (`PerMonitorV2`):** Prefer `<dpiAwareness>PerMonitorV2</dpiAwareness>` in `app.manifest` (or call `SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)` before any HWND exists — note the `_AWARE_` in the Win32 C constant!). Size outer rects via `AdjustWindowRectExForDpi(&rc, style, FALSE, exStyle, GetDpiForWindow(hwnd))` and handle `WM_DPICHANGED` (`LOWORD(wParam)` DPI, `reinterpret_cast<RECT const*>(lParam)` suggested bounds via `SetWindowPos`).
- **Zero-redirection window + Win11 DWM:** Pass `WS_EX_NOREDIRECTIONBITMAP` to `CreateWindowExW` (avoids redundant GDI redirection surface allocation when presenting via DirectComposition) and call `DwmSetWindowAttribute` (`DWMWA_USE_IMMERSIVE_DARK_MODE`, `DWMWA_WINDOW_CORNER_PREFERENCE = DWMWCP_ROUND`, `DWMWA_SYSTEMBACKDROP_TYPE`).

```cpp
#include <windows.h>
#include <dwmapi.h>
#include <d3d11_1.h>
#include <dxgi1_3.h>
#include <d2d1_2.h>
#include <d2d1_1helper.h>
#include <dcomp.h>
#include <wrl/client.h>
#include <wil/result.h>

using Microsoft::WRL::ComPtr;

struct D2DCompPipeline
{
    ComPtr<ID3D11Device> d3dDevice; ComPtr<IDXGIDevice> dxgiDevice; ComPtr<IDXGISwapChain1> swapChain;
    ComPtr<ID2D1Factory2> d2dFactory; ComPtr<ID2D1Device1> d2dDevice; ComPtr<ID2D1DeviceContext1> d2dContext;
    ComPtr<IDCompositionDevice> dcompDevice; ComPtr<IDCompositionTarget> dcompTarget; ComPtr<IDCompositionVisual> rootVisual;

    HRESULT Initialize(HWND hwnd, UINT widthPx, UINT heightPx) noexcept
    {
        RETURN_IF_FAILED(D3D11CreateDevice(
            nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, D3D11_CREATE_DEVICE_BGRA_SUPPORT,
            nullptr, 0, D3D11_SDK_VERSION, &d3dDevice, nullptr, nullptr));
        RETURN_IF_FAILED(d3dDevice.As(&dxgiDevice));

        ComPtr<IDXGIAdapter> adapter; ComPtr<IDXGIFactory2> dxgiFactory;
        RETURN_IF_FAILED(dxgiDevice->GetAdapter(&adapter));
        RETURN_IF_FAILED(adapter->GetParent(IID_PPV_ARGS(&dxgiFactory)));

        DXGI_SWAP_CHAIN_DESC1 desc{};
        desc.Width = widthPx; desc.Height = heightPx;
        desc.Format = DXGI_FORMAT_B8G8R8A8_UNORM; desc.SampleDesc.Count = 1;
        desc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT; desc.BufferCount = 2;
        desc.Scaling = DXGI_SCALING_STRETCH; desc.SwapEffect = DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL;
        desc.AlphaMode = DXGI_ALPHA_MODE_PREMULTIPLIED;
        RETURN_IF_FAILED(dxgiFactory->CreateSwapChainForComposition(dxgiDevice.Get(), &desc, nullptr, &swapChain));

        RETURN_IF_FAILED(D2D1CreateFactory(
            D2D1_FACTORY_TYPE_SINGLE_THREADED, __uuidof(ID2D1Factory2), nullptr, &d2dFactory));
        RETURN_IF_FAILED(d2dFactory->CreateDevice(dxgiDevice.Get(), &d2dDevice));
        RETURN_IF_FAILED(d2dDevice->CreateDeviceContext(D2D1_DEVICE_CONTEXT_OPTIONS_NONE, &d2dContext));

        RETURN_IF_FAILED(DCompositionCreateDevice(dxgiDevice.Get(), IID_PPV_ARGS(&dcompDevice)));
        RETURN_IF_FAILED(dcompDevice->CreateTargetForHwnd(hwnd, TRUE, &dcompTarget));
        RETURN_IF_FAILED(dcompDevice->CreateVisual(&rootVisual));
        RETURN_IF_FAILED(rootVisual->SetContent(swapChain.Get()));
        RETURN_IF_FAILED(dcompTarget->SetRoot(rootVisual.Get()));
        RETURN_IF_FAILED(dcompDevice->Commit());
        return BindBackBufferTarget(static_cast<float>(GetDpiForWindow(hwnd)));
    }

    HRESULT BindBackBufferTarget(float dpi) noexcept
    {
        ComPtr<IDXGISurface2> surface;
        RETURN_IF_FAILED(swapChain->GetBuffer(0, IID_PPV_ARGS(&surface)));
        D2D1_BITMAP_PROPERTIES1 props = D2D1::BitmapProperties1(
            D2D1_BITMAP_OPTIONS_TARGET | D2D1_BITMAP_OPTIONS_CANNOT_DRAW,
            D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM, D2D1_ALPHA_MODE_PREMULTIPLIED),
            dpi, dpi);
        ComPtr<ID2D1Bitmap1> targetBitmap;
        RETURN_IF_FAILED(d2dContext->CreateBitmapFromDxgiSurface(surface.Get(), &props, &targetBitmap));
        d2dContext->SetTarget(targetBitmap.Get());
        d2dContext->SetDpi(dpi, dpi);
        return S_OK;
    }
    // On WM_SIZE: d2dContext->SetTarget(nullptr); swapChain->ResizeBuffers(...); BindBackBufferTarget(...);
    // On Paint: d2dContext->BeginDraw(); ...; d2dContext->EndDraw(); swapChain->Present(1, 0);
};
```
