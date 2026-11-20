#!/usr/bin/env python3
"""Static auditor for Windows desktop apps (WPF, WinUI 3, C++/WinRT, .csproj, app.manifest, C# & WebView2).

UI / XAML Checks (also runnable alone via --ui-only or audit_wpf_ui.py):
  1. WCAG 2.1 contrast ratios for palette brush pairs in ResourceDictionaries.
  2. Missing po:Freeze="True" on static WPF SolidColorBrush / DropShadowEffect resources.
  3. Hardcoded hex colors in Views/Controls XAML and unfrozen new SolidColorBrush in C#.
  4. Virtualization killers (<ScrollViewer> wrapping <ItemsControl>/<ListBox>, CanContentScroll="False").
  5. Expensive DropShadowEffect or shadow resource inside ItemTemplate/DataTemplate.
  6. Animation & rendering traps (RepeatBehavior="Forever" on Loaded, CompositionTarget.Rendering without
     unsubscribe / RenderingTime dedupe, BlurRadius or .Height mutations in render callbacks, VisualState.Setters).
  7. WindowChrome & DWM traps (AllowsTransparency="True", missing IsHitTestVisibleInChrome, missing HTMAXBUTTON).
  8. Accessibility gaps (icon-only Buttons missing AutomationProperties.Name, FocusVisualStyle="{x:Null}",
     clickable Border MouseLeftButtonDown/MouseBinding, WinUI-only AccessibilityView in WPF XAML).
  9. WPF runtime traps (Panel.Children[i] = x assignment, ApplicationIdle PushFrame with active Rendering loops).

Windows App Engineering Checks (default full mode):
  10. [.csproj] PublishTrimmed/PublishAot on WPF (NETSDK1168), [LibraryImport] without AllowUnsafeBlocks,
      CommunityToolkit.Mvvm < 8.4.2 with partial [ObservableProperty] (CS9248), missing ApplicationManifest
      on WinExe, PublishSingleFile warnings, missing PublishReadyToRun info note.
  11. [app.manifest] Missing PerMonitorV2 dpiAwareness, missing Win10/11 supportedOS GUID,
      missing longPathAware note, requireAdministrator least-privilege / UIPI warning.
  12. [C# Lifecycle & Security] new Mutex without GC.KeepAlive/using, SystemEvents += without -=,
      new HttpClient() inside methods/loops, async void outside event handlers/lifecycle overrides,
      ProtectedData.Protect(LocalMachine), unvalidated/interpolated Process.Start(UseShellExecute=true),
      RegisterHotKey without matching UnregisterHotKey, NamedPipeServerStream without CurrentUserOnly/PipeSecurity,
      bypassed ServerCertificateCustomValidationCallback outside #if DEBUG, raw LoadLibrary P/Invoke.
  13. [WebView2 & WinUI 3] EnsureCoreWebView2Async() without explicit environment/UserDataFolder,
      AddHostObjectToScript surface note, AreDevToolsEnabled = true outside #if DEBUG, Window.Current in WinUI 3,
      ApplicationData.Current in unpackaged projects without identity guard.
  14. [C++ / C++/WinRT] co_await in Class::Method(...) without get_weak()/get_strong(), raw LoadLibraryA/W
      without LoadLibraryEx + LOAD_LIBRARY_SEARCH_SYSTEM32, AdjustWindowRect instead of AdjustWindowRectExForDpi.

Usage:
  python audit_windows_app.py <path-to-project-dir> [--ui-only] [--strict] [--json | --sarif]
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import itertools
import json
import re
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

IGNORE_DIRS = {"bin", "obj", ".git", ".vs", "packages", ".svn", "node_modules", "CMakeFiles", "vcpkg_installed"}
WIN10_11_SUPPORTED_OS_GUID = "{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"


@dataclass(frozen=True)
class Finding:
    """Structured audit finding."""

    severity: str  # ERROR, WARN, INFO
    tag: str
    file: str | None
    line: int | None
    message: str

    def format_line(self) -> str:
        loc = ""
        if self.file and self.line is not None:
            loc = f"{self.file}:{self.line} "
        elif self.file:
            loc = f"{self.file} "
        prefix = f"[{self.tag}]" if self.severity != "INFO" else "[INFO]"
        if self.severity == "INFO" and self.tag != "INFO":
            prefix = f"[INFO:{self.tag}]"
        return f"{prefix} {loc}{self.message}".strip()


def _strip_xml_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def strip_xml_comments_preserve_lines(text: str) -> str:
    """Replace XML comment interiors with spaces while keeping newlines so line numbers match."""
    return re.sub(
        r"<!--.*?-->",
        lambda m: "".join("\n" if ch == "\n" else " " for ch in m.group(0)),
        text,
        flags=re.DOTALL,
    )


def strip_cs_comments(text: str, blank_strings: bool = False) -> str:
    """Strip C# // and /* */ comments (and optionally string contents) while preserving line numbers."""
    out: list[str] = []
    n = len(text)
    i = 0
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        # Line comment
        if ch == "/" and nxt == "/":
            out.append("  ")
            i += 2
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue

        # Block comment
        if ch == "/" and nxt == "*":
            out.append("  ")
            i += 2
            while i < n:
                if text[i] == "*" and i + 1 < n and text[i + 1] == "/":
                    out.append("  ")
                    i += 2
                    break
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            continue

        # C# 11+ raw string literal: """...""" or $"""..."""
        if ch in ('"', "$"):
            d_cnt = 0
            while i + d_cnt < n and text[i + d_cnt] == "$":
                d_cnt += 1
            q_cnt = 0
            while i + d_cnt + q_cnt < n and text[i + d_cnt + q_cnt] == '"':
                q_cnt += 1
            if q_cnt >= 3:
                prefix_len = d_cnt + q_cnt
                closing = '"' * q_cnt
                out.append(" " * prefix_len if blank_strings else text[i : i + prefix_len])
                i += prefix_len
                while i < n:
                    if text.startswith(closing, i):
                        out.append(" " * q_cnt if blank_strings else closing)
                        i += q_cnt
                        break
                    c = text[i]
                    out.append("\n" if c == "\n" else (" " if blank_strings else c))
                    i += 1
                continue

        # Verbatim / interpolated verbatim string @"..." or $@"..." or @$"..."
        if (ch == "@" and nxt == '"') or (
            ch == "$" and nxt == "@" and i + 2 < n and text[i + 2] == '"'
        ) or (ch == "@" and nxt == "$" and i + 2 < n and text[i + 2] == '"'):
            prefix_len = 2 if ch == "@" and nxt == '"' else 3
            out.append(" " * prefix_len if blank_strings else text[i : i + prefix_len])
            i += prefix_len
            while i < n:
                c = text[i]
                if c == '"':
                    if i + 1 < n and text[i + 1] == '"':
                        out.append("  " if blank_strings else '""')
                        i += 2
                        continue
                    out.append('"' if not blank_strings else " ")
                    i += 1
                    break
                out.append("\n" if c == "\n" else (" " if blank_strings else c))
                i += 1
            continue

        # Interpolated or normal string "..." or $"..."
        if ch == '"' or (ch == "$" and nxt == '"'):
            prefix_len = 2 if ch == "$" else 1
            out.append('"' if (blank_strings and prefix_len == 1) else ('""' if blank_strings else text[i : i + prefix_len]))
            i += prefix_len
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    out.append("  " if blank_strings else text[i : i + 2])
                    i += 2
                    continue
                if c == '"':
                    out.append('"' if blank_strings else '"')
                    i += 1
                    break
                out.append("\n" if c == "\n" else (" " if blank_strings else c))
                i += 1
            continue

        # Char literal '...'
        if ch == "'":
            out.append(ch)
            i += 1
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    out.append("  " if blank_strings else text[i : i + 2])
                    i += 2
                    continue
                out.append("'" if c == "'" else ("\n" if c == "\n" else (" " if blank_strings else c)))
                i += 1
                if c == "'":
                    break
            continue

        out.append(ch)
        i += 1

    return "".join(out)


def strip_cpp_comments(text: str, blank_strings: bool = False) -> str:
    """Strip C++ // and /* */ comments (and optionally string/char contents) while preserving line numbers."""
    out: list[str] = []
    n = len(text)
    i = 0

    def _is_ident_char(c: str) -> bool:
        return c.isalnum() or c == "_"

    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""

        # Line comment
        if ch == "/" and nxt == "/":
            out.append("  ")
            i += 2
            while i < n and text[i] != "\n":
                out.append(" ")
                i += 1
            continue

        # Block comment
        if ch == "/" and nxt == "*":
            out.append("  ")
            i += 2
            while i < n:
                if text[i] == "*" and i + 1 < n and text[i + 1] == "/":
                    out.append("  ")
                    i += 2
                    break
                out.append("\n" if text[i] == "\n" else " ")
                i += 1
            continue

        # Raw string literal: (u8|u|U|L)?R"delim(...)delim"
        raw_prefix_len = 0
        if i == 0 or not _is_ident_char(text[i - 1]):
            for pref in ("u8R\"", "uR\"", "UR\"", "LR\"", "R\""):
                if text.startswith(pref, i):
                    raw_prefix_len = len(pref)
                    break
        if raw_prefix_len:
            paren_idx = text.find("(", i + raw_prefix_len)
            if paren_idx != -1 and (paren_idx - (i + raw_prefix_len)) <= 16:
                delim = text[i + raw_prefix_len : paren_idx]
                if not any(c.isspace() or c in ("\\", ")") for c in delim):
                    closing = f"){delim}\""
                    header = text[i : paren_idx + 1]
                    out.append('"' + " " * (len(header) - 1) if blank_strings else header)
                    i = paren_idx + 1
                    while i < n:
                        if text.startswith(closing, i):
                            out.append(" " * (len(closing) - 1) + '"' if blank_strings else closing)
                            i += len(closing)
                            break
                        c = text[i]
                        out.append("\n" if c == "\n" else (" " if blank_strings else c))
                        i += 1
                    continue

        # Regular / wide / UTF string literal: (u8|u|U|L)?"..."
        str_prefix_len = 0
        if ch == '"':
            str_prefix_len = 1
        elif i == 0 or not _is_ident_char(text[i - 1]):
            for pref in ('u8"', 'u"', 'U"', 'L"'):
                if text.startswith(pref, i):
                    str_prefix_len = len(pref)
                    break
        if str_prefix_len:
            out.append('"' + " " * (str_prefix_len - 1) if blank_strings else text[i : i + str_prefix_len])
            i += str_prefix_len
            while i < n:
                c = text[i]
                if c == "\\" and i + 1 < n:
                    if text[i + 1] == "\n":
                        out.append(" \n" if blank_strings else "\\\n")
                    else:
                        out.append("  " if blank_strings else text[i : i + 2])
                    i += 2
                    continue
                if c == '"':
                    out.append('"')
                    i += 1
                    break
                out.append("\n" if c == "\n" else (" " if blank_strings else c))
                i += 1
            continue

        # Char literal '...' (skip C++14 digit separators like 1'000 or 0xFF'FF)
        if ch == "'":
            prev_ch = text[i - 1] if i > 0 else ""
            is_u8_pref = i >= 2 and text[i - 2 : i] == "u8" and (i == 2 or not _is_ident_char(text[i - 3]))
            is_digit_sep = prev_ch in "0123456789abcdefABCDEF" and not is_u8_pref
            if not is_digit_sep:
                out.append(ch)
                i += 1
                while i < n:
                    c = text[i]
                    if c == "\\" and i + 1 < n:
                        out.append("  " if blank_strings else text[i : i + 2])
                        i += 2
                        continue
                    if c == "\n":
                        out.append("\n")
                        i += 1
                        break
                    out.append("'" if c == "'" else (" " if blank_strings else c))
                    i += 1
                    if c == "'":
                        break
                continue

        out.append(ch)
        i += 1

    return "".join(out)


