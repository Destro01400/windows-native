#!/usr/bin/env python3
"""Comprehensive zero-dependency unittest suite for audit_windows_app.py and audit_wpf_ui.py."""

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import audit_windows_app as auditor
import audit_wpf_ui as ui_wrapper


class TempProjectMixin:
    """Helpers for creating isolated temporary Windows app test projects."""

    def make_project(self, files: dict[str, str]) -> tempfile.TemporaryDirectory[str]:
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        for rel_path, content in files.items():
            full = root / rel_path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text(content, encoding="utf-8")
        return tmp

    def run_cli(self, func, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        code = 0
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                code = func(argv)
            except SystemExit as exc:
                code = exc.code if isinstance(exc.code, int) else 2
        return code, stdout.getvalue(), stderr.getvalue()


CLEAN_MANIFEST = """<?xml version="1.0" encoding="utf-8"?>
<assembly manifestVersion="1.0" xmlns="urn:schemas-microsoft-com:asm.v1">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v2">
    <security>
      <requestedPrivileges xmlns="urn:schemas-microsoft-com:asm.v3">
        <requestedExecutionLevel level="asInvoker" uiAccess="false" />
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}" />
    </application>
  </compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2</dpiAwareness>
      <longPathAware xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">true</longPathAware>
    </windowsSettings>
  </application>
</assembly>
"""

CLEAN_WPF_CSPROJ = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net10.0-windows10.0.19041.0</TargetFramework>
    <UseWPF>true</UseWPF>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <ApplicationManifest>app.manifest</ApplicationManifest>
    <PublishReadyToRun Condition="'$(Configuration)' == 'Release'">true</PublishReadyToRun>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="CommunityToolkit.Mvvm" Version="8.4.2" />
  </ItemGroup>
</Project>
"""


class TestLegacyUiAndXamlRules(TempProjectMixin, unittest.TestCase):
    def test_palette_contrast_positive_and_negative(self) -> None:
        bad_tokens = """<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
            xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
            xmlns:po="http://schemas.microsoft.com/winfx/2006/xaml/presentation/options">
  <SolidColorBrush x:Key="Surface0Brush" Color="#FFFFFF" po:Freeze="True" />
  <SolidColorBrush x:Key="TextSecondaryBrush" Color="#CCCCCC" po:Freeze="True" />
  <SolidColorBrush x:Key="AccentBrush" Color="#99CCFF" po:Freeze="True" />
  <SolidColorBrush x:Key="OnAccentBrush" Color="#FFFFFF" po:Freeze="True" />
</ResourceDictionary>"""
        with self.make_project({"Themes/Tokens.xaml": bad_tokens}) as tmp:
            res = auditor.run_audit(Path(tmp), ui_only=True)
            tags = [d["tag"] for d in res["details"]]
            self.assertEqual(tags.count("CONTRAST"), 2, res["findings"])

        good_tokens = """<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
            xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
            xmlns:po="http://schemas.microsoft.com/winfx/2006/xaml/presentation/options">
  <!-- <SolidColorBrush x:Key="TextSecondaryBrush" Color="#CCCCCC" /> -->
  <SolidColorBrush x:Key="Surface0Brush" Color="#FFFFFF" po:Freeze="True" />
  <SolidColorBrush x:Key="TextSecondaryBrush" Color="#444444" po:Freeze="True" />
  <SolidColorBrush x:Key="AccentBrush" Color="#005FB8" po:Freeze="True" />
  <SolidColorBrush x:Key="OnAccentBrush" Color="#FFFFFF" po:Freeze="True" />
</ResourceDictionary>"""
        with self.make_project({"Themes/Tokens.xaml": good_tokens}) as tmp:
            res = auditor.run_audit(Path(tmp), ui_only=True)
            self.assertEqual(res["details"], [], res["findings"])

    def test_freeze_tokens_and_runtime_brushes(self) -> None:
        bad_files = {
            "Themes/Tokens.xaml": """<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <SolidColorBrush x:Key="CardBrush" Color="#FFFFFF" />
  <DropShadowEffect x:Key="CardShadow" BlurRadius="8" />
</ResourceDictionary>""",
            "Views/MainView.xaml": """<UserControl xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
  <Border Background="#123456" />
</UserControl>""",
            "Views/MainView.xaml.cs": """using System.Windows.Media;
class MainView {
    void PaintBad() {
        var b = new SolidColorBrush(Colors.Red);
    }
    void PaintSpacer1() {}
    void PaintSpacer2() {}
    void PaintSpacer3() {}
    void PaintGood() {
        var ok = new SolidColorBrush(Colors.Blue);
        ok.Freeze();
    }
}""",
        }
        with self.make_project(bad_files) as tmp:
            res = auditor.run_audit(Path(tmp), ui_only=True)
            tags = [d["tag"] for d in res["details"]]
            self.assertEqual(tags.count("FREEZE"), 3, res["findings"])
            self.assertEqual(tags.count("TOKEN"), 1, res["findings"])

    def test_virtualization_and_shadow_in_datatemplate(self) -> None:
        bad_xaml = """<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
  <StackPanel>
    <ScrollViewer>
      <ListBox ItemsSource="{Binding Items}" />
    </ScrollViewer>
    <ListView ScrollViewer.CanContentScroll="False">
      <ListView.ItemTemplate>
        <DataTemplate>
          <Border Effect="{StaticResource CardShadow}" />
        </DataTemplate>
      </ListView.ItemTemplate>
    </ListView>
  </StackPanel>
</Window>"""
        with self.make_project({"MainWindow.xaml": bad_xaml}) as tmp:
            res = auditor.run_audit(Path(tmp), ui_only=True)
            perf_msgs = [d["message"] for d in res["details"] if d["tag"] == "PERF"]
            self.assertEqual(len(perf_msgs), 3, perf_msgs)

        good_xaml = """<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
  <StackPanel>
    <ScrollViewer />
    <ListBox ItemsSource="{Binding Items}" ScrollViewer.CanContentScroll="True" />
  </StackPanel>
</Window>"""
        with self.make_project({"MainWindow.xaml": good_xaml}) as tmp:
            res = auditor.run_audit(Path(tmp), ui_only=True)
            self.assertEqual(res["details"], [])

    def test_animations_rendering_and_pushframe_traps(self) -> None:
        bad_files = {
            "Views/Spinner.xaml": """<UserControl xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
  <UserControl.Triggers>
    <EventTrigger RoutedEvent="Loaded">
      <BeginStoryboard>
        <Storyboard RepeatBehavior="Forever" />
      </BeginStoryboard>
    </EventTrigger>
  </UserControl.Triggers>
</UserControl>""",
            "Views/Spinner.xaml.cs": """using System.Windows.Media;
using System.Windows.Threading;
class Spinner {
    void Start() {
        CompositionTarget.Rendering += OnRendering;
        Dispatcher.PushFrame(new DispatcherFrame()); // ApplicationIdle
        var p = DispatcherPriority.ApplicationIdle;
        Dispatcher.PushFrame(new DispatcherFrame());
    }
    void OnRendering(object? s, System.EventArgs e) {
        blur.BlurRadius = 10;
        bar.Height = 20;
    }
}""",
        }
        with self.make_project(bad_files) as tmp:
            res = auditor.run_audit(Path(tmp), ui_only=True)
            tags = [d["tag"] for d in res["details"]]
            self.assertIn("ANIM", tags)
            self.assertIn("ANIM-LEAK", tags)
            self.assertIn("PERF", tags)
            self.assertIn("TRAP", tags)

        good_files = {
            "Views/Spinner.xaml.cs": """using System;
using System.Windows.Media;
class Spinner {
    TimeSpan _last;
    void Start() => CompositionTarget.Rendering += OnRendering;
    void Stop() => CompositionTarget.Rendering -= OnRendering;
    void OnRendering(object? s, EventArgs e) {
        if (e is RenderingEventArgs r && r.RenderingTime == _last) return;
    }
}"""
        }
        with self.make_project(good_files) as tmp:
            res = auditor.run_audit(Path(tmp), ui_only=True)
            self.assertEqual(res["details"], [])

    def test_dwm_window_chrome_and_multimon_coords(self) -> None:
        bad_files = {
            "MainWindow.xaml": """<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    AllowsTransparency="True" WindowStyle="None">
  <WindowChrome.WindowChrome>
    <WindowChrome CaptionHeight="32" />
  </WindowChrome.WindowChrome>
</Window>""",
            "MainWindow.xaml.cs": """class MainWindow { }""",
            "Interop/DwmHelper.cs": """class DwmHelper {
    const int WM_NCHITTEST = 0x0084;
    const int HTMAXBUTTON = 9;
    int HitTest(long lParam) {
        int x = (int)(lParam & 0xFFFF);
        return x > 0 ? HTMAXBUTTON : WM_NCHITTEST;
    }
}""",
        }
        with self.make_project(bad_files) as tmp:
            res = auditor.run_audit(Path(tmp), ui_only=True)
            tags = [d["tag"] for d in res["details"]]
            self.assertIn("DWM", tags)
            self.assertEqual(tags.count("CHROME"), 2)
            self.assertIn("DPI/MULTI-MON", tags)

        good_files = {
            "MainWindow.xaml": """<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    WindowStyle="None">
  <WindowChrome.WindowChrome>
    <WindowChrome CaptionHeight="32" />
  </WindowChrome.WindowChrome>
  <Button WindowChrome.IsHitTestVisibleInChrome="True" Content="Close" />
</Window>""",
            "MainWindow.xaml.cs": """class MainWindow {
    const int WM_NCHITTEST = 0x0084;
    const int HTMAXBUTTON = 9;
    int HitTest(long lParam) {
        int x = (short)(lParam & 0xFFFF);
        return x > 0 ? HTMAXBUTTON : WM_NCHITTEST;
    }
}""",
        }
        with self.make_project(good_files) as tmp:
            res = auditor.run_audit(Path(tmp), ui_only=True)
            self.assertEqual(res["details"], [])

    def test_a11y_and_wpf_bugs(self) -> None:
        bad_files = {
            "MainWindow.xaml": """<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml">
  <StackPanel>
    <Button Content="&#xE710;" FocusVisualStyle="{x:Null}" />
    <Border MouseLeftButtonDown="OnBorderClick" />
    <TextBlock AutomationProperties.AccessibilityView="Raw" />
    <VisualStateManager.VisualStateGroups>
      <VisualStateGroup>
        <VisualState x:Name="Active">
          <VisualState.Setters />
        </VisualState>
      </VisualStateGroup>
    </VisualStateManager.VisualStateGroups>
  </StackPanel>
</Window>""",
            "MainWindow.xaml.cs": """class MainWindow {
    void Swap() { panel.Children[0] = child; }
}""",
        }
        with self.make_project(bad_files) as tmp:
            res = auditor.run_audit(Path(tmp), ui_only=True)
            tags = [d["tag"] for d in res["details"]]
            self.assertEqual(tags.count("A11Y"), 3, res["findings"])
            self.assertEqual(tags.count("WPF-BUG"), 3, res["findings"])

        # WinUI XAML must NOT trigger WPF-BUG on VisualState.Setters or AccessibilityView
        winui_xaml = """<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                    xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                    xmlns:muxc="using:Microsoft.UI.Xaml.Controls">
  <Grid>
    <TextBlock AutomationProperties.AccessibilityView="Raw" />
    <VisualStateManager.VisualStateGroups>
      <VisualStateGroup>
        <VisualState x:Name="Active">
          <VisualState.Setters />
        </VisualState>
      </VisualStateGroup>
    </VisualStateManager.VisualStateGroups>
  </Grid>
</Window>"""
        with self.make_project({"MainWindow.xaml": winui_xaml}) as tmp:
            res = auditor.run_audit(Path(tmp), ui_only=True)
            self.assertEqual(res["details"], [], res["findings"])


class TestLegacyCsprojManifestAndCsEngineering(TempProjectMixin, unittest.TestCase):
    def test_csproj_rules_and_central_package_management(self) -> None:
        bad_proj = {
            "Directory.Packages.props": """<Project>
  <ItemGroup>
    <PackageVersion Include="CommunityToolkit.Mvvm" Version="8.4.0" />
  </ItemGroup>
</Project>""",
            "MyApp.csproj": """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <UseWPF>true</UseWPF>
    <PublishAot>true</PublishAot>
    <PublishSingleFile>true</PublishSingleFile>
    <IncludeAllContentForSelfExtract>true</IncludeAllContentForSelfExtract>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="CommunityToolkit.Mvvm" />
  </ItemGroup>
</Project>""",
            "Interop.cs": """using System.Runtime.InteropServices;
using CommunityToolkit.Mvvm.ComponentModel;
partial class Vm {
    [ObservableProperty]
    public partial string Title { get; set; }
    [LibraryImport("user32.dll")]
    internal static partial int GetDpiForWindow(nint hwnd);
}""",
        }
        with self.make_project(bad_proj) as tmp:
            res = auditor.run_audit(Path(tmp))
            csproj_msgs = [d["message"] for d in res["details"] if d["tag"] == "CSPROJ"]
            self.assertTrue(any("NETSDK1168" in m for m in csproj_msgs), csproj_msgs)
            self.assertTrue(any("SYSLIB1062" in m for m in csproj_msgs), csproj_msgs)
            self.assertTrue(any("CS9248" in m for m in csproj_msgs), csproj_msgs)
            self.assertTrue(any("ApplicationManifest" in m for m in csproj_msgs), csproj_msgs)
            self.assertTrue(any("IncludeNativeLibrariesForSelfExtract" in m for m in csproj_msgs), csproj_msgs)
            self.assertTrue(any("IncludeAllContentForSelfExtract" in m for m in csproj_msgs), csproj_msgs)

        clean_proj = {
            "MyApp.csproj": CLEAN_WPF_CSPROJ,
            "app.manifest": CLEAN_MANIFEST,
            "Vm.cs": """using CommunityToolkit.Mvvm.ComponentModel;
partial class Vm {
    [ObservableProperty]
    public partial string Title { get; set; }
}""",
        }
        with self.make_project(clean_proj) as tmp:
            res = auditor.run_audit(Path(tmp))
            self.assertEqual(res["counts"]["error"], 0, res["findings"])
            self.assertEqual(res["counts"]["warn"], 0, res["findings"])
            # PublishReadyToRun has Condition so has_true sees "true" -> 0 INFOs too
            self.assertEqual(res["counts"]["info"], 0, res["findings"])

    def test_manifest_rules(self) -> None:
        bad_manifest = """<?xml version="1.0" encoding="utf-8"?>
<assembly manifestVersion="1.0" xmlns="urn:schemas-microsoft-com:asm.v1">
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v2">
    <security>
      <requestedPrivileges xmlns="urn:schemas-microsoft-com:asm.v3">
        <requestedExecutionLevel level="requireAdministrator" uiAccess="false" />
      </requestedPrivileges>
    </security>
  </trustInfo>
</assembly>"""
        with self.make_project({"app.manifest": bad_manifest}) as tmp:
            res = auditor.run_audit(Path(tmp))
            msgs = [d["message"] for d in res["details"] if d["tag"] == "MANIFEST"]
            self.assertEqual(len(msgs), 4, msgs)

        with self.make_project({"app.manifest": CLEAN_MANIFEST}) as tmp:
            res = auditor.run_audit(Path(tmp))
            self.assertEqual(res["details"], [])

    def test_legacy_cs_engineering_positive_and_negative(self) -> None:
        bad_cs = """using System;
using System.Net.Http;
using System.Security.Cryptography;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32;

class BadApp {
    [DllImport("user32.dll")] static extern bool RegisterHotKey(nint hWnd, int id, uint fsModifiers, uint vk);
    void Start() {
        var m = new Mutex(true, "SingleInstance");
        SystemEvents.PowerModeChanged += OnPower;
        using var client = new HttpClient();
        var enc = ProtectedData.Protect(new byte[4], null, DataProtectionScope.LocalMachine);
        string url = GetUrl();
        Process.Start(new ProcessStartInfo($"https://example.com/{url}") { UseShellExecute = true });
        RegisterHotKey(0, 1, 0, 0x41);
    }
    async void BadAsync() { await System.Threading.Tasks.Task.Delay(1); }
    void OnPower(object? s, PowerModeChangedEventArgs e) {}
    string GetUrl() => "a";
}"""
        with self.make_project({"BadApp.cs": bad_cs}) as tmp:
            res = auditor.run_audit(Path(tmp))
            tags = [d["tag"] for d in res["details"]]
            self.assertIn("LIFECYCLE", tags)
            self.assertIn("MEMORY-LEAK", tags)
            self.assertIn("PERF", tags)
            self.assertIn("SECURITY", tags)
            self.assertEqual(res["counts"]["error"], 1)  # DPAPI LocalMachine
            self.assertEqual(len(res["details"]), 7, res["findings"])

        safe_cs = """using System;
using System.Net.Http;
using System.Security.Cryptography;
using System.Diagnostics;
using System.Runtime.InteropServices;
using Microsoft.Win32;

class GoodApp {
    private static readonly HttpClient s_http = new HttpClient();
    [DllImport("user32.dll")] static extern bool RegisterHotKey(nint hWnd, int id, uint fsModifiers, uint vk);
    [DllImport("user32.dll")] static extern bool UnregisterHotKey(nint hWnd, int id);
    void Start() {
        var m = new Mutex(true, "SingleInstance");
        SystemEvents.PowerModeChanged += OnPower;
        var enc = ProtectedData.Protect(new byte[4], null, DataProtectionScope.CurrentUser);
        Process.Start(new ProcessStartInfo("https://example.com") { UseShellExecute = true });
        RegisterHotKey(0, 1, 0, 0x41);
        GC.KeepAlive(m);
    }
    void Stop() {
        SystemEvents.PowerModeChanged -= OnPower;
        UnregisterHotKey(0, 1);
    }
    async void OnClicked(object? sender, EventArgs e) { await System.Threading.Tasks.Task.CompletedTask; }
    protected override async void OnStartup(EventArgs e) { await System.Threading.Tasks.Task.CompletedTask; }
    void OnPower(object? s, PowerModeChangedEventArgs e) {}
}"""
        with self.make_project({"GoodApp.cs": safe_cs}) as tmp:
            res = auditor.run_audit(Path(tmp))
            self.assertEqual(res["details"], [], res["findings"])


class TestV2WebView2WinUI3SecurityAndCppRules(TempProjectMixin, unittest.TestCase):
    def test_webview2_rules_and_comment_string_safety(self) -> None:
        bad_cs = """class BrowserHost {
    async void OnInit(object s, System.EventArgs e) {
        await webView.EnsureCoreWebView2Async();
        webView.CoreWebView2.AddHostObjectToScript("bridge", new object());
        webView.CoreWebView2.Settings.AreDevToolsEnabled = true;
    }
}"""
        with self.make_project({"BrowserHost.cs": bad_cs}) as tmp:
            res = auditor.run_audit(Path(tmp))
            wv2 = [d for d in res["details"] if d["tag"] == "WEBVIEW2"]
            self.assertEqual(len(wv2), 3, wv2)
            self.assertEqual([d["severity"] for d in wv2], ["WARN", "INFO", "WARN"])

        # #else branch of #if DEBUG must STILL trigger
        else_cs = """class BrowserHost {
    void Config() {
#if DEBUG
        webView.CoreWebView2.Settings.AreDevToolsEnabled = true;
#else
        webView.CoreWebView2.Settings.AreDevToolsEnabled = true;
#endif
    }
}"""
        with self.make_project({"ElseHost.cs": else_cs}) as tmp:
            res = auditor.run_audit(Path(tmp))
            wv2 = [d for d in res["details"] if d["tag"] == "WEBVIEW2"]
            self.assertEqual(len(wv2), 1, wv2)
            self.assertEqual(wv2[0]["line"], 6)

        safe_files = {
            "SafeHost.xaml": """<UserControl xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                xmlns:wv2="clr-namespace:Microsoft.Web.WebView2.Wpf;assembly=Microsoft.Web.WebView2.Wpf">
  <wv2:WebView2>
    <wv2:WebView2.CreationProperties>
      <wv2:CoreWebView2CreationProperties UserDataFolder="%LocalAppData%\\MyApp\\WebView2" />
    </wv2:WebView2.CreationProperties>
  </wv2:WebView2>
</UserControl>""",
            "SafeHost.xaml.cs": """class SafeHost {
    async void OnLoaded(object s, System.EventArgs e) {
        // await webView.EnsureCoreWebView2Async();
        // webView.CoreWebView2.AddHostObjectToScript("x", this);
        // AreDevToolsEnabled = true;
        var doc = @"EnsureCoreWebView2Async() AddHostObjectToScript( AreDevToolsEnabled = true";
        var raw = \"\"\"
            EnsureCoreWebView2Async()
            AreDevToolsEnabled = true
        \"\"\";
        await webView.EnsureCoreWebView2Async();
        await webView2.EnsureCoreWebView2Async(env);
#if DEBUG
        webView.CoreWebView2.Settings.AreDevToolsEnabled = true;
#else
        webView.CoreWebView2.Settings.AreDevToolsEnabled = false;
#endif
    }
}""",
        }
        with self.make_project(safe_files) as tmp:
            res = auditor.run_audit(Path(tmp))
            self.assertEqual(res["details"], [], res["findings"])

    def test_winui3_window_current_and_unpackaged_appdata(self) -> None:
        bad_winui = {
            "App.csproj": """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net10.0-windows10.0.19041.0</TargetFramework>
    <UseWinUI>true</UseWinUI>
    <WindowsPackageType>None</WindowsPackageType>
    <ApplicationManifest>app.manifest</ApplicationManifest>
    <PublishReadyToRun>true</PublishReadyToRun>
  </PropertyGroup>
</Project>""",
            "app.manifest": CLEAN_MANIFEST,
            "MainPage.xaml.cs": """using Microsoft.UI.Xaml.Controls;
using Windows.Storage;
class MainPage {
    void Check() {
        var w = Window.Current;
        // Package.Current mentioned only in comment should NOT silence the guard!
        var folder = ApplicationData.Current.LocalFolder;
    }
}""",
        }
        with self.make_project(bad_winui) as tmp:
            res = auditor.run_audit(Path(tmp))
            winui = [d for d in res["details"] if d["tag"] == "WINUI3"]
            self.assertEqual(len(winui), 2, winui)
            self.assertEqual(winui[0]["severity"], "ERROR")
            self.assertEqual(winui[1]["severity"], "WARN")

        # Safe: UWP Windows.UI.Xaml, comments/strings, packaged project, or unpackaged WITH guard
        safe_winui = {
            "App.csproj": """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net10.0-windows10.0.19041.0</TargetFramework>
    <UseWinUI>true</UseWinUI>
    <WindowsPackageType>None</WindowsPackageType>
    <ApplicationManifest>app.manifest</ApplicationManifest>
    <PublishReadyToRun>true</PublishReadyToRun>
  </PropertyGroup>
</Project>""",
            "app.manifest": CLEAN_MANIFEST,
            "SafePage.xaml.cs": """using Microsoft.UI.Xaml.Controls;
using Windows.ApplicationModel;
using Windows.Storage;
class SafePage {
    void Check() {
        // Window.Current is null in WinUI 3
        var msg = "Window.Current and ApplicationData.Current";
        var app = Application.Current;
        if (IsPackaged()) {
            var folder = ApplicationData.Current.LocalFolder;
        }
    }
    bool IsPackaged() {
        try { return Package.Current != null; } catch { return false; }
    }
}""",
            "UwpLegacy.cs": """using Windows.UI.Xaml;
class UwpLegacy { object W() => Window.Current; }""",
        }
        with self.make_project(safe_winui) as tmp:
            res = auditor.run_audit(Path(tmp))
            self.assertEqual(res["details"], [], res["findings"])

    def test_security_pipes_tls_and_loadlibrary_cs(self) -> None:
        bad_sec = """using System;
using System.IO.Pipes;
using System.Net.Http;
using System.Runtime.InteropServices;

class InsecureService {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern IntPtr LoadLibraryW(string name);

    void Run() {
        using var pipe = new NamedPipeServerStream("my-pipe", PipeDirection.InOut);
        using var h1 = new HttpClientHandler {
            ServerCertificateCustomValidationCallback = (_, _, _, _) => true
        };
        using var h2 = new HttpClientHandler {
            ServerCertificateCustomValidationCallback = HttpClientHandler.DangerousAcceptAnyServerCertificateValidator
        };
        LoadLibraryW("plugin.dll");
    }
}"""
        with self.make_project({"InsecureService.cs": bad_sec}) as tmp:
            res = auditor.run_audit(Path(tmp))
            sec = [d for d in res["details"] if d["tag"] == "SECURITY"]
            self.assertEqual(len(sec), 5, sec)  # 1 pipe + 2 TLS + 2 LoadLibraryW (decl + call)
            tls_errors = [d for d in sec if d["severity"] == "ERROR"]
            self.assertEqual(len(tls_errors), 2)

        safe_sec = """using System;
using System.IO.Pipes;
using System.Net.Http;
using System.Net.Security;
using System.Runtime.InteropServices;

class SecureService {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    static extern IntPtr LoadLibraryExW(string name, IntPtr file, uint flags);
    const uint LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x00000800;

    void Run() {
        // new NamedPipeServerStream("comment-only");
        // ServerCertificateCustomValidationCallback = (_, _, _, _) => true;
        // LoadLibraryW("comment.dll");
        var text = "DangerousAcceptAnyServerCertificateValidator LoadLibraryA(\"x\")";
        using var pipe = new NamedPipeServerStream(
            "my-pipe",
            PipeDirection.InOut,
            1,
            PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous | PipeOptions.CurrentUserOnly);
        var ps = new PipeSecurity();
        using var pipe2 = new NamedPipeServerStream("p2", PipeDirection.InOut, 1, PipeTransmissionMode.Byte, PipeOptions.None, 0, 0, ps);
        using var handler = new HttpClientHandler {
            ServerCertificateCustomValidationCallback = (_, _, _, errors) => errors == SslPolicyErrors.None
        };
#if DEBUG
        using var devHandler = new HttpClientHandler {
            ServerCertificateCustomValidationCallback = HttpClientHandler.DangerousAcceptAnyServerCertificateValidator
        };
#endif
        LoadLibraryExW("user32.dll", IntPtr.Zero, LOAD_LIBRARY_SEARCH_SYSTEM32);
    }
}"""
        with self.make_project({"SecureService.cs": safe_sec}) as tmp:
            res = auditor.run_audit(Path(tmp))
            self.assertEqual(res["details"], [], res["findings"])

    def test_cpp_and_cppwinrt_rules(self) -> None:
        bad_cpp = """#include <windows.h>

namespace App::Views {
winrt::fire_and_forget MainWindow::OnLoadClicked(IInspectable const&, RoutedEventArgs const&)
{
    // get_weak() in a comment must NOT suppress the warning!
    int delay_ms = 1'000;
    co_await winrt::resume_background();
    this->Title(L"Done");
}

auto MainWindow::TrailingAsync() -> winrt::Windows::Foundation::IAsyncAction
{
    co_await winrt::resume_background();
}
}

void InitNative(HWND hwnd, RECT* rc) {
    HMODULE m = LoadLibraryW(L"helper.dll");
    HMODULE m2 = LoadLibraryA("helper2.dll");
    AdjustWindowRect(rc, WS_OVERLAPPEDWINDOW, FALSE);
}
"""
        safe_cpp = """#include <windows.h>

// co_await inside MainWindow::Commented() without get_weak()
winrt::Windows::Foundation::IAsyncAction FreeHelperAsync() {
    co_await winrt::resume_background();
}

auto DecltypeFreeFunc() -> decltype(Helper::Value()) {
    co_await winrt::resume_background();
}

struct ComObj { void LoadLibrary(const wchar_t*); };
void CallMethod(ComObj& o) { o.LoadLibrary(L"safe"); }

winrt::fire_and_forget MainWindow::SafeWeakAsync()
{
    auto weak = get_weak();
    co_await winrt::resume_background();
    if (auto strong = weak.get()) {
        strong->Title(L"Safe");
    }
}

winrt::Windows::Foundation::IAsyncAction MainWindow::SafeStrongAsync()
{
    auto strong = get_strong();
    auto s = R"(co_await LoadLibraryW("a") AdjustWindowRect(&r, 0, FALSE))";
    int timeout = 1'000'000;
    co_await winrt::resume_background();
}

void SafeNative(RECT* rc, UINT dpi) {
    HMODULE m = LoadLibraryExW(L"uxtheme.dll", nullptr, LOAD_LIBRARY_SEARCH_SYSTEM32);
    AdjustWindowRectExForDpi(rc, WS_OVERLAPPEDWINDOW, FALSE, 0, dpi);
}
"""
        with self.make_project({"src/bad.cpp": bad_cpp, "include/safe.hpp": safe_cpp}) as tmp:
            res = auditor.run_audit(Path(tmp))
            self.assertEqual(res["cpp_files"], 2)
            tags = [d["tag"] for d in res["details"]]
            self.assertEqual(tags.count("CPP-LIFETIME"), 2, res["findings"])
            self.assertEqual(tags.count("SECURITY"), 2, res["findings"])
            self.assertEqual(tags.count("DPI"), 1, res["findings"])
            # Ensure zero findings came from include/safe.hpp
            files = {d["file"] for d in res["details"]}
            self.assertEqual(files, {"src/bad.cpp"})


class TestCliSarifAndWrapper(TempProjectMixin, unittest.TestCase):
    def test_json_schema_ui_only_and_strict_exit_codes(self) -> None:
        files = {
            "App.csproj": """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <UseWPF>true</UseWPF>
    <ApplicationManifest>app.manifest</ApplicationManifest>
  </PropertyGroup>
</Project>""",
            "app.manifest": """<?xml version="1.0" encoding="utf-8"?>
<assembly manifestVersion="1.0" xmlns="urn:schemas-microsoft-com:asm.v1">
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application><supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}" /></application>
  </compatibility>
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2</dpiAwareness>
    </windowsSettings>
  </application>
