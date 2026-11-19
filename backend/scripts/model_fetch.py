"""Model delivery (API 8.2, ADR-0022 D16). Runs at image BUILD time only; the running app
never contacts Hugging Face.

    python scripts/model_fetch.py download --out /model   # Docker model stage
    python scripts/model_fetch.py hash ./ner-distilbert-v1 # print MODEL_SHA256 (P11.1)
    python scripts/model_fetch.py fake --out /model       # tiny random model for CI

download reads:
    MODEL_REPO       owner/name of the private model repo
    MODEL_REVISION   40-character commit hash (never a branch: builds must be repeatable)
    MODEL_SHA256     expected manifest hash (see `hash`)
    token            file /run/secrets/hf_token (Docker build secret), or HF_TOKEN_FILE.
                     Never an environment variable or argument: those end up in image
                     metadata, shell history or process lists.

Safety rules:
- Only the files the model needs are downloaded, and only safetensors weights (pickle
  weights can run code when loaded).
- The manifest hash covers every file, so a changed tokenizer or config fails the build
  too, not just changed weights.
- 3 retries with backoff 2 s, 8 s, 30 s for network trouble, 5xx and 429. Wrong token,
  missing repo or revision, or a hash mismatch fail at once: retrying cannot fix them.
- Files land in a temporary folder and move into place only after every check passed,
  so a failed build never leaves a half model behind.
- The token is never printed, logged or written anywhere.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

ALLOW = [
    "config.json",
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
    "special_tokens_map.json",
]
REQUIRED = {"config.json", "model.safetensors"}
FORBIDDEN_SUFFIXES = (".bin", ".pt", ".pth", ".pkl", ".pickle", ".ckpt")
BACKOFF_S = (2.0, 8.0, 30.0)
MAX_RETRY_AFTER_S = 60.0
SECRET_PATHS = ("/run/secrets/hf_token",)

REPO_RE = re.compile(r"^[A-Za-z0-9][\w.-]{0,95}/[\w.-]{1,96}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class FetchError(Exception):
    """Fails the build. `retry` = worth trying again (network, server busy)."""

    def __init__(self, message: str, retry: bool = False, wait: float | None = None) -> None:
        super().__init__(message)
        self.retry, self.wait = retry, wait


# ---------------------------------------------------------------- config and secrets


def read_config(env: dict[str, str]) -> tuple[str, str, str]:
    repo = env.get("MODEL_REPO", "").strip()
    rev = env.get("MODEL_REVISION", "").strip().lower()
    sha = env.get("MODEL_SHA256", "").strip().lower()
    if not REPO_RE.match(repo):
        raise FetchError("MODEL_REPO must look like owner/name")
    if not REVISION_RE.match(rev):
        raise FetchError("MODEL_REVISION must be a 40-character commit hash, not a branch")
    if not SHA_RE.match(sha):
        raise FetchError("MODEL_SHA256 must be 64 hex characters (see: model_fetch.py hash)")
    return repo, rev, sha


def read_token(env: dict[str, str], paths: tuple[str, ...] = SECRET_PATHS) -> str:
    if env.get("HF_TOKEN"):
        raise FetchError("pass the token as a build secret file, not as HF_TOKEN")
    candidates = [env["HF_TOKEN_FILE"]] if env.get("HF_TOKEN_FILE") else list(paths)
    for p in candidates:
        path = Path(p)
        if path.is_file():
            token = path.read_text().strip()
            if not token or "\n" in token or len(token) > 512:
                raise FetchError("the token file must hold exactly one token")
            return token
    raise FetchError("no token: build with --secret id=hf_token,src=<file>")


# ---------------------------------------------------------------- hashing


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def model_files(folder: Path) -> list[Path]:
    """Files that make up the model; the hub's .cache folder and our VERSION are not."""
    return sorted(
        p
        for p in folder.rglob("*")
        if p.is_file() and ".cache" not in p.relative_to(folder).parts and p.name != "VERSION"
    )


def manifest_sha256(folder: Path) -> str:
    """One hash over every file name and content, so any change is caught."""
    h = hashlib.sha256()
    for p in model_files(folder):
        h.update(f"{p.relative_to(folder).as_posix()}\t{file_sha256(p)}\n".encode())
    return h.hexdigest()


def make_readable(folder: Path) -> None:
    """Files 0644, folders 0755: the app runs as a non-root user and only reads them."""
    folder.chmod(0o755)
    for p in folder.rglob("*"):
        p.chmod(0o755 if p.is_dir() else 0o644)


def check_files(folder: Path) -> None:
    names = {p.relative_to(folder).as_posix() for p in model_files(folder)}
    bad = sorted(n for n in names if n.endswith(FORBIDDEN_SUFFIXES))
    if bad:
        raise FetchError(f"pickle weights are not allowed: {', '.join(bad)}")
    missing = sorted(REQUIRED - names)
    if missing:
        raise FetchError(f"model is missing: {', '.join(missing)}")
    if not ({"tokenizer.json"} & names or {"vocab.txt"} & names):
        raise FetchError("model is missing a tokenizer (tokenizer.json or vocab.txt)")
    try:
        cfg = json.loads((folder / "config.json").read_text())
    except (OSError, ValueError) as e:
        raise FetchError("config.json is not valid JSON") from e
    if not isinstance(cfg.get("id2label"), dict) or not cfg["id2label"]:
        raise FetchError("config.json has no id2label: not a token classification model")


# ---------------------------------------------------------------- download


Downloader = Callable[[str, str, str, Path], None]


