"""게임 CSV 파일을 UTF-8 dict row로 읽는 작은 로더입니다."""

from __future__ import annotations

import csv
from pathlib import Path


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    """CSV 파일을 읽고 빈 값을 빈 문자열로 정리해 반환합니다."""

    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        return [
            {key: value or "" for key, value in row.items() if key is not None}
            for row in reader
        ]