</assembly>""",
            "Host.cs": 'class Host { void Wire() { webView.CoreWebView2.AddHostObjectToScript("h", this); } }',
            "src/main.cpp": "void f() { AdjustWindowRect(nullptr, 0, 0); }",
        }
        with self.make_project(files) as tmp:
            # 1. --json includes all schema keys + cpp_files
            code, out, _ = self.run_cli(auditor.main, [tmp, "--json"])
            self.assertEqual(code, 0)
            payload = json.loads(out)
            for key in (
                "root",
                "mode",
                "xaml_files",
                "cs_files",
                "cpp_files",
                "csproj_files",
                "manifest_files",
                "counts",
                "findings",
                "details",
            ):
                self.assertIn(key, payload)
            self.assertEqual(payload["cpp_files"], 1)

            # 2. --strict fails because src/main.cpp emits WARN
            code_strict, _, _ = self.run_cli(auditor.main, [tmp, "--strict"])
            self.assertEqual(code_strict, 1)

            # 3. --ui-only excludes cpp/csproj/manifest/engineering findings -> 0 findings -> --strict exits 0
            code_ui, out_ui, _ = self.run_cli(auditor.main, [tmp, "--ui-only", "--strict", "--json"])
            self.assertEqual(code_ui, 0)
            ui_payload = json.loads(out_ui)
            self.assertEqual(ui_payload["mode"], "ui-only")
            self.assertEqual(ui_payload["cpp_files"], 0)
            self.assertEqual(ui_payload["findings"], [])

        # INFO-only project must pass --strict with exit 0
        info_only_files = {
            "App.csproj": files["App.csproj"],
            "app.manifest": files["app.manifest"],
            "Host.cs": files["Host.cs"],
        }
        with self.make_project(info_only_files) as tmp:
            code_info, out_info, _ = self.run_cli(auditor.main, [tmp, "--strict", "--json"])
            self.assertEqual(code_info, 0)
            info_payload = json.loads(out_info)
            self.assertEqual(info_payload["counts"], {"error": 0, "warn": 0, "info": 3})

    def test_sarif_output_schema_levels_locations_and_mutual_exclusion(self) -> None:
        files = {
            "Themes/Tokens.xaml": """<ResourceDictionary xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
                xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
                xmlns:po="http://schemas.microsoft.com/winfx/2006/xaml/presentation/options">
  <SolidColorBrush x:Key="Surface0Brush" Color="#FFFFFF" po:Freeze="True" />
  <SolidColorBrush x:Key="TextSecondaryBrush" Color="#CCCCCC" po:Freeze="True" />