def hub_download(repo: str, revision: str, token: str, dest: Path) -> None:
    """The real call. Maps Hugging Face errors to retry / do not retry."""
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "15")
    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import (
        EntryNotFoundError,
        GatedRepoError,
        HfHubHTTPError,
        RepositoryNotFoundError,
        RevisionNotFoundError,
    )

    try:
        snapshot_download(
            repo_id=repo,
            repo_type="model",
            revision=revision,
            token=token,
            local_dir=dest,
            allow_patterns=ALLOW,
            max_workers=4,
        )
    except (RepositoryNotFoundError, GatedRepoError) as e:
        # Private repos answer "not found" to a wrong or missing token.
        raise FetchError("repo not found or token has no read access") from e
    except RevisionNotFoundError as e:
        raise FetchError("MODEL_REVISION does not exist in the repo") from e
    except EntryNotFoundError as e:
        raise FetchError("a model file is missing in the repo") from e
    except HfHubHTTPError as e:
        status = e.response.status_code if e.response is not None else 0
        if status in (401, 403):
            raise FetchError("token rejected (needs read access to the repo)") from e
        if status == 429:
            after = e.response.headers.get("Retry-After") if e.response is not None else None
            wait = float(after) if after and after.isdigit() else None
            raise FetchError("rate limited by Hugging Face", retry=True, wait=wait) from e
        if status >= 500 or status == 0:
            raise FetchError(f"Hugging Face server error ({status})", retry=True) from e
        raise FetchError(f"download refused ({status})") from e
    except OSError as e:  # network: DNS, reset, timeout
        raise FetchError(f"network error ({type(e).__name__})", retry=True) from e


def download(
    out: Path,
    env: dict[str, str],
    downloader: Downloader = hub_download,
    sleep: Callable[[float], None] = time.sleep,
    secret_paths: tuple[str, ...] = SECRET_PATHS,
) -> str:
    repo, revision, expected = read_config(env)
    token = read_token(env, secret_paths)
    if out.exists() and any(out.iterdir()):
        raise FetchError(f"{out} is not empty")
    out.parent.mkdir(parents=True, exist_ok=True)

    attempt = 0
    while True:
        tmp = Path(tempfile.mkdtemp(prefix=".model-", dir=out.parent))
        try:
            downloader(repo, revision, token, tmp)
            check_files(tmp)
            got = manifest_sha256(tmp)
            if got != expected:
                raise FetchError(f"MODEL_SHA256 mismatch: got {got}")
            shutil.rmtree(tmp / ".cache", ignore_errors=True)
            (tmp / "VERSION").write_text(f"{repo.split('/')[1]}@{revision[:12]}\n")
            make_readable(tmp)
            if out.exists():
                out.rmdir()
            tmp.rename(out)
            return got
        except FetchError as e:
            shutil.rmtree(tmp, ignore_errors=True)
            if not e.retry or attempt >= len(BACKOFF_S):
                raise
            wait = min(e.wait, MAX_RETRY_AFTER_S) if e.wait else BACKOFF_S[attempt]
            print(f"model_fetch: {e}; retry {attempt + 1}/{len(BACKOFF_S)} in {wait:.0f} s")
            sleep(wait)
            attempt += 1
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise


# ---------------------------------------------------------------- fake model (CI)


def make_fake(out: Path, seed: int = 7) -> str:
    """A tiny random DistilBERT with our labels. Exercises the real loading code in CI
    without the private weights. Its predictions are noise: never ship it."""
    import torch
    from transformers import (
        DistilBertConfig,
        DistilBertForTokenClassification,
        DistilBertTokenizerFast,
    )

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.detectors.types import PiiType

    torch.manual_seed(seed)
    labels = ["O"] + [f"{p}-{t.value}" for t in PiiType for p in ("B", "I")]
    out.mkdir(parents=True, exist_ok=True)
    words = "rahul priya sharma kochi pune call email phone the a and patient met".split()
    vocab = [
        "[PAD]",
        "[UNK]",
        "[CLS]",
        "[SEP]",
        "[MASK]",
        *words,
        *"abcdefghijklmnopqrstuvwxyz0123456789@.,-",
    ]
    (out / "vocab.txt").write_text("\n".join(vocab) + "\n")
    tok = DistilBertTokenizerFast(vocab_file=str(out / "vocab.txt"), do_lower_case=True)
    cfg = DistilBertConfig(
        vocab_size=len(vocab), dim=32, hidden_dim=64, n_layers=1, n_heads=2,
        max_position_embeddings=512, num_labels=len(labels),
        id2label=dict(enumerate(labels)), label2id={v: i for i, v in enumerate(labels)},
    )  # fmt: skip
    DistilBertForTokenClassification(cfg).save_pretrained(out, safe_serialization=True)
    tok.save_pretrained(out)
    for extra in out.glob("*"):  # keep only what a real model ships
        if extra.is_file() and extra.name not in ALLOW:
            extra.unlink()
    check_files(out)
    (out / "VERSION").write_text("fake-ci-model\n")
    make_readable(out)
    return manifest_sha256(out)


# ---------------------------------------------------------------- cli


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="model_fetch.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("download").add_argument("--out", type=Path, required=True)
    sub.add_parser("hash").add_argument("folder", type=Path)
    sub.add_parser("fake").add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "hash":
            check_files(args.folder)
            print(manifest_sha256(args.folder))
        elif args.cmd == "fake":
            print(f"model_fetch: fake model written, sha256 {make_fake(args.out)}")
        else:
            got = download(args.out, dict(os.environ))
            print(f"model_fetch: model verified, sha256 {got}")
    except FetchError as e:
        print(f"model_fetch: FAILED: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