def _eval_pp_expr(expr: str, env: dict[str, bool]) -> bool:
    tokens = re.findall(r"&&|\|\||==|!=|!|\(|\)|[A-Za-z_]\w*", expr)
    pos = 0

    def parse_or() -> bool:
        val = parse_and()
        while pos < len(tokens) and tokens[pos] == "||":
            _advance()
            rhs = parse_and()
            val = val or rhs
        return val

    def parse_and() -> bool:
        val = parse_eq()
        while pos < len(tokens) and tokens[pos] == "&&":
            _advance()
            rhs = parse_eq()
            val = val and rhs
        return val

    def parse_eq() -> bool:
        val = parse_unary()
        while pos < len(tokens) and tokens[pos] in ("==", "!="):
            op = tokens[pos]
            _advance()
            rhs = parse_unary()
            val = (val == rhs) if op == "==" else (val != rhs)
        return val

    def parse_unary() -> bool:
        if pos < len(tokens) and tokens[pos] == "!":
            _advance()
            return not parse_unary()
        return parse_primary()

    def parse_primary() -> bool:
        if pos >= len(tokens):
            raise ValueError("unexpected end")
        tok = tokens[pos]
        if tok == "(":
            _advance()
            val = parse_or()
            if pos >= len(tokens) or tokens[pos] != ")":
                raise ValueError("missing )")
            _advance()
            return val
        _advance()
        if tok == "true":
            return True
        if tok == "false":
            return False
        if re.fullmatch(r"[A-Za-z_]\w*", tok):
            return env.get(tok, False)
        raise ValueError(f"unexpected token {tok}")

    def _advance() -> None:
        nonlocal pos
        pos += 1

    result = parse_or()
    if pos != len(tokens):
        raise ValueError("trailing tokens")
    return result


def _can_run_without_debug(expr: str) -> bool:
    syms = sorted({t for t in re.findall(r"[A-Za-z_]\w*", expr) if t not in ("DEBUG", "true", "false")})
    if len(syms) > 6:
        return True
    try:
        for combo in itertools.product((False, True), repeat=len(syms)):
            env = dict(zip(syms, combo))
            env["DEBUG"] = False
            if _eval_pp_expr(expr, env):
                return True
        return False
    except ValueError:
        return True


def _compute_debug_guarded_lines(code_only: str) -> set[int]:
    """Return 1-based line numbers strictly gated behind #if DEBUG (never executed when DEBUG is undefined)."""
    guarded: set[int] = set()
    # Stack entries: (branch_exprs_seen_so_far, current_branch_can_run_in_release)
    stack: list[tuple[list[str], bool]] = []

    for idx, line in enumerate(code_only.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            m_if = re.match(r"^#\s*if\b(.*)$", stripped)
            if m_if:
                expr = m_if.group(1).strip() or "false"
                runs_rel = _can_run_without_debug(expr)
                stack.append(([expr], runs_rel))
                continue
            m_elif = re.match(r"^#\s*elif\b(.*)$", stripped)
            if m_elif and stack:
                prior, _ = stack[-1]
                expr = m_elif.group(1).strip() or "false"
                prior_or = " || ".join(f"({p})" for p in prior)
                cond = f"!({prior_or}) && ({expr})"
                runs_rel = _can_run_without_debug(cond)
                stack[-1] = (prior + [expr], runs_rel)
                continue
            if re.match(r"^#\s*else\b", stripped) and stack:
                prior, _ = stack[-1]
                prior_or = " || ".join(f"({p})" for p in prior)
                runs_rel = _can_run_without_debug(f"!({prior_or})")
                stack[-1] = (prior, runs_rel)
                continue
            if re.match(r"^#\s*endif\b", stripped) and stack:
                stack.pop()
                continue

        if any(not runs_rel for _, runs_rel in stack):
            guarded.add(idx)

    return guarded


def parse_hex_color(hex_str: str) -> tuple[float, int, int, int] | None:
    h = hex_str.strip().lstrip("#")
    if len(h) == 6:
        a = 255
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    elif len(h) == 8:
        a = int(h[0:2], 16)
        r, g, b = int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)
    else:
        return None
    return (a / 255.0, r, g, b)


