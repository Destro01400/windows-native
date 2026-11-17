# Windows 11 & Fluent 2 Design System, Tokens, and UX Patterns

> **Scope:** Visual, spatial, typographic, color, material, and UX specifications for Windows 11 and Fluent 2, adapted for C# + XAML desktop apps (both stock Fluent and custom brand themes).

## Table of Contents

1. [Design Principles (and Custom Brand Rules)](#1-design-principles-and-custom-brand-rules)
2. [Layout, Effective Pixels, 4px Grid & Breakpoints](#2-layout-effective-pixels-4px-grid--breakpoints)
3. [Typography & Custom Brand Fonts](#3-typography--custom-brand-fonts)
4. [Color Hierarchy, Accent Shades & WCAG Contrast](#4-color-hierarchy-accent-shades--wcag-contrast)
5. [Geometry, Corner Radius & Elevation Strokes](#5-geometry-corner-radius--elevation-strokes)
6. [Materials, Layering & Elevation Scale](#6-materials-layering--elevation-scale)
7. [Iconography & App Icons](#7-iconography--app-icons)
8. [Navigation, Commanding & Transient Surfaces](#8-navigation-commanding--transient-surfaces)
9. [Wait UX, Empty/Error/Offline States & Writing Style](#9-wait-ux-emptyerroroffline-states--writing-style)
10. [Control Density, Touch Targets, Focus Visuals & Settings Cards](#10-control-density-touch-targets-focus-visuals--settings-cards)

---

## 1. Design Principles (and Custom Brand Rules)

Windows 11 rests on five OS principles paired with four Fluent 2 design pillars:

| Principle | Meaning in Practice | How to Apply in a Custom-Themed WPF App |
|---|---|---|
| **Effortless** | Focus on the task; progressive disclosure; crisp `83–250 ms` motion. | Avoid multi-row chrome or permanent telemetry clutter; use `ICommand` shortcuts and overflow menus. |
| **Calm** | Restrained neutrals, soft `4px`/`8px` geometry, quiet surfaces. | **Never flood backgrounds with brand accent color.** Keep brand warmth in subtle tinted neutrals (`Surface0..4`) and reserve saturated `Accent` for primary CTAs, active borders, and focus indicators. |
| **Personal** | Adapts to Light/Dark, Contrast themes, DPI, and Windows text scale. | Avoid hardcoded hexes in views; bind via `{DynamicResource}` and respond to OS accessibility/theme signals. |
| **Familiar** | Predictable window silhouette, title bar placement, standard shortcuts. | Even with custom `WindowChrome`, preserve Snap Layouts, double-click maximize, system menu, `Ctrl+C/F/S/W`, `Esc`, `F6`. |
| **Complete & Coherent** | Every dialog, popup, list, and fallback matches the same system. | Reuse native/Fluent patterns ~80% of the time; style **all** built-in controls (`ComboBox`, `CheckBox`, `Slider`, `ScrollBar`, `Expander`) so unstyled Windows Aero controls never leak into branded cards. |

---

## 2. Layout, Effective Pixels, 4px Grid & Breakpoints

### 2.1 Effective Pixels (epx / WPF DIPs) & the 4px Base Grid

- Windows uses **effective pixels (`epx`)** — equivalent to WPF **Device-Independent Pixels (`1/96 inch`)** — across 10 scaling plateaus: `100%`, `125%`, `150%`, `175%`, `200%`, `225%`, `250%`, `300%`, `350%`, `400%`.
- **Why everything aligns to multiples of `4`:** Every Windows scaling plateau multiplies `4` into an exact integer (`4 × 1.25 = 5`, `4 × 1.5 = 6`, `4 × 1.75 = 7`, `4 × 2.25 = 9`), preventing half-pixel edge blur on borders, paddings, and icons.
- **Only three intentional `2px` exceptions** exist (`2`, `6`, `10`) for icon-box optical alignment so the outer control lands back on a `4px` multiple.
- Enable `UseLayoutRounding="True"` and `SnapsToDevicePixels="True"` at the root `Window` / control templates so `1px` hairline borders never blur at `125%`–`175%`.

### 2.2 Fluent 2 Global Spacing Ramp

| Token Concept | Value | Standard Usage |
|---|---|---|
| `SpaceNone` | `0` | Flush edges, split-button seams |
| `SpaceXXS` | `2` | Optical icon nudge (`2px` exception) |
| `SpaceXS` | `4` | Base grid unit; icon-to-label gap (`4–8`), header-to-input (`4`), spacing between Settings cards (`4`) |
| `SpaceSNudge` | `6` | Tight toolbar/tab padding (`6px` exception) |
| `SpaceS` | `8` | Gap between sibling buttons (`8`), control-to-header (`8`), dialog button spacing (`8`), button-to-flyout (`8`) |
| `SpaceMNudge` | `10` | Compact badge/toggle alignment (`10px` exception) |
| `SpaceM` | `12` | Gap between cards/sections (`12`), label-to-control (`12`), small-window margins (`12`), tight editor margins |
| `SpaceL` | `16` | Surface-to-edge card padding (`16`), expander content padding (`16`), control-to-chevron (`16`) |
| `SpaceXL` | `20` | Generous card padding (`20`), major section gaps |
| `SpaceXXL` | `24` | `ContentDialog` padding (`24`), standard desktop window gutters (`24`), `BreadcrumbBar` side margins (`24`) |
| `SpaceXXXL` | `32` | Standard control height (`32`), large section separation (`32`) |
| Rail / Margin | `48` / `56` | Compact nav rail width (`48`), expanded app silhouette content margin (`56`) |

### 2.3 Breakpoints, Min Width & Responsive Patterns

| Window Width (`epx` / DIP) | Class | Margin / Gutter | Layout Strategy |
|---|---|---|---|
| `<= 640` | **Small** | `12` | Stack panels vertically; collapse left nav into overlay hamburger; single-pane list or detail. |
| `641 – 1007` | **Medium** | `24` | Compact `48px` icon nav rail; balanced 2-column splits where readable. |
| `>= 1008` | **Large** | `24` (or `56` content margin) | Expanded sidebar (`~220–260px`) + full workspace; cap readable prose / settings width (`~860–1000px`). |

- **Snap Layout Width Rule:** Keep `Window.MinWidth <= 500` (ideally **`<= 330`**) so Windows 11 Snap Layouts offer 2-, 3-, and 4-zone splits cleanly.
- **Five Responsive Techniques:**
  1. **Reposition** (stack vertical -> horizontal row),
  2. **Resize** (fluid `*` tracks + clamped reading width),
  3. **Reflow** (1-col list -> multi-col grid via `WrapPanel` or responsive columns),
  4. **Show/Hide** (drop non-essential metadata columns/timestamps below `640px`),
  5. **Re-architect** (side-by-side master/detail -> single-pane drill-in below `640px`).

### 2.4 Two-Layer Architecture & Alignment

- **Base Layer (`Surface0`/`Surface1` or Mica):** Window foundation, title bar, navigation pane, `MenuBar`, `CommandBar`.
- **Content Layer (`Surface2`/Cards):** Primary workspace canvas or elevated card containers (`CornerRadius="8,0,0,0"` where a full-bleed content canvas meets a left/top navigation pane).
- **Alignment:** Left-align text in LTR (`Right` in RTL); center-align only short labels under icons or focal empty-state callouts. Align **icons centrally** inside fixed-width boxes (`40px`) so text columns align vertically down a list.

---

## 3. Typography & Custom Brand Fonts

### 3.1 Official Windows 11 Type Ramp

> **Rule:** Native Windows 11 excludes **Bold (`700`)** and **Italic** from standard UI chrome. Use **Semibold (`600`)** for hierarchy and avoid italic UI labels (harder to read for dyslexia).

| Style Name | WinUI Resource Key | Weight | Size / Line Height (`epx`) | Typical Role |
|---|---|---|---|---|
| **Caption** | `CaptionTextBlockStyle` | Regular (`400`) | **`12 / 16`** | Metadata, timestamps, title bar text, badges |
| **Body** | `BodyTextBlockStyle` | Regular (`400`) | **`14 / 20`** | Standard UI copy, inputs, list primary text, settings descriptions |
| **Body Strong** | `BodyStrongTextBlockStyle` | Semibold (`600`) | **`14 / 20`** | Card titles, subsection headers, settings group titles |
| **Body Large** | `BodyLargeTextBlockStyle` | Regular (`400`) | **`18 / 24`** | Lead paragraphs |
| **Body Large Strong** | `BodyLargeStrongTextBlockStyle` | Semibold (`600`) | **`18 / 24`** | Emphasized subheadings |
| **Subtitle** | `SubtitleTextBlockStyle` | Semibold (`600`) | **`20 / 28`** | Modal/dialog titles (`ContentDialog`), section headers |
| **Title** | `TitleTextBlockStyle` | Semibold (`600`) | **`28 / 36`** | Top-of-page headers |
| **Title Large** | `TitleLargeTextBlockStyle` | Semibold (`600`) | **`40 / 52`** | Hero page headers |
| **Display** | `DisplayTextBlockStyle` | Semibold (`600`) | **`68 / 92`** | Editorial/hero callout numbers |

*(Note: Fluent 2 Web adds intermediate `10/14` Caption 2, `16/22` Subtitle 2, `24/32` Title 3, `32/40` Title 1 and `Bold` `"Stronger"` tokens; in Windows native apps keep body >= `14` and captions >= `12`, never below `12px` Regular / `14px` Semibold.)*

- **Line Length:** Keep body prose to **`50–60` characters per line** (never `< 20` or `> 75` for long reading).
- **Casing:** **Sentence case everywhere** — titles, buttons, tabs, tooltips, settings labels. Avoid `ALL CAPS` except intentionally styled micro-eyebrow labels (`10–11px` monospace tags if part of an editorial brand).

### 3.2 Using Custom Brand Fonts in WPF (.NET 10)

1. **Embed cleanly as `<Resource>`** (not `<EmbeddedResource>`): reference in XAML as `pack://application:,,,/<Assembly>;component/Fonts/#<Internal Family Name>`, and in C# via `new FontFamily(new Uri("pack://application:,,,/"), "./Fonts/#<Internal Family Name>")` (passing a single pack string to `new FontFamily(string)` is documented invalid!).
2. **Always declare an international fallback chain:** Custom fonts rarely ship CJK, Arabic, Thai, or Indic glyphs. Append system fallbacks:
   ```xml
   <FontFamily x:Key="FontSans">
       pack://application:,,,/MyApp;component/Fonts/#Work Sans, Segoe UI Variable Text, Segoe UI, Yu Gothic UI, Microsoft YaHei UI, Malgun Gothic, Nirmala UI
   </FontFamily>
   ```
3. **Explicitly set `LineHeight` + `LineStackingStrategy="BlockLineHeight"`** in `TextBlock` ramp styles because WPF does not automatically apply Windows `14/20` or `20/28` leading from `FontSize` alone.
4. **Respect Windows Text Scaling (`Make text bigger`):** WPF does **not** scale `FontSize` automatically with `UISettings.TextScaleFactor` (`1.0–2.25`). Hook `UISettings.TextScaleFactorChanged` (`net10.0-windows10.0.19041.0`+) and update `DynamicResource` font size tokens proportionally (attenuating display sizes so headers don't overflow).
5. **Licensing:** Never embed or redistribute `Segoe UI`, `Segoe UI Variable`, or `Segoe Fluent Icons`; reference them by installed name only.

---

## 4. Color Hierarchy, Accent Shades & WCAG Contrast

### 4.1 Light vs. Dark Value Rules (Windows Native vs. Web)

- **Depth hierarchy:** In **both** Light and Dark modes, **recessed base layers are slightly darker** and **elevated cards/controls are brighter** (`Surface0` -> `Surface2`).
- **Control interaction state asymmetry:**
  - **Light mode:** Controls dim slightly on hover/press (`#B3FFFFFF` -> `#80F9F9F9` -> `#4DF9F9F9`, or warm cream -> deeper inset).
  - **Dark mode (CRITICAL difference from web):** Windows native subtle/neutral controls **brighten** on hover (`#0FFFFFFF` -> `#15FFFFFF`), then dim on press (`#08FFFFFF`).
- **Colorblindness rule:** ~8% of men and ~0.5% of women have red-green colorblindness. **Never communicate status by color alone** — always pair color with an icon, text label, or distinct border/shape.

### 4.2 Official WinUI 3 Reference Palette (`Common_themeresources_any.xaml`)

| Semantic Token | Dark Theme | Light Theme | Purpose |
|---|---|---|---|
| `TextFillColorPrimary` | `#FFFFFFFF` | `#E4000000` | Primary titles & body |
| `TextFillColorSecondary` | `#C5FFFFFF` | `#9E000000` | Subtitles, descriptions (verify >= 4.5:1!) |
| `TextFillColorTertiary` | `#87FFFFFF` | `#72000000` | Watermarks / subtle metadata (large text/icons only if < 4.5:1) |
| `TextFillColorDisabled` | `#5DFFFFFF` | `#5C000000` | Disabled controls only |
| `ControlFillColorDefault` | `#0FFFFFFF` | `#B3FFFFFF` | Control rest fill |
| `ControlFillColorSecondary` | `#15FFFFFF` | `#80F9F9F9` | Control hover fill (brightens in Dark!) |
| `ControlFillColorTertiary` | `#08FFFFFF` | `#4DF9F9F9` | Control pressed fill |
| `ControlFillColorDisabled` | `#0BFFFFFF` | `#4DF9F9F9` | Control disabled fill |
| `SubtleFillColorSecondary` / `Tertiary` | `#0FFFFFFF` / `#0AFFFFFF` | `#09000000` / `#06000000` | Transparent/icon button hover & press |
| `SolidBackgroundFillColorBase` | `#FF202020` | `#FFF3F3F3` | Mica fallback / app base canvas |
| `CardBackgroundFillColorDefault` | `#0DFFFFFF` | `#B3FFFFFF` | Elevated cards |
| `LayerFillColorDefault` | `#4C3A3A3A` | `#80FFFFFF` | Content layer over Mica |
| `SmokeFillColorDefault` | `#4D000000` | `#4D000000` | Modal backdrop scrim (both themes) |
| `ControlStrokeColorDefault` | `#12FFFFFF` | `#0F000000` | Control hairline outline |
| `DividerStrokeColorDefault` | `#15FFFFFF` | `#0F000000` | 1px divider |
| `SystemFillColorSuccess` / `Background` | `#6CCB5F` / `#393D1B` | `#0F7B0F` / `#DFF6DD` | Success indicator & soft pill |
| `SystemFillColorCaution` / `Background` | `#FCE100` / `#433519` | `#9D5D00` / `#FFF4CE` | Warning indicator & soft pill |
| `SystemFillColorCritical` / `Background` | `#FF99A4` / `#442726` | `#C42B1C` / `#FDE7E9` | Error indicator & soft pill |

### 4.3 Accent Color Shade Rules & WCAG Contrast Math

- Windows generates 6 shades around `SystemAccentColor` (`Light1..3`, `Dark1..3`, exposed in WPF .NET 9+ via `SystemColors.AccentColor*`):
  - **Light theme:** Use `Dark1` for primary fills (`#FFFFFF` text on top), `Dark2`/`Dark3` for accent links/text so contrast stays `>= 4.5:1`.
  - **Dark theme:** Use `Light2` for primary fills (with `#000000` dark text on top if bright!) and `Light3` for accent text.
- **WCAG 2.1 Minimum Contrast Ratios:**
  - Normal body/caption/label text (`< 18.67px` bold or `< 24px` regular): **`>= 4.5:1`** (AA).
  - Large text (`>= 24px` regular or `>= 18.67px` bold) & UI borders/icons conveying state: **`>= 3.0:1`**.
  - **Soft-badge trap:** Bright status foregrounds (`#059669`, `#D97706`, `#EF4444`) on pastel soft backgrounds (`#DCFCE7`, `#FEF3C7`, `#FEE2E2`) or white text on `#EF4444` routinely fall to `2.8:1–3.8:1`. Pair pastel badges with darker text tokens (`#047857`, `#92400E`, `#B91C1C`) or neutral `TextPrimary`!
- **High Contrast Themes (`Aquatic`, `Desert`, `Dusk`, `Night sky`):**
  - Never invent High Contrast colors — map all brushes in `Brushes.HighContrast.xaml` to `SystemColors.WindowBrushKey`, `WindowTextBrushKey`, `ControlBrushKey`, `ControlTextBrushKey`, `HighlightBrushKey`, `HighlightTextBrushKey`, `GrayTextBrushKey` (strictly disabled only!), `HotTrackBrushKey` (hyperlinks only!).
  - Reset secondary text opacity to **`1.0`** in High Contrast (opacity `< 1` breaks contrast in *Desert*), remove inline `Foreground` overrides inside `ListBoxItem` `DataTemplate`s so selection highlight inverts cleanly, and bump popup/card strokes to `2px`.

---

## 5. Geometry, Corner Radius & Elevation Strokes

### 5.1 Corner Radius Standard

| Surface / Control | Windows 11 Standard | Custom Brand Adaptation Rule |
|---|---|---|
| Top-level Windows, Dialogs, Flyouts, Context Menus | **`8px`** (`OverlayCornerRadius`) | May soften to `14–18px` for editorial/warm brand cards, **provided nested radii stay concentric**. |
| In-page Controls (`Button`, `TextBox`, `ComboBox`, `ListBoxItem`) | **`4px`** (`ControlCornerRadius`) | Keep controls consistently smaller than parent containers (`8–12px` max if cards are `16px`). |
| `ToolTip` exception | **`4px`** | Always tighter than flyouts so tooltips read as transient labels, not interactive menus. |
| Thin tracks / Selection pills | `1.5–2px` | `3px` tall `ProgressBar` -> `1.5px`; left nav active pill (`3x16px`) -> `1.5–2px`. |
| Circular / Pill elements | `Height / 2` | Round icon buttons, toggle tracks, status pills. |
| **Snapped / Maximized Window & Touching Seams** | **`0px`** | Reset outer window border radius to `0` when `WindowState == Maximized` or snapped. |

- **Concentric Nested Radius Rule:** `innerRadius = max(0, outerRadius - padding)`. E.g., a `16px`-radius card with `12px` padding frames a `4–8px`-radius inner inset nicely; never put a `16px` child tightly inside a `16px` parent with `4px` gap (looks pinched at corners).

### 5.2 Directional 1px Elevation Bezel (`ControlElevationBorderBrush`)

Windows 11 replaces heavy drop shadows on buttons/inputs with a **`1px` vertical linear gradient stroke** simulating overhead light:
- **Light theme:** Bottom edge is slightly darker (`ControlStrokeColorSecondary` `#29000000`) fading up to `ControlStrokeColorDefault` (`#0F000000`).
- **Dark theme:** Top edge catches a subtle `1px` specular highlight (`#18FFFFFF`) fading down to `#12FFFFFF`.
- **`TextBox` focus cue:** Rest = `1px` bezel; Focused = `BorderThickness="1,1,1,2"` with a `2px` solid bottom `Accent` stroke.

---

## 6. Materials, Layering & Elevation Scale

| Material | Visual Recipe & Behavior | Valid Uses | Anti-Patterns |
|---|---|---|---|
| **Mica** (`DWMSBT_MAINWINDOW=2`) | Opaque sampling of desktop wallpaper; auto-dims to solid neutral when window is inactive. | Main window base layer & title bar (`Window.Background=Transparent`, `GlassFrameThickness=-1`). | Never apply to inner controls or with `AllowsTransparency="True"`. |
| **Mica Alt** (`DWMSBT_TABBEDWINDOW=4`) | Deeper wallpaper tint for stronger contrast against tabbed headers. | Tabbed apps (`TabView` in title bar), multi-pane shells. | Don't use without separating commanding/content layers. |
| **Background Acrylic** (`DWMSBT_TRANSIENTWINDOW=3`) | Real-time translucent blur + exclusion + tint + noise. | Transient flyouts, context menus, `ComboBox` popups. | **Never** paint the main app background with Acrylic (causes visual fatigue & GPU cost). |
| **Smoke** (`#4D000000`) | 30% black translucent overlay (both themes). | Behind **modal** dialogs (`ContentDialog`) to lock background UI. | Never behind light-dismiss flyouts/popups. |

### Elevation Hierarchy (`ThemeShadow` vs. WPF)

| Layer | Z-Depth | Border / Shadow Guidance in WPF |
|---|---|---|
| **Base -> Content Layer** | `1` | Value step + `1px` hairline border (no shadow). |
| **In-Page Controls** | `2` -> `1` (pressed) | `1px` directional bezel; flatten shadow/bezel on press. |
| **Cards** | `8` | Prefer **surface value step + `1px` border** (`CardStrokeColor`). **Avoid attaching `DropShadowEffect` to every item inside scrolling lists** — it multiplies GPU shader passes on integrated GPUs! |
| **Tooltips / Nav Overlay** | `16` | Subtle shadow on transient overlay only. |
| **Flyouts / Menus / Dialogs** | `32` / `128` | `Popup` / modal overlay over `#4D000000` Smoke; restrained `DropShadowEffect` (`BlurRadius="16..20"`, `Opacity="0.12..0.22"`) frozen on one backdrop border. |

*(For opaque custom brand palettes without Mica, retain the exact same 2-layer luminance step between base/sidebar and cards, and still dim inactive title-bar text/icons to `~0.55` opacity when `Window.IsActive == false`.)*

---

## 7. Iconography & App Icons

- **Font Icons (`Segoe Fluent Icons` / `Material Icons Outlined`):**
  - Snap icon sizes to crisp grid steps: **`16`, `20`, `24`, `32`, `40`, `48`, `64`** epx (`16px` for title bar/toolbar/inline buttons, `20px` for `InfoBar`/nav, `12px` for non-interactive status badges only).
  - Always provide fallback for `Segoe Fluent Icons`: `FontFamily="Segoe Fluent Icons, Segoe MDL2 Assets"` (Windows 10 lacks `Segoe Fluent Icons`).
  - **One icon system per app:** Pick either `Segoe Fluent Icons` or one embedded vector icon font — **never mix raw Unicode emojis** (`⚡`, `▶`, `⏸`, `✓`) into UI buttons alongside crisp monochrome vector icons.
  - Use **Regular (outline)** for default states and **Filled** or accent-tinted layered glyphs for active/selected states. Mirror directional arrows when `FlowDirection="RightToLeft"`.
  - Icon-only buttons **must** carry both `ToolTip` and `AutomationProperties.Name`. In **WPF**, place decorative icon `TextBlock`s inside the button's `ControlTemplate` (so `TextBlockAutomationPeer.IsControlElementCore()` returns `false` automatically) or set `IsHitTestVisible="False"` with a decorative peer (`AutomationProperties.AccessibilityView="Raw"` is **WinUI 3 only**!).
- **Vector vs. SVG vs. `.ico`:**
  - Simple/monochrome custom brand marks -> XAML `<Path Data="..." />` (frozen `StreamGeometry`).
  - Complex multi-color illustrations -> `SharpVectors.Wpf` (`1.8.6`, BSD-3-Clause, supports `net10.0-windows`).
  - App `.ico` -> bundle **`16`, `24`, `32`, `48`, `256 px`** RGBA frames (PNG-compressed 256px) on a `48x48` design grid with `>= 3:1` contrast over both light and dark taskbars and **no text/letters**.

---

## 8. Navigation, Commanding & Transient Surfaces

### 8.1 Navigation Selection

- **Left Nav (`NavigationView` style):** Best for `>= 5` top-level views; `Compact` rail = `48px` wide, item `MinHeight=36`, active indicator pill `3x16px` (`CornerRadius="1.5"`), Settings pinned at bottom.
- **Top Nav:** Maximize vertical workspace when categories fit cleanly in a single `48px` top bar.
- **`TabView`:** Dynamic user-managed documents/sessions (`MinHeight=32`, width `100–240`, `Ctrl+T`, `Ctrl+W`, `Ctrl+Shift+T`, `Ctrl+1..9`).
- **`BreadcrumbBar`:** Mandatory when navigation exceeds **2 levels deep**; collapse leftmost crumbs into an ellipsis menu when narrow.

### 8.2 Confirmations vs. Undo (`commanding-basics.md` + NN/g)

- **Prefer Undo over confirmation** for reversible actions (archiving, deleting to trash, clearing a filter): execute immediately and surface a non-blocking snackbar with **`Undo`** (`4–6 s`).
- **Require a modal confirmation dialog ONLY** for irreversible or high-impact actions (permanent deletion, overwriting files, remote shell execution, unsaved loss on exit).
- State the exact consequence and item name (`"Delete conversation 'Architecture notes' (24 messages) permanently?"`), use call-and-response verb buttons (**`Delete`** / **`Keep`**, never `Yes`/`No` or `OK`), and **never** mark the destructive button `IsDefault="True"`.

### 8.3 Transient UI Decision Matrix

| Surface | Dismissal | Use For | Never Use For |
|---|---|---|---|
| **Modal Dialog (`ContentDialog` style)** | Explicit button click only (`Smoke` scrim behind, `Min 320`, `Max 548`, `Padding 24`) | Blocking critical errors, permanent delete confirmations, security approvals | Inline form validation, routine click feedback |
| **Flyout / Popup** | Light-dismiss (outside click, `Esc`) | Quick pickers (model/voice selector), lightweight filters, rich previews | Long persistent workflows, blocking choices |
| **Context Menu** | Light-dismiss (`Right-click`, `Shift+F10`) | Secondary object actions; place top commands (Copy/Cut/Paste) in an optional horizontal icon strip | Essential commands invisible elsewhere |
| **`InfoBar` Banner** | Inline (pushes layout, never floats over text); optional close `X` | Persistent workspace states: WebSocket offline, rate limit, sync error, pending queue | Transient "Copied!" confirmations (use temporary toast/inline swap) |
| **`TeachingTip`** | Targeted callout (`Width 320–336`, `8px` beak) | Non-blocking onboarding or feature discovery | Critical errors or blocking alerts |
| **`ToolTip`** | Hover / keyboard focus (`CornerRadius="4"`) | Labeling icon-only buttons, showing keyboard shortcuts (`"Send (Enter)"`) | Essential instructions, clickable links, duplicating visible text |

---

## 9. Wait UX, Empty/Error/Offline States & Writing Style

### 9.1 Response-Time & Loading Rules (Fluent 2 + Nielsen)

| Delay | User Perception | Required Pattern |
|---|---|---|
| **`< 0.1 s`** | Instantaneous | Direct update; zero spinner. |
| **`0.1 – 1.0 s`** | Noticeable, uninterrupted | **Show no spinner or skeleton** — flashing a loader for 300ms creates jitter. |
| **`1.0 – 3.0 s`** | Short wait | Indeterminate spinner/ring + present-participle label (`"Loading conversations…"`). |
| **`> 3.0 – 10+ s`** | Attention drifts | **Determinate `ProgressBar`** (`MinHeight=3`, `%` + ETA) or **Skeleton Shimmer** (matching card wireframe) + **`Cancel` button** so the user stays unblocked. |

- **Virtualized lists:** Show **one** progress bar at the top of the collection — never render spinners on every individual placeholder row.

### 9.2 Empty, Offline & Error States

- **Empty State (first-run) vs. No Search Results:**
  - *First-run:* Friendly icon + 1-line explanation + 1–3 starter CTAs.
  - *Empty filter/search:* Explicitly echo the query (`"No results for '...'"`) + **`Clear filters`** button.
- **Offline / Disconnected State:** Show a persistent non-blocking `InfoBar` (`"Offline — trying to reconnect…"` + **`Reconnect`**). **Never** wipe the user's draft input or block browsing cached history.
- **Inline Validation & Error Copy:** Validate fields on blur/submit (never on empty initial focus). Write in active, blame-free language addressing the user ("you"): *(What happened)* + *(Impact)* + *(Next step)*, tucking raw exceptions/codes under an expandable `"Technical details"`.

### 9.3 Microcopy Punctuation & Settings Pages

- **Sentence case** on everything. Periods on full sentences in descriptions, errors, and dialogs; **no periods** on buttons, headers, labels, check boxes, or short fragments.
- **Buttons:** 1–2 active verbs (`"Save"`, `"New chat"`, `"Run now"`).
- **Windows 11 Settings Pages:** Single scrollable column (`MaxWidth="1000"`), `BodyStrong` section headers (`14/20 SemiBold`), `SettingsCard` rows (`4px` vertical gap, concise noun title + explanatory description + right-aligned control, max 1 expander nesting level), **apply immediately** without a global Save button, and end with an **"About"** expander.

---

## 10. Control Density, Touch Targets, Focus Visuals & Settings Cards

- **Hit Targets:** Minimum **`40 × 40 epx`** for icon/square buttons (or **`32px` tall** when `Width >= 120`, e.g., wide menu rows/checkboxes); **`44 × 44 epx`** touch-optimal with **`>= 4px` gap** between adjacent controls.
  - *Compact icon buttons (`24–30px` visual badge):* Give the `ControlTemplate` a `Background="Transparent"` outer `Border` padded out to `32–40px` hit target so visual compactness doesn't hurt pointer/touch accuracy.
- **Two Official Density Tiers:** Standard (`32px` TextBox/Button height) vs. Compact (`24px` TextBox height for dense data grids/inspector panels).

### 10.1 Compile-Verified Dual-Stroke Keyboard Focus Visual (`Windows11FocusVisual`)

Windows uses a **2px outer stroke** + **1px inner stroke** so keyboard focus stays visible over any background (`FocusVisualStyle` renders on the Adorner layer **only for keyboard navigation**, staying invisible on mouse clicks):

```xml
<Style x:Key="Windows11FocusVisual">
    <Setter Property="Control.Template">
        <Setter.Value>
            <ControlTemplate>
                <Border Margin="-3"
                        BorderThickness="2"
                        BorderBrush="{DynamicResource FocusOuterBrush}"
                        CornerRadius="6"
                        SnapsToDevicePixels="True">
                    <Border BorderThickness="1"
                            BorderBrush="{DynamicResource FocusInnerBrush}"
                            CornerRadius="4" />
                </Border>
            </ControlTemplate>
        </Setter.Value>
    </Setter>
</Style>
```

### 10.2 Windows 11 `SettingsCard` Row Pattern (WPF XAML)

```xml
<Border Background="{DynamicResource CardSurfaceBrush}"
        BorderBrush="{DynamicResource CardStrokeBrush}"
        BorderThickness="1" CornerRadius="8" Padding="16,12" Margin="0,0,0,4">
    <Grid ColumnDefinitions="Auto, *, Auto">
        <TextBlock Grid.Column="0" FontFamily="{StaticResource SymbolThemeFontFamily}"
                   FontSize="16" Text="&#xE790;" Margin="0,0,16,0" VerticalAlignment="Center" />
        <StackPanel Grid.Column="1" VerticalAlignment="Center" Margin="0,0,16,0">
            <TextBlock Text="Theme" Style="{StaticResource BodyTextBlockStyle}" />
            <TextBlock Text="Choose light, dark, or Windows system appearance"
                       Style="{StaticResource CaptionTextBlockStyle}" />
        </StackPanel>
        <ComboBox Grid.Column="2" MinWidth="160" VerticalAlignment="Center"
                  SelectedIndex="{Binding SelectedThemeIndex}" />
    </Grid>
</Border>
```
