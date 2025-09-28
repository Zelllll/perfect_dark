#!/usr/bin/env python3
"""Standalone helper to assemble Perfect Dark's ASP microcode.

This avoids invoking the full build system. It shells out to armips with the
same arguments as the Makefile rule, then optionally concatenates the IMEM and
DMEM images into a single `asp.bin` blob.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run_armips(armips: Path, source: Path, text_out: Path, data_out: Path) -> None:
    """Invoke armips with the CODE_FILE/DATA_FILE defines."""
    if not shutil.which(str(armips)):
        raise FileNotFoundError(
            f"armips executable '{armips}' was not found in PATH; use --armips to "
            "point at a valid binary."
        )

    cmd = [
        str(armips),
        "-strequ",
        "CODE_FILE",
        text_out.as_posix(),
        "-strequ",
        "DATA_FILE",
        data_out.as_posix(),
        source.as_posix(),
    ]

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"armips failed with exit code {exc.returncode}") from exc


def combine(text_out: Path, data_out: Path, combined: Path) -> None:
    """Concatenate the IMEM and DMEM blobs into a single file."""
    with text_out.open("rb") as f_text, data_out.open("rb") as f_data, combined.open(
        "wb"
    ) as f_out:
        f_out.write(f_text.read())
        f_out.write(f_data.read())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("build/standalone/rsp"),
        help="Directory where asp.text.bin, asp.data.bin, and asp.bin will be written.",
    )
    parser.add_argument(
        "--armips",
        type=Path,
        default=Path("armips"),
        help="Path to the armips executable (defaults to searching PATH).",
    )
    parser.add_argument(
        "--no-combined",
        dest="combined",
        action="store_false",
        help="Do not emit asp.bin (the concatenated IMEM+DMEM image).",
    )

    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parent.parent
    source = repo_root / "src" / "rsp" / "asp.s"

    if not source.exists():
        raise FileNotFoundError(f"Could not find source file: {source}")

    outdir = (repo_root / args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    text_out = outdir / "asp.text.bin"
    data_out = outdir / "asp.data.bin"

    run_armips(args.armips, source, text_out, data_out)

    if args.combined:
        combined_path = outdir / "asp.bin"
        combine(text_out, data_out, combined_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
