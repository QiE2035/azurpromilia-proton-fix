"""Tests for the byte-signature engine."""

from __future__ import annotations

import pytest

from apfix.signature import AmbiguousSignature, PatternError, Signature, SignatureNotFound


def test_parse_and_length() -> None:
    signature = Signature("48 8B 49 18")
    assert len(signature) == 4
    assert signature.values == (0x48, 0x8B, 0x49, 0x18)


def test_wildcards_are_optional() -> None:
    signature = Signature("AA ?? BB")
    assert len(signature) == 3
    assert signature.values == (0xAA, None, 0xBB)


def test_rejects_bad_tokens() -> None:
    with pytest.raises(PatternError):
        Signature("48 8B 4")
    with pytest.raises(PatternError):
        Signature("ZZ")


def test_rejects_all_wildcards() -> None:
    with pytest.raises(PatternError):
        Signature("?? ??")


def test_find_unique_hits_exact_offset() -> None:
    data = b"\x00" * 16 + bytes.fromhex("48 8b 49 18 e8 aa aa aa aa 90") + b"\x00" * 16
    signature = Signature("48 8B 49 18 E8 ?? ?? ?? ?? 90")
    assert signature.find_unique(data) == 16


def test_find_all_reports_every_match() -> None:
    needle = bytes.fromhex("aa bb cc")
    data = needle + b"\x00" + needle
    assert Signature("AA BB CC").find_all(data) == [0, 4]


def test_ambiguous_signature_is_refused() -> None:
    data = bytes.fromhex("aa bb cc 00 aa bb cc")
    with pytest.raises(AmbiguousSignature):
        Signature("AA BB CC").find_unique(data)


def test_missing_signature_is_refused() -> None:
    with pytest.raises(SignatureNotFound):
        Signature("DE AD BE EF").find_unique(b"\x00" * 32)


def test_matches_at_pads_correctly() -> None:
    signature = Signature("AA ?? CC")
    assert signature.matches_at(bytes.fromhex("aa 00 cc"), 0)
    assert not signature.matches_at(bytes.fromhex("aa 00 cd"), 0)
    assert not signature.matches_at(bytes.fromhex("aa 00"), 0)


def test_from_bytes_roundtrip() -> None:
    signature = Signature.from_bytes(bytes.fromhex("0f 86 31 01 00 00"))
    assert signature.raw == "0F 86 31 01 00 00"
    assert signature.find_unique(bytes.fromhex("ff 0f 86 31 01 00 00")) == 1