def composite_over(fg: tuple[float, int, int, int], bg_rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    a, r, g, b = fg
    br, bg_c, bb = bg_rgb
    return (
        round(r * a + br * (1.0 - a)),
        round(g * a + bg_c * (1.0 - a)),
        round(b * a + bb * (1.0 - a)),
    )


def relative_luminance(rgb: tuple[int, int, int]) -> float:
    def ch(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(c1: tuple[int, int, int], c2: tuple[int, int, int]) -> float:
    l1 = relative_luminance(c1)
    l2 = relative_luminance(c2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def iter_project_files(root: Path, exts: tuple[str, ...]) -> list[Path]:
    out: list[Path] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in IGNORE_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in exts:
            out.append(p)
    return out


def _is_winui_xaml(text: str, xaml_path: Path, project_is_winui_only: bool) -> bool:
    if project_is_winui_only:
        return True
    if "xmlns:muxc" in text or "Microsoft.UI.Xaml" in text:
        return True
    cs_pair = xaml_path.with_suffix(".xaml.cs")
    if cs_pair.exists():
        cs_text = cs_pair.read_text(encoding="utf-8", errors="replace")
        if "using Microsoft.UI.Xaml" in cs_text and "using System.Windows" not in cs_text:
            return True
    return False


def audit_palette_contrast(xaml_files: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    brushes: dict[str, tuple[float, int, int, int]] = {}
    tag_re = re.compile(r"<SolidColorBrush\b([^>]+)>", re.IGNORECASE)
    key_re = re.compile(r'\bx:Key="([^"]+)"')
    color_re = re.compile(r'\bColor="(#[0-9A-Fa-f]{6,8})"')

    for f in xaml_files:
        text = strip_xml_comments_preserve_lines(f.read_text(encoding="utf-8", errors="replace"))
        for m in tag_re.finditer(text):
            attrs = m.group(1)
            km = key_re.search(attrs)
            cm = color_re.search(attrs)
            if not (km and cm):
                continue
            parsed = parse_hex_color(cm.group(1))
            if parsed:
                brushes[km.group(1)] = parsed

    if not brushes:
        return findings

    surface_keys = [k for k in brushes if re.search(r"Surface\d|AppBackground|CardSurface|WindowBackground", k)]
    text_keys = [
        k
        for k in brushes
        if re.search(r"Text(Primary|Secondary|Muted|Tertiary)|Foreground(Primary|Secondary)", k)
        and "Disabled" not in k
        and "OnAccent" not in k
    ]

    for tk in text_keys:
        fg = brushes[tk]
        for sk in surface_keys:
            bg = brushes[sk]
            bg_rgb = composite_over(bg, (255, 255, 255))
            fg_rgb = composite_over(fg, bg_rgb)
            ratio = contrast_ratio(fg_rgb, bg_rgb)
            if ratio < 4.5:
                findings.append(
                    Finding("WARN", "CONTRAST", None, None, f"'{tk}' on '{sk}' = {ratio:.2f}:1 (< 4.5:1 WCAG AA normal text)")
                )

    candidate_pairs: list[tuple[str, str]] = []
    for fg_k in brushes:
        stem = re.sub(r"Brush$", "", fg_k)
        for bg_suffix in ("Soft", "SoftBrush", "Background", "BackgroundBrush"):
            bg_k = f"{stem}{bg_suffix}"
            if bg_k in brushes:
                candidate_pairs.append((fg_k, bg_k))
    for fg_k, bg_k in (
        ("OnAccent", "Accent"),
        ("OnAccentBrush", "AccentBrush"),
        ("TextOnAccentBrush", "BrandAccentBrush"),
        ("OnAccent", "Coral"),
        ("OnAccent", "Error"),
    ):
        if fg_k in brushes and bg_k in brushes:
            candidate_pairs.append((fg_k, bg_k))

    seen_pairs: set[tuple[str, str]] = set()
    for fg_k, bg_k in candidate_pairs:
        if (fg_k, bg_k) in seen_pairs:
            continue
        seen_pairs.add((fg_k, bg_k))
        bg_rgb = composite_over(brushes[bg_k], (255, 255, 255))
        fg_rgb = composite_over(brushes[fg_k], bg_rgb)
        ratio = contrast_ratio(fg_rgb, bg_rgb)
        if ratio < 4.5:
            findings.append(Finding("WARN", "CONTRAST", None, None, f"'{fg_k}' on '{bg_k}' = {ratio:.2f}:1 (< 4.5:1 WCAG AA)"))

    return findings


def audit_xaml(f: Path, root: Path, project_is_winui_only: bool = False) -> list[Finding]:
    rel = f.relative_to(root).as_posix()
    raw_text = f.read_text(encoding="utf-8", errors="replace")
    text = strip_xml_comments_preserve_lines(raw_text)
    lines = text.splitlines()
    findings: list[Finding] = []

    is_winui = _is_winui_xaml(text, f, project_is_winui_only)
    is_app_or_theme = f.name.lower() == "app.xaml" or "theme" in rel.lower() or "tokens" in rel.lower()

    for idx, line in enumerate(lines, 1):
        if not is_winui:
            if is_app_or_theme:
                if "<SolidColorBrush" in line and "x:Key=" in line and "Freeze=" not in line and "DynamicResource" not in line:
                    findings.append(Finding("WARN", "FREEZE", rel, idx, 'SolidColorBrush resource missing po:Freeze="True"'))
                if "<DropShadowEffect" in line and "x:Key=" in line and "Freeze=" not in line:
                    findings.append(Finding("WARN", "FREEZE", rel, idx, 'DropShadowEffect resource missing po:Freeze="True"'))

            if 'AllowsTransparency="True"' in line and "<Window" in "\n".join(lines[max(0, idx - 15) : idx + 1]):
                findings.append(
                    Finding("WARN", "DWM", rel, idx, 'Window uses AllowsTransparency="True" (breaks Win11 corners, Snap & Mica)')
                )

            if re.search(r"<VisualState\.Setters(?=\s|>|/)", line):
                findings.append(Finding("ERROR", "WPF-BUG", rel, idx, "<VisualState.Setters> is WinUI/UWP only and invalid in WPF"))

            if "AutomationProperties.AccessibilityView" in line and "http://schemas.microsoft.com/winfx/2006/xaml/presentation" in text:
                findings.append(
                    Finding(
                        "ERROR",
                        "WPF-BUG",
                        rel,
                        idx,
                        "AutomationProperties.AccessibilityView is WinUI/UWP only and fails WPF XAML compilation (MC3072)",
                    )
                )

        if not is_app_or_theme and re.search(r'(Background|Foreground|BorderBrush|Fill|Stroke)="#[0-9A-Fa-f]{6,8}"', line):
            findings.append(
                Finding("WARN", "TOKEN", rel, idx, "Hardcoded hex color in view/control; prefer a DynamicResource/ThemeResource token")
            )

        if 'CanContentScroll="False"' in line:
            findings.append(Finding("WARN", "PERF", rel, idx, 'CanContentScroll="False" disables UI virtualization'))

        if 'FocusVisualStyle="{x:Null}"' in line:
            findings.append(Finding("WARN", "A11Y", rel, idx, 'FocusVisualStyle="{x:Null}" removes keyboard focus cue'))

        if 'RepeatBehavior="Forever"' in line:
            ctx = "\n".join(lines[max(0, idx - 6) : idx])
            if 'RoutedEvent="Loaded"' in ctx or "EventTrigger" in ctx:
                findings.append(
                    Finding(
                        "WARN",
                        "ANIM",
                        rel,
                        idx,
                        'RepeatBehavior="Forever" started on Loaded keeps ticking while Collapsed; gate on IsVisible with StopStoryboard',
                    )
                )

        if ("MouseLeftButtonDown=" in line and "<Border" in "\n".join(lines[max(0, idx - 4) : idx + 1])) or (
            "<MouseBinding" in line and "Border.InputBindings" in "\n".join(lines[max(0, idx - 4) : idx])
        ):
            findings.append(Finding("WARN", "A11Y", rel, idx, "Clickable Border is not keyboard-focusable; use Button or ListBoxItem"))

    sv_depth = 0
    dt_depth = 0
    for idx, line in enumerate(lines, 1):
        sv_depth += len(re.findall(r"<ScrollViewer(?=\s|>)(?![^>]*/>)", line))
        if sv_depth > 0 and re.search(r"<(?:ItemsControl|ListBox|ListView)(?=\s|>)", line):
            findings.append(
                Finding("WARN", "PERF", rel, idx, "<ItemsControl>/<ListBox> nested inside <ScrollViewer> disables UI virtualization")
            )
        sv_depth = max(0, sv_depth - len(re.findall(r"</ScrollViewer>", line)))

        dt_depth += len(re.findall(r"<(?:DataTemplate|ItemsControl\.ItemTemplate)(?=\s|>)(?![^>]*/>)", line))
        if dt_depth > 0 and (
            "DropShadowEffect" in line or re.search(r"\{(?:StaticResource|DynamicResource)\s+[^}]*Shadow[^}]*\}", line)
        ):
            findings.append(
                Finding("WARN", "PERF", rel, idx, "Shadow effect inside ItemTemplate/DataTemplate multiplies GPU shader passes on lists")
            )
        dt_depth = max(0, dt_depth - len(re.findall(r"</(?:DataTemplate|ItemsControl\.ItemTemplate)>", line)))

    for m in re.finditer(r"<Button\b([^>]*)(?:/>|>(.*?)</Button>)", text, re.DOTALL):
        attrs, inner = m.group(1), m.group(2) or ""
        if "AutomationProperties.Name" in attrs or "AutomationProperties.LabeledBy" in attrs:
            continue
        is_glyph_attr = bool(re.search(r'Content="&#x|IconButton|CaptionButton', attrs))
        is_glyph_inner = bool(re.search(r"&#x[0-9A-Fa-f]{4};|FontIcons|SymbolFont|SymbolThemeFontFamily", inner)) and not re.search(
            r'Text="(?!&#x)[^"{]+', inner
        )
        if is_glyph_attr or is_glyph_inner:
            line_no = text[: m.start()].count("\n") + 1
            findings.append(Finding("WARN", "A11Y", rel, line_no, "Icon-only Button missing AutomationProperties.Name"))

    if not is_winui:
        if "<WindowChrome" in text and "CaptionHeight=" in text and "IsHitTestVisibleInChrome" not in text:
            findings.append(
                Finding("WARN", "CHROME", rel, None, "WindowChrome sets CaptionHeight without any IsHitTestVisibleInChrome controls")
            )

        if 'UseAeroCaptionButtons="False"' in text or ('WindowStyle="None"' in text and "<WindowChrome" in text):
            cs_pair = f.with_suffix(".xaml.cs")
            if cs_pair.exists():
                cs_text = strip_cs_comments(cs_pair.read_text(encoding="utf-8", errors="replace"))
                if "HTMAXBUTTON" not in cs_text:
                    findings.append(
                        Finding(
                            "WARN",
                            "CHROME",
                            rel,
                            None,
                            "Custom title bar lacks WM_NCHITTEST -> HTMAXBUTTON handling for Windows 11 Snap Layouts",
                        )
                    )

    return findings


def audit_cs_ui(f: Path, root: Path) -> list[Finding]:
    rel = f.relative_to(root).as_posix()
    raw_text = f.read_text(encoding="utf-8", errors="replace")
    text = strip_cs_comments(raw_text)
    lines = text.splitlines()
    findings: list[Finding] = []

    if "CompositionTarget.Rendering +=" in text:
        if "CompositionTarget.Rendering -=" not in text:
            findings.append(
                Finding("WARN", "ANIM-LEAK", rel, None, "Subscribes to CompositionTarget.Rendering without unsubscribing (-=)")
            )
        if "RenderingTime" not in text:
            findings.append(
                Finding("WARN", "ANIM", rel, None, "CompositionTarget.Rendering lacks RenderingEventArgs.RenderingTime deduplication / delta-time")
            )
        if "BlurRadius" in text:
            findings.append(Finding("WARN", "PERF", rel, None, "Animates BlurRadius inside rendering code (severe iGPU shader cost)"))

        render_fn = re.search(r"(?:OnRendering|OnCompositionRendering|OnRender)\s*\([^)]*\)\s*\{(.*?)\n\s*\}", text, re.DOTALL)
        if render_fn and re.search(r"\.Height\s*=", render_fn.group(1)):
            findings.append(
                Finding(
                    "WARN",
                    "PERF",
                    rel,
                    None,
                    "Mutates .Height inside rendering callback (per-frame layout invalidation; use ScaleTransform.ScaleY or DrawingContext)",
                )
            )

    for idx, line in enumerate(lines, 1):
        if re.search(r"\.Children\s*\[\s*[^\]]+\s*\]\s*=", line):
            findings.append(Finding("ERROR", "WPF-BUG", rel, idx, "Direct Children[i] = x throws in WPF; use RemoveAt + Insert"))
        if "new SolidColorBrush(" in line:
            ctx = "\n".join(lines[idx - 1 : min(len(lines), idx + 4)])
            if "Freeze(" not in ctx and "BeginAnimation" not in ctx:
                findings.append(
                    Finding("WARN", "FREEZE", rel, idx, "Runtime new SolidColorBrush(...) without .Freeze() or shared Theme resource")
                )
        if "Dispatcher.PushFrame" in line and "ApplicationIdle" in "\n".join(lines[max(0, idx - 3) : min(len(lines), idx + 3)]):
            findings.append(
                Finding("WARN", "TRAP", rel, idx, "Dispatcher.PushFrame(ApplicationIdle) hangs if 60 FPS CompositionTarget.Rendering runs")
            )

    if "WM_NCHITTEST" in text and "HTMAXBUTTON" in text and "0xFFFF" in text and "(short)" not in text:
        findings.append(
            Finding(
                "WARN",
                "DPI/MULTI-MON",
                rel,
                None,
                "Extract screen coordinates from lParam with signed (short) casts for negative multi-monitor coords",
            )
        )

    return findings


def _parse_semver_prefix(ver_str: str) -> tuple[int, int, int] | None:
    cleaned = (ver_str or "").strip().lstrip("[(")
    m = re.match(r"^(\d+|\*)(?:\.(\d+|\*))?(?:\.(\d+|\*))?", cleaned)
    if not m:
        return None
    parts: list[int] = []
    for raw in m.groups():
        if raw is None:
            parts.append(0)
        elif raw == "*":
            if not parts:
                return None
            return (parts[0], parts[1] if len(parts) > 1 else 999999, 999999)
        else:
            parts.append(int(raw))
    return (parts[0], parts[1], parts[2])


def _skip_cs_string_or_char(text: str, i: int) -> int:
    """If text[i:] starts at a C# string or char literal (incl. interpolated/verbatim), return index after it; else i."""
    n = len(text)
    if i >= n:
        return i
    ch = text[i]
    nxt = text[i + 1] if i + 1 < n else ""
    nxt2 = text[i + 2] if i + 2 < n else ""

    # Verbatim or interpolated-verbatim: @"...", $@"...", @$"..."
    if (ch == "@" and nxt == '"') or (ch in ("$", "@") and nxt in ("$", "@") and ch != nxt and nxt2 == '"'):
        is_interp = "$" in text[i : i + 2]
        j = i + (2 if ch == "@" and nxt == '"' else 3)
        while j < n:
            c = text[j]
            if is_interp and c == "{":
                if j + 1 < n and text[j + 1] == "{":
                    j += 2
                    continue
                j += 1
                depth = 1
                while j < n and depth > 0:
                    nxt_j = _skip_cs_string_or_char(text, j)
                    if nxt_j > j:
                        j = nxt_j
                        continue
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                    j += 1
                continue
            if c == '"':
                if j + 1 < n and text[j + 1] == '"':
                    j += 2
                    continue
                return j + 1
            j += 1
        return n

    # Standard or interpolated string: "..." or $"..."
    if ch == '"' or (ch == "$" and nxt == '"'):
        is_interp = ch == "$"
        j = i + (2 if is_interp else 1)
        while j < n:
            c = text[j]
            if c == "\\" and j + 1 < n:
                j += 2
                continue
            if is_interp and c == "{":
                if j + 1 < n and text[j + 1] == "{":
                    j += 2
                    continue
                j += 1
                depth = 1
                while j < n and depth > 0:
                    nxt_j = _skip_cs_string_or_char(text, j)
                    if nxt_j > j:
                        j = nxt_j
                        continue
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                    j += 1
                continue
            if c == '"':
                return j + 1
            j += 1
        return n

    # Char literal: '...'
    if ch == "'":
        j = i + 1
        while j < n:
            if text[j] == "\\" and j + 1 < n:
                j += 2
                continue
            if text[j] == "'":
                return j + 1
            j += 1
        return n

    return i


def _scan_balanced_cs(text: str, pos: int, open_ch: str, close_ch: str) -> tuple[str, int] | None:
    """Scan balanced (...) or {...} starting at text[pos] == open_ch, skipping C# string literals."""
    n = len(text)
    if pos >= n or text[pos] != open_ch:
        return None
    depth = 1
    i = pos + 1
    while i < n and depth > 0:
        nxt_i = _skip_cs_string_or_char(text, i)
        if nxt_i > i:
            i = nxt_i
            continue
        if text[i] == open_ch:
            depth += 1
        elif text[i] == close_ch:
            depth -= 1
            if depth == 0:
                return text[pos + 1 : i], i + 1
        i += 1
    return None


def _split_top_level_cs_items(text: str, sep: str = ",") -> list[str]:
    """Split a C# initializer or argument list on top-level separators outside strings/parens/braces."""
    items: list[str] = []
    start = 0
    depth_paren = 0
    depth_brace = 0
    depth_bracket = 0
    i = 0
    n = len(text)
    while i < n:
        nxt_i = _skip_cs_string_or_char(text, i)
        if nxt_i > i:
            i = nxt_i
            continue
        c = text[i]
        if c == "(":
            depth_paren += 1
        elif c == ")" and depth_paren > 0:
            depth_paren -= 1
        elif c == "{":
            depth_brace += 1
        elif c == "}" and depth_brace > 0:
            depth_brace -= 1
        elif c == "[":
            depth_bracket += 1
        elif c == "]" and depth_bracket > 0:
            depth_bracket -= 1
        elif c == sep and depth_paren == 0 and depth_brace == 0 and depth_bracket == 0:
            items.append(text[start:i].strip())
            start = i + 1
        i += 1
    tail = text[start:].strip()
    if tail:
        items.append(tail)
    return items


def _collect_central_package_versions(root: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for props in iter_project_files(root, (".props",)):
        if props.name.lower() != "directory.packages.props":
            continue
        try:
            tree = ET.parse(props)
        except ET.ParseError:
            continue
        for elem in tree.getroot().iter():
            if _strip_xml_ns(elem.tag) == "PackageVersion":
                inc = elem.attrib.get("Include") or elem.attrib.get("Update")
                ver = elem.attrib.get("Version")
                if inc and ver:
                    versions[inc.lower()] = ver
    return versions


def _detect_cs_project_signals(cs_files: list[Path]) -> tuple[bool, bool]:
    uses_library_import = False
    uses_partial_observable = False
    partial_obs_re = re.compile(
        r"\[ObservableProperty[^\]]*\](?:\s*\[[^\]]*\])*\s*"
        r"(?:(?:public|private|internal|protected|new|virtual|override|sealed|required)\s+)*"
        r"partial\s+[^;=]+?\{",
        re.DOTALL,
    )

    for f in cs_files:
        stripped = strip_cs_comments(f.read_text(encoding="utf-8", errors="replace"), blank_strings=True)
        if re.search(r"\[(?:System\.Runtime\.InteropServices\.)?LibraryImport\b", stripped):
            uses_library_import = True
        if partial_obs_re.search(stripped):
            uses_partial_observable = True

    return uses_library_import, uses_partial_observable


def audit_csproj(
    f: Path,
    root: Path,
    all_cs_files: list[Path],
    central_versions: dict[str, str],
    has_appx_manifest: bool,
) -> tuple[list[Finding], bool, bool]:
    rel = f.relative_to(root).as_posix()
    findings: list[Finding] = []
    try:
        tree = ET.parse(f)
    except ET.ParseError as exc:
        return [Finding("ERROR", "CSPROJ", rel, None, f"Invalid XML in .csproj: {exc}")], False, False

    xml_root = tree.getroot()
    props_all: dict[str, list[tuple[str, str | None]]] = {}
    packages: dict[str, str] = {}

    for elem in xml_root.iter():
        tag = _strip_xml_ns(elem.tag)
        if tag == "PackageReference":
            inc = (elem.attrib.get("Include") or elem.attrib.get("Update") or "").strip()
            ver = (elem.attrib.get("Version") or elem.attrib.get("VersionOverride") or "").strip()
            if not ver:
                for child in elem:
                    if _strip_xml_ns(child.tag) == "Version" and child.text:
                        ver = child.text.strip()
                        break
            if inc:
                packages[inc.lower()] = ver or central_versions.get(inc.lower(), "")
        elif elem.text is not None and len(list(elem)) == 0:
            cond = elem.attrib.get("Condition")
            props_all.setdefault(tag.lower(), []).append((elem.text.strip().lower(), cond))

    def has_true(prop: str) -> bool:
        return any(val == "true" for val, _ in props_all.get(prop.lower(), []))

    def has_unconditional_true(prop: str) -> bool:
        return any(val == "true" and not cond for val, cond in props_all.get(prop.lower(), []))

    def get_vals(prop: str) -> list[str]:
        return [val for val, _ in props_all.get(prop.lower(), [])]

    use_wpf = has_true("UseWPF")
    use_winui = has_true("UseWinUI") or ("microsoft.windowsappsdk" in packages)
    output_types = get_vals("OutputType")
    is_winexe = "winexe" in output_types

    proj_dir = f.parent
    scoped_cs = [c for c in all_cs_files if proj_dir == root or proj_dir in c.parents]
    if not scoped_cs:
        scoped_cs = all_cs_files
    uses_library_import, uses_partial_observable = _detect_cs_project_signals(scoped_cs)

    if use_wpf and (has_true("PublishTrimmed") or has_true("PublishAot")):
        findings.append(
            Finding(
                "ERROR",
                "CSPROJ",
                rel,
                None,
                "PublishTrimmed/PublishAot=true with UseWPF=true is unsupported (NETSDK1168; XAML & bindings rely on runtime reflection)",
            )
        )

    if uses_library_import and not has_true("AllowUnsafeBlocks"):
        findings.append(
            Finding(
                "ERROR",
                "CSPROJ",
                rel,
                None,
                "Project uses [LibraryImport] without <AllowUnsafeBlocks>true</AllowUnsafeBlocks> (triggers SYSLIB1062 compile error)",
            )
        )

    mvvm_ver_str = packages.get("communitytoolkit.mvvm", "")
    mvvm_ver = _parse_semver_prefix(mvvm_ver_str)
    if mvvm_ver and mvvm_ver < (8, 4, 2) and uses_partial_observable:
        lang_vals = get_vals("LangVersion")
        if "preview" in lang_vals:
            findings.append(
                Finding(
                    "WARN",
                    "CSPROJ",
                    rel,
                    None,
                    f"CommunityToolkit.Mvvm {mvvm_ver_str} (< 8.4.2) relies on LangVersion=preview for partial [ObservableProperty]; upgrade to >= 8.4.2",
                )
            )
        else:
            findings.append(
                Finding(
                    "ERROR",
                    "CSPROJ",
                    rel,
                    None,
                    f"CommunityToolkit.Mvvm {mvvm_ver_str} (< 8.4.2) with partial [ObservableProperty] fails with CS9248; upgrade to >= 8.4.2 or use backing fields",
                )
            )

    has_app_manifest = bool(get_vals("ApplicationManifest"))
    if is_winexe and not has_app_manifest and (use_wpf or not has_appx_manifest):
        findings.append(
            Finding(
                "WARN",
                "CSPROJ",
                rel,
                None,
                "OutputType=WinExe lacks <ApplicationManifest> (needed to declare PerMonitorV2 DPI & Win10/11 supportedOS)",
            )
        )

    if has_true("PublishSingleFile"):
        if use_wpf and not has_true("IncludeNativeLibrariesForSelfExtract"):
            findings.append(
                Finding(
                    "WARN",
                    "CSPROJ",
                    rel,
                    None,
                    "PublishSingleFile=true on WPF without <IncludeNativeLibrariesForSelfExtract>true</IncludeNativeLibrariesForSelfExtract> leaves native WPF DLLs loose beside the exe",
                )
            )
        if has_true("IncludeAllContentForSelfExtract"):
            findings.append(
                Finding(
                    "WARN",
                    "CSPROJ",
                    rel,
                    None,
                    "IncludeAllContentForSelfExtract=true extracts all assemblies to %TEMP%\\.net\\ at startup; prefer IncludeNativeLibrariesForSelfExtract=true",
                )
            )
        elif has_unconditional_true("PublishSingleFile"):
            findings.append(
                Finding(
                    "WARN",
                    "CSPROJ",
                    rel,
                    None,
                    "Unconditional PublishSingleFile=true packs dev/Debug runs too (breaks Snoop injection and unpacks to %TEMP%\\.net\\); gate to Release/publish or pass via CLI",
                )
            )

    if is_winexe and not has_true("PublishReadyToRun") and not has_true("PublishAot"):
        findings.append(
            Finding(
                "INFO",
                "CSPROJ",
                rel,
                None,
                "Missing <PublishReadyToRun>true</PublishReadyToRun> (recommended for Release desktop builds to cut cold-start JIT stalls)",
            )
        )

    return findings, use_wpf, use_winui


def audit_manifest(f: Path, root: Path) -> list[Finding]:
    rel = f.relative_to(root).as_posix()
    findings: list[Finding] = []
    try:
        tree = ET.parse(f)
    except ET.ParseError as exc:
        return [Finding("ERROR", "MANIFEST", rel, None, f"Invalid XML in manifest: {exc}")]

    xml_root = tree.getroot()
    if _strip_xml_ns(xml_root.tag).lower() != "assembly":
        return findings

    dpi_awareness_values: list[str] = []
    supported_os_ids: set[str] = set()
    long_path_aware = False
    req_level: str | None = None

    for elem in xml_root.iter():
        tag = _strip_xml_ns(elem.tag).lower()
        if tag == "dpiawareness" and elem.text:
            tokens = [t.strip().lower() for t in re.split(r"[\s,]+", elem.text) if t.strip()]
            dpi_awareness_values.extend(tokens)
        elif tag == "supportedos":
            os_id = (elem.attrib.get("Id") or elem.attrib.get("id") or "").strip().lower()
            if os_id:
                supported_os_ids.add(os_id)
        elif tag == "longpathaware" and elem.text and elem.text.strip().lower() == "true":
            long_path_aware = True
        elif tag == "requestedexecutionlevel":
            req_level = (elem.attrib.get("level") or "").strip()

    if "permonitorv2" not in dpi_awareness_values:
        findings.append(
            Finding(
                "WARN",
                "MANIFEST",
                rel,
                None,
                "Missing PerMonitorV2 in <dpiAwareness> (app blurs or mis-scales when moved across mixed-DPI monitors)",
            )
        )

    if WIN10_11_SUPPORTED_OS_GUID not in supported_os_ids:
        findings.append(
            Finding(
                "WARN",
                "MANIFEST",
                rel,
                None,
                f"Missing Windows 10/11 <supportedOS Id=\"{WIN10_11_SUPPORTED_OS_GUID}\" /> in <compatibility>",
            )
        )

    if req_level and req_level.lower() == "requireadministrator":
        findings.append(
            Finding(
                "WARN",
                "MANIFEST",
                rel,
                None,
                'Uses requestedExecutionLevel level="requireAdministrator" (review least privilege & UIPI: blocks standard-user drag-drop and window messages)',
            )
        )

    if not long_path_aware:
        findings.append(
            Finding(
                "INFO",
                "MANIFEST",
                rel,
                None,
                "Missing <longPathAware>true</longPathAware> (deep user/workspace paths > 260 chars may fail MAX_PATH)",
            )
        )

    return findings


def _is_valid_async_void(header_context: str, params_raw: str) -> bool:
    if re.search(r"\boverride\b", header_context):
        return True
    params = [p.strip() for p in params_raw.split(",") if p.strip()]
    if len(params) != 2:
        return False
    # Check 2nd parameter type ends with EventArgs or Args (handles WPF RoutedEventArgs, WinUI TypedEventHandler Args, etc.)
    second_tokens = [tok for tok in re.split(r"\s+", params[1]) if tok and not tok.startswith("[")]
    if len(second_tokens) >= 2:
        param_type = second_tokens[-2].rstrip("?")
        if param_type.endswith(("EventArgs", "Args")):
            return True
    return False


def _is_extern_decl(lines: list[str], idx: int) -> bool:
    window = "\n".join(lines[max(0, idx - 3) : idx])
    return bool(re.search(r"\[(?:DllImport|LibraryImport)\b|\bextern\b|\bstatic\s+partial\b", window))


def _collect_unpackaged_project_dirs(csproj_files: list[Path]) -> set[Path]:
    unpackaged: set[Path] = set()
    for csproj in csproj_files:
        try:
            tree = ET.parse(csproj)
        except ET.ParseError:
            continue
        for elem in tree.getroot().iter():
            if _strip_xml_ns(elem.tag).lower() == "windowspackagetype":
                if (elem.text or "").strip().lower() == "none":
                    unpackaged.add(csproj.parent.resolve())
                    break
    return unpackaged


def _cs_belongs_to_unpackaged_project(
    cs_path: Path,
    root: Path,
    csproj_files: list[Path],
    unpackaged_dirs: set[Path],
) -> bool:
    if not unpackaged_dirs:
        return False
    resolved = cs_path.resolve()
    matching = [p for p in csproj_files if p.parent.resolve() == root.resolve() or p.parent.resolve() in resolved.parents]
    if not matching:
        return any(p.parent.resolve() in unpackaged_dirs for p in csproj_files)
    # Closest .csproj ancestor owns the file
    closest = max(matching, key=lambda p: len(p.parent.resolve().parts))
    return closest.parent.resolve() in unpackaged_dirs


def _has_webview2_creation_udf(cs_path: Path, code_only: str) -> bool:
    if "CreationProperties" in code_only and "UserDataFolder" in code_only:
        return True
    if cs_path.name.lower().endswith(".xaml.cs"):
        xaml_pair = cs_path.with_suffix("")
        if xaml_pair.exists():
            xaml_text = strip_xml_comments_preserve_lines(xaml_pair.read_text(encoding="utf-8", errors="replace"))
            if "CreationProperties" in xaml_text and "UserDataFolder" in xaml_text:
                return True
    return False


def audit_cs_engineering(f: Path, root: Path, is_unpackaged: bool = False) -> list[Finding]:
    rel = f.relative_to(root).as_posix()
    raw_text = f.read_text(encoding="utf-8", errors="replace")
    no_comments = strip_cs_comments(raw_text, blank_strings=False)
    code_only = strip_cs_comments(raw_text, blank_strings=True)
    code_lines = code_only.splitlines()
    text_lines = no_comments.splitlines()
    debug_lines = _compute_debug_guarded_lines(code_only)
    findings: list[Finding] = []

    # 1. new Mutex(...) without GC.KeepAlive or using scope
    mutex_re = re.compile(r"\bnew\s+(?:System\.Threading\.)?Mutex\s*\(")
    has_keep_alive = "GC.KeepAlive" in code_only
    for idx, line in enumerate(code_lines, 1):
        if mutex_re.search(line):
            ctx = "\n".join(code_lines[max(0, idx - 2) : idx])
            in_using = bool(re.search(r"\busing\s*(?:\(|\bvar\b|\bMutex\b)", ctx))
            is_static_field = bool(re.search(r"\bstatic\s+(?:readonly\s+)?Mutex\b", ctx))
            if not has_keep_alive and not in_using and not is_static_field:
                findings.append(
                    Finding(
                        "WARN",
                        "LIFECYCLE",
                        rel,
                        idx,
                        "new Mutex(...) without GC.KeepAlive(...) or using scope (Release JIT can finalize local Mutex early and break single-instance lock)",
                    )
                )

    # 2. SystemEvents.* += without matching -=
    sub_re = re.compile(r"\bSystemEvents\.([A-Za-z_]\w*)\s*\+=")
    for idx, line in enumerate(code_lines, 1):
        for m in sub_re.finditer(line):
            ev = m.group(1)
            if not re.search(rf"\bSystemEvents\.{re.escape(ev)}\s*-=", code_only):
                findings.append(
                    Finding(
                        "WARN",
                        "MEMORY-LEAK",
                        rel,
                        idx,
                        f"SystemEvents.{ev} += without matching -= (static event holds strong GC root and leaks Window/Control)",
                    )
                )

    # 3. new HttpClient() inside methods/loops (skip static/readonly class fields)
    http_re = re.compile(r"\bnew\s+(?:System\.Net\.Http\.)?HttpClient\s*\(|\bHttpClient\s+[A-Za-z_]\w*\s*=\s*new\s*\(")
    for idx, line in enumerate(code_lines, 1):
        if http_re.search(line):
            ctx = "\n".join(code_lines[max(0, idx - 2) : idx])
            if re.search(r"\bstatic\b|\bAddSingleton\b|\bAddHttpClient\b", ctx):
                continue
            if re.match(r"^\s*(?:private|protected|internal|public)\s+readonly\s+HttpClient\b", line):
                continue
            findings.append(
                Finding(
                    "WARN",
                    "PERF",
                    rel,
                    idx,
                    "new HttpClient() inside method/loop risks socket exhaustion & stale DNS; reuse a static/SocketsHttpHandler instance or IHttpClientFactory",
                )
            )

    # 4. async void outside event handlers / UI lifecycle overrides
    async_void_re = re.compile(
        r"([^\n;{}]*?)\basync\s+void\s+([A-Za-z_]\w*)\s*\(([^()]*(?:\([^()]*\)[^()]*)*)\)",
        re.DOTALL,
    )
    for m in async_void_re.finditer(code_only):
        header_ctx, method_name, params_raw = m.group(1), m.group(2), m.group(3)
        if not _is_valid_async_void(header_ctx, params_raw):
            line_no = code_only[: m.start(2)].count("\n") + 1
            findings.append(
                Finding(
                    "WARN",
                    "LIFECYCLE",
                    rel,
                    line_no,
                    f"async void {method_name}(...) outside event handler or UI lifecycle override (unhandled exceptions crash process; return async Task)",
                )
            )

    # 5. ProtectedData.Protect(..., DataProtectionScope.LocalMachine)
    dpapi_re = re.compile(r"\bProtectedData\s*\.\s*Protect\s*\([^;]*?DataProtectionScope\s*\.\s*LocalMachine", re.DOTALL)
    for m in dpapi_re.finditer(code_only):
        line_no = code_only[: m.start()].count("\n") + 1
        findings.append(
            Finding(
                "ERROR",
                "SECURITY",
                rel,
                line_no,
                "ProtectedData.Protect uses DataProtectionScope.LocalMachine (any local user/process can decrypt); use DataProtectionScope.CurrentUser for user secrets",
            )
        )

    # 6. Process.Start / ProcessStartInfo with UseShellExecute = true and unvalidated/interpolated URL or args
    psi_head_re = re.compile(r"(?:(\b[A-Za-z_]\w*)\s*=\s*)?\bnew\s+(?:System\.Diagnostics\.)?ProcessStartInfo\b")
    safe_literal_re = re.compile(r'^"(?:https?://|ms-settings:)[^"]+"$')
    for m in psi_head_re.finditer(no_comments):
        var_name = m.group(1)
        pos = m.end()
        n_txt = len(no_comments)
        while pos < n_txt and no_comments[pos].isspace():
            pos += 1

        ctor_str = ""
        init_str = ""
        has_ctor = False
        has_init = False

        if pos < n_txt and no_comments[pos] == "(":
            parsed_ctor = _scan_balanced_cs(no_comments, pos, "(", ")")
            if parsed_ctor is not None:
                ctor_str, pos = parsed_ctor
                has_ctor = True
                while pos < n_txt and no_comments[pos].isspace():
                    pos += 1

        if pos < n_txt and no_comments[pos] == "{":
            parsed_init = _scan_balanced_cs(no_comments, pos, "{", "}")
            if parsed_init is not None:
                init_str, pos = parsed_init
                has_init = True

        if not has_ctor and not has_init:
            continue

        line_no = no_comments[: m.start()].count("\n") + 1
        ctx_after = "\n".join(text_lines[line_no - 1 : min(len(text_lines), line_no + 12)])
        has_var_shell_exec = bool(
            var_name
            and var_name != "new"
            and re.search(rf"\b{re.escape(var_name)}\s*\.\s*UseShellExecute\s*=\s*true\b", ctx_after)
        )
        init_items = _split_top_level_cs_items(init_str, ",") if init_str else []
        has_init_shell_exec = any(re.match(r"^UseShellExecute\s*=\s*true$", item) for item in init_items)
        if not (has_init_shell_exec or has_var_shell_exec):
            continue

        ctx_before = "\n".join(text_lines[max(0, line_no - 25) : line_no + 3])
        has_scheme_allowlist = bool(
            re.search(
                r"UriSchemeHttp|UriSchemeHttps|\.Scheme\s*(?:==|\.Equals)|StartsWith\(\s*\"https?://\"",
                ctx_before,
            )
        )

        ctor_items = _split_top_level_cs_items(ctor_str, ",") if ctor_str else []
        var_assign_items: list[str] = []
        if var_name and var_name != "new":
            for stmt in re.findall(rf"\b{re.escape(var_name)}\s*\.\s*(?:FileName|Arguments)\s*=[^;\n]+;", ctx_after):
                var_assign_items.append(stmt.rstrip(";").split(".", 1)[1].strip())

        target_rhs: str | None = ctor_items[0] if ctor_items else None
        args_rhs: str | None = ctor_items[1] if len(ctor_items) > 1 else None
        for item in init_items + var_assign_items:
            if re.match(r"^FileName\s*=", item):
                target_rhs = item.split("=", 1)[1].strip()
            elif re.match(r"^Arguments\s*=", item):
                args_rhs = item.split("=", 1)[1].strip()

        def _is_interpolated_or_concat(expr: str | None) -> bool:
            if not expr:
                return False
            if re.search(r'(?:\$"|\$@"|@\$")', expr):
                return True
            stripped_expr = strip_cs_comments(expr, blank_strings=True)
            return "+" in stripped_expr

        has_interpolated_target = _is_interpolated_or_concat(target_rhs) or _is_interpolated_or_concat(args_rhs)
        is_literal_safe_target = bool(target_rhs and safe_literal_re.match(target_rhs.strip())) and not args_rhs

        if has_interpolated_target or (not is_literal_safe_target and not has_scheme_allowlist):
            findings.append(
                Finding(
                    "WARN",
                    "SECURITY",
                    rel,
                    line_no,
                    "Process.Start with UseShellExecute=true uses interpolated/unvalidated target or Arguments (allowlist http/https via Uri.TryCreate + Scheme check, or pass ArgumentList with UseShellExecute=false)",
                )
            )

    # 7. RegisterHotKey without matching UnregisterHotKey
    reg_re = re.compile(r"\bRegisterHotKey\s*\(")
    unreg_re = re.compile(r"\bUnregisterHotKey\s*\(")
    has_unreg_call = any(unreg_re.search(line) and not _is_extern_decl(code_lines, idx) for idx, line in enumerate(code_lines, 1))
    if not has_unreg_call:
        for idx, line in enumerate(code_lines, 1):
            if reg_re.search(line) and not _is_extern_decl(code_lines, idx):
                findings.append(
                    Finding(
                        "WARN",
                        "LIFECYCLE",
                        rel,
                        idx,
                        "Calls RegisterHotKey without matching UnregisterHotKey cleanup (leaks global OS hotkey)",
                    )
                )

    # 8. WebView2: EnsureCoreWebView2Async() without explicit CoreWebView2Environment / UserDataFolder
    if not _has_webview2_creation_udf(f, code_only):
        for m in re.finditer(r"\bEnsureCoreWebView2Async\s*\(\s*(?:null\s*)?\)", code_only):
            line_no = code_only[: m.start()].count("\n") + 1
            findings.append(
                Finding(
                    "WARN",
                    "WEBVIEW2",
                    rel,
                    line_no,
                    "EnsureCoreWebView2Async() without explicit CoreWebView2Environment / UserDataFolder under %LocalAppData% fails under Program Files",
                )
            )

    # 9. WebView2: AddHostObjectToScript security surface reminder
    for m in re.finditer(r"\bAddHostObjectToScript\s*\(", code_only):
        line_no = code_only[: m.start()].count("\n") + 1
        findings.append(
            Finding(
                "INFO",
                "WEBVIEW2",
                rel,
                line_no,
                "AddHostObjectToScript exposes a .NET/COM host object to script; review origin allowlists or prefer typed PostWebMessageAsJson/WebMessageReceived",
            )
        )

    # 10. WebView2: AreDevToolsEnabled = true outside #if DEBUG
    for m in re.finditer(r"\bAreDevToolsEnabled\s*(?<![=!<>])=(?!=)\s*true\b", code_only):
        line_no = code_only[: m.start()].count("\n") + 1
        if line_no not in debug_lines:
            findings.append(
                Finding(
                    "WARN",
                    "WEBVIEW2",
                    rel,
                    line_no,
                    "AreDevToolsEnabled = true outside #if DEBUG leaves browser DevTools enabled in Release builds",
                )
            )

    # 11. WinUI 3: Window.Current is always null in desktop WinUI 3
    if "Microsoft.UI.Xaml" in code_only:
        for m in re.finditer(r"(?<!Windows\.)\bWindow\s*\.\s*Current\b", code_only):
            line_no = code_only[: m.start()].count("\n") + 1
            findings.append(
                Finding(
                    "ERROR",
                    "WINUI3",
                    rel,
                    line_no,
                    "Window.Current is always null in WinUI 3 desktop apps; keep an explicit Window / XamlRoot reference instead",
                )
            )

    # 12. WinUI 3: ApplicationData.Current in unpackaged projects without identity guard
    if is_unpackaged and "Package.Current" not in code_only and "GetCurrentPackageFullName" not in code_only:
        for m in re.finditer(r"\bApplicationData\s*\.\s*Current\b", code_only):
            line_no = code_only[: m.start()].count("\n") + 1
            findings.append(
                Finding(
                    "WARN",
                    "WINUI3",
                    rel,
                    line_no,
                    "ApplicationData.Current throws in unpackaged projects (<WindowsPackageType>None</WindowsPackageType>) without a Package.Current / GetCurrentPackageFullName identity guard",
                )
            )

    # 13. Security: new NamedPipeServerStream(...) without PipeOptions.CurrentUserOnly or PipeSecurity
    for m in re.finditer(r"\bnew\s+(?:System\.IO\.Pipes\.)?NamedPipeServerStream\s*\(", code_only):
        line_no = code_only[: m.start()].count("\n") + 1
        parsed = _scan_balanced_cs(code_only, m.end() - 1, "(", ")")
        args_str = parsed[0] if parsed is not None else code_only[m.end() : m.end() + 300]
        has_acl = ("CurrentUserOnly" in args_str) or ("PipeSecurity" in args_str)
        if not has_acl:
            ctx_before = "\n".join(code_lines[max(0, line_no - 16) : line_no])
            acl_vars = set(
                re.findall(r"\bPipeSecurity\s+([A-Za-z_]\w*)", ctx_before)
                + re.findall(r"\b([A-Za-z_]\w*)\s*=\s*new\s+(?:System\.IO\.Pipes\.)?PipeSecurity\b", ctx_before)
                + re.findall(r"\b([A-Za-z_]\w*)\s*=[^;\n]*\bCurrentUserOnly\b", ctx_before)
            )
            has_acl = any(re.search(rf"\b{re.escape(v)}\b", args_str) for v in acl_vars)
        if not has_acl:
            findings.append(
                Finding(
                    "WARN",
                    "SECURITY",
                    rel,
                    line_no,
                    "new NamedPipeServerStream(...) without PipeOptions.CurrentUserOnly or PipeSecurity allows arbitrary local users/processes to connect",
                )
            )

    # 14. Security: ServerCertificateCustomValidationCallback returning true / DangerousAcceptAnyServerCertificateValidator outside #if DEBUG
    reported_tls_lines: set[int] = set()
    tls_cb_re = re.compile(
        r"\bServerCertificateCustomValidationCallback\s*=\s*"
        r"(?:(?:\([^)]*\)|[A-Za-z_]\w*)\s*=>\s*(?:\{\s*return\s+true\s*;\s*\}|true\b)"
        r"|delegate(?:\s*\([^)]*\))?\s*\{\s*return\s+true\s*;\s*\})"
    )
    for m in tls_cb_re.finditer(code_only):
        line_no = code_only[: m.start()].count("\n") + 1
        if line_no not in debug_lines and line_no not in reported_tls_lines:
            reported_tls_lines.add(line_no)
            findings.append(
                Finding(
                    "ERROR",
                    "SECURITY",
                    rel,
                    line_no,
                    "ServerCertificateCustomValidationCallback unconditionally returns true outside #if DEBUG (disables TLS certificate validation)",
                )
            )
    for m in re.finditer(r"\bDangerousAcceptAnyServerCertificateValidator\b", code_only):
        line_no = code_only[: m.start()].count("\n") + 1
        if line_no not in debug_lines and line_no not in reported_tls_lines:
            reported_tls_lines.add(line_no)
            findings.append(
                Finding(
                    "ERROR",
                    "SECURITY",
                    rel,
                    line_no,
                    "DangerousAcceptAnyServerCertificateValidator used outside #if DEBUG (disables TLS certificate validation)",
                )
            )

    # 15. Security: P/Invoke LoadLibrary / LoadLibraryA / LoadLibraryW without LoadLibraryEx + LOAD_LIBRARY_SEARCH_SYSTEM32 / SetDefaultDllDirectories
    has_safe_cs_dll = ("SetDefaultDllDirectories" in code_only) or (
        "LoadLibraryEx" in code_only and "LOAD_LIBRARY_SEARCH_SYSTEM32" in code_only
    )
    if not has_safe_cs_dll:
        for m in re.finditer(r"\bLoadLibrary(?:A|W)?\s*\(", code_only):
            line_no = code_only[: m.start()].count("\n") + 1
            findings.append(
                Finding(
                    "WARN",
                    "SECURITY",
                    rel,
                    line_no,
                    "P/Invoke LoadLibrary/LoadLibraryA/LoadLibraryW without LoadLibraryEx + LOAD_LIBRARY_SEARCH_SYSTEM32 or SetDefaultDllDirectories risks DLL hijacking",
                )
            )

    return findings


def _scan_balanced_cpp_brace(text: str, open_pos: int) -> int | None:
    """Given text[open_pos] == '{', return index of matching '}', skipping balanced braces."""
    n = len(text)
    if open_pos >= n or text[open_pos] != "{":
        return None
    depth = 1
    i = open_pos + 1
    while i < n:
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _scan_balanced_cpp_paren(text: str, open_pos: int) -> int | None:
    n = len(text)
    if open_pos >= n or text[open_pos] != "(":
        return None
    depth = 1
    i = open_pos + 1
    while i < n:
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def audit_cpp(f: Path, root: Path) -> list[Finding]:
    rel = f.relative_to(root).as_posix()
    raw_text = f.read_text(encoding="utf-8", errors="replace")
    code_only = strip_cpp_comments(raw_text, blank_strings=True)
    findings: list[Finding] = []

    # 1. co_await inside qualified Class::Method(...) without get_weak() or get_strong()
    if "co_await" in code_only:
        n = len(code_only)
        i = 0
        stmt_start = 0
        qual_method_re = re.compile(
            r"([A-Za-z_]\w*(?:\s*<[^;{}()]*?>)?(?:::(?:~?[A-Za-z_]\w*|operator\s*[^(\s]+)(?:\s*<[^;{}()]*?>)?)+)\s*\("
        )
        control_kw_re = re.compile(r"^\s*(?:if|else|for|while|switch|catch|try|do|return|co_return)\b")

        while i < n:
            ch = code_only[i]
            # Skip preprocessor directives (start of line '#')
            if ch == "#" and (i == 0 or code_only[i - 1] == "\n"):
                while i < n:
                    nl = code_only.find("\n", i)
                    if nl == -1:
                        i = n
                        break
                    if nl > 0 and code_only[nl - 1] == "\\":
                        i = nl + 1
                        continue
                    i = nl + 1
                    break
                stmt_start = i
                continue

            if ch in (";", "}"):
                stmt_start = i + 1
                i += 1
                continue

            if ch == "{":
                header = code_only[stmt_start:i]
                # Enter namespace or extern "..." blocks instead of skipping them
                if re.match(r"^\s*(?:(?:inline\s+)?namespace\b|extern\s+\"[^\"]*\"\s*$)", header):
                    stmt_start = i + 1
                    i += 1
                    continue

                close_brace = _scan_balanced_cpp_brace(code_only, i)
                if close_brace is None:
                    break

                if not control_kw_re.match(header) and not re.match(r"^\s*(?:template\s*<[^>]*>\s*)?(?:class|struct|union|enum)\b", header):
                    m = qual_method_re.search(header)
                    if m is not None:
                        prefix_before_name = header[: m.start()]
                        paren_open_in_header = m.end() - 1
                        paren_close_in_header = _scan_balanced_cpp_paren(header, paren_open_in_header)
                        has_eq_before = "=" in re.sub(r"<[^<>]*>", "", prefix_before_name)
                        tail_after_paren = header[paren_close_in_header + 1 :] if paren_close_in_header is not None else ""
                        valid_tail = bool(
                            re.match(
                                r"^\s*(?:const\b|volatile\b|mutable\b|noexcept\b|override\b|final\b|requires\b|&|&&|->|:|\[\[|$)",
                                tail_after_paren,
                            )
                        )
                        if paren_close_in_header is not None and not has_eq_before and valid_tail:
                            body = code_only[i + 1 : close_brace]
                            co_m = re.search(r"\bco_await\b", body)
                            if co_m is not None and not re.search(r"\b(?:get_weak|get_strong)\s*\(", body):
                                qual_name = re.sub(r"\s+", "", m.group(1))
                                line_no = code_only[: i + 1 + co_m.start()].count("\n") + 1
                                findings.append(
                                    Finding(
                                        "WARN",
                                        "CPP-LIFETIME",
                                        rel,
                                        line_no,
                                        f"co_await inside {qual_name}(...) without get_weak() or get_strong() risks dangling 'this' after coroutine suspension",
                                    )
                                )

                i = close_brace + 1
                stmt_start = i
                continue

            i += 1

    # 2. Raw LoadLibraryA / LoadLibraryW (or LoadLibrary) without LoadLibraryEx + LOAD_LIBRARY_SEARCH_SYSTEM32
    has_safe_cpp_dll = "LoadLibraryEx" in code_only and "LOAD_LIBRARY_SEARCH_SYSTEM32" in code_only
    if not has_safe_cpp_dll:
        for m in re.finditer(r"(?<![.\w>])\bLoadLibrary(?:A|W)?\s*\(", code_only):
            line_no = code_only[: m.start()].count("\n") + 1
            findings.append(
                Finding(
                    "WARN",
                    "SECURITY",
                    rel,
                    line_no,
                    "Raw LoadLibraryA/LoadLibraryW without LoadLibraryEx + LOAD_LIBRARY_SEARCH_SYSTEM32 risks DLL search-order hijacking",
                )
            )

    # 3. AdjustWindowRect instead of AdjustWindowRectExForDpi
    for m in re.finditer(r"(?<![.\w>])\bAdjustWindowRect(?:Ex)?\s*\(", code_only):
        line_no = code_only[: m.start()].count("\n") + 1
        findings.append(
            Finding(
                "WARN",
                "DPI",
                rel,
                line_no,
                "AdjustWindowRect/AdjustWindowRectEx assumes 96 DPI; use AdjustWindowRectExForDpi for PerMonitorV2 DPI scaling",
            )
        )

    return findings


def _make_sarif_rule(
    rule_id: str,
    name: str,
    level: str,
    short_desc: str,
    tags: list[str],
) -> dict[str, object]:
    return {
        "id": rule_id,
        "name": name,
        "shortDescription": {"text": short_desc},
        "defaultConfiguration": {"level": level},
        "properties": {"tags": ["windows-native", *tags]},
    }


SARIF_RULES: list[dict[str, object]] = [
    _make_sarif_rule("WN-CSPROJ-001", "WpfTrimmingOrAotUnsupported", "error", "PublishTrimmed or PublishAot is unsupported with UseWPF=true (NETSDK1168).", ["csproj", "wpf"]),
    _make_sarif_rule("WN-CSPROJ-002", "LibraryImportRequiresUnsafe", "error", "[LibraryImport] requires AllowUnsafeBlocks=true (SYSLIB1062).", ["csproj", "interop"]),
    _make_sarif_rule("WN-CSPROJ-003", "MvvmPartialPropertyRequires842", "error", "CommunityToolkit.Mvvm < 8.4.2 fails CS9248 on partial [ObservableProperty].", ["csproj", "mvvm"]),
    _make_sarif_rule("WN-CSPROJ-004", "WinExeMissingApplicationManifest", "warning", "OutputType=WinExe lacks an ApplicationManifest for PerMonitorV2 DPI and Win10/11 supportedOS.", ["csproj", "manifest"]),
    _make_sarif_rule("WN-CSPROJ-005", "PublishSingleFileConfiguration", "warning", "PublishSingleFile configuration issue (missing IncludeNativeLibrariesForSelfExtract, IncludeAllContentForSelfExtract, or unconditional Debug packing).", ["csproj", "packaging"]),
    _make_sarif_rule("WN-CSPROJ-006", "MissingPublishReadyToRun", "note", "Release desktop WinExe builds benefit from PublishReadyToRun=true.", ["csproj", "performance"]),
    _make_sarif_rule("WN-CSPROJ-007", "InvalidCsprojXml", "error", "Malformed XML in .csproj file.", ["csproj"]),
    _make_sarif_rule("WN-MANIFEST-001", "ManifestMissingPerMonitorV2", "warning", "app.manifest lacks PerMonitorV2 dpiAwareness.", ["manifest", "dpi"]),
    _make_sarif_rule("WN-MANIFEST-002", "ManifestMissingSupportedOs", "warning", "app.manifest lacks Windows 10/11 supportedOS compatibility GUID.", ["manifest"]),
    _make_sarif_rule("WN-MANIFEST-003", "ManifestRequestsAdministrator", "warning", "app.manifest requests requireAdministrator elevation (review least privilege & UIPI).", ["manifest", "security"]),
    _make_sarif_rule("WN-MANIFEST-004", "ManifestMissingLongPathAware", "note", "app.manifest lacks longPathAware=true.", ["manifest"]),
    _make_sarif_rule("WN-MANIFEST-005", "InvalidManifestXml", "error", "Malformed XML in .manifest file.", ["manifest"]),
    _make_sarif_rule("WN-WPF-001", "WpfInvalidVisualStateSetters", "error", "VisualState.Setters is WinUI/UWP only and invalid in WPF XAML.", ["wpf", "xaml"]),
    _make_sarif_rule("WN-WPF-002", "WpfInvalidAccessibilityView", "error", "AutomationProperties.AccessibilityView is WinUI/UWP only and triggers MC3072 in WPF.", ["wpf", "xaml", "a11y"]),
    _make_sarif_rule("WN-WPF-003", "WpfChildrenIndexerAssignment", "error", "Direct Panel.Children[i] = x assignment throws in WPF; use RemoveAt + Insert.", ["wpf", "csharp"]),
    _make_sarif_rule("WN-WINUI-001", "WinUI3WindowCurrentNull", "error", "Window.Current is always null in WinUI 3 desktop apps.", ["winui3", "csharp"]),
    _make_sarif_rule("WN-WINUI-002", "WinUI3UnpackagedApplicationData", "warning", "ApplicationData.Current throws in unpackaged apps without a Package.Current / GetCurrentPackageFullName guard.", ["winui3", "packaging"]),
    _make_sarif_rule("WN-WV2-001", "WebView2DefaultUserDataFolder", "warning", "EnsureCoreWebView2Async() without explicit environment/UserDataFolder fails under Program Files.", ["webview2", "packaging"]),
    _make_sarif_rule("WN-WV2-002", "WebView2HostObjectSurface", "note", "AddHostObjectToScript exposes .NET/COM host objects to web script.", ["webview2", "security"]),
    _make_sarif_rule("WN-WV2-003", "WebView2DevToolsInRelease", "warning", "AreDevToolsEnabled = true outside #if DEBUG leaves DevTools enabled in Release.", ["webview2", "security"]),
    _make_sarif_rule("WN-SEC-001", "DpapiLocalMachineScope", "error", "ProtectedData.Protect uses DataProtectionScope.LocalMachine instead of CurrentUser.", ["security", "dpapi"]),
    _make_sarif_rule("WN-SEC-002", "UnsafeShellExecuteProcessStart", "warning", "Process.Start with UseShellExecute=true uses unvalidated or interpolated target/arguments.", ["security"]),
    _make_sarif_rule("WN-SEC-003", "UnrestrictedNamedPipeServer", "warning", "NamedPipeServerStream created without PipeOptions.CurrentUserOnly or PipeSecurity.", ["security", "ipc"]),
    _make_sarif_rule("WN-SEC-004", "TlsValidationDisabled", "error", "ServerCertificateCustomValidationCallback unconditionally returns true or uses DangerousAcceptAnyServerCertificateValidator outside #if DEBUG.", ["security", "tls"]),
    _make_sarif_rule("WN-SEC-005", "UnsafeLoadLibrary", "warning", "LoadLibrary/LoadLibraryA/LoadLibraryW used without LoadLibraryEx + LOAD_LIBRARY_SEARCH_SYSTEM32.", ["security", "dll-hijacking"]),
    _make_sarif_rule("WN-LIFE-001", "MutexPrematureGc", "warning", "new Mutex(...) without GC.KeepAlive or using scope risks premature finalization.", ["lifecycle"]),
    _make_sarif_rule("WN-LIFE-002", "SystemEventsLeak", "warning", "SystemEvents subscription without matching -= unsubscription leaks strong GC roots.", ["lifecycle", "memory-leak"]),
    _make_sarif_rule("WN-LIFE-003", "AsyncVoidNonEventHandler", "warning", "async void method outside event handler or UI lifecycle override can crash the process.", ["lifecycle"]),
    _make_sarif_rule("WN-LIFE-004", "UnpairedRegisterHotKey", "warning", "RegisterHotKey called without matching UnregisterHotKey cleanup.", ["lifecycle"]),
    _make_sarif_rule("WN-LIFE-005", "ApplicationIdlePushFrameHang", "warning", "Dispatcher.PushFrame(ApplicationIdle) hangs when 60 FPS CompositionTarget.Rendering runs.", ["lifecycle", "wpf"]),
    _make_sarif_rule("WN-CPP-001", "CppWinrtCoroutineDanglingThis", "warning", "co_await inside Class::Method(...) without get_weak() or get_strong() risks dangling this.", ["cpp", "cppwinrt", "lifetime"]),
    _make_sarif_rule("WN-CPP-002", "CppNonDpiAdjustWindowRect", "warning", "AdjustWindowRect/AdjustWindowRectEx assumes 96 DPI; use AdjustWindowRectExForDpi.", ["cpp", "dpi"]),
    _make_sarif_rule("WN-A11Y-001", "IconButtonMissingAutomationName", "warning", "Icon-only Button missing AutomationProperties.Name.", ["a11y", "xaml"]),
    _make_sarif_rule("WN-A11Y-002", "FocusVisualStyleRemoved", "warning", "FocusVisualStyle='{x:Null}' removes keyboard focus cue.", ["a11y", "xaml"]),
    _make_sarif_rule("WN-A11Y-003", "ClickableBorderNotFocusable", "warning", "Clickable Border is not keyboard-focusable; use Button or ListBoxItem.", ["a11y", "xaml"]),
    _make_sarif_rule("WN-PERF-001", "UiVirtualizationDisabled", "warning", "UI virtualization disabled (ScrollViewer wrapping ItemsControl/ListBox or CanContentScroll=False).", ["performance", "xaml"]),
    _make_sarif_rule("WN-PERF-002", "ItemTemplateDropShadow", "warning", "Shadow effect inside DataTemplate/ItemTemplate multiplies GPU shader passes.", ["performance", "xaml"]),
    _make_sarif_rule("WN-PERF-003", "UnfrozenResourceOrBrush", "warning", "Static WPF brush/effect resource or runtime SolidColorBrush not frozen.", ["performance", "wpf"]),
    _make_sarif_rule("WN-PERF-004", "TransientHttpClient", "warning", "new HttpClient() inside method/loop risks socket exhaustion and stale DNS.", ["performance", "networking"]),
    _make_sarif_rule("WN-PERF-005", "RenderingCallbackIssue", "warning", "CompositionTarget.Rendering leak, missing RenderingTime dedupe, BlurRadius animation, or .Height mutation.", ["performance", "animation"]),
    _make_sarif_rule("WN-PERF-006", "ForeverAnimationOnLoaded", "warning", "RepeatBehavior='Forever' started on Loaded keeps ticking while Collapsed.", ["performance", "animation"]),
    _make_sarif_rule("WN-CONTRAST-001", "WcagContrastBelowThreshold", "warning", "Foreground/background palette brush contrast ratio is below WCAG AA 4.5:1.", ["a11y", "contrast"]),
    _make_sarif_rule("WN-UI-001", "HardcodedHexColorToken", "warning", "Hardcoded hex color in view/control XAML; prefer a DynamicResource/ThemeResource token.", ["ui", "theming"]),
    _make_sarif_rule("WN-UI-002", "AllowsTransparencyBreaksDwm", "warning", "Window AllowsTransparency='True' breaks Windows 11 corners, Snap Layouts, and Mica.", ["ui", "dwm"]),
    _make_sarif_rule("WN-UI-003", "WindowChromeMissingSnapOrHitTest", "warning", "WindowChrome title bar missing IsHitTestVisibleInChrome or HTMAXBUTTON Snap Layout handling.", ["ui", "chrome"]),
    _make_sarif_rule("WN-UI-004", "MultiMonitorUnsignedCoordinates", "warning", "WM_NCHITTEST lParam extraction missing signed (short) casts for negative multi-monitor coordinates.", ["ui", "dpi"]),
]

_SARIF_RULE_INDEX = {str(rule["id"]): idx for idx, rule in enumerate(SARIF_RULES)}
_SARIF_LEVEL_MAP = {"ERROR": "error", "WARN": "warning", "INFO": "note"}


def _resolve_rule_id(detail: dict[str, object]) -> str:
    tag = str(detail.get("tag") or "")
    msg = str(detail.get("message") or "")

    if tag == "CONTRAST":
        return "WN-CONTRAST-001"
    if tag == "CSPROJ":
        if "Invalid XML" in msg:
            return "WN-CSPROJ-007"
        if "PublishTrimmed/PublishAot" in msg:
            return "WN-CSPROJ-001"
        if "LibraryImport" in msg:
            return "WN-CSPROJ-002"
        if "CommunityToolkit.Mvvm" in msg:
            return "WN-CSPROJ-003"
        if "ApplicationManifest" in msg:
            return "WN-CSPROJ-004"
        if "PublishSingleFile" in msg or "IncludeAllContentForSelfExtract" in msg:
            return "WN-CSPROJ-005"
        return "WN-CSPROJ-006"
    if tag == "MANIFEST":
        if "Invalid XML" in msg:
            return "WN-MANIFEST-005"
        if "PerMonitorV2" in msg:
            return "WN-MANIFEST-001"
        if "supportedOS" in msg:
            return "WN-MANIFEST-002"
        if "requireAdministrator" in msg:
            return "WN-MANIFEST-003"
        return "WN-MANIFEST-004"
    if tag == "WPF-BUG":
        if "VisualState.Setters" in msg:
            return "WN-WPF-001"
        if "AccessibilityView" in msg:
            return "WN-WPF-002"
        return "WN-WPF-003"
    if tag == "WINUI3":
        if "Window.Current" in msg:
            return "WN-WINUI-001"
        return "WN-WINUI-002"
    if tag == "WEBVIEW2":
        if "EnsureCoreWebView2Async" in msg:
            return "WN-WV2-001"
        if "AddHostObjectToScript" in msg:
            return "WN-WV2-002"
        return "WN-WV2-003"
    if tag == "SECURITY":
        if "ProtectedData.Protect" in msg:
            return "WN-SEC-001"
        if "Process.Start" in msg:
            return "WN-SEC-002"
        if "NamedPipeServerStream" in msg:
            return "WN-SEC-003"
        if "ServerCertificateCustomValidationCallback" in msg or "DangerousAcceptAnyServerCertificateValidator" in msg:
            return "WN-SEC-004"
        return "WN-SEC-005"
    if tag in ("LIFECYCLE", "MEMORY-LEAK", "TRAP"):
        if "Mutex" in msg:
            return "WN-LIFE-001"
        if "SystemEvents." in msg:
            return "WN-LIFE-002"
        if "async void" in msg:
            return "WN-LIFE-003"
        if "RegisterHotKey" in msg:
            return "WN-LIFE-004"
        return "WN-LIFE-005"
    if tag == "CPP-LIFETIME":
        return "WN-CPP-001"
    if tag == "DPI":
        return "WN-CPP-002"
    if tag == "A11Y":
        if "Icon-only Button" in msg:
            return "WN-A11Y-001"
        if "FocusVisualStyle" in msg:
            return "WN-A11Y-002"
        return "WN-A11Y-003"
    if tag in ("PERF", "FREEZE", "ANIM", "ANIM-LEAK"):
        if "ScrollViewer" in msg or "CanContentScroll" in msg:
            return "WN-PERF-001"
        if "Shadow effect" in msg:
            return "WN-PERF-002"
        if "Freeze" in msg:
            return "WN-PERF-003"
        if "HttpClient" in msg:
            return "WN-PERF-004"
        if "RepeatBehavior" in msg:
            return "WN-PERF-006"
        return "WN-PERF-005"
    if tag == "TOKEN":
        return "WN-UI-001"
    if tag == "DWM":
        return "WN-UI-002"
    if tag == "CHROME":
        return "WN-UI-003"
    if tag == "DPI/MULTI-MON":
        return "WN-UI-004"
    return "WN-UI-001"


def _find_brush_definition_location(root: Path, message: str) -> tuple[str, int]:
    m = re.match(r"^'([^']+)'\s+on\s+'([^']+)'", message)
    brush_key = m.group(1) if m else None
    xaml_files = iter_project_files(root, (".xaml",)) if root.is_dir() else []
    if brush_key:
        key_pat = re.compile(rf'\bx:Key="{re.escape(brush_key)}"')
        for xf in xaml_files:
            text = strip_xml_comments_preserve_lines(xf.read_text(encoding="utf-8", errors="replace"))
            km = key_pat.search(text)
            if km:
                line_no = text[: km.start()].count("\n") + 1
                return xf.relative_to(root).as_posix(), line_no
    if xaml_files:
        return xaml_files[0].relative_to(root).as_posix(), 1
    return ".", 1


def build_sarif_report(result: dict[str, object]) -> dict[str, object]:
    """Convert a run_audit() dictionary into a valid SARIF 2.1.0 report."""
    root = Path(str(result.get("root") or "."))
    details = result.get("details") or []
    sarif_results: list[dict[str, object]] = []

    for detail in details:
        if not isinstance(detail, dict):
            continue
        severity = str(detail.get("severity") or "WARN").upper()
        level = _SARIF_LEVEL_MAP.get(severity, "warning")
        rule_id = _resolve_rule_id(detail)
        rule_index = _SARIF_RULE_INDEX[rule_id]
        message_text = str(detail.get("message") or "")
        file_rel = detail.get("file")
        line_raw = detail.get("line")

        if isinstance(file_rel, str) and file_rel:
            uri = file_rel.replace("\\", "/")
            start_line = int(line_raw) if isinstance(line_raw, int) and line_raw >= 1 else 1
        else:
            uri, start_line = _find_brush_definition_location(root, message_text)

        sarif_results.append(
            {
                "ruleId": rule_id,
                "ruleIndex": rule_index,
                "level": level,
                "message": {"text": message_text},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": uri},
                            "region": {"startLine": start_line},
                        }
                    }
                ],
            }
        )

    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "windows-native-auditor",
                        "version": "2.0.0",
                        "informationUri": "https://github.com/Destro01400/windows-native",
                        "rules": SARIF_RULES,
                    }
                },
                "results": sarif_results,
            }
        ],
    }


