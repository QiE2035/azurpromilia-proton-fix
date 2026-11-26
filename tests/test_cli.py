"""CLI smoke tests (no Proton required)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from apfix.cli import main
from apfix.patches import DEFAULT_DLL_NAME, PATCHES


def materialize(patch):
    before = bytes(value if value is not None else 0x3E for value in patch.before.values)
    after = bytes(value if value is not None else 0x2D for value in patch.after.values)
    return before + patch.original + after


def make_install(tmp_path: Path) -> Path:
    game = tmp_path / "AzurPromilia_Game"
    game.mkdir()
    (game / "AzurPromilia.exe").write_bytes(b"MZ")
    dll = game / DEFAULT_DLL_NAME
    dll.parent.mkdir(parents=True)
    dll.write_bytes(b"\xcc" * 64 + materialize(PATCHES[0]) + b"\xcc" * 64 + materialize(PATCHES[1]))
    return game


def test_status_then_apply_then_revert(tmp_path: Path) -> None:
    game = make_install(tmp_path)
    runner = CliRunner()

    status = runner.invoke(main, ["status", "--game-dir", str(game)])
    assert status.exit_code == 0, status.output
    assert "pending" in status.output

    applied = runner.invoke(main, ["apply", "--game-dir", str(game), "--force"])
    assert applied.exit_code == 0, applied.output
    assert "all patches applied" in runner.invoke(main, ["status", "--game-dir", str(game)]).output

    reverted = runner.invoke(main, ["revert", "--game-dir", str(game)])
    assert reverted.exit_code == 0, reverted.output
    assert "pending" in runner.invoke(main, ["status", "--game-dir", str(game)]).output


def test_list_shows_both_patches() -> None:
    result = CliRunner().invoke(main, ["list"])
    assert result.exit_code == 0
    assert "skip-agreement-gate" in result.output
    assert "detach-overlay-window" in result.output


def test_info_and_doctor_run(tmp_path: Path) -> None:
    game = make_install(tmp_path)
    runner = CliRunner()
    info = runner.invoke(main, ["info", "--game-dir", str(game)])
    assert info.exit_code == 0, info.output
    assert "signature" in info.output

    doctor = runner.invoke(main, ["doctor", "--game-dir", str(game)])
    assert doctor.exit_code == 0, doctor.output
    assert "dwproton" in doctor.output


def test_status_quiet_exit_codes(tmp_path: Path) -> None:
    """`status -q` 只给退出码，供启动脚本用。"""
    game = make_install(tmp_path)
    runner = CliRunner()

    pending = runner.invoke(main, ["status", "--quiet", "--game-dir", str(game)])
    assert pending.exit_code == 1
    assert pending.output.strip() == ""

    runner.invoke(main, ["apply", "--game-dir", str(game), "--force"])
    applied = runner.invoke(main, ["status", "-q", "--game-dir", str(game)])
    assert applied.exit_code == 0
    assert applied.output.strip() == ""

    missing = runner.invoke(main, ["status", "-q", "--game-dir", str(game.parent / "nope")])
    assert missing.exit_code != 0
