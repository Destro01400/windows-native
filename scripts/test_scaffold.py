#!/usr/bin/env python3
"""Unit tests for scaffold_windows_app.py and starter templates."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import uuid

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import scaffold_windows_app as scaffolder  # noqa: E402

PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-B", str(SCRIPTS_DIR / "scaffold_windows_app.py"), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        check=False,
    )


class ScaffoldCliTests(unittest.TestCase):
    def test_list_templates(self) -> None:
        proc = _run_cli("--list")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for name in ("wpf-modern", "winui3-aot", "cppwinrt-dcomp"):
            self.assertIn(name, proc.stdout)

    def test_rejects_invalid_app_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            for bad_name in ("123App", "My-App", "My App", "App.Name", "../Escape", "_LeadingUnderscore"):
                proc = _run_cli("--template", "wpf-modern", "--name", bad_name, "--out", str(out_dir))
                self.assertNotEqual(proc.returncode, 0, f"Expected failure for invalid name '{bad_name}'")
                self.assertIn("Invalid --name", proc.stderr)

    def test_rejects_missing_required_args_without_list(self) -> None:
        proc = _run_cli("--template", "wpf-modern")
        self.assertNotEqual(proc.returncode, 0)

    def test_refuses_non_empty_directory_without_force_and_allows_with_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "existing"
            target.mkdir()
            sentinel = target / "keep.txt"
            sentinel.write_text("important", encoding="utf-8")

            denied = _run_cli("--template", "wpf-modern", "--name", "SampleApp", "--out", str(target))
            self.assertNotEqual(denied.returncode, 0)
            self.assertIn("not empty", denied.stderr)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "important")
            self.assertFalse((target / "SampleApp.csproj").exists())

            allowed = _run_cli(
                "--template", "wpf-modern", "--name", "SampleApp", "--out", str(target), "--force"
            )
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            self.assertTrue((target / "SampleApp.csproj").exists())

    def test_allows_existing_empty_directory_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "empty_dir"
            target.mkdir()
            proc = _run_cli("--template", "cppwinrt-dcomp", "--name", "TinyTool", "--out", str(target))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertTrue((target / "CMakeLists.txt").exists())

    def test_all_templates_generate_and_substitute_placeholders(self) -> None:
        expected_files = {
            "wpf-modern": {
                "SampleApp.csproj",
                "app.manifest",
                "App.xaml",
                "App.xaml.cs",
                "MainWindow.xaml",
                "MainWindow.xaml.cs",
                "NativeMethods.txt",
                "NativeMethods.json",
                "Themes/Tokens.xaml",
                "Motion/MotionSettings.cs",
                "ViewModels/MainViewModel.cs",
            },
            "winui3-aot": {
                "SampleApp.csproj",
                "app.manifest",
                "Program.cs",
                "App.xaml",
                "App.xaml.cs",
                "MainWindow.xaml",
                "MainWindow.xaml.cs",
                "ViewModels/MainViewModel.cs",
            },
            "cppwinrt-dcomp": {
                "CMakeLists.txt",
                "app.manifest",
                "src/main.cpp",
                "src/d2d_window.hpp",
            },
        }

        guids_seen: set[str] = set()

        with tempfile.TemporaryDirectory() as tmp:
            for template_name, rel_set in expected_files.items():
                out_dir = Path(tmp) / template_name
                proc = _run_cli(
                    "--template",
                    template_name,
                    "--name",
                    "SampleApp",
                    "--namespace",
                    "Contoso.SampleApp",
                    "--out",
                    str(out_dir),
                )
                self.assertEqual(proc.returncode, 0, f"{template_name} failed: {proc.stderr}")

                actual_rel = {
                    p.relative_to(out_dir).as_posix()
                    for p in out_dir.rglob("*")
                    if p.is_file()
                }
                self.assertEqual(actual_rel, rel_set, f"File mismatch in {template_name}")

                for p in out_dir.rglob("*"):
                    if not p.is_file():
                        continue
                    rel = p.relative_to(out_dir).as_posix()
                    self.assertIsNone(PLACEHOLDER_RE.search(rel), f"Unreplaced token in path {rel}")
                    text = p.read_text(encoding="utf-8")
                    self.assertIsNone(
                        PLACEHOLDER_RE.search(text),
                        f"Unreplaced placeholder in {template_name}/{rel}",
                    )

                manifest_text = (out_dir / "app.manifest").read_text(encoding="utf-8")
                self.assertIn('name="Contoso.SampleApp.app"', manifest_text)
                self.assertIn("PerMonitorV2", manifest_text)
                self.assertIn("{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}", manifest_text)
                self.assertIn("<longPathAware", manifest_text)
                self.assertIn(">true</longPathAware>", manifest_text)
                self.assertIn('level="asInvoker"', manifest_text)

                if template_name == "wpf-modern":
                    native_txt = (out_dir / "NativeMethods.txt").read_text(encoding="utf-8")
                    for line in native_txt.splitlines():
                        self.assertFalse(
                            line.lstrip().startswith("#"),
                            "NativeMethods.txt must use // comments, never #",
                        )
                    app_cs = (out_dir / "App.xaml.cs").read_text(encoding="utf-8")
                    m = re.search(r"([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})", app_cs)
                    self.assertIsNotNone(m, "Expected generated GUID in wpf-modern App.xaml.cs")
                    if m:
                        uuid.UUID(m.group(1))
                        guids_seen.add(m.group(1))
                elif template_name == "winui3-aot":
                    prog_cs = (out_dir / "Program.cs").read_text(encoding="utf-8")
                    self.assertNotIn("_ = new App()", prog_cs)
                    m = re.search(r"([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})", prog_cs)
                    self.assertIsNotNone(m, "Expected generated GUID in winui3-aot Program.cs")
                    if m:
                        uuid.UUID(m.group(1))
                        guids_seen.add(m.group(1))
                elif template_name == "cppwinrt-dcomp":
                    hpp = (out_dir / "src" / "d2d_window.hpp").read_text(encoding="utf-8")
                    m = re.search(r"([0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12})", hpp)
                    self.assertIsNotNone(m, "Expected generated GUID in cppwinrt-dcomp d2d_window.hpp")
                    if m:
                        uuid.UUID(m.group(1))
                        guids_seen.add(m.group(1))

        self.assertEqual(len(guids_seen), 3, "Each scaffold run should generate a fresh unique GUID")

    def test_default_namespace_matches_app_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "default_ns"
            result = scaffolder.scaffold_project(
                template="wpf-modern",
                app_name="EchoDesk",
                output_dir=out_dir,
            )
            self.assertEqual(result.namespace, "EchoDesk")
            vm_cs = (out_dir / "ViewModels" / "MainViewModel.cs").read_text(encoding="utf-8")
            self.assertIn("namespace EchoDesk.ViewModels;", vm_cs)


if __name__ == "__main__":
    unittest.main()
