"""Write and optionally run a Fluent TUI journal that dumps per-zone wall forces."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

DEFAULT_FLUENT = Path(r"C:\Program Files\ANSYS Inc\v231\fluent\ntbin\win64\fluent.exe")


def find_fluent() -> Path | None:
    env = os.environ.get("FLUENT_EXE")
    if env:
        p = Path(env)
        if p.exists():
            return p
    if DEFAULT_FLUENT.exists():
        return DEFAULT_FLUENT
    which = shutil.which("fluent")
    return Path(which) if which else None


def _posix(path: Path) -> str:
    return path.resolve().as_posix()


def write_force_journal(
    cas_h5: Path,
    out_dir: Path,
    cx_vector: list[float],
    cz_vector: list[float],
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    cx_txt = out_dir / "wall_forces_cx.txt"
    cz_txt = out_dir / "wall_forces_cz.txt"
    journal = out_dir / "dump_wall_forces.jou"
    lines = [
        "/file/set-tui-version \"23.1\"",
        "/file/confirm-overwrite? yes",
        f"/file/read-case-data \"{_posix(cas_h5)}\"",
        (
            "(ti-menu-load-string \"/report/forces/wall-forces yes "
            f"{cx_vector[0]} {cx_vector[1]} {cx_vector[2]} yes "
            f"\\\"{_posix(cx_txt)}\\\" ()\")"
        ),
        (
            "(ti-menu-load-string \"/report/forces/wall-forces yes "
            f"{cz_vector[0]} {cz_vector[1]} {cz_vector[2]} yes "
            f"\\\"{_posix(cz_txt)}\\\" ()\")"
        ),
        "/exit yes",
        "",
    ]
    journal.write_text("\n".join(lines), encoding="utf-8")
    return journal


def pick_cas_h5(cas_paths: list[Path]) -> Path | None:
    h5 = [p for p in cas_paths if p.name.lower().endswith(".cas.h5") and p.exists()]
    if not h5:
        return None
    return max(h5, key=lambda p: p.stat().st_size)


def run_fluent_dump(
    cas_h5: Path,
    out_dir: Path,
    cx_vector: list[float],
    cz_vector: list[float],
    *,
    procs: int = 4,
    timeout_s: int = 900,
) -> dict:
    fluent = find_fluent()
    journal = write_force_journal(cas_h5, out_dir, cx_vector, cz_vector)
    log_path = out_dir / "dump_wall_forces.log"
    if fluent is None:
        return {
            "ok": False,
            "reason": "Brak fluent.exe (ustaw FLUENT_EXE albo zainstaluj v231).",
            "journal": str(journal),
            "ran": False,
        }
    cmd = [
        str(fluent),
        "3ddp",
        "-g",
        "-wait",
        f"-t{procs}",
        "-i",
        str(journal),
    ]
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            proc = subprocess.run(
                cmd,
                cwd=str(out_dir),
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout_s,
            )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "reason": f"Fluent przekroczył {timeout_s}s przy zrzucie sił.",
            "journal": str(journal),
            "log": str(log_path),
            "ran": True,
            "cmd": cmd,
        }
    cx_txt = out_dir / "wall_forces_cx.txt"
    cz_txt = out_dir / "wall_forces_cz.txt"
    ok = proc.returncode == 0 and cx_txt.exists() and cz_txt.exists()
    return {
        "ok": ok,
        "ran": True,
        "returncode": proc.returncode,
        "journal": str(journal),
        "log": str(log_path),
        "cmd": cmd,
        "files": [p.name for p in (cx_txt, cz_txt) if p.exists()],
        "reason": None if ok else "Fluent skończył bez kompletnych plików wall_forces_*.txt.",
    }
