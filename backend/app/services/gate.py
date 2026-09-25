"""闸口通行业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.store import store

MODULE = "gate"
REQUIRED_FIELDS = ["通行编号", "车牌号码", "关联箱号"]
STATUS_ORDER = ["待放行", "已放行", "已拦截", "已复核"]
ACTION_RULES = {"确认放行": "已放行", "拦截车辆": "已拦截", "复核通行": "已复核"}
NEGATIVE_ACTIONS = []
# 识别失败或箱号对不上时的挂起状态：记录保留在台账里，人工补录核实后再回到正常流转
REVIEW_STATUS = "待核实"
OPTIONAL_FIELDS = ["进出方向", "道口编号", "值守人员"]
SUPPLEMENT_FIELDS = ["车牌号码", "关联箱号", *OPTIONAL_FIELDS]


def _container_exists(container_no: str) -> bool:
    return any(
        str(row.get("箱号", "")).strip() == container_no
        for row in store.rows("container")
    )


def _recognition_issues(plate: str, container_no: str) -> list[str]:
    """识别核对：车牌没读到、箱号缺失或箱号在集装箱档案里查不到，都算未通过。"""
    issues: list[str] = []
    if not plate:
        issues.append("车牌识别失败，未读到车牌号码")
    if not container_no:
        issues.append("未识别到关联箱号")
    elif not _container_exists(container_no):
        issues.append(f"关联箱号 {container_no} 在集装箱档案中查不到")
    return issues


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class GateService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("通行编号", ""))
                or keyword in str(row.get("车牌号码", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def list_pending_review(self) -> list[dict[str, Any]]:
        """待核实台账：识别未通过的记录单独归集，随数据文件跨班次保留。"""
        return [row for row in store.rows(MODULE) if row.get("status") == REVIEW_STATUS]

    def stats(self) -> dict[str, Any]:
        rows = store.rows(MODULE)
        by_status: dict[str, int] = {}
        for row in rows:
            key = str(row.get("status", ""))
            by_status[key] = by_status.get(key, 0) + 1
        return {
            "total": len(rows),
            "by_status": by_status,
            "pending_review": by_status.get(REVIEW_STATUS, 0),
        }

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
        store.save()
        return entry, []

    def register_recognition(self, values: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """闸口识别登记：识别失败不丢记录，标为待核实并写明原因，等人工补录。"""
        plate = str(values.get("车牌号码") or "").strip()
        container_no = str(values.get("关联箱号") or "").strip()
        issues = _recognition_issues(plate, container_no)
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["通行编号"] = f"GATE-{entry['id']:04d}"
        entry["车牌号码"] = plate
        entry["关联箱号"] = container_no
        for field in OPTIONAL_FIELDS:
            entry[field] = str(values.get(field) or "").strip()
        entry["通行时间"] = _now()
        entry["识别备注"] = "；".join(issues)
        entry["补录次数"] = 0
        entry["status"] = REVIEW_STATUS if issues else STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = bool(issues)
        entry["通行状态"] = entry["status"]
        rows.append(entry)
        store.save()
        return entry, issues

    def supplement_entry(
        self, entry_id: int, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str, list[str]]:
        """人工补录：补全车牌、箱号等信息后重新核实，通过则转回待放行。"""
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"通行记录 {entry_id} 不存在或已归档", []
        for field in SUPPLEMENT_FIELDS:
            text = str(values.get(field) or "").strip()
            if text:
                entry[field] = text
        entry["补录次数"] = int(entry.get("补录次数", 0) or 0) + 1
        entry["补录时间"] = _now()
        operator = str(values.get("值守人员") or "").strip()
        if operator:
            entry["补录人"] = operator
        issues = _recognition_issues(
            str(entry.get("车牌号码") or "").strip(),
            str(entry.get("关联箱号") or "").strip(),
        )
        if issues:
            entry["status"] = REVIEW_STATUS
            entry["识别备注"] = "；".join(issues)
            message = "补录已保存，但仍有未核实项，记录保持待核实"
        else:
            entry["status"] = STATUS_ORDER[0]
            entry["识别备注"] = ""
            entry["abnormal"] = False
            message = "补录完成，记录已核实并转入待放行"
        entry["pending"] = True
        entry["通行状态"] = entry["status"]
        store.save()
        return entry, message, issues

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"通行记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于闸口通行可执行范围"
        if entry.get("status") == REVIEW_STATUS:
            return None, f"通行记录 {entry_id} 处于待核实状态，请先人工补录核实再执行放行类操作"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        entry["通行状态"] = target
        store.save()
        return entry, f"通行记录已{action}"
