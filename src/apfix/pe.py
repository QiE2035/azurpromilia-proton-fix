"""Thin helpers around :mod:`pefile` so we can sanity-check what we are patching."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pefile

__all__ = ["PEInfo", "read_pe"]

MACHINES = {0x8664: "x86-64", 0x14C: "x86", 0xAA64: "arm64"}


@dataclass(frozen=True)
class PEInfo:
    path: Path
    is_pe: bool
    machine: str | None = None
    sections: tuple[tuple[str, int, int], ...] = ()  # (name, file_offset, file_size)
    note: str = ""

    def section_of(self, offset: int) -> str | None:
        for name, start, size in self.sections:
            if start <= offset < start + size:
                return name
        return None


def read_pe(path: Path) -> PEInfo:
    try:
        pe = pefile.PE(str(path), fast_load=True)
    except pefile.PEFormatError as exc:
        return PEInfo(path=path, is_pe=False, note=str(exc))

    sections = tuple(
        (
            section.Name.rstrip(b"\x00").decode("ascii", "replace"),
            int(section.PointerToRawData),
            int(section.SizeOfRawData),
        )
        for section in pe.sections
    )
    machine = MACHINES.get(pe.FILE_HEADER.Machine, hex(pe.FILE_HEADER.Machine))
    pe.close()
    return PEInfo(path=path, is_pe=True, machine=machine, sections=sections)
