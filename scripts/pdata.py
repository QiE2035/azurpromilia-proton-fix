#!/usr/bin/env python3
"""用 PE 的 .pdata 反查"某个地址属于哪个函数"。

定位这个游戏时非常有用：DLL 没有 PDB 符号，`rizin axt` 在 20 MB 样本上不可靠，
而 `.pdata` 里的 RUNTIME_FUNCTION 表（x86-64 的 unwind 信息）能给出精确的函数边界。

    python3 scripts/pdata.py union_pcsdk.dll 0x1801f8037
    python3 scripts/pdata.py union_pcsdk.dll 0x1801f8037 0x1801bd27e 0x180214500
    python3 scripts/pdata.py union_pcsdk.dll --list 0x1801f7000:0x1801f9000

只依赖标准库：手写 PE 头解析，够用就行。
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

IMAGE_SCN_MEM_EXECUTE = 0x20000000
UNW_FLAG_CHAININFO = 0x4


class PE:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.data = path.read_bytes()
        if self.data[:2] != b"MZ":
            raise SystemExit(f"{path} 不是 MZ（不是 PE 文件）")
        e_lfanew = struct.unpack_from("<I", self.data, 0x3C)[0]
        if self.data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
            raise SystemExit("缺少 PE 签名")
        coff = e_lfanew + 4
        self.machine, self.num_sections = struct.unpack_from("<HH", self.data, coff)
        self.opt_size = struct.unpack_from("<H", self.data, coff + 16)[0]
        opt = coff + 20
        magic = struct.unpack_from("<H", self.data, opt)[0]
        if magic == 0x20B:  # PE32+
            self.image_base = struct.unpack_from("<Q", self.data, opt + 24)[0]
        elif magic == 0x10B:  # PE32
            self.image_base = struct.unpack_from("<I", self.data, opt + 28)[0]
        else:
            raise SystemExit(f"未知的可选头 magic 0x{magic:X}")
        self.sections: list[dict] = []
        self._cache: list[tuple[int, int, bool]] | None = None
        base = opt + self.opt_size
        for i in range(self.num_sections):
            off = base + i * 40
            name = self.data[off : off + 8].rstrip(b"\0").decode("ascii", "replace")
            v_size, v_addr, raw_size, raw_ptr = struct.unpack_from("<IIII", self.data, off + 8)
            chars = struct.unpack_from("<I", self.data, off + 36)[0]
            self.sections.append(
                {
                    "name": name,
                    "va": v_addr,
                    "vsize": v_size,
                    "raw_ptr": raw_ptr,
                    "raw_size": raw_size,
                    "chars": chars,
                }
            )

    # --- 地址换算 -------------------------------------------------------
    def section_at(self, va: int) -> dict | None:
        """va 是绝对虚拟地址；节表里存的是 RVA。"""
        rva = va - self.image_base
        for sec in self.sections:
            if sec["va"] <= rva < sec["va"] + max(sec["vsize"], sec["raw_size"]):
                return sec
        return None

    def va_to_offset(self, va: int) -> int | None:
        sec = self.section_at(va)
        if sec is None:
            return None
        return sec["raw_ptr"] + (va - self.image_base - sec["va"])

    def offset_to_va(self, offset: int) -> int | None:
        for sec in self.sections:
            if sec["raw_ptr"] <= offset < sec["raw_ptr"] + sec["raw_size"]:
                return self.image_base + sec["va"] + (offset - sec["raw_ptr"])
        return None

    def read_rva(self, rva: int, size: int) -> bytes:
        offset = self.va_to_offset(self.image_base + rva)
        if offset is None:
            return b""
        return self.data[offset : offset + size]

    # --- .pdata --------------------------------------------------------
    def functions(self) -> list[tuple[int, int, bool]]:
        """返回 [(begin_va, end_va, is_fragment)]，已按 begin 排序。

        `is_fragment` 表示该记录的 UNWIND_INFO 带 CHAININFO 标志（函数的一段），
        它的区间通常被主记录包住。注意 CHAININFO 是 UNWIND_INFO 第一个字节的
        flags 位，不是 RUNTIME_FUNCTION 里的 unwind RVA 的位——早期版本这里踩过坑。
        """
        if self._cache is not None:
            return self._cache
        pdata = next((s for s in self.sections if s["name"] == ".pdata"), None)
        if pdata is None:
            self._cache = []
            return self._cache
        raw = self.data[pdata["raw_ptr"] : pdata["raw_ptr"] + pdata["raw_size"]]
        spans: list[tuple[int, int, bool]] = []
        for i in range(len(raw) // 12):
            begin, end, unwind_rva = struct.unpack_from("<III", raw, i * 12)
            if begin == 0 or end <= begin:
                continue
            info = self.read_rva(unwind_rva, 1)
            flags = (info[0] >> 3) if info else 0
            spans.append(
                (self.image_base + begin, self.image_base + end, bool(flags & UNW_FLAG_CHAININFO))
            )
        spans.sort()
        self._cache = spans
        return spans

    def lookup(self, va: int) -> tuple[int, int, bool] | None:
        """取包含 va 的最小 span（片段优先于其父函数，给出更精确的边界）。"""
        best: tuple[int, int, bool] | None = None
        for span in self.functions():
            if span[0] <= va < span[1] and (best is None or span[1] - span[0] < best[1] - best[0]):
                best = span
        return best


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="map addresses to .pdata function ranges")
    parser.add_argument("pe", type=Path)
    parser.add_argument(
        "addresses", nargs="*", help="0x-prefixed VAs (or file offsets with --offset)"
    )
    parser.add_argument("--offset", action="store_true", help="treat arguments as file offsets")
    parser.add_argument("--list", metavar="START:END", help="list every function in a VA range")
    args = parser.parse_args(argv)

    pe = PE(args.pe)
    print(f"file       {pe.path}  ({len(pe.data)} bytes)")
    print(f"imagebase  0x{pe.image_base:X}   sections={pe.num_sections}")

    if args.list:
        low, _, high = args.list.partition(":")
        lo = int(low, 0)
        hi = int(high, 0) if high else (1 << 63)
        for begin, end, fragment in pe.functions():
            if lo <= begin < hi:
                mark = "  (片段)" if fragment else ""
                print(f"  0x{begin:X}..0x{end:X}  ({end - begin} bytes){mark}")
        return 0

    if not args.addresses:
        parser.print_help()
        return 2

    for text in args.addresses:
        value = int(text, 0)
        va = pe.offset_to_va(value) if args.offset else value
        if va is None:
            print(f"  0x{value:X}  -> 不在任何节内")
            continue
        span = pe.lookup(va)
        offset = pe.va_to_offset(va)
        sec = pe.section_at(va)
        where = f"file 0x{offset:X}" if offset is not None else "file ?"
        name = sec["name"] if sec else "?"
        if span is None:
            print(f"  0x{va:X}  ({where}, {name})  -> 不在任何 .pdata 函数内")
            continue
        begin, end, fragment = span
        kind = "片段" if fragment else "函数"
        print(
            f"  0x{va:X}  ({where}, {name})  -> {kind} 0x{begin:X}..0x{end:X}"
            f"  +0x{va - begin:X} / {end - begin} bytes"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
