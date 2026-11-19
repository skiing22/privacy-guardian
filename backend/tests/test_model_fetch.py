"""Model delivery (API 8.2): config checks, token handling, retries, integrity, cleanup."""

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "model_fetch", Path(__file__).resolve().parents[1] / "scripts" / "model_fetch.py"
)
assert _spec and _spec.loader
mf = importlib.util.module_from_spec(_spec)
sys.modules["model_fetch"] = mf
_spec.loader.exec_module(mf)

REV = "a" * 40
TOKEN = "hf_SECRETtoken123"
CFG = {"id2label": {"0": "O", "1": "B-PERSON"}, "model_type": "distilbert"}


def write_model(
    d: Path, weights: bytes = b"weights", extra: dict[str, bytes] | None = None
) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / "config.json").write_text(json.dumps(CFG))
    (d / "model.safetensors").write_bytes(weights)
    (d / "tokenizer.json").write_text("{}")
    (d / ".cache" / "huggingface").mkdir(parents=True)
    (d / ".cache" / "huggingface" / "x.lock").write_text("hub bookkeeping")
    for name, data in (extra or {}).items():
        (d / name).write_bytes(data)


def good_sha(tmp: Path) -> str:
    ref = tmp / "ref"
    write_model(ref)
    return str(mf.manifest_sha256(ref))


@pytest.fixture
def setup(tmp_path: Path):  # type: ignore[no-untyped-def]
    secret = tmp_path / "hf_token"
    secret.write_text(TOKEN + "\n")
    env = {"MODEL_REPO": "skiing22/pg-ner", "MODEL_REVISION": REV,
           "MODEL_SHA256": good_sha(tmp_path), "HF_TOKEN_FILE": str(secret)}  # fmt: skip
    return env, tmp_path / "out" / "model"


def ok_downloader(calls: list[tuple[str, str, str]]):  # type: ignore[no-untyped-def]
    def dl(repo: str, rev: str, token: str, dest: Path) -> None:
        calls.append((repo, rev, token))
        write_model(dest)

    return dl


def test_download_verifies_and_moves_into_place(setup, capsys) -> None:  # type: ignore[no-untyped-def]
    env, out = setup
    calls: list[tuple[str, str, str]] = []
    got = mf.download(out, env, ok_downloader(calls), sleep=lambda s: None)
    assert got == env["MODEL_SHA256"]
    assert calls == [("skiing22/pg-ner", REV, TOKEN)]
    assert (out / "VERSION").read_text() == "pg-ner@aaaaaaaaaaaa\n"
    assert not (out / ".cache").exists()  # hub bookkeeping removed
    assert stat.S_IMODE((out / "model.safetensors").stat().st_mode) == 0o644
    assert [p.name for p in out.parent.iterdir()] == ["model"]  # no temp folders left
    assert TOKEN not in capsys.readouterr().out


@pytest.mark.parametrize(
    ("key", "value", "msg"),
    [
        ("MODEL_REVISION", "main", "commit hash"),
        ("MODEL_REVISION", "a" * 39, "commit hash"),
        ("MODEL_REPO", "no-slash", "owner/name"),
        ("MODEL_REPO", "../etc/passwd", "owner/name"),
        ("MODEL_SHA256", "abc", "64 hex"),
    ],
)
def test_bad_config_fails_before_any_download(setup, key: str, value: str, msg: str) -> None:  # type: ignore[no-untyped-def]
    env, out = setup
    env[key] = value
    with pytest.raises(mf.FetchError, match=msg):
        mf.download(out, env, lambda *a: pytest.fail("must not download"))


