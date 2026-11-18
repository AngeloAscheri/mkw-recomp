#!/usr/bin/env python3
"""Packs a spirv/ folder's runtime inputs (<key>.spv, .res.json and .cs.spv) into spirv/shaders.pack, the one file the
boot prewarm reads them from (runtime/gfx/nvn/host/gfx_shader.c prepared_read).

Why: the prewarm loads every program of the copy, 23 124 small files. With the file cache cold (any start after a
reboot) the Windows PC took 24.0 s for them, the 7 loading threads no faster than one; the same 349 MB as one file read
cold in 0.68 s (prep-pack, 18/11/2026). The loose files stay: the tools and an update's --base read them.

Format (little-endian): "MKWSPK1\\0", u32 version, u32 count; count entries of 72 bytes sorted by key (key[32], then
offset u64 and length u32 of the .spv, the .res.json and the .cs.spv; length 0 = no such file); then the data. Written
beside, renamed, then its last write time set to now: while it is current the folder's last write time is never later
than the pack's. Any file written, renamed or removed in the folder afterwards (put() of translate.py renames) moves the
folder's time past it, and the runtime then reads the loose files.

Usage: python3 tools/shaders/pack.py [--dir build/spirv]   (seconds)
"""

import argparse
import os
import struct
from pathlib import Path

MAGIC = b"MKWSPK1\0"
VERSION = 1
NAME = "shaders.pack"
ENTRY = struct.Struct("<32sQIQIQI4x")
SUFFIXES = (".spv", ".res.json", ".cs.spv")


def keys(folder: Path) -> list[str]:
    """Every program with a reflection file: the runtime loads no program without one."""
    return sorted(n[: -len(".res.json")] for n in os.listdir(folder) if n.endswith(".res.json") and len(n) == 73)


def current(folder: Path) -> bool:
    """Whether folder/shaders.pack is of this format and the runtime would use it (the folder not written after it)."""
    p = folder / NAME
    try:
        with p.open("rb") as f:
            head = f.read(12)
        fresh = folder.stat().st_mtime_ns <= p.stat().st_mtime_ns
    except OSError:
        return False
    return fresh and head[:8] == MAGIC and int.from_bytes(head[8:12], "little") == VERSION


def pack(folder: Path) -> tuple[int, int]:
    """Writes folder/shaders.pack; (programs, bytes)."""
    ks = keys(folder)
    data_off = 16 + ENTRY.size * len(ks)
    tmp = folder / (NAME + ".tmp")
    with tmp.open("wb") as f:
        f.seek(data_off)
        index, off = [], data_off
        for k in ks:
            spans = []
            for suffix in SUFFIXES:
                try:
                    b = (folder / (k + suffix)).read_bytes()
                except FileNotFoundError:
                    b = b""
                f.write(b)
                spans += [off if b else 0, len(b)]
                off += len(b)
            index.append(ENTRY.pack(bytes.fromhex(k), *spans))
        f.seek(0)
        f.write(MAGIC + struct.pack("<II", VERSION, len(ks)) + b"".join(index))
    os.replace(tmp, folder / NAME)
    os.utime(folder / NAME)  # after the rename, which wrote the folder
    return len(ks), off


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dir", type=Path, help="the spirv/ folder (default build/spirv of this checkout)")
    a = ap.parse_args()
    folder = a.dir or Path(__file__).resolve().parents[2] / "build/spirv"
    n, size = pack(folder)
    print(f"pack.py: {n} programs, {size / 2**20:.0f} MiB in {folder / NAME}")


if __name__ == "__main__":
    main()
