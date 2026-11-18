from collections.abc import Iterator
from pathlib import Path

import pytest

from app.storage.db import Database, migrate


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Database]:
    migrate(tmp_path, backup=False)
    d = Database.at(tmp_path)
    yield d
    d.engine.dispose()
