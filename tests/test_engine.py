"""Tests for apply / revert against a synthetic DLL."""

from __future__ import annotations

from pathlib import Path

import pytest

from apfix.engine import State, apply_patches, backup_path, inspect_binary, revert_patches
from apfix.patches import PATCHES


def materialize(patch) -> bytes:
    """Render the concrete instruction bytes a build would contain."""
    before = bytes(value if value is not None else 0x3E for value in patch.before.values)
    after = bytes(value if value is not None else 0x2D for value in patch.after.values)
    return before + patch.original + after


def make_fake_dll(tmp_path: Path) -> Path:
    payload = b"\xcc" * 64 + materialize(PATCHES[0]) + b"\xcc" * 64 + materialize(PATCHES[1])
    target = tmp_path / "union_pcsdk.dll"
    target.write_bytes(payload)
    return target


def test_clean_binary_reports_pending(tmp_path: Path) -> None:
    report = inspect_binary(make_fake_dll(tmp_path))
    assert report.untouched
    assert {result.state for result in report.results} == {State.PENDING}


def test_apply_then_revert_is_lossless(tmp_path: Path) -> None:
    target = make_fake_dll(tmp_path)
    original = target.read_bytes()

    applied = apply_patches(target)
    assert applied.fully_applied
    patched = target.read_bytes()
    assert patched != original
    assert backup_path(target).read_bytes() == original
    assert target.with_name("union_pcsdk.dll.apfix.json").is_file()

    reverted = revert_patches(target)
    assert reverted.untouched
    assert target.read_bytes() == original


def test_apply_is_idempotent(tmp_path: Path) -> None:
    target = make_fake_dll(tmp_path)
    apply_patches(target)
    first = target.read_bytes()
    again = apply_patches(target)
    assert again.fully_applied
    assert target.read_bytes() == first


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    target = make_fake_dll(tmp_path)
    original = target.read_bytes()
    report = apply_patches(target, dry_run=True)
    assert report.untouched
    assert target.read_bytes() == original
    assert not backup_path(target).exists()


def test_unexpected_bytes_are_reported_not_overwritten(tmp_path: Path) -> None:
    target = make_fake_dll(tmp_path)
    data = bytearray(target.read_bytes())
    index = data.find(PATCHES[0].original)
    data[index + 1] = 0x99
    target.write_bytes(bytes(data))

    report = inspect_binary(target)
    gate = next(result for result in report.results if result.patch.id == "skip-agreement-gate")
    assert gate.state is State.FOREIGN
    with pytest.raises(RuntimeError):
        apply_patches(target)


def test_updated_binary_with_missing_signature_is_reported(tmp_path: Path) -> None:
    target = tmp_path / "union_pcsdk.dll"
    target.write_bytes(b"\xcc" * 256)
    report = inspect_binary(target)
    assert {result.state for result in report.results} == {State.FOREIGN}
    assert all("not found" in result.detail for result in report.results)


def test_revert_from_backup(tmp_path: Path) -> None:
    target = make_fake_dll(tmp_path)
    original = target.read_bytes()
    apply_patches(target)
    report = revert_patches(target, from_backup=True)
    assert report.untouched
    assert target.read_bytes() == original
