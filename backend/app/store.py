"""内存数据仓库：给每个业务模块准备一份可筛选、可流转的示例数据。

真实项目里这里会换成数据库访问层；当前实现只依赖标准库，保证克隆下来就能起。

闸口台账需要跨班次保留（换班、重开页面后待核实清单不能丢），所以 Store 支持
把当前数据快照落到本地 JSON 文件：启动时若文件存在就从文件恢复，否则用示例数据。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.seed import SEED_ROWS

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "store.json"


class Store:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = self._load()

    def _load(self) -> dict[str, list[dict[str, Any]]]:
        if DATA_FILE.exists():
            try:
                data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = None
            if isinstance(data, dict):
                return {
                    str(name): [dict(row) for row in rows]
                    for name, rows in data.items()
                    if isinstance(rows, list)
                }
        return {name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()}

    def save(self) -> None:
        """把当前数据快照写入本地文件，换班或服务重启后仍能恢复台账。"""
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(
            json.dumps(self._tables, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def module_names(self) -> list[str]:
        return sorted(self._tables)

    def rows(self, module: str) -> list[dict[str, Any]]:
        return self._tables.setdefault(module, [])

    def find(self, module: str, entry_id: int) -> dict[str, Any] | None:
        for row in self.rows(module):
            if int(row.get("id", 0)) == entry_id:
                return row
        return None

    def overview(self) -> dict[str, object]:
        modules: list[dict[str, object]] = []
        for name in self.module_names():
            rows = self.rows(name)
            modules.append({
                "name": name,
                "created": len(rows),
                "pending": sum(1 for row in rows if row.get("pending")),
                "abnormal": sum(1 for row in rows if row.get("abnormal")),
            })
        cards = [
            {"label": "业务模块", "value": len(modules)},
            {"label": "今日新增", "value": sum(int(item["created"]) for item in modules)},
            {"label": "待处理", "value": sum(int(item["pending"]) for item in modules)},
            {"label": "异常量", "value": sum(int(item["abnormal"]) for item in modules)},
        ]
        return {"cards": cards, "modules": modules}


store = Store()