def test_token_only_from_a_secret_file(setup, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    env, out = setup
    with pytest.raises(mf.FetchError, match="build secret file"):
        mf.download(out, {**env, "HF_TOKEN": TOKEN}, lambda *a: None)
    del env["HF_TOKEN_FILE"]
    with pytest.raises(mf.FetchError, match="no token") as e:
        mf.download(out, env, lambda *a: None, secret_paths=(str(tmp_path / "missing"),))
    assert TOKEN not in str(e.value)
    two = tmp_path / "two"
    two.write_text("a\nb")
    with pytest.raises(mf.FetchError, match="exactly one token"):
        mf.read_token({"HF_TOKEN_FILE": str(two)})


def test_retries_network_errors_with_backoff(setup) -> None:  # type: ignore[no-untyped-def]
    env, out = setup
    waits: list[float] = []
    tries = {"n": 0}

    def flaky(repo: str, rev: str, token: str, dest: Path) -> None:
        tries["n"] += 1
        write_model(dest, b"partial")  # a half download must not survive
        if tries["n"] < 3:
            raise mf.FetchError("network error", retry=True)
        for p in dest.iterdir():
            if p.is_file():
                p.unlink()
        write_model_clean(dest)

    def write_model_clean(dest: Path) -> None:
        (dest / "config.json").write_text(json.dumps(CFG))
        (dest / "model.safetensors").write_bytes(b"weights")
        (dest / "tokenizer.json").write_text("{}")

    assert mf.download(out, env, flaky, sleep=waits.append) == env["MODEL_SHA256"]
    assert waits == [2.0, 8.0] and tries["n"] == 3


def test_gives_up_after_three_retries(setup) -> None:  # type: ignore[no-untyped-def]
    env, out = setup
    waits: list[float] = []

    def down(*a: object) -> None:
        raise mf.FetchError("Hugging Face server error (503)", retry=True)

    with pytest.raises(mf.FetchError, match="503"):
        mf.download(out, env, down, sleep=waits.append)
    assert waits == [2.0, 8.0, 30.0]
    assert not out.exists() and list(out.parent.iterdir()) == []


def test_rate_limit_uses_retry_after_but_capped(setup) -> None:  # type: ignore[no-untyped-def]
    env, out = setup
    waits: list[float] = []
    n = {"i": 0}

    def limited(repo: str, rev: str, token: str, dest: Path) -> None:
        n["i"] += 1
        if n["i"] == 1:
            raise mf.FetchError("rate limited", retry=True, wait=7)
        if n["i"] == 2:
            raise mf.FetchError("rate limited", retry=True, wait=3600)
        write_model(dest)

    mf.download(out, env, limited, sleep=waits.append)
    assert waits == [7, 60.0]


def test_permanent_errors_are_not_retried(setup) -> None:  # type: ignore[no-untyped-def]
    env, out = setup
    n = {"i": 0}

    def denied(*a: object) -> None:
        n["i"] += 1
        raise mf.FetchError("repo not found or token has no read access")

    with pytest.raises(mf.FetchError, match="read access"):
        mf.download(out, env, denied, sleep=lambda s: pytest.fail("no retry"))
    assert n["i"] == 1


def test_hash_mismatch_fails_and_leaves_nothing(setup) -> None:  # type: ignore[no-untyped-def]
    env, out = setup

    def tampered(repo: str, rev: str, token: str, dest: Path) -> None:
        write_model(dest, b"weights with a backdoor")

    with pytest.raises(mf.FetchError, match="mismatch"):
        mf.download(out, env, tampered, sleep=lambda s: pytest.fail("no retry"))
    assert not out.exists() and list(out.parent.iterdir()) == []


def test_tokenizer_change_also_changes_the_hash(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    write_model(a)
    write_model(b)
    assert mf.manifest_sha256(a) == mf.manifest_sha256(b)
    (b / "tokenizer.json").write_text('{"x": 1}')
    assert mf.manifest_sha256(a) != mf.manifest_sha256(b)


@pytest.mark.parametrize(
    ("extra", "msg"),
    [
        ({"pytorch_model.bin": b"pickle"}, "pickle weights"),
        ({"config.json": b"not json"}, "valid JSON"),
        ({"config.json": b'{"model_type": "x"}'}, "id2label"),
    ],
)
def test_unsafe_or_wrong_files_are_refused(
    tmp_path: Path, extra: dict[str, bytes], msg: str
) -> None:
    d = tmp_path / "m"
    write_model(d, extra=extra)
    with pytest.raises(mf.FetchError, match=msg):
        mf.check_files(d)


def test_missing_weights_refused(tmp_path: Path) -> None:
    d = tmp_path / "m"
    write_model(d)
    (d / "model.safetensors").unlink()
    with pytest.raises(mf.FetchError, match="model.safetensors"):
        mf.check_files(d)


def test_refuses_non_empty_output(setup) -> None:  # type: ignore[no-untyped-def]
    env, out = setup
    out.mkdir(parents=True)
    (out / "old").write_text("x")
    with pytest.raises(mf.FetchError, match="not empty"):
        mf.download(out, env, lambda *a: None)


def test_cli_hash_and_failure_exit_codes(tmp_path: Path, capsys, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    d = tmp_path / "m"
    write_model(d)
    assert mf.main(["hash", str(d)]) == 0
    assert capsys.readouterr().out.strip() == mf.manifest_sha256(d)
    monkeypatch.setattr(mf.os, "environ", {"MODEL_REPO": "bad"})
    assert mf.main(["download", "--out", str(tmp_path / "o")]) == 1
    assert "FAILED" in capsys.readouterr().err


def test_fake_model_loads_in_the_real_pipeline(tmp_path: Path) -> None:
    pytest.importorskip("transformers")  # ml extra: present in the Docker image, not CI
    from app.detectors.ner import NerDetector

    sha = mf.make_fake(tmp_path / "fake")
    assert sha == mf.manifest_sha256(tmp_path / "fake")
    spans = NerDetector(str(tmp_path / "fake"), threshold=0.0).detect("Rahul met Priya in Kochi.")
    assert isinstance(spans, list)  # random weights: only the loading path is under test
