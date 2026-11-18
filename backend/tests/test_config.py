import secrets
from typing import Any

import pytest

from app.config import Settings, check_prod, load_keyring
from app.crypto.keys import KeyConfigError, KeyRing, Purpose


def keys(**over: str) -> dict[str, Any]:
    base = {f"pg_{p.value}_key": secrets.token_hex(32) for p in Purpose}
    base.update(over)
    return base


def prod(**kw: Any) -> Settings:
    kw.setdefault("public_origin", "https://pg.example")
    s = Settings(_env_file=None, env="prod", **kw)
    check_prod(s)
    return s


def test_dev_starts_with_nothing_set() -> None:
    s = Settings(_env_file=None)
    ring, dev = load_keyring(s)
    assert dev and s.env == "dev" and s.max_upload_bytes == 10 * 1024 * 1024
    assert len({ring[p].current[1] for p in Purpose}) == 4


def test_prod_accepts_four_good_keys() -> None:
    ring, dev = load_keyring(prod(**keys()))
    assert not dev and len({ring[p].current[1] for p in Purpose}) == 4


@pytest.mark.parametrize(
    "bad",
    [
        {"pg_storage_key": None},  # missing
        {"pg_vault_key": "abcd"},  # too short
        {"pg_audit_key": "SAME", "pg_vault_key": "SAME"},  # reused
    ],
)
def test_prod_refuses_bad_keys(bad: dict[str, Any]) -> None:
    k = keys()
    same = secrets.token_hex(32)
    for name, v in bad.items():
        if v is None:
            k.pop(name)
        else:
            k[name] = same if v == "SAME" else v
    with pytest.raises(KeyConfigError) as err:
        prod(**k)
    assert all(v not in str(err.value) for v in k.values())  # never echoes a key


def test_prod_refuses_dev_keys_and_http_origin() -> None:
    dev = KeyRing.dev()
    dev_keys = {f"pg_{p.value}_key": dev[p].current[1].hex() for p in Purpose}
    with pytest.raises(KeyConfigError, match="DEV"):
        prod(**dev_keys)
    with pytest.raises(KeyConfigError, match="https"):
        prod(public_origin="http://pg.example", **keys())


def test_empty_key_lines_count_as_unset() -> None:
    s = Settings(_env_file=None, pg_token_key="", pg_audit_key="  ")
    assert s.key_env() == {}


def test_secrets_never_in_repr() -> None:
    k = keys()
    text = repr(prod(**k)) + str(prod(**k))
    assert all(v not in text for v in k.values())
