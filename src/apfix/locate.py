"""Find the pieces of a Proton/Wine install that this project cares about."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import psutil

from .patches import DEFAULT_DLL_NAME

__all__ = [
    "Install",
    "discover",
    "find_game_root",
    "proton_prefix_candidates",
    "running_game_processes",
]

GAME_EXE = "AzurPromilia.exe"
LAUNCH_ARGS = ("-start=azurpromilia_launcher",)


@dataclass(frozen=True)
class Install:
    root: Path
    exe: Path
    dll: Path
    prefix: Path | None
    notes: tuple[str, ...] = ()

    @property
    def launch_command(self) -> list[str]:
        return ["dwproton", "waitforexitandrun", f"./{self.exe.name}", *LAUNCH_ARGS]


def _is_game_dir(candidate: Path) -> bool:
    return (candidate / GAME_EXE).is_file()


def find_game_root(start: Path | None = None) -> Path:
    """Walk up from ``start`` (default: CWD) looking for ``AzurPromilia.exe``."""
    current = (start or Path.cwd()).resolve()
    for directory in (current, *current.parents):
        if _is_game_dir(directory):
            return directory
        for child in sorted(directory.iterdir() if directory.is_dir() else []):
            if child.is_dir() and _is_game_dir(child):
                return child
    raise FileNotFoundError(
        f"could not find {GAME_EXE} in {current} or above it; pass --game-dir explicitly"
    )


def proton_prefix_candidates(game_root: Path) -> list[Path]:
    """Places Proton keeps ``drive_c`` for a non-Steam game."""
    candidates: list[Path] = []
    env_prefix = os.environ.get("STEAM_COMPAT_DATA_PATH")
    if env_prefix:
        candidates.append(Path(env_prefix))
    candidates.append(Path.home() / ".local/share/proton-pfx/0")
    steam_root = Path.home() / ".steam/steam/steamapps/compatdata"
    if steam_root.is_dir():
        candidates.extend(sorted(steam_root.iterdir()))
    return [
        candidate for candidate in candidates if (candidate / "pfx").is_dir() or candidate.is_dir()
    ]


def discover(game_dir: str | os.PathLike[str] | None = None) -> Install:
    """Resolve the DLL, the prefix and any caveats worth showing the user."""
    root = Path(game_dir).expanduser().resolve() if game_dir else find_game_root()
    if _is_game_dir(root):
        game_root = root
    elif (root / "AzurPromilia_Game").is_dir():
        game_root = root / "AzurPromilia_Game"
    else:
        game_root = find_game_root(root)

    exe = game_root / GAME_EXE
    dll = game_root / DEFAULT_DLL_NAME
    notes: list[str] = []
    if not dll.is_file():
        notes.append(f"missing {DEFAULT_DLL_NAME} - is this a full install?")

    prefix = next((p for p in proton_prefix_candidates(game_root)), None)
    if prefix is None:
        notes.append("no Proton prefix found; launch the game once so Proton creates one")
    if shutil.which("dwproton") is None:
        notes.append("dwproton is not on PATH")
    return Install(root=game_root, exe=exe, dll=dll, prefix=prefix, notes=tuple(notes))


def running_game_processes() -> list[psutil.Process]:
    """Processes that would keep the DLL locked (i.e. must be closed first)."""
    interesting = {"azurpromilia.exe", "unitycrashhandler64.exe", "manjuu_sdk_browser.exe"}
    found: list[psutil.Process] = []
    for process in psutil.process_iter(["name", "exe", "cmdline"]):
        try:
            name = (process.info["name"] or "").lower()
            exe = Path(process.info["exe"] or "").name.lower()
            argv0 = (process.info["cmdline"] or [""])[0]
            argv0_name = Path(argv0).name.lower()
        except (psutil.NoSuchProcess, psutil.AccessDenied):  # pragma: no cover
            continue
        # Match process identities only: a shell whose *cwd* happens to be the game
        # directory (or whose arguments merely mention it) must not block patching.
        if {name, exe, argv0_name} & interesting:
            found.append(process)
    return found
