# Motion Design & High-Performance WPF Animations (.NET 9/10)

> **Scope:** Fluent 2 / Windows 11 motion principles, timing/easing translation into WPF `KeySpline`s, `VisualStateManager` vs. triggers, complete compile-verified MVVM animation recipes, `CompositionTarget.Rendering` per-frame loops, GPU optimization for integrated graphics, reduced motion, and common WPF animation bugs.

## Table of Contents

1. [Motion Design Principles & Choreography](#1-motion-design-principles--choreography)
2. [Timing & Easing Table (Fluent / WinUI -> WPF)](#2-timing--easing-table-fluent--winui---wpf)
3. [WPF Animation Mechanics & Critical Pitfalls](#3-wpf-animation-mechanics--critical-pitfalls)
4. [Complete Compile-Verified Recipes (XAML & C#)](#4-complete-compile-verified-recipes-xaml--c)
5. [Per-Frame Rendering (`CompositionTarget.Rendering`) Done Right](#5-per-frame-rendering-compositiontargetrendering-done-right)
6. [Performance on Integrated GPUs & Profiling Tools](#6-performance-on-integrated-gpus--profiling-tools)
7. [Motion Accessibility & Bug Checklist](#7-motion-accessibility--bug-checklist)

---

## 1. Motion Design Principles & Choreography

Motion in a Windows desktop app communicates **feedback**, **spatial continuity**, and **hierarchy** — never decorative delay.

- **Five Windows Motion Rules:**
  1. **Responsive (`<= 83–167 ms`):** Pointer hover/press and tab switches react immediately; redirect cleanly if input reverses mid-flight.
  2. **Entrance vs. Exit Asymmetry:** Entrances are longer (`250–333 ms` decelerating into view) so users orient to arriving content; exits are brisk (`83–167 ms` accelerating or fading out) so departing UI gets out of the way.
  3. **Subtle Spatial Offsets:** Slide cards/pages by **`12–28 px`** (or `~100 px` on spacious hero views) — never sweep elements across the whole window.
  4. **Top-Level Nav = Quick Fade + Subtle Lift:** Avoid dizzying horizontal page slides across unrelated top-level tabs; use crisp crossfade + `16–20 px` vertical lift (`Entrance` pattern). Reserve horizontal slide (`Left`/`Right`) for sequential wizards or back/next flows, and scale-up for drill-in (`List -> Detail`).
  5. **Choreography Cap:** Stagger only small groups of newly entered items (`25–40 ms` offset per item, **total delay capped at `~250 ms`**). Never stagger 20+ rows one by one.

---

## 2. Timing & Easing Table (Fluent / WinUI -> WPF)

> **`KeySpline` Rules:** WPF `KeySpline="x1,y1 x2,y2"` maps 1:1 to CSS `cubic-bezier(x1, y1, x2, y2)`. Control point `X` must stay in `[0, 1]`; keep `Y` in `[0, 1]` too and use `BackEase` / `ElasticEase` or multi-keyframe sequences for overshoot.

| Motion Role | Recommended Duration | Curve (`cubic-bezier`) | Exact WPF `KeySpline` | Nearest `EasingFunctionBase` |
|---|---|---|---|---|
| **Hover / Press / Opacity Micro-State** | **`83 ms`** (5 frames @ 60Hz) | `(0, 0, 1, 1)` linear or `(0, 0, 0, 1)` | Linear / `0,0 0,1` | `QuarticEase` (`EaseOut`) |
| **Direct Entrance** (flyout, card, view) | **`200–250 ms`** (`333 ms` large) | `(0, 0, 0, 1)` (`FastOutSlowIn`) | **`0,0 0,1`** | `ExponentialEase` (`Exponent=6, EaseOut`) / `QuinticEase` |
| **Gentle Decelerate** | `200–250 ms` | `(0.33, 0, 0.1, 1)` | `0.33,0 0.1,1` | `CubicEase` (`EaseOut`) |
| **Point-to-Point Move** (reposition, resize) | `250 ms` (`167–333 ms`) | `(0.55, 0.55, 0, 1)` | **`0.55,0.55 0,1`** | `QuarticEase` (`EaseInOut`) |
| **Symmetric Ease** (drawer, expand) | `250–300 ms` | `(0.8, 0, 0.2, 1)` (`EasyEaseMax`) | `0.8,0 0.2,1` | `ExponentialEase` (`EaseInOut`) |
| **Direct Exit** (dismiss + fade) | **`150–167 ms`** | `(0, 0, 0, 1)` + opacity `0` | `0,0 0,1` + `83–150 ms` fade | `QuinticEase` (`EaseOut`) + Opacity |
| **Gentle Exit** (accelerate out) | **`167 ms`** | `(1, 0, 1, 1)` (`SlowOutFastIn`) | **`1,0 1,1`** | `QuinticEase` / `ExponentialEase` (`EaseIn`) |
| **Modals / Dialogs** | Show **`250 ms`** / Hide **`167 ms`** | Scale `1.05 -> 1.0` (`0,0,0,1`) + `83 ms` opacity | `0,0 0,1` | `QuinticEase` (`EaseOut`) |
| **Expander** | Expand **`333 ms`** / Collapse **`167 ms`** | Expand `0,0,0,1` / Collapse `1,1,0,1` or `1,0,1,1` | `0,0 0,1` / `1,0 1,1` | `QuinticEase` |
| **Skeleton Shimmer** | **`3000 ms`** (`30 fps` cap) | `(0.33, 0, 0.67, 1)` | `0.33,0 0.67,1` | `SineEase` (`EaseInOut`) |

---

## 3. WPF Animation Mechanics & Critical Pitfalls

### 3.1 WPF UI-Thread Engine vs. WinUI Composition
- **WinUI 3** runs `Opacity`, `RenderTransform`, and `Brush` color animations off the UI thread (`Microsoft.UI.Composition`) and **blocks layout-affecting animations** unless `EnableDependentAnimation="True"` is set.
- **WPF runs its `TimeManager` on the UI `Dispatcher` thread** and has **no guardrail blocking dependent animations**: animating `Width`, `Height`, `Margin`, `Padding`, or `LayoutTransform` silently triggers full Measure + Arrange cascades every frame! Any GC pause or synchronous work on the UI thread stalls every animation.

### 3.2 `FillBehavior.HoldEnd` Precedence Trap & Releasing Clocks
- Default `FillBehavior="HoldEnd"` keeps an active `AnimationClock` at **Dependency Property Precedence Rank #2** — higher than Local Values (Rank #3) and Style/Trigger Setters!
- Result: after an animation finishes with `HoldEnd`, setting `element.Opacity = 1` or `element.Height = double.NaN` in C# appears ignored!
- **Three clean fixes:**
  1. Set **`FillBehavior="Stop"`** after assigning the resting base/local value *before* starting the animation.
  2. Call `element.BeginAnimation(UIElement.OpacityProperty, null);` to clear direct clocks.
  3. On `Completed`, assign final resting state with `SetCurrentValue(...)` (preserves data bindings!) and call `storyboard.Remove(element)`.

### 3.3 `HandoffBehavior` & Interruptible Motion
- **Never set `From="..."` on interactive hover/press/toggle animations.** Omitting `From` lets `SnapshotAndReplace` (the default `HandoffBehavior`) smoothly start from whatever mid-flight value the property currently holds!
- Avoid `HandoffBehavior.Compose` in loops — repeated `Compose` stacks unresolved clocks indefinitely and leaks CPU every frame.

### 3.4 `VisualStateManager` vs. `Triggers` (and the WinUI `Setters` Trap)
- **WPF `VisualState` only supports `<Storyboard>`** — it does **NOT** have WinUI's `<VisualState.Setters>`! Instant state changes inside a WPF `VisualState` require zero-duration `ObjectAnimationUsingKeyFrames` (`DiscreteObjectKeyFrame`) or `DoubleAnimation Duration="0"`.
- **Use `VisualStateManager`** on `ControlTemplate`s (`CommonStates`: `Normal`, `MouseOver`, `Pressed`, `Disabled`; `FocusStates`) instead of overlapping `Trigger.EnterActions`/`ExitActions` so `MouseOver <-> Pressed` transitions cleanly (`VisualTransition` with `GeneratedDuration="0:0:0.120"` + `GeneratedEasingFunction` interpolates automatically!).
- **Trigger `EnterActions`/`ExitActions` trap:** They fire *only on state transitions*, not if the bound property already starts true when loaded.
- **`Storyboard.TargetName` NameScope trap:** External storyboards cannot target named elements inside a `ControlTemplate` or `DataTemplate`. Keep template storyboards inside the template itself, or drive state via attached properties / `VisualStateManager.GoToState`.

### 3.5 Frozen Brushes & GPU-Heavy Properties
- **Frozen `SolidColorBrush` crash:** Theme brushes in `App.xaml` are shared/frozen; animating `(Border.Background).(SolidColorBrush.Color)` throws `InvalidOperationException`!
  - **Best GPU-safe fix:** Keep base and hover brushes **frozen** in `App.xaml`, stack an unfrozen overlay `<Border x:Name="PART_Hover" Opacity="0" Background="{DynamicResource SurfaceHoverBrush}" IsHitTestVisible="False"/>` inside the template, and animate **`Opacity`** (`0 -> 1` in `83 ms`). Works seamlessly with runtime theme swaps!
  - **C# fallback:** Clone a frozen brush (`if (brush.IsFrozen) brush = brush.Clone();`) before calling `brush.BeginAnimation(SolidColorBrush.ColorProperty, anim)`.
- **Avoid animating `UIElement.Opacity` on complex subtrees** when `Brush.Opacity` suffices — `UIElement.Opacity < 1` allocates an offscreen isolation surface.
- **BAN per-frame `DropShadowEffect.BlurRadius` or `BlurEffect` animation:** Forces full offscreen shader passes and inflates dirty rectangles every frame on integrated GPUs. Put a **static frozen shadow** on a separate sibling `Border` behind the target and animate its **`Opacity`** (`0 -> 0.25`) instead!

---

## 4. Complete Compile-Verified Recipes (XAML & C#)

### 4.1 `MotionSettings` (Live OS Reduced Motion + Render Tier)

*(Uses `CommunityToolkit.Mvvm >= 8.4.2` for C# 14 `partial` properties without `<LangVersion>preview</LangVersion>`; on `8.4.0`, either enable `<LangVersion>preview</LangVersion>` or use a private `_isReducedMotion` backing field.)*

```csharp
using System;
using System.ComponentModel;
using System.Windows;
using System.Windows.Media;
using CommunityToolkit.Mvvm.ComponentModel;

namespace MyApp.Motion;

public sealed partial class MotionSettings : ObservableObject, IDisposable
{
    public static MotionSettings Instance { get; } = new();
    private bool _appReducedMotionOverride;

    [ObservableProperty]
    public partial bool IsReducedMotion { get; set; }

    public bool AllowMotion => !IsReducedMotion;

    private MotionSettings()
    {
        Refresh();
        SystemParameters.StaticPropertyChanged += OnSystemParametersChanged;
        RenderCapability.TierChanged += OnTierChanged;
    }

    public bool AppReducedMotionOverride
    {
        get => _appReducedMotionOverride;
        set { if (_appReducedMotionOverride != value) { _appReducedMotionOverride = value; Refresh(); } }
    }

    private void OnSystemParametersChanged(object? sender, PropertyChangedEventArgs e)
    {
        if (e.PropertyName is nameof(SystemParameters.ClientAreaAnimation) or null)
            Application.Current?.Dispatcher.BeginInvoke(Refresh);
    }

    private void OnTierChanged(object? sender, EventArgs e) =>
        Application.Current?.Dispatcher.BeginInvoke(Refresh);

    private void Refresh()
    {
        bool reduced = _appReducedMotionOverride || !SystemParameters.ClientAreaAnimation || (RenderCapability.Tier >> 16) == 0;
        if (reduced != IsReducedMotion)
        {
            IsReducedMotion = reduced;
            OnPropertyChanged(nameof(AllowMotion));
        }
    }

    public void Dispose()
    {
        SystemParameters.StaticPropertyChanged -= OnSystemParametersChanged;
        RenderCapability.TierChanged -= OnTierChanged;
    }
}
```

### 4.2 Button Press Scale + Hover Crossfade (Zero Layout Cost, Frozen-Brush Safe)

```xml
<Style x:Key="BrandMotionButton" TargetType="{x:Type Button}">
    <Setter Property="OverridesDefaultStyle" Value="True" />
    <Setter Property="RenderTransformOrigin" Value="0.5,0.5" />
    <Setter Property="FocusVisualStyle" Value="{DynamicResource Windows11FocusVisual}" />
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="{x:Type Button}">
                <Grid x:Name="PART_Root" RenderTransformOrigin="0.5,0.5">
                    <Grid.RenderTransform>
                        <ScaleTransform x:Name="PART_Scale" ScaleX="1" ScaleY="1" />
                    </Grid.RenderTransform>
                    <VisualStateManager.VisualStateGroups>
                        <VisualStateGroup x:Name="CommonStates">
                            <VisualState x:Name="Normal">
                                <Storyboard>
                                    <DoubleAnimation Storyboard.TargetName="PART_Hover" Storyboard.TargetProperty="Opacity" To="0" Duration="0:0:0.120" />
                                    <DoubleAnimationUsingKeyFrames Storyboard.TargetName="PART_Scale" Storyboard.TargetProperty="ScaleX">
                                        <SplineDoubleKeyFrame KeyTime="0:0:0.167" Value="1.0" KeySpline="0,0 0,1" />
                                    </DoubleAnimationUsingKeyFrames>
                                    <DoubleAnimationUsingKeyFrames Storyboard.TargetName="PART_Scale" Storyboard.TargetProperty="ScaleY">
                                        <SplineDoubleKeyFrame KeyTime="0:0:0.167" Value="1.0" KeySpline="0,0 0,1" />
                                    </DoubleAnimationUsingKeyFrames>
                                </Storyboard>
                            </VisualState>
                            <VisualState x:Name="MouseOver">
                                <Storyboard>
                                    <DoubleAnimation Storyboard.TargetName="PART_Hover" Storyboard.TargetProperty="Opacity" To="1" Duration="0:0:0.083" />
                                    <DoubleAnimationUsingKeyFrames Storyboard.TargetName="PART_Scale" Storyboard.TargetProperty="ScaleX">
                                        <SplineDoubleKeyFrame KeyTime="0:0:0.083" Value="1.0" KeySpline="0,0 0,1" />
                                    </DoubleAnimationUsingKeyFrames>
                                    <DoubleAnimationUsingKeyFrames Storyboard.TargetName="PART_Scale" Storyboard.TargetProperty="ScaleY">
                                        <SplineDoubleKeyFrame KeyTime="0:0:0.083" Value="1.0" KeySpline="0,0 0,1" />
                                    </DoubleAnimationUsingKeyFrames>
                                </Storyboard>
                            </VisualState>
                            <VisualState x:Name="Pressed">
                                <Storyboard>
                                    <DoubleAnimation Storyboard.TargetName="PART_Hover" Storyboard.TargetProperty="Opacity" To="0.7" Duration="0:0:0.050" />
                                    <DoubleAnimationUsingKeyFrames Storyboard.TargetName="PART_Scale" Storyboard.TargetProperty="ScaleX">
                                        <SplineDoubleKeyFrame KeyTime="0:0:0.083" Value="0.97" KeySpline="0,0 0,1" />
                                    </DoubleAnimationUsingKeyFrames>
                                    <DoubleAnimationUsingKeyFrames Storyboard.TargetName="PART_Scale" Storyboard.TargetProperty="ScaleY">
                                        <SplineDoubleKeyFrame KeyTime="0:0:0.083" Value="0.97" KeySpline="0,0 0,1" />
                                    </DoubleAnimationUsingKeyFrames>
                                </Storyboard>
                            </VisualState>
                            <VisualState x:Name="Disabled">
                                <Storyboard>
                                    <DoubleAnimation Storyboard.TargetName="PART_Root" Storyboard.TargetProperty="Opacity" To="0.4" Duration="0:0:0.083" />
                                </Storyboard>
                            </VisualState>
                        </VisualStateGroup>
                    </VisualStateManager.VisualStateGroups>
                    <Border Background="{TemplateBinding Background}" BorderBrush="{TemplateBinding BorderBrush}"
                            BorderThickness="{TemplateBinding BorderThickness}" CornerRadius="8" />
                    <Border x:Name="PART_Hover" Background="{DynamicResource CardSurfaceHoverBrush}" CornerRadius="8" Opacity="0" IsHitTestVisible="False" />
                    <ContentPresenter Margin="{TemplateBinding Padding}" HorizontalAlignment="{TemplateBinding HorizontalContentAlignment}" VerticalAlignment="Center" RecognizesAccessKey="True" />
                </Grid>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
```

### 4.3 Dual-Presenter View Transition (`TransitioningContentControl`)

Holds **two** `ContentPresenter`s (`PART_SiteA` / `PART_SiteB`), clears outgoing `Content = null` when the transition completes (preventing ViewModel memory leaks and invisible hit-testing), and skips motion when reduced motion or software Tier 0 is active.

```xml
<!-- Themes/Generic.xaml (requires [assembly: ThemeInfo(ResourceDictionaryLocation.None, ResourceDictionaryLocation.SourceAssembly)]) -->
<Style TargetType="{x:Type local:TransitioningContentControl}">
    <Setter Property="ClipToBounds" Value="True" />
    <Setter Property="Template">
        <Setter.Value>
            <ControlTemplate TargetType="{x:Type local:TransitioningContentControl}">
                <Grid ClipToBounds="True">
                    <ContentPresenter x:Name="PART_SiteA" ContentTemplate="{TemplateBinding ContentTemplate}"
                                      ContentTemplateSelector="{TemplateBinding ContentTemplateSelector}" RenderTransformOrigin="0.5,0.5">
                        <ContentPresenter.RenderTransform><TranslateTransform /></ContentPresenter.RenderTransform>
                    </ContentPresenter>
                    <ContentPresenter x:Name="PART_SiteB" Visibility="Collapsed" ContentTemplate="{TemplateBinding ContentTemplate}"
                                      ContentTemplateSelector="{TemplateBinding ContentTemplateSelector}" RenderTransformOrigin="0.5,0.5">
                        <ContentPresenter.RenderTransform><TranslateTransform /></ContentPresenter.RenderTransform>
                    </ContentPresenter>
                </Grid>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
```

```csharp
using System;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Animation;

public class TransitioningContentControl : ContentControl
{
    private ContentPresenter? _siteA, _siteB;
    private bool _showingA = true;
    private Storyboard? _activeStoryboard;

    public static readonly DependencyProperty IsMotionEnabledProperty =
        DependencyProperty.Register(nameof(IsMotionEnabled), typeof(bool), typeof(TransitioningContentControl), new PropertyMetadata(true));
    public bool IsMotionEnabled { get => (bool)GetValue(IsMotionEnabledProperty); set => SetValue(IsMotionEnabledProperty, value); }

    static TransitioningContentControl() =>
        DefaultStyleKeyProperty.OverrideMetadata(typeof(TransitioningContentControl), new FrameworkPropertyMetadata(typeof(TransitioningContentControl)));

    public override void OnApplyTemplate()
    {
        base.OnApplyTemplate();
        _siteA = GetTemplateChild("PART_SiteA") as ContentPresenter;
        _siteB = GetTemplateChild("PART_SiteB") as ContentPresenter;
        _showingA = true;
        if (_siteA is not null) _siteA.Content = Content;
        if (_siteB is not null) { _siteB.Content = null; _siteB.Visibility = Visibility.Collapsed; }
    }

    protected override void OnContentChanged(object oldContent, object newContent)
    {
        base.OnContentChanged(oldContent, newContent);
        if (_siteA is null || _siteB is null) return;

        _activeStoryboard?.Stop(this);
        _activeStoryboard = null;

        ContentPresenter incoming = _showingA ? _siteB : _siteA;
        ContentPresenter outgoing = _showingA ? _siteA : _siteB;
        _showingA = !_showingA;

        incoming.Content = newContent;
        incoming.Visibility = Visibility.Visible;

        if (!IsMotionEnabled || !SystemParameters.ClientAreaAnimation || (RenderCapability.Tier >> 16) == 0)
        {
            incoming.Opacity = 1;
            ((TranslateTransform)incoming.RenderTransform).Y = 0;
            outgoing.Content = null;
            outgoing.Visibility = Visibility.Collapsed;
            return;
        }

        var spline = new KeySpline(0, 0, 0, 1); spline.Freeze();
        var inOp = new DoubleAnimation(0, 1, TimeSpan.FromMilliseconds(200)) { EasingFunction = new QuadraticEase { EasingMode = EasingMode.EaseOut }, FillBehavior = FillBehavior.Stop };
        var inSlide = new DoubleAnimationUsingKeyFrames { FillBehavior = FillBehavior.Stop };
        inSlide.KeyFrames.Add(new DiscreteDoubleKeyFrame(20, KeyTime.FromTimeSpan(TimeSpan.Zero)));
        inSlide.KeyFrames.Add(new SplineDoubleKeyFrame(0, KeyTime.FromTimeSpan(TimeSpan.FromMilliseconds(250)), spline));
        var outOp = new DoubleAnimation(outgoing.Opacity, 0, TimeSpan.FromMilliseconds(120)) { FillBehavior = FillBehavior.Stop };

        incoming.Opacity = 1;
        ((TranslateTransform)incoming.RenderTransform).Y = 0;

        Storyboard.SetTarget(inOp, incoming); Storyboard.SetTargetProperty(inOp, new PropertyPath(OpacityProperty));
        Storyboard.SetTarget(inSlide, incoming); Storyboard.SetTargetProperty(inSlide, new PropertyPath("(UIElement.RenderTransform).(TranslateTransform.Y)"));
        Storyboard.SetTarget(outOp, outgoing); Storyboard.SetTargetProperty(outOp, new PropertyPath(OpacityProperty));

        var sb = new Storyboard();
        sb.Children.Add(inOp); sb.Children.Add(inSlide); sb.Children.Add(outOp);
        sb.Completed += (_, _) =>
        {
            if (!ReferenceEquals(_activeStoryboard, sb)) return;
            outgoing.Content = null; outgoing.Visibility = Visibility.Collapsed; outgoing.Opacity = 1;
        };
        _activeStoryboard = sb;
        sb.Begin(this, isControllable: true);
    }
}
```

### 4.4 Smooth Expander Height & `GridLengthAnimation`

*For floating drawers, animate `TranslateTransform.Y` inside `ClipToBounds="True"` (zero layout cost). When inline layout must push siblings down cleanly:*

```csharp
public static class SmoothExpandBehavior
{
    public static readonly DependencyProperty IsExpandedProperty =
        DependencyProperty.RegisterAttached("IsExpanded", typeof(bool), typeof(SmoothExpandBehavior), new PropertyMetadata(false, OnIsExpandedChanged));
    public static bool GetIsExpanded(DependencyObject obj) => (bool)obj.GetValue(IsExpandedProperty);
    public static void SetIsExpanded(DependencyObject obj, bool value) => obj.SetValue(IsExpandedProperty, value);

    private static void OnIsExpandedChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is not FrameworkElement host || !host.IsLoaded) return;
        bool expand = (bool)e.NewValue;
        if (!SystemParameters.ClientAreaAnimation || (RenderCapability.Tier >> 16) == 0)
        {
            host.BeginAnimation(FrameworkElement.HeightProperty, null);
            host.Height = double.NaN;
            host.Visibility = expand ? Visibility.Visible : Visibility.Collapsed;
            return;
        }

        host.ClipToBounds = true;
        double start = host.Visibility == Visibility.Visible ? host.ActualHeight : 0;

        if (expand)
        {
            host.BeginAnimation(FrameworkElement.HeightProperty, null);
            host.Height = double.NaN;
            host.Visibility = Visibility.Visible;
            host.Measure(new Size(host.ActualWidth > 0 ? host.ActualWidth : double.PositiveInfinity, double.PositiveInfinity));
            double target = host.DesiredSize.Height;

            var spline = new KeySpline(0, 0, 0, 1); spline.Freeze();
            var anim = new DoubleAnimationUsingKeyFrames { FillBehavior = FillBehavior.Stop };
            anim.KeyFrames.Add(new DiscreteDoubleKeyFrame(start, KeyTime.FromTimeSpan(TimeSpan.Zero)));
            anim.KeyFrames.Add(new SplineDoubleKeyFrame(target, KeyTime.FromTimeSpan(TimeSpan.FromMilliseconds(333)), spline));
            anim.Completed += (_, _) => { host.BeginAnimation(FrameworkElement.HeightProperty, null); host.Height = double.NaN; };
            host.BeginAnimation(FrameworkElement.HeightProperty, anim);
        }
        else
        {
            var spline = new KeySpline(1, 0, 1, 1); spline.Freeze();
            var anim = new DoubleAnimationUsingKeyFrames { FillBehavior = FillBehavior.Stop };
            anim.KeyFrames.Add(new DiscreteDoubleKeyFrame(start, KeyTime.FromTimeSpan(TimeSpan.Zero)));
            anim.KeyFrames.Add(new SplineDoubleKeyFrame(0, KeyTime.FromTimeSpan(TimeSpan.FromMilliseconds(167)), spline));
            anim.Completed += (_, _) => { host.BeginAnimation(FrameworkElement.HeightProperty, null); host.Height = double.NaN; host.Visibility = Visibility.Collapsed; };
            host.BeginAnimation(FrameworkElement.HeightProperty, anim);
        }
    }
}

public sealed class GridLengthAnimation : AnimationTimeline
{
    public static readonly DependencyProperty FromProperty = DependencyProperty.Register(nameof(From), typeof(GridLength), typeof(GridLengthAnimation), new PropertyMetadata(GridLength.Auto));
    public static readonly DependencyProperty ToProperty = DependencyProperty.Register(nameof(To), typeof(GridLength), typeof(GridLengthAnimation), new PropertyMetadata(GridLength.Auto));
    public static readonly DependencyProperty EasingFunctionProperty = DependencyProperty.Register(nameof(EasingFunction), typeof(IEasingFunction), typeof(GridLengthAnimation));
    public GridLength From { get => (GridLength)GetValue(FromProperty); set => SetValue(FromProperty, value); }
    public GridLength To { get => (GridLength)GetValue(ToProperty); set => SetValue(ToProperty, value); }
    public IEasingFunction? EasingFunction { get => (IEasingFunction?)GetValue(EasingFunctionProperty); set => SetValue(EasingFunctionProperty, value); }
    public override Type TargetPropertyType => typeof(GridLength);
    protected override Freezable CreateInstanceCore() => new GridLengthAnimation();
    public override object GetCurrentValue(object dOrig, object dDest, AnimationClock clock)
    {
        double p = clock.CurrentProgress ?? 0.0;
        if (EasingFunction is not null) p = EasingFunction.Ease(p);
        var o = From.IsAuto && dOrig is GridLength gl ? gl : From;
        var d = To.IsAuto && dDest is GridLength gl2 ? gl2 : To;
        double f = o.IsAuto ? 0 : o.Value, t = d.IsAuto ? 0 : d.Value;
        return new GridLength(f + (t - f) * p, d.IsStar || o.IsStar ? GridUnitType.Star : GridUnitType.Pixel);
    }
}
```

### 4.5 Skeleton Shimmer (`30 fps` Cap + Visibility-Safe Stop) & Virtualized Stagger

```xml
<Border x:Name="SkeletonPlaceholder" Height="48" CornerRadius="8" Visibility="{Binding IsLoading, Converter={StaticResource BoolToVis}}">
    <Border.Background>
        <LinearGradientBrush StartPoint="0,0" EndPoint="1,0">
            <LinearGradientBrush.RelativeTransform><TranslateTransform X="-1.0" /></LinearGradientBrush.RelativeTransform>
            <GradientStop Color="#EAEAEA" Offset="0.0" />
            <GradientStop Color="#F6F6F6" Offset="0.5" />
            <GradientStop Color="#EAEAEA" Offset="1.0" />
        </LinearGradientBrush>
    </Border.Background>
    <Border.Style>
        <Style TargetType="{x:Type Border}">
            <Style.Triggers>
                <MultiDataTrigger>
                    <MultiDataTrigger.Conditions>
                        <Condition Binding="{Binding IsVisible, RelativeSource={RelativeSource Self}}" Value="True" />
                        <Condition Binding="{Binding AllowMotion, Source={x:Static motion:MotionSettings.Instance}}" Value="True" />
                    </MultiDataTrigger.Conditions>
                    <MultiDataTrigger.EnterActions>
                        <BeginStoryboard x:Name="ShimmerStoryboard">
                            <Storyboard Timeline.DesiredFrameRate="30" RepeatBehavior="Forever">
                                <DoubleAnimationUsingKeyFrames Storyboard.TargetProperty="(Border.Background).(LinearGradientBrush.RelativeTransform).(TranslateTransform.X)">
                                    <DiscreteDoubleKeyFrame KeyTime="0:0:0" Value="-1.0" />
                                    <SplineDoubleKeyFrame KeyTime="0:0:1.8" Value="1.0" KeySpline="0.33,0 0.67,1" />
                                    <DiscreteDoubleKeyFrame KeyTime="0:0:3.0" Value="1.0" />
                                </DoubleAnimationUsingKeyFrames>
                            </Storyboard>
                        </BeginStoryboard>
                    </MultiDataTrigger.EnterActions>
                    <MultiDataTrigger.ExitActions>
                        <StopStoryboard BeginStoryboardName="ShimmerStoryboard" />
                    </MultiDataTrigger.ExitActions>
                </MultiDataTrigger>
            </Style.Triggers>
        </Style>
    </Border.Style>
</Border>
```

```csharp
// Tracks DATA items in ConditionalWeakTable so VirtualizingStackPanel container recycling never replays staggers!
public static class StaggerEntranceBehavior
{
    private static readonly KeySpline Spline = CreateSpline();
    private static readonly ConditionalWeakTable<object, object> Animated = new();
    private static readonly object Marker = new();
    private static KeySpline CreateSpline() { var ks = new KeySpline(0, 0, 0, 1); ks.Freeze(); return ks; }

    public static readonly DependencyProperty IsEnabledProperty = DependencyProperty.RegisterAttached("IsEnabled", typeof(bool), typeof(StaggerEntranceBehavior), new PropertyMetadata(false, OnChanged));
    public static bool GetIsEnabled(DependencyObject obj) => (bool)obj.GetValue(IsEnabledProperty);
    public static void SetIsEnabled(DependencyObject obj, bool value) => obj.SetValue(IsEnabledProperty, value);

    private static void OnChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is ItemsControl ic) { if ((bool)e.NewValue) ic.Loaded += OnLoaded; else ic.Loaded -= OnLoaded; }
    }

    private static void OnLoaded(object sender, RoutedEventArgs e)
    {
        if (sender is not ItemsControl ic || !SystemParameters.ClientAreaAnimation || (RenderCapability.Tier >> 16) == 0) return;
        int slot = 0;
        for (int i = 0; i < ic.Items.Count; i++)
        {
            if (ic.ItemContainerGenerator.ContainerFromIndex(i) is not FrameworkElement c) continue;
            object item = ic.Items[i];
            if (Animated.TryGetValue(item, out _)) continue;
            Animated.Add(item, Marker);

            var delay = TimeSpan.FromMilliseconds(Math.Min(slot++, 8) * 35);
            if (c.RenderTransform is not TranslateTransform tt || tt.IsFrozen) { tt = new TranslateTransform(); c.RenderTransform = tt; }
            c.Opacity = 1; tt.Y = 0;

            var fade = new DoubleAnimationUsingKeyFrames { BeginTime = delay, FillBehavior = FillBehavior.Stop };
            fade.KeyFrames.Add(new DiscreteDoubleKeyFrame(0, KeyTime.FromTimeSpan(TimeSpan.Zero)));
            fade.KeyFrames.Add(new LinearDoubleKeyFrame(1, KeyTime.FromTimeSpan(TimeSpan.FromMilliseconds(167))));

            var slide = new DoubleAnimationUsingKeyFrames { BeginTime = delay, FillBehavior = FillBehavior.Stop };
            slide.KeyFrames.Add(new DiscreteDoubleKeyFrame(14, KeyTime.FromTimeSpan(TimeSpan.Zero)));
            slide.KeyFrames.Add(new SplineDoubleKeyFrame(0, KeyTime.FromTimeSpan(TimeSpan.FromMilliseconds(250)), Spline));

            c.BeginAnimation(UIElement.OpacityProperty, fade);
            tt.BeginAnimation(TranslateTransform.YProperty, slide);
        }
    }
}
```

### 4.6 Lottie Vector Animations (`SkiaSharp.Skottie` + `SKElement`)
For complex illustrated animations (onboarding, empty states), use **`SkiaSharp.Skottie`** + **`SkiaSharp.Views.WPF`**: parse JSON once (`Animation.TryParse`), advance frame time only while `IsVisible`, and keep surfaces `<= 200 px`.

---

## 5. Per-Frame Rendering (`CompositionTarget.Rendering`) Done Right

Use `CompositionTarget.Rendering` (never `DispatcherTimer`) for live voice/audio visualizers, obeying **all five safety rules**:

1. **Lifecycle-gated attach/detach:** Subscribe ONLY when `IsLoaded && IsVisible && IsListening`. Detach immediately in `IsVisibleChanged` and `Unloaded` (`CompositionTarget.Rendering` is `static` and leaks forever + blocks `DispatcherPriority.ApplicationIdle` if left hooked!).
2. **Duplicate-frame guard:** WPF can raise `Rendering` more than once per frame with identical `RenderingTime`. Return early when `args.RenderingTime == _lastRenderingTime`.
3. **Delta-time (`dt`) smoothing:** Never use frame-count steps (`+= 1.2`, `*= 0.85f` — runs 2.4× fast on 144Hz displays!) or `DateTime.Now`. Normalize via `1.0 - Math.Exp(-speed * dt)`.
4. **Idle convergence sleep:** Once amplitude drops below `0.002` and rotation/pulse isn't needed, snap to `0` and **detach** until new audio arrives.
5. **Zero layout & zero allocations per frame:** Draw via `OnRender(DrawingContext)` / `DrawingVisual` with pre-frozen brushes, or mutate `ScaleTransform.ScaleY` — **never** mutate `Border.Height` inside a `StackPanel`!

```csharp
public sealed class VoiceOrbControl : FrameworkElement
{
    public static readonly DependencyProperty AmplitudeProperty = DependencyProperty.Register(nameof(Amplitude), typeof(double), typeof(VoiceOrbControl), new PropertyMetadata(0.0));
    public static readonly DependencyProperty IsListeningProperty = DependencyProperty.Register(nameof(IsListening), typeof(bool), typeof(VoiceOrbControl), new PropertyMetadata(false, (d, _) => ((VoiceOrbControl)d).UpdateSubscription()));
    public double Amplitude { get => (double)GetValue(AmplitudeProperty); set => SetValue(AmplitudeProperty, value); }
    public bool IsListening { get => (bool)GetValue(IsListeningProperty); set => SetValue(IsListeningProperty, value); }

    private readonly SolidColorBrush _glowBrush, _coreBrush;
    private TimeSpan _lastRenderingTime = TimeSpan.MinValue;
    private bool _isSubscribed, _listeningMotion;
    private double _smoothedLevel, _phase;

    public VoiceOrbControl()
    {
        _glowBrush = new SolidColorBrush(Color.FromArgb(90, 59, 130, 246)); _glowBrush.Freeze();
        _coreBrush = new SolidColorBrush(Color.FromRgb(59, 130, 246)); _coreBrush.Freeze();
        Loaded += (_, _) => { if (!_listeningMotion) { MotionSettings.Instance.PropertyChanged += OnMotionChanged; _listeningMotion = true; } UpdateSubscription(); };
        Unloaded += (_, _) => { Detach(); if (_listeningMotion) { MotionSettings.Instance.PropertyChanged -= OnMotionChanged; _listeningMotion = false; } };
        IsVisibleChanged += (_, _) => UpdateSubscription();
    }

    private void OnMotionChanged(object? s, PropertyChangedEventArgs e) => UpdateSubscription();

    private void UpdateSubscription()
    {
        bool run = IsLoaded && IsVisible && IsListening;
        if (run && !_isSubscribed) { _lastRenderingTime = TimeSpan.MinValue; CompositionTarget.Rendering += OnRendering; _isSubscribed = true; }
        else if (!run && _isSubscribed) { Detach(); _smoothedLevel = 0; InvalidateVisual(); }
    }

    private void Detach() { if (_isSubscribed) { CompositionTarget.Rendering -= OnRendering; _isSubscribed = false; } }

    private void OnRendering(object? s, EventArgs e)
    {
        if (e is not RenderingEventArgs args || args.RenderingTime == _lastRenderingTime) return;
        double dt = _lastRenderingTime == TimeSpan.MinValue ? 1.0 / 60.0 : Math.Clamp((args.RenderingTime - _lastRenderingTime).TotalSeconds, 0.001, 0.05);
        _lastRenderingTime = args.RenderingTime;

        _smoothedLevel += (Math.Clamp(Amplitude, 0.0, 1.0) - _smoothedLevel) * (1.0 - Math.Exp(-14.0 * dt));
        _phase = MotionSettings.Instance.AllowMotion ? (_phase + dt * 2.4) % (Math.PI * 2) : 0;
        InvalidateVisual();
    }

    protected override void OnRender(DrawingContext dc)
    {
        double r = Math.Min(ActualWidth, ActualHeight) * 0.5;
        if (r <= 0) return;
        var c = new Point(ActualWidth * 0.5, ActualHeight * 0.5);
        double pulse = MotionSettings.Instance.AllowMotion ? Math.Sin(_phase) * 0.04 : 0.0;
        dc.DrawEllipse(_glowBrush, null, c, r * (0.65 + 0.30 * _smoothedLevel + pulse), r * (0.65 + 0.30 * _smoothedLevel + pulse));
        dc.DrawEllipse(_coreBrush, null, c, r * (0.42 + 0.12 * _smoothedLevel), r * (0.42 + 0.12 * _smoothedLevel));
    }
}
```

---

## 6. Performance on Integrated GPUs & Profiling Tools

- **Check `RenderCapability.Tier >> 16`:** `2` = Full DX9+ HW, `1` = Partial HW, `0` = Software fallback (RDP/VM/driver reset). Cut animations to instant/83ms fades on Tier 0 and subscribe to `RenderCapability.TierChanged`.
- **Down-throttle ambient animations:** Put `Timeline.DesiredFrameRate="30"` on background shimmers/pulses so interactive `60–120 fps` UI stays fluid.
- **`BitmapCache` / `CacheMode`:** Helps when translating/fading a static complex card; **destroys iGPU bandwidth** if placed on containers whose children change every frame (streaming text, visualizers, scrolling lists)!
- **`Freeze()` everything static:** Freeze programmatic `Brush`, `Pen`, `Geometry`, `Transform`, `KeySpline`s, and add `po:Freeze="True"` in `App.xaml`.
- **Profiling tools on `.NET 9/10`:** Use **Visual Studio Application Timeline**, **VS Live Visual Tree**, **VS Diagnostic Tools**, **PerfView** (`Microsoft-Windows-WPF`), and **WPR / WPA**. Legacy *WPF Performance Suite (`Perforator` / `Visual Profiler`)* is **obsolete and fails to attach to `.NET 8–10` processes**.

---

## 7. Motion Accessibility & Bug Checklist

- **Respect Windows "Animation effects":** Bind/listen to **`SystemParameters.ClientAreaAnimation`** (`SPI_GETCLIENTAREAANIMATION = 0x1042`) via `SystemParameters.StaticPropertyChanged` (plus optional `UISettings.AnimationsEnabled`).
- **Reduced motion != frozen UI:** Replace sliding/zooming/floating loops with instant swaps (`Duration="0"`) or subtle `<= 83 ms` opacity cues.
- **WCAG 2.3.1 (Photosensitivity):** Never flash high-contrast luminance or saturated red **more than 3 times per second**; keep pulsing indicators calm (`<= 1–2 Hz`).

### Pre-Ship Animation Checklist
- [ ] No `EventTrigger RoutedEvent="Loaded"` with `RepeatBehavior="Forever"` on `Visibility`-toggled elements (`MultiDataTrigger` on `IsVisible && AllowMotion` + `<StopStoryboard>`).
- [ ] Every `CompositionTarget.Rendering` handler dedupes `RenderingTime`, computes bounded `dt`, sleeps at zero amplitude, and detaches on `!IsVisible` / `Unloaded`.
- [ ] Zero per-frame `DropShadowEffect.BlurRadius` or `Border.Height`/`Width`/`Margin` mutations inside 60 FPS loops.
- [ ] Zero animations targeting frozen `StaticResource` brushes (overlay opacity or `.Clone()`).
- [ ] `RenderTransformOrigin="0.5,0.5"` on scale/rotate elements; no WinUI `<VisualState.Setters>`; `FillBehavior="Stop"` or `BeginAnimation(..., null)` releasing held clocks.
