"""COR-9: Python side of the Rust `stable_hash_int` repr parity pin.

`chronicler-agents/src/politics.rs` holds the same table in
`SECESSION_HASH_PARITY` and recomputes it with `py_repr_str`, so both
implementations are pinned to the same digests for names that need quoting
or escaping.
"""

from __future__ import annotations

import pytest

from chronicler.utils import stable_hash_int

# (name, Python repr, stable_hash_int("secession", 7, 3, name))
SECESSION_HASH_PARITY: list[tuple[str, str, int]] = [
    ("Aldor", "'Aldor'", 5965020321537964785),
    ("Ka'lo", "\"Ka'lo\"", 824216405042331300),
    ("A\\B", "'A\\\\B'", 753379866302640020),
    ("Zoë", "'Zoë'", 2123918839911951856),
    ("He said \"hi\"", "'He said \"hi\"'", 5665349242566717993),
    ("tab\there", "'tab\\there'", 8333909184004934855),
    ("Both ' and \"", "'Both \\' and \"'", 6631886806500821251),
    ("line\nbreak\r", "'line\\nbreak\\r'", 17064170672029403852),
    ("bell\x07del\x7f", "'bell\\x07del\\x7f'", 8829576378575621579),
    ("nel\x85", "'nel\\x85'", 1040625089979112548),
]


@pytest.mark.parametrize(("name", "expected_repr", "expected_hash"), SECESSION_HASH_PARITY)
def test_secession_hash_table_matches_python(name: str, expected_repr: str, expected_hash: int) -> None:
    assert repr(name) == expected_repr
    assert stable_hash_int("secession", 7, 3, name) == expected_hash


def test_proxy_detection_two_name_hash_matches_rust_constant() -> None:
    assert stable_hash_int("proxy_detection", 7, 3, "Ka'lo", "A\\B") == 8235038744015777200