</ResourceDictionary>""",
            "MyApp.csproj": """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <UseWPF>true</UseWPF>
    <PublishAot>true</PublishAot>
    <ApplicationManifest>app.manifest</ApplicationManifest>
  </PropertyGroup>
</Project>""",
            "app.manifest": CLEAN_MANIFEST,
            "Host.cs": 'class Host { void Wire() { webView.CoreWebView2.AddHostObjectToScript("h", this); } }',
            "src/win.cpp": "void f() { LoadLibraryA(\"a.dll\"); }",
        }
        with self.make_project(files) as tmp:
            # --json and --sarif must be mutually exclusive
            code_excl, _, _ = self.run_cli(auditor.main, [tmp, "--json", "--sarif"])
            self.assertEqual(code_excl, 2)

            code, out, _ = self.run_cli(auditor.main, [tmp, "--sarif", "--strict"])
            self.assertEqual(code, 1)
            sarif = json.loads(out)

            self.assertEqual(sarif["$schema"], "https://json.schemastore.org/sarif-2.1.0.json")
            self.assertEqual(sarif["version"], "2.1.0")
            self.assertEqual(len(sarif["runs"]), 1)

            driver = sarif["runs"][0]["tool"]["driver"]
            self.assertEqual(driver["name"], "windows-native-auditor")
            rule_ids = {r["id"] for r in driver["rules"]}
            for required_id in (
                "WN-CSPROJ-001",
                "WN-MANIFEST-001",
                "WN-WPF-001",
                "WN-WINUI-001",
                "WN-WV2-001",
                "WN-SEC-001",
                "WN-LIFE-001",
                "WN-CPP-001",
                "WN-A11Y-001",
                "WN-PERF-001",
                "WN-CONTRAST-001",
                "WN-UI-001",
            ):
                self.assertIn(required_id, rule_ids)

            results = sarif["runs"][0]["results"]
            self.assertEqual(len(results), 4)
            levels = {r["level"] for r in results}
            self.assertEqual(levels, {"error", "warning", "note"})
            for r in results:
                self.assertIn(r["ruleId"], rule_ids)
                self.assertEqual(driver["rules"][r["ruleIndex"]]["id"], r["ruleId"])
                loc = r["locations"][0]["physicalLocation"]
                uri = loc["artifactLocation"]["uri"]
                self.assertNotIn("\\", uri)
                self.assertGreaterEqual(loc["region"]["startLine"], 1)

            contrast_res = next(r for r in results if r["ruleId"] == "WN-CONTRAST-001")
            self.assertEqual(contrast_res["locations"][0]["physicalLocation"]["artifactLocation"]["uri"], "Themes/Tokens.xaml")
            self.assertEqual(contrast_res["locations"][0]["physicalLocation"]["region"]["startLine"], 5)

        # Missing directory returns exit code 2
        code_missing, _, _ = self.run_cli(auditor.main, [str(Path(tmp) / "does_not_exist")])
        self.assertEqual(code_missing, 2)

    def test_set_default_dll_directories_suppresses_cs_loadlibrary(self) -> None:
        safe_cs = """using System;
