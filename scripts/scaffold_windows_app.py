#!/usr/bin/env python3
"""Zero-dependency CLI scaffolder for native Windows starter templates.

Usage:
  python scaffold_windows_app.py --list
  python scaffold_windows_app.py --template wpf-modern --name MyApp --out ./MyApp
  python scaffold_windows_app.py --template winui3-aot --name MyApp --namespace Company.MyApp --out ./MyApp
  python scaffold_windows_app.py --template cppwinrt-dcomp --name MyTool --out ./MyTool --force
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import uuid

APP_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
NAMESPACE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)*$")
SKIP_NAMES = {"__pycache__", ".git", "bin", "obj"}

TEMPLATES: dict[str, str] = {
    "wpf-modern": ".NET 10 WPF + Generic Host DI + WindowChrome Snap Layouts + CsWin32 + MotionSettings + WCAG tokens",
    "winui3-aot": ".NET 10 WinUI 3 + Windows App SDK 1.7 + NativeAOT + AppInstance single-instance + TitleBar + Mica",
    "cppwinrt-dcomp": "C++20 / CMake + C++/WinRT + Direct2D + DirectComposition + PerMonitorV2 DPI",
}


@dataclass(frozen=True)
class ScaffoldResult:
    """Summary returned by scaffold_project."""

    template: str
    app_name: str
    namespace: str
    app_guid: str
    output_dir: Path
    files: tuple[Path, ...]


def get_templates_root() -> Path:
    return Path(__file__).resolve().parent.parent / "assets" / "templates"


def validate_app_name(name: str) -> str:
    if not name or not APP_NAME_RE.fullmatch(name):
        raise ValueError(
            f"Invalid --name '{name}'. Expected identifier matching ^[A-Za-z][A-Za-z0-9_]*$."
        )
    return name


def validate_namespace(namespace: str) -> str:
    if not namespace or not NAMESPACE_RE.fullmatch(namespace):
        raise ValueError(
            f"Invalid --namespace '{namespace}'. Expected dotted identifier segments matching ^[A-Za-z][A-Za-z0-9_]*$."
        )
    return namespace


def _apply_tokens(value: str, tokens: dict[str, str]) -> str:
    for placeholder, replacement in tokens.items():
        value = value.replace(placeholder, replacement)
    return value


def scaffold_project(
    template: str,
    app_name: str,
    output_dir: Path,
    namespace: str | None = None,
    force: bool = False,
    templates_root: Path | None = None,
) -> ScaffoldResult:
    """Generate a project from a template directory into output_dir."""
    if template not in TEMPLATES:
        available = ", ".join(TEMPLATES)
        raise ValueError(f"Unknown template '{template}'. Choose one of: {available}.")

    validated_name = validate_app_name(app_name)
    validated_ns = validate_namespace(namespace if namespace is not None else validated_name)

    root = (templates_root or get_templates_root()) / template
    if not root.is_dir():
        raise FileNotFoundError(f"Template directory does not exist: {root}")

    resolved_out = output_dir.resolve()
    if resolved_out.exists():
        if not resolved_out.is_dir():
            raise FileExistsError(f"Target path exists and is not a directory: {resolved_out}")
        if any(resolved_out.iterdir()) and not force:
            raise FileExistsError(
                f"Target directory is not empty: {resolved_out}. Pass --force to overwrite."
            )

    resolved_out.mkdir(parents=True, exist_ok=True)
    app_guid = str(uuid.uuid4()).upper()
    tokens = {
        "{{APP_NAME}}": validated_name,
        "{{NAMESPACE}}": validated_ns,
        "{{APP_GUID}}": app_guid,
    }

    written: list[Path] = []
    for src_path in sorted(root.rglob("*")):
        if not src_path.is_file():
            continue
        if any(part in SKIP_NAMES for part in src_path.parts):
            continue

        rel_parts = [_apply_tokens(part, tokens) for part in src_path.relative_to(root).parts]
        dest_path = (resolved_out.joinpath(*rel_parts)).resolve()
        if resolved_out not in dest_path.parents and dest_path != resolved_out:
            raise ValueError(f"Refusing path outside target directory: {dest_path}")

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            content = src_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            dest_path.write_bytes(src_path.read_bytes())
        else:
            rendered = _apply_tokens(content, tokens)
            dest_path.write_text(rendered, encoding="utf-8", newline="\n")

        written.append(dest_path)

    return ScaffoldResult(
        template=template,
        app_name=validated_name,
        namespace=validated_ns,
        app_guid=app_guid,
        output_dir=resolved_out,
        files=tuple(written),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scaffold a native Windows desktop starter project (WPF, WinUI 3 NativeAOT, or C++/WinRT DirectComposition)."
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available starter templates and exit",
    )
    parser.add_argument(
        "--template",
        choices=tuple(TEMPLATES.keys()),
        help="Starter template to generate",
    )
    parser.add_argument(
        "--name",
        help="Application name (must match ^[A-Za-z][A-Za-z0-9_]*$)",
    )
    parser.add_argument(
        "--out",
        help="Destination directory path",
    )
    parser.add_argument(
        "--namespace",
        default=None,
        help="Root namespace (defaults to --name)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow writing into a non-empty target directory and overwriting existing files",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        print("Available templates:")
        for key, desc in TEMPLATES.items():
            print(f"  {key:<16} {desc}")
        return 0

    missing = [
        flag
        for flag, val in (("--template", args.template), ("--name", args.name), ("--out", args.out))
        if not val
    ]
    if missing:
        parser.error(f"the following arguments are required: {', '.join(missing)}")

    try:
        result = scaffold_project(
            template=args.template,
            app_name=args.name,
            output_dir=Path(args.out),
            namespace=args.namespace,
            force=args.force,
        )
    except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Scaffolded '{result.template}' as '{result.app_name}' "
        f"(namespace={result.namespace}, guid={result.app_guid}) -> {result.output_dir}"
    )
    print(f"Created {len(result.files)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
