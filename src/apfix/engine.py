"""Apply / revert / inspect the patches against a real DLL."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from .patches import PATCHES, Patch
from .signature import AmbiguousSignature, SignatureNotFound

__all__ = [
    "BinaryReport",
    "Manifest",
    "PatchResult",
    "State",
    "apply_patches",
    "backup_path",
    "inspect_binary",
    "revert_patches",
    "sha256",
]


class State(str, Enum):
    APPLIED = "applied"
    PENDING = "pending"
    FOREIGN = "foreign"  # bytes are neither the expected original nor our replacement


@dataclass(frozen=True)
class PatchResult:
    patch: Patch
    state: State
    address: int | None = None  # file offset of the rewritten bytes
    current: bytes = b""
    detail: str = ""


@dataclass(frozen=True)
class BinaryReport:
    path: Path
    size: int
    digest: str
    results: tuple[PatchResult, ...]

    @property
    def fully_applied(self) -> bool:
        return all(result.state is State.APPLIED for result in self.results)

    @property
    def untouched(self) -> bool:
        return all(result.state is State.PENDING for result in self.results)

    @property
    def mixed(self) -> bool:
        states = {result.state for result in self.results}
        return len(states) > 1 or State.FOREIGN in states


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def backup_path(target: Path) -> Path:
    return target.with_name(target.name + ".apfix-backup")


def manifest_path(target: Path) -> Path:
    return target.with_name(target.name + ".apfix.json")


def _read(path: Path) -> bytearray:
    if not path.is_file():
        raise FileNotFoundError(f"{path} does not exist")
    return bytearray(path.read_bytes())


def _atomic_write(path: Path, data: bytes) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        shutil.copymode(path, tmp_name)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _locate(patch: Patch, data: bytes) -> int:
    """Return the absolute file offset of the bytes this patch rewrites."""
    match = patch.signature.find_unique(data, what=f"patch {patch.id!r}")
    return match + patch.offset


def inspect_binary(path: Path, patches: tuple[Patch, ...] = PATCHES) -> BinaryReport:
    data = _read(path)
    results: list[PatchResult] = []
    for patch in patches:
        try:
            offset = _locate(patch, data)
        except (SignatureNotFound, AmbiguousSignature) as exc:
            results.append(PatchResult(patch, State.FOREIGN, None, b"", str(exc)))
            continue
        current = bytes(data[offset : offset + len(patch.replacement)])
        if current == patch.replacement:
            state, detail = State.APPLIED, "already patched"
        elif current == patch.original:
            state, detail = State.PENDING, "ready to patch"
        else:
            state, detail = State.FOREIGN, f"unexpected bytes {current.hex(' ').upper()}"
        results.append(PatchResult(patch, state, offset, current, detail))
    return BinaryReport(
        path=path, size=len(data), digest=sha256(bytes(data)), results=tuple(results)
    )


class Manifest:
    """Small state file written next to the DLL so ``status`` stays meaningful."""

    def __init__(self, target: Path) -> None:
        self.path = manifest_path(target)
        self.target = target

    def read(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            return json.loads(self.path.read_text("utf-8"))
        except (OSError, ValueError):
            return {}

    def write(self, *, original_digest: str, patched: bool, patches: list[str]) -> None:
        payload = {
            "tool": "apfix",
            "dll": self.target.name,
            "original_sha256": original_digest,
            "patched": patched,
            "patches": patches,
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n", "utf-8")

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


def apply_patches(
    path: Path,
    *,
    patches: tuple[Patch, ...] = PATCHES,
    dry_run: bool = False,
    keep_backup: bool = True,
) -> BinaryReport:
    """Patch ``path`` in place and return the resulting state."""
    report = inspect_binary(path, patches)
    if report.fully_applied:
        return report
    foreign = [result for result in report.results if result.state is State.FOREIGN]
    if foreign:
        details = "; ".join(f"{result.patch.id}: {result.detail}" for result in foreign)
        raise RuntimeError(f"cannot patch, unexpected state ({details})")

    data = _read(path)
    if keep_backup and not dry_run and not backup_path(path).exists():
        shutil.copy2(path, backup_path(path))

    touched: dict[str, str] = {}
    for result in report.results:
        if result.state is not State.PENDING or result.address is None:
            continue
        start = result.address
        data[start : start + len(result.patch.replacement)] = result.patch.replacement
        touched[result.patch.id] = f"0x{start:X}"

    if dry_run:
        return report

    _atomic_write(path, bytes(data))
    Manifest(path).write(
        original_digest=report.digest,
        patched=True,
        patches=[result.patch.id for result in report.results],
    )
    return inspect_binary(path, patches)


def revert_patches(
    path: Path,
    *,
    patches: tuple[Patch, ...] = PATCHES,
    from_backup: bool = False,
    dry_run: bool = False,
) -> BinaryReport:
    """Undo the patches, either by rewriting the known bytes or from the backup."""
    if from_backup:
        backup = backup_path(path)
        if not backup.is_file():
            raise FileNotFoundError(f"no backup at {backup}")
        if not dry_run:
            shutil.copy2(backup, path)
        return inspect_binary(path, patches)

    report = inspect_binary(path, patches)
    data = _read(path)
    pending = [result for result in report.results if result.state is State.APPLIED]
    if not pending:
        return report
    for result in pending:
        if result.address is None:
            continue
        start = result.address
        data[start : start + len(result.patch.original)] = result.patch.original
    if not dry_run:
        _atomic_write(path, bytes(data))
        manifest = Manifest(path)
        backup = backup_path(path)
        original = manifest.read().get("original_sha256", "")
        if backup.is_file():
            manifest.write(
                original_digest=sha256(backup.read_bytes()),
                patched=False,
                patches=[],
            )
        elif original:
            manifest.write(original_digest=original, patched=False, patches=[])
    return inspect_binary(path, patches)
