# WPF UI Architecture, Performance, Accessibility & Testing (.NET 9/10)

> **Scope:** Scalable XAML token architecture, `ControlTemplate`/`Generic.xaml`, `CommunityToolkit.Mvvm` 8.4 (C# 14), streaming/Markdown performance, UI virtualization, UI Automation accessibility, smart chat UX, localization, and `FlaUI.UIA3` testing.

## Table of Contents

1. [Layered XAML Design System & Resource Hygiene](#1-layered-xaml-design-system--resource-hygiene)
2. [Custom Controls, Procedural UI & Attached Behaviors (Compile-Verified)](#2-custom-controls-procedural-ui--attached-behaviors-compile-verified)
3. [MVVM with CommunityToolkit.Mvvm 8.4 & DI](#3-mvvm-with-communitytoolkitmvvm-84--di)
4. [WPF Performance Engineering (Virtualization, Text, Streaming, Leaks)](#4-wpf-performance-engineering-virtualization-text-streaming-leaks)
5. [Accessibility (UI Automation, Keyboard, Live Regions, High Contrast)](#5-accessibility-ui-automation-keyboard-live-regions-high-contrast)
6. [Chat & Streaming UI Patterns, Localization & Automated Testing](#6-chat--streaming-ui-patterns-localization--automated-testing)

---

## 1. Layered XAML Design System & Resource Hygiene

### 1.1 ResourceDictionary Architecture

Separate primitive tokens from semantic brushes, metrics, typography, styles, and templates (mirroring `PresentationFramework.Fluent`):

```text
Resources/
├── Tokens/
│   ├── Colors.Light.xaml         # Raw & theme-specific Color tokens (Light)
│   ├── Colors.Dark.xaml          # Raw & theme-specific Color tokens (Dark)
│   ├── Brushes.xaml              # Semantic SolidColorBrush aliases + po:Freeze="True" when static
│   ├── Brushes.HighContrast.xaml # SystemColors.*BrushKey overrides
│   ├── Typography.xaml           # FontFamily chains, FontSizes, TextBlock ramp styles
│   └── Metrics.xaml              # CornerRadius, Thickness, Double spacing/height tokens
├── Styles/
│   ├── FocusVisuals.xaml         # High-contrast dual-stroke FocusVisualStyle
│   ├── Buttons.xaml              # DefaultButtonStyle, PrimaryButtonStyle, IconButtonStyle
│   ├── Inputs.xaml               # TextBox, ComboBox, CheckBox, RadioButton, Slider, ScrollBar
│   └── Cards.xaml                # Card, Pill, SettingsCard, ToolCard
└── Templates/
    └── DataTemplates.xaml        # ViewModel-first DataTemplates & selectors
```

- **Merge Order in `App.xaml`:** Lookup searches the local dictionary first, then `MergedDictionaries` **in reverse order (last wins)**. Put `Colors.*.xaml` at index `0`, then `Brushes.xaml`, `Metrics.xaml`, `Typography.xaml`, `FocusVisuals.xaml`, control styles, and `DataTemplates.xaml`.
- **Naming Conventions:**
  - Colors: `<Role><Variant>Color` (`SurfaceCardColor`, `TextSecondaryColor`)
  - Brushes: `<Role><Variant>Brush` (`SurfaceCardBrush`, `StatusDangerBrush`)
  - Variants: `Default<Control>Style` + `<Variant><Control>Style` (`AccentButtonStyle`, `IconButtonStyle`)
  - Template parts: `PART_<Role>` (`PART_ContentHost`, `PART_ExpandButton`)

### 1.2 `StaticResource` vs. `DynamicResource` & Freezing Rules

| Criterion | `StaticResource` | `DynamicResource` |
|---|---|---|
| **When evaluated** | XAML load time (no forward refs) | Runtime deferred expression |
| **Runtime overhead** | Minimal; supports DP effective-value caching | Holds expression listener per target |
| **`po:Freeze="True"`** | **Compatible** (`212 B` vs `972 B` for 10 users of a brush) | **Cannot** freeze a `SolidColorBrush` whose `Color="{DynamicResource ...}"` |
| **Use for** | `Thickness`, `CornerRadius`, `FontSize` (unless live text-scaled), geometries, `BasedOn` style refs | Theme-swappable `*Brush` resources, `SystemColors.*Key`, `FocusVisualStyle`, cross-scope lookup |

- **Best Pattern for Runtime-Swappable Theme Brushes:** Put frozen `<SolidColorBrush po:Freeze="True" Color="#..." />` directly inside each theme dictionary (`Brushes.Light.xaml` / `Brushes.Dark.xaml`), reference them via `{DynamicResource ...}`, and swap ONLY that dictionary index at runtime (never call `MergedDictionaries.Clear()`, which forces re-parsing every control template!).
- **Avoid `UserControl.Resources` brush duplication:** Declaring brushes inside a repeating `UserControl` or `DataTemplate` multiplies instances `N × M` across cards. Hoist shared brushes/styles to `App.xaml` or `Themes/Generic.xaml`.
- **`BasedOn` rule:** Always chain `BasedOn="{StaticResource ...}"` (`BasedOn="{DynamicResource ...}"` throws a XAML parse error!).

---

## 2. Custom Controls, Procedural UI & Attached Behaviors (Compile-Verified)

### 2.1 Choosing the Right Authoring Model

| Need | Best Type | Why |
|---|---|---|
| Screen, form, modal | `UserControl` | Fast XAML layout + Hot Reload + MVVM binding |
| Reusable design-system widget (`ToolCard`, `SettingsCard`) | Custom `Control` (`DefaultStyleKey` + `Themes/Generic.xaml`) | Full `ControlTemplate`, `VisualStateManager`, `AutomationPeer` support |
| 60 FPS audio orb / waveform / spectrum | `FrameworkElement` (`OnRender` / `DrawingVisual`) | Zero visual child tree overhead; pure frozen-brush `DrawingContext` |
| Dynamic AST output (Markdig Markdown blocks) | Procedural C# builder | Variable-depth headings/lists/tables/code blocks without `DataTemplate` bloat |

### 2.2 Mandatory Rules for Procedural C# UI Builders

1. **Build trees TOP-DOWN (never bottom-up):** Attach parent containers before inserting nested children, or assemble inside an unattached root before mounting once. Microsoft benchmark (150-level tree): bottom-up = **366 ms**, top-down = **11 ms** (**33× faster**).
2. **Reuse frozen theme resources:** Never allocate `new SolidColorBrush(Color.FromRgb(...))` inside card factories or render loops. Fetch cached frozen brushes or freeze static fields once.
3. **Never write `panel.Children[i] = newChild`:** `UIElementCollection` throws when replacing an occupied slot! Always use `RemoveAt(i); Insert(i, newChild);` — or bind an `ItemsControl`/`ListBox` to an `ObservableObject` so in-place property updates avoid tearing down containers altogether.
4. **Keep `ControlTemplate` contracts safe:** Decorate custom controls with `[TemplatePart]` and `[TemplateVisualState]`, null-check `GetTemplateChild(...) as T`, include `RecognizesAccessKey="True"` on `<ContentPresenter>`, and unsubscribe old template part events in `OnApplyTemplate()`.

### 2.3 `ToolCard` Custom Control + `AutomationPeer` + `AutoScrollBehavior`

```csharp
using System.Collections.Specialized;
using System.Windows;
using System.Windows.Automation;
using System.Windows.Automation.Peers;
using System.Windows.Automation.Provider;
using System.Windows.Controls;
using System.Windows.Controls.Primitives;
using System.Windows.Input;
using System.Windows.Media;

// Requires [assembly: ThemeInfo(ResourceDictionaryLocation.None, ResourceDictionaryLocation.SourceAssembly)]
public enum ToolExecutionState { Pending, Running, Succeeded, Failed }

[TemplatePart(Name = PartCopyButton, Type = typeof(ButtonBase))]
[TemplateVisualState(Name = "Normal", GroupName = "CommonStates")]
[TemplateVisualState(Name = "MouseOver", GroupName = "CommonStates")]
[TemplateVisualState(Name = "Disabled", GroupName = "CommonStates")]
[TemplateVisualState(Name = "Focused", GroupName = "FocusStates")]
[TemplateVisualState(Name = "Unfocused", GroupName = "FocusStates")]
[TemplateVisualState(Name = "Pending", GroupName = "ExecutionStates")]
[TemplateVisualState(Name = "Running", GroupName = "ExecutionStates")]
[TemplateVisualState(Name = "Succeeded", GroupName = "ExecutionStates")]
[TemplateVisualState(Name = "Failed", GroupName = "ExecutionStates")]
public class ToolCard : ContentControl
{
    public const string PartCopyButton = "PART_CopyButton";
    private ButtonBase? _copyButton;

    static ToolCard() =>
        DefaultStyleKeyProperty.OverrideMetadata(typeof(ToolCard), new FrameworkPropertyMetadata(typeof(ToolCard)));

    public ToolCard() => IsEnabledChanged += (_, _) => UpdateVisualStates(true);

    public static readonly DependencyProperty ToolNameProperty =
        DependencyProperty.Register(nameof(ToolName), typeof(string), typeof(ToolCard), new PropertyMetadata(string.Empty));
    public static readonly DependencyProperty ExecutionStateProperty =
        DependencyProperty.Register(nameof(ExecutionState), typeof(ToolExecutionState), typeof(ToolCard),
            new PropertyMetadata(ToolExecutionState.Pending, (d, _) => ((ToolCard)d).UpdateVisualStates(true)));
    public static readonly RoutedEvent CopyRequestedEvent =
        EventManager.RegisterRoutedEvent(nameof(CopyRequested), RoutingStrategy.Bubble, typeof(RoutedEventHandler), typeof(ToolCard));

    public string ToolName { get => (string)GetValue(ToolNameProperty); set => SetValue(ToolNameProperty, value); }
    public ToolExecutionState ExecutionState { get => (ToolExecutionState)GetValue(ExecutionStateProperty); set => SetValue(ExecutionStateProperty, value); }
    public event RoutedEventHandler CopyRequested { add => AddHandler(CopyRequestedEvent, value); remove => RemoveHandler(CopyRequestedEvent, value); }

    public override void OnApplyTemplate()
    {
        if (_copyButton is not null) _copyButton.Click -= OnCopyButtonClick;
        base.OnApplyTemplate();
        _copyButton = GetTemplateChild(PartCopyButton) as ButtonBase;
        if (_copyButton is not null) _copyButton.Click += OnCopyButtonClick;
        UpdateVisualStates(false);
    }

    protected override AutomationPeer OnCreateAutomationPeer() => new ToolCardAutomationPeer(this);
    protected override void OnMouseEnter(MouseEventArgs e) { base.OnMouseEnter(e); UpdateVisualStates(true); }
    protected override void OnMouseLeave(MouseEventArgs e) { base.OnMouseLeave(e); UpdateVisualStates(true); }
    protected override void OnGotKeyboardFocus(KeyboardFocusChangedEventArgs e) { base.OnGotKeyboardFocus(e); UpdateVisualStates(true); }
    protected override void OnLostKeyboardFocus(KeyboardFocusChangedEventArgs e) { base.OnLostKeyboardFocus(e); UpdateVisualStates(true); }
    private void OnCopyButtonClick(object sender, RoutedEventArgs e) => RaiseEvent(new RoutedEventArgs(CopyRequestedEvent, this));

    private void UpdateVisualStates(bool useTransitions)
    {
        VisualStateManager.GoToState(this, !IsEnabled ? "Disabled" : IsMouseOver ? "MouseOver" : "Normal", useTransitions);
        VisualStateManager.GoToState(this, IsKeyboardFocusWithin ? "Focused" : "Unfocused", useTransitions);
        VisualStateManager.GoToState(this, ExecutionState.ToString(), useTransitions);
    }
}

public sealed class ToolCardAutomationPeer : FrameworkElementAutomationPeer, IInvokeProvider
{
    public ToolCardAutomationPeer(ToolCard owner) : base(owner) { }
    protected override string GetClassNameCore() => nameof(ToolCard);
    protected override AutomationControlType GetAutomationControlTypeCore() => AutomationControlType.Group;
    protected override string GetNameCore()
    {
        string baseName = base.GetNameCore();
        if (!string.IsNullOrWhiteSpace(baseName)) return baseName;
        var card = (ToolCard)Owner;
        return $"{card.ToolName}, {card.ExecutionState}";
    }
    public override object? GetPattern(PatternInterface patternInterface) =>
        patternInterface == PatternInterface.Invoke ? this : base.GetPattern(patternInterface);
    void IInvokeProvider.Invoke() { if (!IsEnabled()) throw new ElementNotEnabledException(); }
}

public static class AutoScrollBehavior
{
    public static readonly DependencyProperty AutoScrollToEndProperty =
        DependencyProperty.RegisterAttached("AutoScrollToEnd", typeof(bool), typeof(AutoScrollBehavior),
            new PropertyMetadata(false, (d, e) => { if (d is ItemsControl ic) { if ((bool)e.NewValue) ic.Loaded += OnLoaded; else ic.Loaded -= OnLoaded; } }));
    public static bool GetAutoScrollToEnd(DependencyObject obj) => (bool)obj.GetValue(AutoScrollToEndProperty);
    public static void SetAutoScrollToEnd(DependencyObject obj, bool value) => obj.SetValue(AutoScrollToEndProperty, value);

    private static void OnLoaded(object sender, RoutedEventArgs e)
    {
        var ic = (ItemsControl)sender;
        var sv = FindDescendant<ScrollViewer>(ic);
        if (sv is null || ic.ItemsSource is not INotifyCollectionChanged ncc) return;
        bool stick = true;
        void OnScrollChanged(object s, ScrollChangedEventArgs a) { if (a.ExtentHeightChange == 0) stick = sv.VerticalOffset >= sv.ScrollableHeight - 24; else if (stick) sv.ScrollToEnd(); }
        void OnCollChanged(object? s, NotifyCollectionChangedEventArgs a) { if (stick && a.Action == NotifyCollectionChangedAction.Add) sv.ScrollToEnd(); }
        void OnUnloaded(object s, RoutedEventArgs a) { sv.ScrollChanged -= OnScrollChanged; ncc.CollectionChanged -= OnCollChanged; ic.Unloaded -= OnUnloaded; }
        sv.ScrollChanged += OnScrollChanged; ncc.CollectionChanged += OnCollChanged; ic.Unloaded += OnUnloaded;
    }

    private static T? FindDescendant<T>(DependencyObject r) where T : DependencyObject
    {
        for (int i = 0; i < VisualTreeHelper.GetChildrenCount(r); i++)
        {
            var c = VisualTreeHelper.GetChild(r, i);
            if (c is T m) return m;
            if (FindDescendant<T>(c) is T n) return n;
        }
        return null;
    }
}
```

---

## 3. MVVM with `CommunityToolkit.Mvvm` 8.4 & DI

### 3.1 Modern `.NET 10` (C# 14) Source Generators

- **`partial` properties vs. backing fields (Verified on `.NET 10.0.302`):**
  - **`CommunityToolkit.Mvvm >= 8.4.2`** compiles `[ObservableProperty] public partial string PromptText { get; set; } = string.Empty;` natively on default `.NET 10` (`C# 14`).
  - **`CommunityToolkit.Mvvm 8.4.0`** fails with **`CS9248`** on `partial` properties unless `<LangVersion>preview</LangVersion>` is set in `.csproj` — otherwise use `[ObservableProperty] private string _promptText = string.Empty;`.
- **Async `[RelayCommand]` flags:**
  - `AllowConcurrentExecutions = false` (default) prevents double-submit while running.
  - `AllowConcurrentExecutions = true` + `CancellationToken ct` auto-cancels the prior run on re-invoke (ideal for live search-as-you-type!).
  - `IncludeCancelCommand = true` generates `<Name>CancelCommand` wired to the running token.
  - `FlowExceptionsToTaskScheduler = false` (default) awaits on UI `SynchronizationContext`; wrap I/O in `try/catch` and preserve draft input on error/cancel!
- **Note on `CanExecute`:** `IRelayCommand` does **not** poll `CommandManager.RequerySuggested`. Always pair `[NotifyCanExecuteChangedFor(nameof(MyCommand))]` on state properties that gate `CanExecute`.

### 3.2 Messaging, Host DI & Background Collections

- **Messengers:** Default to `WeakReferenceMessenger` (or `ObservableRecipient` toggling `IsActive = true/false` on view swap). If using `StrongReferenceMessenger`, always call `UnregisterAll(this)` on teardown; pass `(r, m) => r.Handle(m)` so lambdas don't capture `this`.
- **Generic Host Startup & Culture Fix:** Remove `StartupUri` from `App.xaml`. Build `Host.CreateApplicationBuilder` in `OnStartup`, register singletons/VMs/windows, and **override WPF's `en-US` `XmlLanguage` default** at startup so `StringFormat` and dates honor the user's current culture (e.g. `pt-BR`, `de-DE`, etc.):
  ```csharp
  FrameworkElement.LanguageProperty.OverrideMetadata(
      typeof(FrameworkElement),
      new FrameworkPropertyMetadata(XmlLanguage.GetLanguage(CultureInfo.CurrentCulture.IetfLanguageTag)));
  ```
- **ViewModel-First Navigation:** Bind `<ContentControl Content="{Binding CurrentViewModel}" />` (or `TransitioningContentControl`) and map ViewModels -> Views via implicit `<DataTemplate DataType="{x:Type vm:ChatViewModel}">` in `App.xaml`. Avoid `Frame`/`NavigationWindow` journaling memory traps.
- **Updating Collections Safely:**
  - *Moderate rate:* Call `BindingOperations.EnableCollectionSynchronization(Collection, _lock)` **on the UI thread in the constructor**, then acquire `lock (_lock)` around every read/write on all threads.
  - *High-frequency WebSocket token streaming:* **Never** mutate UI trees or `CollectionChanged` 100+ times/sec! Buffer tokens in a `Channel<T>` / `StringBuilder` behind a lock and flush to an `ObservableObject` message property on a **`33–50 ms` timer (`20–30 Hz`)** at `DispatcherPriority.Background`.

---

## 4. WPF Performance Engineering (Virtualization, Text, Streaming, Leaks)

### 4.1 UI Virtualization Rules (70× Benchmark Speedup)

Microsoft 5,000-item benchmark: `StackPanel` = **3,210 ms** vs. `VirtualizingStackPanel` = **46 ms**.

```xml
<ListBox ItemsSource="{Binding Messages}"
         VirtualizingPanel.IsVirtualizing="True"
         VirtualizingPanel.VirtualizationMode="Recycling"
         VirtualizingPanel.ScrollUnit="Pixel"
         VirtualizingPanel.CacheLength="1,1"
         VirtualizingPanel.CacheLengthUnit="Page"
         VirtualizingPanel.IsVirtualizingWhenGrouping="True"
         ScrollViewer.CanContentScroll="True"
         ScrollViewer.HorizontalScrollBarVisibility="Disabled">
```

**Five things that silently KILL virtualization:**
1. Wrapping `<ItemsControl>` / `<ListBox>` inside an outer `<ScrollViewer>` (gives infinite measure height -> realizes 100% of rows!).
2. Setting `ScrollViewer.CanContentScroll="False"` (use `CanContentScroll="True"` + `VirtualizingPanel.ScrollUnit="Pixel"` for smooth pixel scrolling *with* virtualization).
3. Grouping a `CollectionView` without `VirtualizingPanel.IsVirtualizingWhenGrouping="True"`.
4. Adding raw `ListBoxItem` objects manually instead of binding `ItemsSource` to data items.
5. Storing UI state on container controls under `VirtualizationMode="Recycling"` — bind expand/selection state TwoWay to the item ViewModel instead!

### 4.2 Text, Markdown & Images

- **`TextBlock.Text` vs. `Label.Content`:** Updating a string 1,000× takes **242 ms** (`TextBlock`) vs. **835 ms** (`Label`). Never use `Label` for streaming/dynamic text.
- **Avoid `<Run>` spam & `FlowDocument` per chat bubble:**
  - Inside virtualized chat lists, parse **Markdig** AST directly into lightweight `TextBlock`s (`Inlines` for bold/code/links), `Grid` tables, and `Border` + read-only `TextBox` code blocks (giving copyable text without `FlowDocument` pagination/reflow cost per bubble!).
  - Reserve `FlowDocumentScrollViewer` for single standalone report/reader panes outside virtualized lists.
  - Consolidate onto **one** `Markdig` pipeline instead of maintaining duplicate regex parsers across views.
- **Images (`BitmapImage`):** Always set `DecodePixelWidth` (matches thumbnail/avatar display width!), `CacheOption = BitmapCacheOption.OnLoad` (releases file lock immediately), and `.Freeze()` inside `BeginInit()`/`EndInit()`.
- **Startup & Deployment (`.NET 9/10`):**
  - Enable `<PublishReadyToRun>true</PublishReadyToRun>` to eliminate cold-start JIT stalls.
  - **NEVER enable `PublishTrimmed` on WPF** — unsupported (`NETSDK1168`); reflection in XAML/bindings/templates breaks at runtime.
  - Declare `[assembly: NeutralResourcesLanguage("en-US")]` (or your neutral culture) to skip satellite probing at startup.

### 4.3 Top 7 WPF Memory Leaks & Diagnostics

1. Strong event subscriptions (`SystemEvents`, singletons, `DataContextChanged`) without `-=`.
2. `DependencyPropertyDescriptor.AddValueChanged` without `RemoveValueChanged` (stored in static table!).
3. Unfrozen `Freezable`s assigned to shared `Fill`/`Background` properties.
4. Running `DispatcherTimer` instances not stopped on `Unloaded`.
5. `CompositionTarget.Rendering` attached while `Collapsed` or never detached on `Unloaded`.
6. Binding `OneWay`/`TwoWay` to plain CLR objects lacking `INotifyPropertyChanged` (WPF attaches static `PropertyDescriptor` listener -> use `ObservableObject` or `Mode=OneTime`).
7. `StrongReferenceMessenger` without `UnregisterAll`.

- **Diagnostics:** Use **VS XAML Binding Failures** (target **0** binding errors), **VS Live Visual Tree**, **Snoop** (`snoopwpf`, non-single-file only), **PerfView**, and **WPR/WPA**. Do not rely on legacy *WPF Performance Suite (`Perforator`)* — it is broken on `.NET 8–10`.

---

## 5. Accessibility (UI Automation, Keyboard, Live Regions, High Contrast)

- **`AutomationProperties` Mandatory Rules (Verified against `dotnet/wpf`):**
  - WPF supports: `AutomationId`, `Name`, `HelpText`, `AcceleratorKey`, `AccessKey`, `LabeledBy`, `LiveSetting`, `IsRequiredForForm`, `HeadingLevel`, `IsDialog`, `PositionInSet`, `SizeOfSet`, `IsOffscreenBehavior`.
  - Every icon-only button **must** define `AutomationProperties.Name` (without repeating `"Button"`!) + `ToolTip` + optional `AutomationProperties.AcceleratorKey`.
  - **WPF vs. WinUI 3 Trap:** `AutomationProperties.AccessibilityView="Raw"` is **WinUI 3 / UWP ONLY** and fails WPF compilation (`MC3072`)! In WPF, keep decorative icon `TextBlock`s inside a `ControlTemplate` (where `TextBlockAutomationPeer.IsControlElementCore()` automatically returns `false`) or wrap a custom `DecorativeGlyph : TextBlock` peer returning `false` for `IsControlElementCore()` and `IsContentElementCore()`.
  - Pair form inputs with visible labels via `AutomationProperties.LabeledBy="{Binding ElementName=MyLabel}"` or `<Label Target="...">` with `_` access keys (`<AccessText Text="_Title:" TextWrapping="Wrap"/>`).
  - Mark custom modal overlays/dialogs with `AutomationProperties.IsDialog="True"` and major headings with `AutomationProperties.HeadingLevel`.
- **Live Regions (Streaming Chat & Errors):**
  - Set `AutomationProperties.LiveSetting="Polite"` (assistant turn finished, sync status) or `"Assertive"` (connection lost / critical error).
  - Changing `.Text` alone is **silent** — raise `AutomationEvents.LiveRegionChanged` explicitly (never per streaming token — only at completion/error!):
    ```csharp
    public static void AnnounceLiveRegion(FrameworkElement element)
    {
        if (!AutomationPeer.ListenerExists(AutomationEvents.LiveRegionChanged)) return;
        var peer = FrameworkElementAutomationPeer.FromElement(element)
                   ?? FrameworkElementAutomationPeer.CreatePeerForElement(element);
        peer?.RaiseAutomationEvent(AutomationEvents.LiveRegionChanged);
    }
    ```
- **Keyboard & Focus Discipline:**
  - Never use non-focusable `<Border MouseLeftButtonDown="...">` or `<Border.InputBindings>` for clickable cards/sessions — use `<ListBoxItem>` or `<Button>` templates so `Tab`, `Arrows`, `Enter`, and `Space` work!
  - Reveal hover actions (`Rename`, `Delete`, `Copy`) on **`IsKeyboardFocusWithin == True`**, not just `IsMouseOver == True`! Never hide focusable buttons with `Opacity="0"` (still in Tab order — collapse `Visibility="Collapsed"` or keep accessible!).
  - Implement **`F6` / `Shift+F6`** pane cycling, **`Esc`** to dismiss modals/flyouts, `KeyboardNavigation.TabNavigation="Cycle"` on modals, and **save/restore `Keyboard.FocusedElement`** when opening/closing dialogs/modals!
- **Verification:** Audit with **Accessibility Insights for Windows** (Live Inspect + FastPass) and **Windows Narrator (`Win+Ctrl+Enter`, Developer Mode `Ctrl+CapsLock+F12`)**, plus all 4 Windows Contrast themes (`Left Alt + Left Shift + PrintScreen`).

---

## 6. Chat & Streaming UI Patterns, Localization & Automated Testing

- **Smart Chat Auto-Scroll:** Track `stickToBottom` (`AutoScrollBehavior` in `§2.3`). When user scrolls up to read earlier messages, **stop auto-scrolling immediately** and show a floating **`"New messages ↓"`** pill button.
- **Incremental In-Place Streaming:** Update the single active message ViewModel on a `33–50 ms` throttled dispatcher tick instead of tearing down and calling `UpdateLayout()` on every token.
- **Localization (`.resx`):** Store strings in `.resx` (`LocBaml` does not work on `.NET 9/10`!), set `xml:lang` and `FrameworkElement.LanguageProperty` metadata to match `CultureInfo.CurrentCulture`, and use `Auto`/`*` Grid sizing (never fixed button widths).
- **Automated Testing Pyramid:**
  1. **xUnit / NUnit ViewModel unit tests** (fast, headless, zero `Dispatcher`/`Window` refs — inject `IDialogService` / transport interfaces).
  2. **`FlaUI.UIA3` end-to-end tests** querying stable `AutomationId`s with `Retry.WhileNull` (`microsoft/WinAppDriver` is abandoned since 2020 — prefer `FlaUI.UIA3`).
  3. **Visual snapshots (`RenderTargetBitmap` + `VisualBrush`):** Disable blinking/60 FPS loops via a test flag before snapshot and never wait on `DispatcherPriority.ApplicationIdle` if any continuous timer runs.
