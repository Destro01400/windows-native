# Native Windows 11 Integration in WPF (.NET 9/10), DWM Interop & WinUI 3

> **Scope:** `System.Windows.Shell.WindowChrome`, `dwmapi.dll` backdrops/corners/colors, Windows 11 Snap Layouts (`HTMAXBUTTON`), Per-Monitor DPI v2, crisp rendering, runtime OS theme/accent/text-scale sync, `.NET 9/10` `ThemeMode`, Shell extras, ecosystem libraries, and WinUI 3 patterns.

## Table of Contents

1. [WindowChrome & Custom Title Bar Blueprint](#1-windowchrome--custom-title-bar-blueprint)
2. [DWM Interop (`dwmapi.dll`): Mica, Acrylic, Corners & Active Borders](#2-dwm-interop-dwmapidll-mica-acrylic-corners--active-borders)
3. [Complete Snap-Layout-Aware Custom Chrome Window (Compile-Verified)](#3-complete-snap-layout-aware-custom-chrome-window-compile-verified)
4. [Maximized Overflow Fix (`Root Margin` vs. `WM_GETMINMAXINFO`)](#4-maximized-overflow-fix-root-margin-vs-wm_getminmaxinfo)
5. [Per-Monitor DPI v2 & Crisp DirectWrite/WPF Rendering](#5-per-monitor-dpi-v2--crisp-directwritewpf-rendering)
6. [System Theme, Accent Color, High Contrast & Text Scale Sync](#6-system-theme-accent-color-high-contrast--text-scale-sync)
7. [.NET 9 / .NET 10 `PresentationFramework.Fluent` (`ThemeMode`) & Brand Overrides](#7-net-9--net-10-presentationframeworkfluent-thememode--brand-overrides)
8. [Windows Shell Features (Taskbar, JumpList, Toasts, Tray, Single Instance)](#8-windows-shell-features-taskbar-jumplist-toasts-tray-single-instance)
9. [WPF Ecosystem & WinUI 3 Quick Reference](#9-wpf-ecosystem--winui-3-quick-reference)

---

## 1. `WindowChrome` & Custom Title Bar Blueprint

`System.Windows.Shell.WindowChrome` keeps the native Win32 frame (`WS_CAPTION | WS_THICKFRAME | WS_SYSMENU`), Aero Snap, resize shadows, and `Alt+Space` system menu while letting XAML draw inside the top caption strip.

### 1.1 Critical `WindowChrome` Property Rules

| Property | Recommended Value | Pitfall to Avoid |
|---|---|---|
| `CaptionHeight` | `32` (compact) or `40–48` (tall with search/tabs/actions) | Marks the top strip `HTCAPTION` (draggable). Any button/textbox inside this height **must** set `WindowChrome.IsHitTestVisibleInChrome="True"` or clicks only drag the window! |
| `ResizeBorderThickness` | `5`–`6` (`0` if `NoResize`) | Avoid oversized top resize thickness (`> 6`) or it steals clicks on top title bar buttons. |
| `GlassFrameThickness` | **`-1`** (`new Thickness(-1)`) | **`0` disables DWM sheet-of-glass**, breaking native Windows 11 Mica/Acrylic and (when `WindowStyle="None"`) removing native Windows 11 frame shadow/rounding unless explicitly restored. Use `-1` (or `1` on opaque custom frames). |
| `UseAeroCaptionButtons` | `False` (custom buttons) or `True` (OS native Win11 buttons) | If `True`, Windows draws/handles native Min/Max/Close + Snap Layouts automatically (leave ~`140px` empty on top-right). If `False`, you **must** implement `HTMAXBUTTON` (`§3`) for Snap Layouts. |
| `NonClientFrameEdges` | `None` (or `Left,Right,Bottom` on Win11 `!HighContrast`) | **Never** include `Top` when drawing custom title bar content at `y = 0`. |
| `CornerRadius` | Ignore (`0`) when using DWM `-1` glass | Only affects non-DWM fallback clipping; real Win11 corners come from `DWMWA_WINDOW_CORNER_PREFERENCE`. |

### 1.2 Custom Title Bar UX Rules

- **Metrics:** Compact = `32 epx`; Tall = `48 epx`. App icon `16x16` (`16px` left margin). Title in `Caption` (`12/16 epx`) with `TextTrimming="CharacterEllipsis"`. Always keep **`>= 48 epx`** empty draggable strip next to caption buttons even at `MinWidth`.
- **Active / Inactive Visual Cue:** Bind title bar text, app icon, and caption button foregrounds to `Window.IsActive` -> drop `Opacity` to **`0.55`** when `IsActive == false`.
- **Caption Glyphs (`Segoe Fluent Icons`):** Minimize `&#xE921;`, Maximize `&#xE922;`, Restore `&#xE923;`, Close `&#xE8BB;`, Back `&#xE830;`. Sync Maximize/Restore glyph on **`Window.StateChanged`**, NOT just button click (Aero Snap, `Win+Up`, and title-bar double-click bypass button click!).
- **Close Button Hover:** Standard Windows `#C42B1C` background + `#FFFFFF` glyph on hover.
- **High Contrast:** When `SystemParameters.HighContrast == true`, disable Mica/custom translucency and apply `SystemColors.ActiveCaptionBrushKey` / `HighlightBrushKey`.

### 1.3 Why `AllowsTransparency="True"` Is an Anti-Pattern

- Forces `WindowStyle="None"` and `HwndSourceParameters.UsesPerPixelOpacity = true`, telling Windows to **stop drawing the non-client frame completely**.
- Breaks OS DWM rounded corners (`DWMWA_WINDOW_CORNER_PREFERENCE`), DWM shadows, Aero Snap / Snap Layouts, and Mica/Acrylic (`WindowBackdropManager` explicitly skips it).
- Reserve `AllowsTransparency="True"` strictly for irregular splash screens or small custom `Popup`s — **never** for primary application windows.

---

## 2. DWM Interop (`dwmapi.dll`): Mica, Acrylic, Corners & Active Borders

> **`.csproj` Requirement (`SYSLIB1062`):** Source-generated `[LibraryImport("dwmapi.dll")]` requires `<AllowUnsafeBlocks>true</AllowUnsafeBlocks>` in your `.csproj`! If you cannot enable unsafe blocks, replace `[LibraryImport]` with classic `[DllImport]`.

| Attribute (`DWMWINDOWATTRIBUTE`) | ID | Min Build | Values & Crucial Notes |
|---|---|---|---|
| `DWMWA_USE_IMMERSIVE_DARK_MODE` | `20` | Win10 19041 / Win11 | `1` = Dark chrome/Snap menu/title bar, `0` = Light. **Match your actual theme!** Setting `1` on a light app paints dark Snap menus and frame accents. |
| `DWMWA_WINDOW_CORNER_PREFERENCE` | `33` | Win11 (`22000`) | `0` Default, `1` DoNotRound, **`2` Round (`8px`)**, `3` RoundSmall (`4px`). Auto-resets to square when maximized/snapped. |
| `DWMWA_BORDER_COLOR` | `34` | Win11 (`22000`) | `COLORREF` (`0x00BBGGRR`), `0xFFFFFFFE` (None), `0xFFFFFFFF` (Default). **Update manually in `Activated`/`Deactivated`** (DWM doesn't auto-dim custom border colors!). |
| `DWMWA_CAPTION_COLOR` / `TEXT_COLOR` | `35` / `36` | Win11 (`22000`) | Colors native system caption bar (`0x00BBGGRR`). |
| `DWMWA_SYSTEMBACKDROP_TYPE` | `38` | Win11 22H2 (**`22621`**) | `1` None, **`2` Mica**, `3` Desktop Acrylic, **`4` Mica Alt**. |

### 2.1 Four Mandatory Prerequisites for Real Mica / Acrylic in WPF

1. `AllowsTransparency = false`.
2. `HwndSource.FromHwnd(hwnd).CompositionTarget.BackgroundColor = Colors.Transparent`.
3. `Window.Background = Brushes.Transparent` (and any surface layer above it must be translucent `#CC...`, not opaque full-bleed!).
4. `DwmExtendFrameIntoClientArea(hwnd, ref new MARGINS(-1, -1, -1, -1))` + `OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22621)`.
*(If using an **opaque** custom brand canvas, omit `DWMWA_SYSTEMBACKDROP_TYPE` / set `None` so DWM doesn't composite Mica behind opaque pixels.)*

```csharp
using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;

// Requires <AllowUnsafeBlocks>true</AllowUnsafeBlocks> in .csproj for [LibraryImport]
public static partial class DwmWindowHelper
{
    public enum BackdropType { Auto = 0, None = 1, Mica = 2, Acrylic = 3, MicaAlt = 4 }
    public enum CornerPreference { Default = 0, DoNotRound = 1, Round = 2, RoundSmall = 3 }

    private const int DWMWA_USE_IMMERSIVE_DARK_MODE = 20;
    private const int DWMWA_WINDOW_CORNER_PREFERENCE = 33;
    private const int DWMWA_BORDER_COLOR = 34;
    private const int DWMWA_CAPTION_COLOR = 35;
    private const int DWMWA_TEXT_COLOR = 36;
    private const int DWMWA_SYSTEMBACKDROP_TYPE = 38;
    public const uint DWMWA_COLOR_DEFAULT = 0xFFFFFFFF;
    public const uint DWMWA_COLOR_NONE = 0xFFFFFFFE;

    [StructLayout(LayoutKind.Sequential)]
    private struct MARGINS { public int cxLeftWidth, cxRightWidth, cyTopHeight, cyBottomHeight; }

    [LibraryImport("dwmapi.dll")] private static partial int DwmSetWindowAttribute(nint hwnd, int attr, ref int val, int size);
    [LibraryImport("dwmapi.dll")] private static partial int DwmSetWindowAttribute(nint hwnd, int attr, ref uint val, int size);
    [LibraryImport("dwmapi.dll")] private static partial int DwmExtendFrameIntoClientArea(nint hwnd, ref MARGINS inset);

    public static void SetDarkMode(nint hwnd, bool isDark)
    {
        if (hwnd == 0 || !OperatingSystem.IsWindowsVersionAtLeast(10, 0, 19041)) return;
        int val = isDark ? 1 : 0;
        _ = DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ref val, sizeof(int));
    }

    public static void SetCornerPreference(nint hwnd, CornerPreference pref = CornerPreference.Round)
    {
        if (hwnd == 0 || !OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22000)) return;
        int val = (int)pref;
        _ = DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ref val, sizeof(int));
    }

    public static void SetBorderColor(nint hwnd, Color? color, bool hide = false)
    {
        if (hwnd == 0 || !OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22000)) return;
        uint colorRef = hide ? DWMWA_COLOR_NONE : color is { } c ? ToColorRef(c) : DWMWA_COLOR_DEFAULT;
        _ = DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR, ref colorRef, sizeof(uint));
    }

    public static void SetCaptionColors(nint hwnd, Color? captionColor, Color? textColor)
    {
        if (hwnd == 0 || !OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22000)) return;
        uint cap = captionColor is { } c ? ToColorRef(c) : DWMWA_COLOR_DEFAULT;
        uint txt = textColor is { } t ? ToColorRef(t) : DWMWA_COLOR_DEFAULT;
        _ = DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, ref cap, sizeof(uint));
        _ = DwmSetWindowAttribute(hwnd, DWMWA_TEXT_COLOR, ref txt, sizeof(uint));
    }

    public static bool TryApplyBackdrop(Window window, BackdropType type)
    {
        if (window.AllowsTransparency || SystemParameters.HighContrast || !OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22621))
            return false;

        nint hwnd = new WindowInteropHelper(window).EnsureHandle();
        if (HwndSource.FromHwnd(hwnd)?.CompositionTarget is { } target)
            target.BackgroundColor = type == BackdropType.None ? SystemColors.WindowColor : Colors.Transparent;

        window.Background = type == BackdropType.None ? SystemColors.WindowBrush : Brushes.Transparent;
        var margins = type == BackdropType.None
            ? default
            : new MARGINS { cxLeftWidth = -1, cxRightWidth = -1, cyTopHeight = -1, cyBottomHeight = -1 };
        _ = DwmExtendFrameIntoClientArea(hwnd, ref margins);

        int val = (int)type;
        return DwmSetWindowAttribute(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, ref val, sizeof(int)) == 0;
    }

    private static uint ToColorRef(Color c) => (uint)((c.B << 16) | (c.G << 8) | c.R);
}
```

---

## 3. Complete Snap-Layout-Aware Custom Chrome Window (Compile-Verified)

When `UseAeroCaptionButtons="False"`, hovering Maximize opens Windows 11 Snap Layouts **only** if `WndProc` returns `HTMAXBUTTON (9)` on `WM_NCHITTEST`. Returning `HTMAXBUTTON` stops WPF client mouse events on that button, so you must handle `WM_NCMOUSEMOVE`, `WM_NCMOUSELEAVE`, `WM_NCLBUTTONDOWN`, and `WM_NCLBUTTONUP` and extract screen coords with **signed 16-bit casts** `(short)` for multi-monitor negative positions. *(Keep `MinWidth <= 500`, ideally `<= 330`.)*

```xml
<!-- CustomChromeWindow.xaml (.NET 10 Grid shorthand) -->
<Window x:Class="MyApp.CustomChromeWindow"
        xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        xmlns:po="http://schemas.microsoft.com/winfx/2006/xaml/presentation/options"
        xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
        xmlns:shell="clr-namespace:System.Windows.Shell;assembly=PresentationFramework"
        mc:Ignorable="po"
        Title="My Windows App" Width="1100" Height="720" MinWidth="330" MinHeight="240"
        UseLayoutRounding="True" TextOptions.TextFormattingMode="Display" Background="Transparent">
    <shell:WindowChrome.WindowChrome>
        <shell:WindowChrome CaptionHeight="40" ResizeBorderThickness="5"
                            GlassFrameThickness="-1" UseAeroCaptionButtons="False" NonClientFrameEdges="None" />
    </shell:WindowChrome.WindowChrome>
    <Window.Resources>
        <FontFamily x:Key="SymbolFont">Segoe Fluent Icons, Segoe MDL2 Assets</FontFamily>
        <SolidColorBrush x:Key="CaptionHoverBrush" Color="#14808080" po:Freeze="True" />
        <SolidColorBrush x:Key="CaptionPressedBrush" Color="#24808080" po:Freeze="True" />
        <Style x:Key="CaptionBtnStyle" TargetType="Button">
            <Setter Property="Width" Value="46" />
            <Setter Property="Height" Value="32" />
            <Setter Property="VerticalAlignment" Value="Top" />
            <Setter Property="Background" Value="Transparent" />
            <Setter Property="Foreground" Value="{DynamicResource TextPrimaryBrush}" />
            <Setter Property="BorderThickness" Value="0" />
            <Setter Property="SnapsToDevicePixels" Value="True" />
            <Setter Property="shell:WindowChrome.IsHitTestVisibleInChrome" Value="True" />
            <Setter Property="Template">
                <Setter.Value>
                    <ControlTemplate TargetType="Button">
                        <Border Background="{TemplateBinding Background}">
                            <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center" />
                        </Border>
                    </ControlTemplate>
                </Setter.Value>
            </Setter>
            <Style.Triggers>
                <DataTrigger Binding="{Binding IsActive, RelativeSource={RelativeSource AncestorType=Window}}" Value="False">
                    <Setter Property="Opacity" Value="0.55" />
                </DataTrigger>
                <Trigger Property="IsMouseOver" Value="True"><Setter Property="Background" Value="{StaticResource CaptionHoverBrush}" /></Trigger>
                <Trigger Property="IsPressed" Value="True"><Setter Property="Background" Value="{StaticResource CaptionPressedBrush}" /></Trigger>
            </Style.Triggers>
        </Style>
    </Window.Resources>
    <Grid x:Name="RootLayout" RowDefinitions="40, *">
        <Grid Grid.Row="0" ColumnDefinitions="Auto, *, Auto, Auto, Auto">
            <TextBlock Grid.Column="0" Text="{Binding Title, RelativeSource={RelativeSource AncestorType=Window}}"
                       Margin="16,0,0,0" VerticalAlignment="Center" TextTrimming="CharacterEllipsis" />
            <Button x:Name="MinBtn" Grid.Column="2" Click="OnMinimizeClick" Style="{StaticResource CaptionBtnStyle}"
                    ToolTip="Minimize" AutomationProperties.Name="Minimize">
                <TextBlock FontFamily="{StaticResource SymbolFont}" FontSize="10" Text="&#xE921;" IsHitTestVisible="False" />
            </Button>
            <Button x:Name="MaxBtn" Grid.Column="3" Click="OnMaximizeRestoreClick" Style="{StaticResource CaptionBtnStyle}"
                    ToolTip="Maximize" AutomationProperties.Name="Maximize">
                <TextBlock x:Name="MaxGlyph" FontFamily="{StaticResource SymbolFont}" FontSize="10" Text="&#xE922;" IsHitTestVisible="False" />
            </Button>
            <Button x:Name="CloseBtn" Grid.Column="4" Click="OnCloseClick" Style="{StaticResource CaptionBtnStyle}"
                    ToolTip="Close" AutomationProperties.Name="Close">
                <TextBlock FontFamily="{StaticResource SymbolFont}" FontSize="10" Text="&#xE8BB;" IsHitTestVisible="False" />
            </Button>
        </Grid>
        <ContentPresenter Grid.Row="1" />
    </Grid>
</Window>
```

```csharp
using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Interop;
using System.Windows.Media;

namespace MyApp;

public partial class CustomChromeWindow : Window
{
    private const int WM_NCHITTEST = 0x0084, WM_NCMOUSEMOVE = 0x00A0, WM_NCLBUTTONDOWN = 0x00A1,
                      WM_NCLBUTTONUP = 0x00A2, WM_NCMOUSELEAVE = 0x02A2, HTMAXBUTTON = 9;
    private const uint TME_LEAVE = 0x0002, TME_NONCLIENT = 0x0010;
    private const int SM_CXFRAME = 32, SM_CYFRAME = 33, SM_CXPADDEDBORDER = 92;

    private static readonly SolidColorBrush MaxHoverBrush = CreateFrozenBrush(Color.FromArgb(0x14, 0x80, 0x80, 0x80));
    private bool _maxHovered, _maxPressed, _trackingNcLeave;
    private HwndSource? _hwndSource;

    public CustomChromeWindow()
    {
        InitializeComponent();
        StateChanged += (_, _) => UpdateMaximizedMetrics();
        Closed += (_, _) => _hwndSource?.RemoveHook(WndProc);
    }

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);
        _hwndSource = PresentationSource.FromVisual(this) as HwndSource;
        _hwndSource?.AddHook(WndProc);
        UpdateMaximizedMetrics();
    }

    private void UpdateMaximizedMetrics()
    {
        MaxGlyph.Text = WindowState == WindowState.Maximized ? "\uE923" : "\uE922";
        MaxBtn.ToolTip = WindowState == WindowState.Maximized ? "Restore" : "Maximize";
        if (WindowState == WindowState.Maximized)
        {
            var dpi = VisualTreeHelper.GetDpi(this);
            uint winDpi = (uint)dpi.PixelsPerInchX;
            int pad = GetSystemMetricsForDpi(SM_CXPADDEDBORDER, winDpi);
            double x = (GetSystemMetricsForDpi(SM_CXFRAME, winDpi) + pad) / dpi.DpiScaleX;
            double y = (GetSystemMetricsForDpi(SM_CYFRAME, winDpi) + pad) / dpi.DpiScaleY;
            RootLayout.Margin = new Thickness(x, y, x, y);
        }
        else RootLayout.Margin = default;
    }

    private nint WndProc(nint hwnd, int msg, nint wParam, nint lParam, ref bool handled)
    {
        switch (msg)
        {
            case WM_NCHITTEST:
                long lp = lParam.ToInt64();
                var screenPt = new Point((short)(lp & 0xFFFF), (short)((lp >> 16) & 0xFFFF));
                if (IsOverElement(MaxBtn, screenPt) && (WindowState == WindowState.Maximized || PointFromScreen(screenPt).Y > 5.0))
                {
                    SetMaxHover(true);
                    handled = true;
                    return HTMAXBUTTON;
                }
                SetMaxHover(false);
                break;

            case WM_NCMOUSEMOVE:
                if (!_trackingNcLeave)
                {
                    var tme = new TRACKMOUSEEVENT { cbSize = (uint)Marshal.SizeOf<TRACKMOUSEEVENT>(), dwFlags = TME_LEAVE | TME_NONCLIENT, hwndTrack = hwnd };
                    TrackMouseEvent(ref tme);
                    _trackingNcLeave = true;
                }
                break;

            case WM_NCMOUSELEAVE:
                _trackingNcLeave = false; _maxPressed = false; SetMaxHover(false);
                break;

            case WM_NCLBUTTONDOWN when wParam == HTMAXBUTTON:
                _maxPressed = true; handled = true; return 0;

            case WM_NCLBUTTONUP when _maxPressed && wParam == HTMAXBUTTON:
                _maxPressed = false; SetMaxHover(false);
                WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
                handled = true; return 0;
        }
        return 0;
    }

    private void SetMaxHover(bool hovered)
    {
        if (_maxHovered == hovered) return;
        _maxHovered = hovered;
        MaxBtn.SetCurrentValue(BackgroundProperty, hovered ? MaxHoverBrush : Brushes.Transparent);
        if (!hovered) _maxPressed = false;
    }

    private static SolidColorBrush CreateFrozenBrush(Color color)
    {
        var b = new SolidColorBrush(color);
        b.Freeze();
        return b;
    }

    private static bool IsOverElement(FrameworkElement el, Point screenPt)
    {
        if (!el.IsVisible || PresentationSource.FromVisual(el) is null) return false;
        Point rel = el.PointFromScreen(screenPt); // PointFromScreen returns DIPs
        return rel.X >= -1 && rel.Y >= -1 && rel.X <= el.ActualWidth + 1 && rel.Y <= el.ActualHeight + 1;
    }

    private void OnMinimizeClick(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;
    private void OnMaximizeRestoreClick(object sender, RoutedEventArgs e) => WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
    private void OnCloseClick(object sender, RoutedEventArgs e) => Close();

    [LibraryImport("user32.dll")] private static partial int GetSystemMetricsForDpi(int nIndex, uint dpi);
    [DllImport("user32.dll")] private static extern bool TrackMouseEvent(ref TRACKMOUSEEVENT lpEventTrack);
    [StructLayout(LayoutKind.Sequential)] private struct TRACKMOUSEEVENT { public uint cbSize, dwFlags; public nint hwndTrack; public uint dwHoverTime; }
}
```

---

## 4. Maximized Overflow Fix (`Root Margin` vs. `WM_GETMINMAXINFO`)

Borderless `WindowChrome` windows overhang by `~8 DIPs` (`SM_CXFRAME + SM_CXPADDEDBORDER`) when maximized:
- **Approach A (Recommended for `GlassFrameThickness="-1"`):** Apply `RootLayout.Margin` in `UpdateMaximizedMetrics()` above — plays natively with multi-monitor DPI and Snap.
- **Approach B (`WM_GETMINMAXINFO` — required if `GlassFrameThickness="0"` or `WindowStyle="None"`):**
  1. Use signed `work.Left - mon.Left` and `work.Width`/`work.Height` (never blind `Math.Abs`).
  2. **Scale `ptMinTrackSize` by DPI!** `ptMinTrackSize` uses **physical pixels** (`(int)(MinWidth * dpi.DpiScaleX)`). Hardcoding `750` shrinks minimum width to `375 DIP` on `200%` monitors.
  3. **Auto-hide taskbar edge:** When taskbar auto-hides, `rcWork == rcMonitor`. Call `SHAppBarMessage(ABM_GETSTATE)` + `SHAppBarMessage(ABM_GETTASKBARPOS)` and inset the matching edge by **`2 px`** so hovering reveals the taskbar.

---

## 5. Per-Monitor DPI v2 & Crisp DirectWrite/WPF Rendering

- **Prefer `app.manifest` over `SetProcessDpiAwarenessContext` in code:** Calling `SetProcessDpiAwarenessContext(-4)` in `OnStartup` fails if any native DLL/COM/HWND touches DPI earlier. Always ship an `<ApplicationManifest>` with `<dpiAwareness>PerMonitorV2</dpiAwareness>` + `<dpiAware>true/pm</dpiAware>` + `Microsoft.Windows.Common-Controls` `6.0.0.0`.
- **On `DpiChanged`:** WPF scales DIP controls automatically, **but** recalculate Win32 interop (`WM_GETMINMAXINFO`, `RenderTargetBitmap` via `VisualTreeHelper.SetRootDpi`, multi-scale PNG bitmaps).
- **Crisp Rendering Defaults:**

| Property | Set Where | Recommended Setting |
|---|---|---|
| `UseLayoutRounding` | Root `Window` | `True` (snaps Measure/Arrange to whole pixels) |
| `SnapsToDevicePixels` | `Border`s / `ControlTemplate`s | `True` (`False` on continuously rotating/scaling vectors) |
| `TextOptions.TextFormattingMode` | UI text (`11–14px`) vs Display (`>=18px`) | **`Display`** for crisp 11–14px UI controls & 100–125% DPI; **`Ideal`** (default) for large headings (`>= 18px`) or zooming transforms |
| `TextOptions.TextRenderingMode` | Semi-transparent / Mica surfaces | **`Grayscale`** (prevents colored ClearType fringes on translucent backgrounds); `Auto`/`ClearType` on opaque cards |
| `RenderOptions.BitmapScalingMode` | Static icons/avatars | **`HighQuality`** (default `Linear`/`LowQuality` blurs downscaled photos/icons!) |

---

## 6. System Theme, Accent Color, High Contrast & Text Scale Sync

- **Detect Light/Dark:** Read `HKCU\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize\AppsUseLightTheme` (`0` = Dark, `1` = Light) or WinRT `UISettings.GetColorValue(UIColorType.Foreground)` (`(5*G + 2*R + B) > (8*128)` -> Dark).
- **Listen Live (Leak-Safe!):** Handle `WM_SETTINGCHANGE` (`0x001A`, `lParam == "ImmersiveColorSet"`), `SystemEvents.UserPreferenceChanged`, `SystemParameters.StaticPropertyChanged` (`HighContrast`), and `UISettings.ColorValuesChanged` / `TextScaleFactorChanged` (`net10.0-windows10.0.19041.0`+ TFM). **Always unsubscribe (`-=`) and `RemoveHook` on exit (`SystemEvents` is static and leaks forever!).**
- **Read Accent Color:** Use WPF `.NET 9+` `SystemColors.AccentColor*` (no WinRT TFM needed) or `UISettings.GetColorValue(UIColorType.Accent)`.
- **Runtime Theme Switch (`MergedDictionaries`):** Swap **only the theme dictionary slot** (e.g., `MergedDictionaries[0]`) using `{DynamicResource}` brush references on views; keep styles/templates untouched so WPF doesn't re-parse the whole resource tree.

---

## 7. `.NET 9 / .NET 10` `PresentationFramework.Fluent` (`ThemeMode`) & Brand Overrides

- **Enabling:** Set `ThemeMode="System"` (or `Light`/`Dark`) on `<Application>` / `<Window>`, or merge `pack://application:,,,/PresentationFramework.Fluent;component/Themes/Fluent.xaml`. Suppress experimental warning **`WPF0001`** in `.csproj` (`<NoWarn>$(NoWarn);WPF0001</NoWarn>`).
- **What's Included (.NET 10):** 47 styled controls (`.NET 10` added `DatePicker`, `GridSplitter`, `GridView`, `GroupBox`, `Hyperlink`, `Label`, `NavigationWindow`, `RichTextBox`, `TextBox` and fixed `Expander`, `HighContrast`, `RecognizesAccessKey`, and RTL mirroring) plus automatic Mica backdrop (`DWMSBT_MAINWINDOW`).
- **Known Gotchas:**
  1. **Implicit Style Trap:** Declaring `<Style TargetType="Button">` without `BasedOn="{StaticResource {x:Type Button}}"` (or `DefaultButtonStyle`) wipes out the Fluent `ControlTemplate`!
  2. **`StaticResource` Brush Override Trap:** Fluent `Light.xaml`/`Dark.xaml` bind `AccentFillColorDefaultBrush` via `{StaticResource SystemAccentColorDark1}`. Overriding `SystemAccentColorDark1` alone does **not** recolor Fluent controls — override the **`*Brush` keys directly** (`AccentFillColorDefaultBrush`, `AccentButtonBackground`, etc.) after `Fluent.xaml`.
  3. **`DataGrid`, `StatusBar`, `TreeView` Gaps:** `StatusBar` has minimal styling, `DataGrid` still holds Aero color quirks, and `TreeViewItem` uses a tiny `FontSize="10"` chevron (needs manual size bump for contrast).

---

## 8. Windows Shell Features (Taskbar, JumpList, Toasts, Tray, Single Instance)

- **`Window.TaskbarItemInfo`:** Built-in progress bar (`ProgressState` = `Normal`/`Paused`/`Error`/`Indeterminate`, `ProgressValue` `0..1`), 16x16 `Overlay` badge, `ThumbnailClipMargin`, and up to 7 `ThumbButtonInfo` (`ICommand`, `Description` max 259 chars).
- **`JumpList`:** `JumpList.SetJumpList(Application.Current, list); list.Apply();` on STA thread (`Title=""` = separator; `JumpPath` requires file association). Subscribe to `JumpItemsRejected` (`RemovedByUser` items must never be re-added forcefully).
- **Toast Notifications:** Prefer **`Microsoft.Windows.AppNotifications.AppNotificationManager`** (`Microsoft.WindowsAppSDK`) over legacy `Microsoft.Toolkit.Uwp.Notifications`. Subscribe `NotificationInvoked` **before** calling `Register()` (runs on background thread -> `Dispatcher.Invoke`), call `Unregister()` on exit, and note **Windows App SDK toasts fail when running elevated as Admin**.
- **System Tray:** Prefer **`H.NotifyIcon.Wpf`** (`2.4.1`, MIT, explicit `net10.0-windows7.0`, supports Win11 native dark/light `ContextMenuMode="PopupMenu"` & Win11 Efficiency Mode). Avoid `System.Windows.Forms.NotifyIcon`.
- **Single Instance & Startup:** Use `Mutex` + `NamedPipeServerStream`/`ClientStream` (no WinForms dependency). Startup registration for unpackaged apps writes quoted `.exe` path to `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`; packaged MSIX uses `StartupTask.GetAsync`.

---

## 9. WPF Ecosystem & WinUI 3 Quick Reference

### 9.1 WPF UI Libraries (Verified Nov 2026)

| Library | Version / Date | License | `.NET 10` | Verdict |
|---|---|---|---|---|
| **In-box `PresentationFramework.Fluent`** | .NET 9 & 10 SDK | MIT | Native | Great baseline for standard controls + Mica; missing compound WinUI controls (`NavigationView`, `InfoBar`, `ContentDialog`). |
| **`WPF-UI` (`lepoco/wpfui`)** | `4.3.0` (05/2026) | MIT | Explicit `net10.0` | Best full-featured MIT Win11 suite (`FluentWindow`, Snap Layouts `TitleBar`, `NavigationView`, `ContentDialog`, `InfoBar`, `Snackbar`). |
| **`ModernWpfUI` (`Kinnara`)** | `1.0.0-rc.1` (09/2026) | MIT | Explicit `net10.0` | Revived over `.NET 10` `PresentationFramework.Fluent`; strong option once `1.0.0` GA ships. |
| **`iNKORE.UI.WPF.Modern`** | `0.11.0` (10/2026) | **⚠️ Custom Restrictive** | `net6.0` | **Commercial restriction!** Requires paid/written license for commercial apps + source disclosure. Avoid unless explicitly cleared. |
| **`MahApps.Metro`** | `2.4.11` / `3.0-rc` | MIT | `net8.0` | Battle-tested (`ControlzEx`), but Win10 Metro look — not Win11 Fluent. |
| **`MaterialDesignThemes`** | `5.4.0` (10/2026) | MIT | `net10.0` | Google Material Design 2/3 — wrong fit for native Windows 11 apps. |
| **Custom (`WindowChrome` + Token Dictionary)** | In-house | — | Native `.NET 10` | **Best fit when keeping a distinct brand theme** — zero dictionary collisions, minimal footprint; selectively borrow `ControlTemplate` patterns or `H.NotifyIcon.Wpf`. |

### 9.2 WPF (.NET 10) vs. WinUI 3 (`WindowsAppSDK`)

- **Stay on WPF (.NET 10)** when you need: unpackaged single-folder/installer deploy with tiny RAM/cold start, `DynamicResource` runtime brand theming, `DataGrid` / `FlowDocument` / `AdornerLayer` / `MultiBinding` / `DataTrigger`s, Visual Studio XAML Designer, or an existing WPF investment.
- **Choose WinUI 3** for greenfield Win11 consumer apps prioritizing off-UI-thread `Microsoft.UI.Composition` animations, native `MicaBackdrop` / `AnimatedIcon` / `ConnectedAnimationService`, MSIX Store packaging, or Windows Copilot+ AI SDK controls (at the cost of Windows App Runtime install size, higher RAM, no VS XAML Designer, and no built-in `DataGrid`).
- **XAML Islands warning:** Legacy UWP `WindowsXamlHost` died at `.NET Core 3.x`. Only WinUI `DesktopWindowXamlSource` works on `.NET 10` (`HwndHost`).

### 9.3 WinUI 3 Quick Reference Snippets

```xml
<!-- WinUI 3 Window with native Mica & TitleBar -->
<Window x:Class="MyWinUIApp.MainWindow"
        xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
    <Window.SystemBackdrop>
        <MicaBackdrop Kind="Base" />
    </Window.SystemBackdrop>
    <Grid RowDefinitions="Auto, *">
        <TitleBar x:Name="AppTitleBar" Title="My WinUI App" IsBackButtonVisible="True">
            <TitleBar.Content>
                <AutoSuggestBox PlaceholderText="Search..." Width="320" />
            </TitleBar.Content>
        </TitleBar>
        <NavigationView Grid.Row="1" PaneDisplayMode="Left" />
    </Grid>
</Window>
```

```csharp
// WinUI 3 Code-Behind: extend into title bar + connected animation + theme resources
this.ExtendsContentIntoTitleBar = true;
this.SetTitleBar(AppTitleBar); // Automatically preserves Snap Layouts & drag regions!

// Connected animation between views:
ConnectedAnimationService.GetForCurrentView().PrepareToAnimate("HeroCard", sourceElement);
// On destination page OnNavigatedTo:
ConnectedAnimationService.GetForCurrentView().GetAnimation("HeroCard")?.TryStart(destElement);
```
