"""Command line interface (``apfix ...``)."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from . import __version__
from .engine import (
    State,
    apply_patches,
    backup_path,
    inspect_binary,
    manifest_path,
    revert_patches,
)
from .locate import LAUNCH_ARGS, discover, running_game_processes
from .patches import PATCHES, PATCHES_BY_ID
from .pe import read_pe
from .signature import AmbiguousSignature, SignatureNotFound

console = Console()
err = Console(stderr=True)

STATE_STYLE = {
    State.APPLIED: "[green]applied[/green]",
    State.PENDING: "[yellow]pending[/yellow]",
    State.FOREIGN: "[red]mismatch[/red]",
}


def _resolve(game_dir: str | None) -> Path:
    try:
        return discover(game_dir).dll
    except FileNotFoundError as exc:
        err.print(f"[red]{exc}[/red]")
        raise click.exceptions.Exit(2) from exc


def _guard_running() -> None:
    processes = running_game_processes()
    if processes:
        names = ", ".join(sorted({(p.info.get("name") or str(p.pid)) for p in processes}))
        err.print(f"[red]game is running ({names}); close it first so the DLL is not in use[/red]")
        raise click.exceptions.Exit(3)


def _table(report) -> Table:
    table = Table(title=f"{report.path.name}  sha256={report.digest[:12]}", box=None)
    table.add_column("patch", overflow="fold")
    table.add_column("state")
    table.add_column("offset")
    table.add_column("note", overflow="fold")
    for result in report.results:
        table.add_row(
            result.patch.id,
            STATE_STYLE[result.state],
            f"0x{result.address:X}" if result.address is not None else "-",
            result.detail,
        )
    return table


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="apfix")
def main() -> None:
    """Make the Azur Promilia SDK overlay work under Proton/Wine."""


@main.command()
@click.option("--game-dir", type=click.Path(exists=True, file_okay=False), default=None)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="print nothing; exit 0 only when every patch is applied (for scripts)",
)
def status(game_dir: str | None, quiet: bool) -> None:
    """Show which patches are applied (read-only)."""
    install = discover(game_dir)
    if quiet:
        # 脚本用：只关心"能不能直接启动"，任何异常都退非零
        try:
            report = inspect_binary(install.dll)
        except OSError:
            raise click.exceptions.Exit(2) from None
        raise click.exceptions.Exit(0 if report.fully_applied else 1)
    console.print(f"[bold]game[/bold]   {install.root}")
    console.print(f"[bold]dll[/bold]    {install.dll}")
    if install.prefix:
        console.print(f"[bold]prefix[/bold] {install.prefix}")
    for note in install.notes:
        console.print(f"[yellow]note[/yellow]   {note}")
    if not install.dll.is_file():
        raise click.exceptions.Exit(2)
    report = inspect_binary(install.dll)
    console.print(_table(report))
    if report.fully_applied:
        console.print("[green]all patches applied[/green]")
    elif report.untouched:
        console.print("[yellow]clean DLL - run `apfix apply`[/yellow]")
    else:
        console.print("[red]unexpected byte pattern - see `apfix info`[/red]")


@main.command()
@click.option("--game-dir", type=click.Path(exists=True, file_okay=False), default=None)
@click.option("--dry-run", is_flag=True, help="only report what would change")
@click.option("--no-backup", is_flag=True, help="do not keep a .apfix-backup copy")
@click.option("--force", is_flag=True, help="patch even if the game looks like it is running")
def apply(game_dir: str | None, dry_run: bool, no_backup: bool, force: bool) -> None:
    """Patch the SDK DLL in place."""
    install = discover(game_dir)
    if not force:
        _guard_running()
    try:
        report = apply_patches(install.dll, dry_run=dry_run, keep_backup=not no_backup)
    except (RuntimeError, SignatureNotFound, AmbiguousSignature) as exc:
        err.print(f"[red]{exc}[/red]")
        raise click.exceptions.Exit(1) from exc
    console.print(_table(report))
    if dry_run:
        console.print("[yellow]dry run - nothing written[/yellow]")
    elif report.fully_applied:
        console.print(f"[green]patched[/green] {install.dll}")
        if not no_backup:
            console.print(f"backup: {backup_path(install.dll)}")
        console.print(
            f"launch with: [bold]{' '.join(install.launch_command)}[/bold] (from {install.root})"
        )


@main.command()
@click.option("--game-dir", type=click.Path(exists=True, file_okay=False), default=None)
@click.option("--from-backup", is_flag=True, help="restore the .apfix-backup copy instead")
@click.option("--dry-run", is_flag=True)
@click.option("--force", is_flag=True, help="patch even if the game looks like it is running")
def revert(game_dir: str | None, from_backup: bool, dry_run: bool, force: bool) -> None:
    """Undo the patches (byte-exact, no backup required)."""
    install = discover(game_dir)
    if not force:
        _guard_running()
    report = revert_patches(install.dll, from_backup=from_backup, dry_run=dry_run)
    console.print(_table(report))
    if dry_run:
        console.print("[yellow]dry run - nothing written[/yellow]")
    elif report.untouched:
        console.print("[green]reverted[/green]")


@main.command("list")
def list_patches() -> None:
    """List the patches this build knows about."""
    for patch in PATCHES:
        console.print(patch.describe(), markup=False, highlight=False)
        console.print()


@main.command()
@click.option("--game-dir", type=click.Path(exists=True, file_okay=False), default=None)
def info(game_dir: str | None) -> None:
    """Print raw per-patch diagnostics, including found file offsets."""
    install = discover(game_dir)
    report = inspect_binary(install.dll)
    console.print(f"dll        {install.dll}")
    console.print(f"size       {report.size} bytes")
    console.print(f"sha256     {report.digest}")
    pe_info = read_pe(install.dll)
    console.print(
        f"pe         {'PE ' + (pe_info.machine or '?') if pe_info.is_pe else 'not a PE: ' + pe_info.note}"
    )
    console.print(f"manifest   {manifest_path(install.dll)}")
    console.print(f"backup     {backup_path(install.dll)}")
    for result in report.results:
        patch = PATCHES_BY_ID[result.patch.id]
        console.print()
        console.print(f"[bold]{patch.id}[/bold] -> {STATE_STYLE[result.state]}")
        console.print(f"  signature {patch.signature.raw}")
        address = f"0x{result.address:X}" if result.address is not None else "-"
        section = pe_info.section_of(result.address) if result.address is not None else None
        console.print(f"  address   {address}{f'  ({section})' if section else ''}")
        console.print(f"  expected  {patch.original.hex(' ').upper()}")
        console.print(f"  current   {result.current.hex(' ').upper() or '-'}")
        console.print(f"  detail    {result.detail}")


@main.command()
@click.option("--game-dir", type=click.Path(exists=True, file_okay=False), default=None)
def doctor(game_dir: str | None) -> None:
    """Check the environment: Proton, prefix, DLL, running processes."""
    install = discover(game_dir)
    rows = [
        ("game dir", str(install.root), install.exe.is_file()),
        ("dll", str(install.dll), install.dll.is_file()),
        ("prefix", str(install.prefix or "-"), install.prefix is not None),
        (
            "dwproton on PATH",
            str(bool(__import__("shutil").which("dwproton"))),
            bool(__import__("shutil").which("dwproton")),
        ),
    ]
    table = Table(box=None)
    table.add_column("check")
    table.add_column("value", overflow="fold")
    table.add_column("ok")
    for name, value, ok in rows:
        table.add_row(name, value, "[green]yes[/green]" if ok else "[red]no[/red]")
    console.print(table)

    processes = running_game_processes()
    if processes:
        err.print("[yellow]game processes still running:[/yellow]")
        for process in processes:
            err.print(f"  pid {process.pid}  {process.info.get('name')}")
    console.print("launch: [bold]" + " ".join(install.launch_command) + "[/bold]")
    console.print(f"arguments: {' '.join(LAUNCH_ARGS)}")


def run() -> None:  # pragma: no cover - entry point shim
    try:
        main(prog_name="apfix")
    except KeyboardInterrupt:  # pragma: no cover
        sys.exit(130)


if __name__ == "__main__":  # pragma: no cover
    run()