def run_audit(root: Path, ui_only: bool = False) -> dict[str, object]:
    xaml_files = iter_project_files(root, (".xaml",))
    cs_files = iter_project_files(root, (".cs",))
    cpp_files = [] if ui_only else iter_project_files(root, (".cpp", ".cc", ".h", ".hpp"))
    csproj_files = [] if ui_only else iter_project_files(root, (".csproj",))
    manifest_files = [] if ui_only else iter_project_files(root, (".manifest",))
    appx_manifests = [] if ui_only else iter_project_files(root, (".appxmanifest",))

    findings: list[Finding] = []
    use_wpf_any = False
    use_winui_any = False
    unpackaged_dirs: set[Path] = set()

    if not ui_only:
        central_versions = _collect_central_package_versions(root)
        for csproj in csproj_files:
            proj_findings, use_wpf, use_winui = audit_csproj(csproj, root, cs_files, central_versions, bool(appx_manifests))
            findings.extend(proj_findings)
            use_wpf_any = use_wpf_any or use_wpf
            use_winui_any = use_winui_any or use_winui
        unpackaged_dirs = _collect_unpackaged_project_dirs(csproj_files)

        for mf in manifest_files:
            findings.extend(audit_manifest(mf, root))

    project_is_winui_only = use_winui_any and not use_wpf_any

    findings.extend(audit_palette_contrast(xaml_files))
    for xf in xaml_files:
        findings.extend(audit_xaml(xf, root, project_is_winui_only=project_is_winui_only))
    for cf in cs_files:
        findings.extend(audit_cs_ui(cf, root))
        if not ui_only:
            is_unpackaged = _cs_belongs_to_unpackaged_project(cf, root, csproj_files, unpackaged_dirs)
            findings.extend(audit_cs_engineering(cf, root, is_unpackaged=is_unpackaged))
    for cppf in cpp_files:
        findings.extend(audit_cpp(cppf, root))

    counts = {
        "error": sum(1 for f in findings if f.severity == "ERROR"),
        "warn": sum(1 for f in findings if f.severity == "WARN"),
        "info": sum(1 for f in findings if f.severity == "INFO"),
    }

    return {
        "root": str(root),
        "mode": "ui-only" if ui_only else "full",
        "xaml_files": len(xaml_files),
        "cs_files": len(cs_files),
        "cpp_files": len(cpp_files),
        "csproj_files": len(csproj_files),
        "manifest_files": len(manifest_files),
        "counts": counts,
        "findings": [f.format_line() for f in findings],
        "details": [asdict(f) for f in findings],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static auditor for Windows desktop apps (WPF, WinUI 3, C++/WinRT, .csproj, manifest, C#).")
    parser.add_argument("project_dir", help="Path to the Windows app project directory")
    parser.add_argument("--ui-only", action="store_true", help="Run only XAML & UI C# checks (audit_wpf_ui.py compatibility mode)")
    parser.add_argument("--strict", action="store_true", help="Exit with code 1 if any ERROR or WARN finding is reported (INFO notes do not fail)")
    output_group = parser.add_mutually_exclusive_group()
    output_group.add_argument("--json", action="store_true", help="Print findings as JSON")
    output_group.add_argument("--sarif", action="store_true", help="Print findings as SARIF 2.1.0 JSON")
    args = parser.parse_args(argv)

    root = Path(args.project_dir).resolve()
    if not root.is_dir():
        print(f"Directory not found: {root}", file=sys.stderr)
        return 2

    result = run_audit(root, ui_only=args.ui_only)

    if args.json:
        print(json.dumps(result, indent=2))
    elif args.sarif:
        print(json.dumps(build_sarif_report(result), indent=2))
    else:
        print(
            f"Scanned {result['xaml_files']} XAML, {result['cs_files']} C#, {result['cpp_files']} C++, "
            f"{result['csproj_files']} .csproj, {result['manifest_files']} .manifest files in {root} "
            f"(mode={result['mode']})"
        )
        counts = result["counts"]
        print(
            f"Total findings: {len(result['findings'])} "
            f"(error={counts['error']}, warn={counts['warn']}, info={counts['info']})\n"
        )
        for item in result["findings"]:
            print(item)

    blocking = result["counts"]["error"] + result["counts"]["warn"]
    return 1 if (args.strict and blocking > 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