using System.Runtime.InteropServices;
class DllHost {
    [DllImport("kernel32.dll")] static extern bool SetDefaultDllDirectories(uint flags);
    [DllImport("kernel32.dll")] static extern IntPtr LoadLibraryW(string path);
    void Init() {
        SetDefaultDllDirectories(0x00000800);
        LoadLibraryW("native.dll");
    }
}"""
        with self.make_project({"DllHost.cs": safe_cs}) as tmp:
            res = auditor.run_audit(Path(tmp))
            self.assertEqual(res["details"], [])

    def test_audit_wpf_ui_wrapper_cli(self) -> None:
        files = {
            "Views/Bad.xaml": """<UserControl xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
  <Button Content="&#xE710;" />
</UserControl>""",
            "src/win.cpp": "void f() { AdjustWindowRect(nullptr, 0, 0); }",
        }
        with self.make_project(files) as tmp:
            code_excl, _, _ = self.run_cli(ui_wrapper.main, [tmp, "--json", "--sarif"])
            self.assertEqual(code_excl, 2)

            code_json, out_json, _ = self.run_cli(ui_wrapper.main, [tmp, "--json", "--strict"])
            self.assertEqual(code_json, 1)
            payload = json.loads(out_json)
            self.assertEqual(set(payload.keys()), {"root", "xaml_files", "cs_files", "findings"})
            self.assertEqual(len(payload["findings"]), 1)

            code_sarif, out_sarif, _ = self.run_cli(ui_wrapper.main, [tmp, "--sarif"])
            self.assertEqual(code_sarif, 0)
            sarif = json.loads(out_sarif)
            self.assertEqual(sarif["version"], "2.1.0")
            self.assertEqual(len(sarif["runs"][0]["results"]), 1)
            self.assertEqual(sarif["runs"][0]["results"][0]["ruleId"], "WN-A11Y-001")
            self.assertEqual(
                sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"],
                "Views/Bad.xaml",
            )

    def test_if_debug_nesting_packaged_appdata_and_sarif_catalog_integrity(self) -> None:
        cs = """class GuardCases {
    void Run() {
#if WINDOWS
#if DEBUG
        webView.CoreWebView2.Settings.AreDevToolsEnabled = true;
        handler.ServerCertificateCustomValidationCallback = (_, _, _, _) => true;
#endif
#endif
#if !DEBUG
        webView.CoreWebView2.Settings.AreDevToolsEnabled = true;
#endif
    }
}"""
        with self.make_project({"GuardCases.cs": cs}) as tmp:
            res = auditor.run_audit(Path(tmp))
            self.assertEqual(len(res["details"]), 1, res["findings"])
            self.assertEqual(res["details"][0]["line"], 10)
            self.assertEqual(res["details"][0]["tag"], "WEBVIEW2")

        # Packaged WinUI 3 project (no WindowsPackageType=None) allows ApplicationData.Current cleanly
        packaged_winui = {
            "App.csproj": """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net10.0-windows10.0.19041.0</TargetFramework>
    <UseWinUI>true</UseWinUI>
    <ApplicationManifest>app.manifest</ApplicationManifest>
    <PublishReadyToRun>true</PublishReadyToRun>
  </PropertyGroup>
</Project>""",
            "app.manifest": CLEAN_MANIFEST,
            "Settings.cs": """using Windows.Storage;
class Settings { object Folder() => ApplicationData.Current.LocalFolder; }""",
        }
        with self.make_project(packaged_winui) as tmp:
            res = auditor.run_audit(Path(tmp))
            self.assertEqual(res["details"], [], res["findings"])

        # Validate every rule in SARIF_RULES catalog has required fields and unique IDs
        ids = [r["id"] for r in auditor.SARIF_RULES]
        self.assertEqual(len(ids), len(set(ids)))
        for rule in auditor.SARIF_RULES:
            self.assertIn(rule["defaultConfiguration"]["level"], ("error", "warning", "note"))
            self.assertTrue(rule["shortDescription"]["text"])


if __name__ == "__main__":
    unittest.main()
