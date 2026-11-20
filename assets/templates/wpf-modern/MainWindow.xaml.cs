using System;
using System.Runtime.InteropServices;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Interop;
using System.Windows.Media;
using Windows.Win32;
using Windows.Win32.Foundation;
using Windows.Win32.Graphics.Dwm;
using Windows.Win32.UI.Input.KeyboardAndMouse;
using Windows.Win32.UI.WindowsAndMessaging;
using {{NAMESPACE}}.ViewModels;

namespace {{NAMESPACE}};

public partial class MainWindow : Window
{
    private const int WM_NCHITTEST = 0x0084;
    private const int WM_NCMOUSEMOVE = 0x00A0;
    private const int WM_NCLBUTTONDOWN = 0x00A1;
    private const int WM_NCLBUTTONUP = 0x00A2;
    private const int WM_NCMOUSELEAVE = 0x02A2;
    private const int HTMAXBUTTON = 9;

    private static readonly SolidColorBrush MaxHoverBrush = CreateFrozenBrush(Color.FromArgb(0x0F, 0x00, 0x00, 0x00));

    private bool _maxHovered;
    private bool _maxPressed;
    private bool _trackingNcLeave;
    private HwndSource? _hwndSource;

    public MainWindow(MainViewModel viewModel)
    {
        InitializeComponent();
        DataContext = viewModel;
        Activated += (_, _) => TitleText.Opacity = 1.0;
        Deactivated += (_, _) => TitleText.Opacity = 0.55;
        StateChanged += (_, _) => UpdateMaximizedMetrics();
        Closed += (_, _) => _hwndSource?.RemoveHook(WndProc);
    }

    protected override void OnSourceInitialized(EventArgs e)
    {
        base.OnSourceInitialized(e);
        _hwndSource = PresentationSource.FromVisual(this) as HwndSource;
        _hwndSource?.AddHook(WndProc);

        if (_hwndSource is not null)
        {
            ApplyDwmWindowStyle(_hwndSource.Handle);
        }

        UpdateMaximizedMetrics();
    }

    private static unsafe void ApplyDwmWindowStyle(nint hwnd)
    {
        if (hwnd == 0)
        {
            return;
        }

        var nativeHwnd = new HWND(hwnd);
        if (OperatingSystem.IsWindowsVersionAtLeast(10, 0, 19041))
        {
            int useDarkMode = 0;
            _ = PInvoke.DwmSetWindowAttribute(
                nativeHwnd,
                DWMWINDOWATTRIBUTE.DWMWA_USE_IMMERSIVE_DARK_MODE,
                &useDarkMode,
                sizeof(int));
        }

        if (OperatingSystem.IsWindowsVersionAtLeast(10, 0, 22000))
        {
            int cornerPreference = (int)DWM_WINDOW_CORNER_PREFERENCE.DWMWCP_ROUND;
            _ = PInvoke.DwmSetWindowAttribute(
                nativeHwnd,
                DWMWINDOWATTRIBUTE.DWMWA_WINDOW_CORNER_PREFERENCE,
                &cornerPreference,
                sizeof(int));
        }
    }

    private void UpdateMaximizedMetrics()
    {
        bool isMaximized = WindowState == WindowState.Maximized;
        MaxGlyph.Text = isMaximized ? "\uE923" : "\uE922";
        string label = isMaximized ? "Restore" : "Maximize";
        MaxBtn.ToolTip = label;
        AutomationProperties.SetName(MaxBtn, label);

        if (isMaximized)
        {
            DpiScale dpi = VisualTreeHelper.GetDpi(this);
            uint winDpi = (uint)Math.Max(96, Math.Round(dpi.PixelsPerInchX));
            int pad = PInvoke.GetSystemMetricsForDpi(SYSTEM_METRICS_INDEX.SM_CXPADDEDBORDER, winDpi);
            double x = (PInvoke.GetSystemMetricsForDpi(SYSTEM_METRICS_INDEX.SM_CXFRAME, winDpi) + pad) / dpi.DpiScaleX;
            double y = (PInvoke.GetSystemMetricsForDpi(SYSTEM_METRICS_INDEX.SM_CYFRAME, winDpi) + pad) / dpi.DpiScaleY;
            RootLayout.Margin = new Thickness(x, y, x, y);
        }
        else
        {
            RootLayout.Margin = default;
        }
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
                    var tme = new TRACKMOUSEEVENT
                    {
                        cbSize = (uint)Marshal.SizeOf<TRACKMOUSEEVENT>(),
                        dwFlags = TRACKMOUSEEVENT_FLAGS.TME_LEAVE | TRACKMOUSEEVENT_FLAGS.TME_NONCLIENT,
                        hwndTrack = new HWND(hwnd),
                    };
                    _ = PInvoke.TrackMouseEvent(ref tme);
                    _trackingNcLeave = true;
                }
                break;

            case WM_NCMOUSELEAVE:
                _trackingNcLeave = false;
                _maxPressed = false;
                SetMaxHover(false);
                break;

            case WM_NCLBUTTONDOWN when wParam == HTMAXBUTTON:
                _maxPressed = true;
                handled = true;
                return 0;

            case WM_NCLBUTTONUP when _maxPressed && wParam == HTMAXBUTTON:
                _maxPressed = false;
                SetMaxHover(false);
                WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;
                handled = true;
                return 0;
        }

        return 0;
    }

    private void SetMaxHover(bool hovered)
    {
        if (_maxHovered == hovered)
        {
            return;
        }

        _maxHovered = hovered;
        MaxBtn.SetCurrentValue(BackgroundProperty, hovered ? MaxHoverBrush : Brushes.Transparent);
        if (!hovered)
        {
            _maxPressed = false;
        }
    }

    private static SolidColorBrush CreateFrozenBrush(Color color)
    {
        var brush = new SolidColorBrush(color);
        brush.Freeze();
        return brush;
    }

    private static bool IsOverElement(FrameworkElement element, Point screenPt)
    {
        if (!element.IsVisible || PresentationSource.FromVisual(element) is null)
        {
            return false;
        }

        Point rel = element.PointFromScreen(screenPt);
        return rel.X >= -1 && rel.Y >= -1 && rel.X <= element.ActualWidth + 1 && rel.Y <= element.ActualHeight + 1;
    }

    private void OnMinimizeClick(object sender, RoutedEventArgs e) =>
        WindowState = WindowState.Minimized;

    private void OnMaximizeRestoreClick(object sender, RoutedEventArgs e) =>
        WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;

    private void OnCloseClick(object sender, RoutedEventArgs e) => Close();
}
