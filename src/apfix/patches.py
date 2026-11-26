"""Declarative description of every patch this project knows about.

Each patch is described by three things:

* the instruction context *before* the rewritten bytes,
* the bytes that are replaced (``original``) and the bytes we write instead,
* the instruction context *after* the rewritten bytes.

The signature is assembled from ``before + gap + after`` where the gap is
wildcarded, so the same pattern matches the file **before and after** patching.
That is what makes ``status`` able to tell "already patched" from "not patched
yet", and what keeps the tool working when a game update moves the code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .signature import Signature

__all__ = ["DEFAULT_DLL_NAME", "PATCHES", "PATCHES_BY_ID", "Patch"]


DEFAULT_DLL_NAME = "AzurPromilia_Data/Plugins/mj_sdk/union_pcsdk.dll"


@dataclass(frozen=True)
class Patch:
    """A single in-place byte rewrite of equal length, located by context."""

    id: str
    title: str
    function: str
    summary: str
    rationale: str
    before: Signature
    after: Signature
    original: bytes
    replacement: bytes
    notes: str = ""
    references: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if len(self.original) != len(self.replacement):
            raise ValueError(f"{self.id}: replacement must keep the instruction length")
        signature = Signature.join(self.before, len(self.original), self.after)
        object.__setattr__(self, "signature", signature)

    #: Assembled pattern; assigned in ``__post_init__``.
    signature: Signature = field(init=False)

    @property
    def offset(self) -> int:
        """Offset of the rewritten bytes relative to the signature match."""
        return len(self.before)

    def describe(self) -> str:
        return (
            f"{self.id}: {self.title}\n"
            f"  function  {self.function}\n"
            f"  rewrite   {self.original.hex(' ').upper()} -> {self.replacement.hex(' ').upper()}"
            f"   (signature+0x{self.offset:X})\n"
            f"  why       {self.rationale}"
        )


PATCHES: tuple[Patch, ...] = (
    Patch(
        id="skip-agreement-gate",
        title="Skip the mandatory policy/agreement gate",
        function="MjAgrSdk::OnCheckAgreementFinished",
        summary="Never block input behind the agreement window on start-up.",
        rationale=(
            "The SDK compares the cached agreement state with the freshly fetched policy list "
            "and branches into 'block input + open the Qt agreement window' when they differ. "
            "That window is a child HWND and therefore invisible under Wine, so the game hangs "
            "on a black screen. NOPing the conditional branch always takes the released path."
        ),
        before=Signature("48 8B 49 18 E8 ?? ?? ?? ?? 90 83 7D 98 01"),
        after=Signature("33 C9 E8"),
        original=bytes.fromhex("0f 86 31 01 00 00"),
        replacement=bytes.fromhex("90 90 90 90 90 90"),
        notes=(
            "The last four original bytes are the jbe displacement (0x131) and are therefore "
            "inside the wildcarded gap: they move with every build, the cmp/jbe shape does not."
        ),
        references=("pcsdk_log.txt: [agreement]to open main agreement wnd",),
    ),
    Patch(
        id="detach-overlay-window",
        title="Make the SDK overlay window a top-level window",
        function="mj_base::MjBaseWnd::ChangeParentHwndIfNeeded",
        summary="Replace SetParent(winId, game_hwnd) with SetParent(winId, NULL).",
        rationale=(
            "The SDK reparents its Qt windows (agreement, login, ...) into the Unity window. "
            "Under Wine the D3D/Vulkan swap chain owns the parent drawable, so every child "
            "window is painted underneath it and stays invisible and unclickable. Passing NULL "
            "keeps the window as its own X11 toplevel, which renders and accepts input."
        ),
        # mov [rbx+0x38],rax ; <parent> ; mov rcx,rax ; call SetParent ; mov edx,0x320 ...
        before=Signature("48 89 43 38"),
        after=Signature("48 8B C8 FF 15 ?? ?? ?? ?? BA 20 03 00 00 41 B8 58 02 00 00"),
        original=bytes.fromhex("48 8b 53 30"),
        replacement=bytes.fromhex("31 d2 90 90"),
        notes=(
            "Only the parent argument is nulled. Do NOT skip the whole routine: it stores "
            "winId() into this+0x38 and later code dereferences it (a naive jump patch crashes "
            "inside unityplayer). The 0x320/0x258 constants are the 800x600 default size used by "
            "the routine, which makes this signature very stable across builds."
        ),
        references=(
            "wnd_controller.cc: UpdateWidgetFocus: wgt_cls_type: mj_official_cn::MjMainWnd",
        ),
    ),
)

PATCHES_BY_ID: dict[str, Patch] = {patch.id: patch for patch in PATCHES}
