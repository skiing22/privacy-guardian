import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_layers", ROOT / "scripts" / "check_layers.py")
assert spec and spec.loader
check_layers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_layers)


def test_repo_follows_layer_rules() -> None:
    assert check_layers.check(ROOT / "app") == []


def test_planted_bad_import_is_caught(tmp_path: Path) -> None:
    app = tmp_path / "app"
    shutil.copytree(ROOT / "app" / "fusion", app / "fusion")
    (app / "fusion" / "bad.py").write_text("from sqlalchemy import select\nimport app.api.x\n")
    errors = check_layers.check(app)
    assert len(errors) == 2 and all("fusion" in e for e in errors)
