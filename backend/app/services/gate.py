"""闸口通行业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.store import store

MODULE = "gate"
REQUIRED_FIELDS = ["通行编号", "车牌号码", "关联箱号"]
STATUS_ORDER = ["待放行", "已放行", "已拦截", "已复核"]
ACTION_RULES = {"确认放行": "已放行", "拦截车辆": "已拦截", "复核通行": "已复核"}
NEGATIVE_ACTIONS = []

# 待核实：识别失败或箱号未匹配的记录先归集到这里，核实后再回到正常放行流程
VERIFY_STATUS = "待核实"
RECOGNITION_FAILED_REASON = "车牌识别失败，待人工补录"

# 通行记录落盘位置：换班、重开页面、服务重启后待核实清单都要还在
DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "gate_entries.json"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class GateService:
    def __init__(self) -> None:
        self._restore()

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        plate: str | None = None,
        container_no: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("通行编号", ""))]
        if plate:
            rows = [row for row in rows if plate in str(row.get("车牌号码", ""))]
        if container_no:
            rows = [row for row in rows if container_no in str(row.get("关联箱号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def list_pending_verification(self) -> list[dict[str, Any]]:
        """待核实台账：识别失败或箱号未匹配的记录单独归集。"""
        return [row for row in store.rows(MODULE) if row.get("status") == VERIFY_STATUS]

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        self._persist()
        return entry, []

    def register_recognition(self, values: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """闸口识别登记：识别失败或箱号查不到时落成待核实记录，而不是让记录消失。"""
        plate = str(values.get("车牌号码") or "").strip()
        recognition_failed = bool(values.get("recognition_failed")) or not plate
        container_no = str(values.get("关联箱号") or "").strip()
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["通行编号"] = str(values.get("通行编号") or "").strip() or self._next_pass_no()
        entry["车牌号码"] = "" if recognition_failed else plate
        entry["关联箱号"] = container_no
        entry["进出方向"] = str(values.get("进出方向") or "").strip() or "进闸"
        entry["通行时间"] = str(values.get("通行时间") or "").strip() or _now()
        entry["道口编号"] = str(values.get("道口编号") or "").strip()
        entry["值守人员"] = str(values.get("值守人员") or "").strip()
        entry["recognition_failed"] = recognition_failed
        entry["pending"] = True
        entry["abnormal"] = False
        if recognition_failed:
            entry["status"] = VERIFY_STATUS
            entry["核实说明"] = RECOGNITION_FAILED_REASON
            message = f"车牌识别失败，通行记录 {entry['通行编号']} 已列入待核实台账，请人工补录车牌"
        elif container_no and not self._container_registered(container_no):
            entry["status"] = VERIFY_STATUS
            entry["核实说明"] = f"关联箱号 {container_no} 未在集装箱档案中登记，待核实"
            message = f"关联箱号 {container_no} 查不到，通行记录 {entry['通行编号']} 已列入待核实台账"
        else:
            entry["status"] = STATUS_ORDER[0]
            entry["核实说明"] = ""
            message = f"通行记录 {entry['通行编号']} 已登记，状态待放行"
        rows.append(entry)
        self._persist()
        return entry, message

    def complete_manual_entry(self, entry_id: int, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """人工补录：补全车牌（必填）与箱号；补录后按车牌可检索到该记录。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"通行记录 {entry_id} 不存在或已归档"
        if entry.get("status") != VERIFY_STATUS:
            return None, f"通行记录 {entry.get('通行编号', entry_id)} 当前状态为{entry.get('status')}，无需人工补录"
        plate = str(values.get("车牌号码") or "").strip()
        if not plate:
            return None, "人工补录必须填写车牌号码"
        container_no = str(values.get("关联箱号") or "").strip()
        entry["车牌号码"] = plate
        if container_no:
            entry["关联箱号"] = container_no
        operator = str(values.get("值守人员") or "").strip()
        if operator:
            entry["值守人员"] = operator
        entry["recognition_failed"] = False
        linked = str(entry.get("关联箱号") or "").strip()
        if linked and not self._container_registered(linked):
            entry["核实说明"] = f"已于 {_now()} 人工补录车牌，关联箱号 {linked} 仍未登记，继续待核实"
            self._persist()
            return entry, f"车牌已补录为 {plate}，但关联箱号 {linked} 仍未登记，记录继续留在待核实台账"
        entry["status"] = STATUS_ORDER[0]
        entry["核实说明"] = f"已于 {_now()} 人工补录，转入待放行"
        self._persist()
        return entry, f"人工补录完成，通行记录 {entry['通行编号']} 已转入待放行，按车牌 {plate} 可查到补录结果"

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"通行记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于闸口通行可执行范围"
        if entry.get("status") == VERIFY_STATUS:
            return None, f"通行记录 {entry.get('通行编号', entry_id)} 待核实，请先完成人工补录再执行{action}"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        self._persist()
        return entry, f"通行记录已{action}"

    @staticmethod
    def _container_registered(container_no: str) -> bool:
        return any(
            str(row.get("箱号", "")).strip() == container_no
            for row in store.rows("container")
        )

    @staticmethod
    def _next_pass_no() -> str:
        suffixes: list[int] = []
        for row in store.rows(MODULE):
            pass_no = str(row.get("通行编号", ""))
            if pass_no.startswith("GATE-"):
                try:
                    suffixes.append(int(pass_no.split("-", 1)[1]))
                except ValueError:
                    continue
        return f"GATE-{max(suffixes, default=0) + 1:04d}"

    def _restore(self) -> None:
        """启动时从落盘文件恢复通行记录，保证换班、重开页面后待核实清单还在。"""
        if not DATA_FILE.exists():
            return
        try:
            rows = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(rows, list):
            store.replace_rows(MODULE, [row for row in rows if isinstance(row, dict)])

    @staticmethod
    def _persist() -> None:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        DATA_FILE.write_text(
            json.dumps(store.rows(MODULE), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
