"""闸口通行接口：维护通行记录，覆盖确认放行、拦截车辆、复核通行等动作。

识别相关：/recognition 登记闸口识别结果，识别失败自动生成待核实记录；
/pending-review 单独归集待核实台账；/{entry_id}/supplement 人工补录。
固定路径要放在 /{entry_id} 之前注册，否则会被路径参数抢占。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, GateRecognitionResult, PageResult
from app.services.gate import GateService

router = APIRouter(prefix="/api/gate", tags=["闸口通行"])

service = GateService()

LIST_FIELDS = ["通行编号", "车牌号码", "关联箱号", "进出方向", "通行时间", "道口编号", "值守人员", "通行状态"]
STATUSES = ["待放行", "已放行", "已拦截", "已复核", "待核实"]


@router.get("/pending-review", response_model=PageResult[dict])
def list_pending_review() -> PageResult[dict]:
    """待核实台账：识别失败或箱号查不到的记录单独归集，换班后依然保留。"""
    items = service.list_pending_review()
    return PageResult(items=items, total=len(items))


@router.get("/stats")
def gate_stats() -> dict[str, Any]:
    """闸口台账统计：总数、待核实数量与各状态分布，供页面统计卡使用。"""
    return service.stats()


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出闸口通行清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "gate", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按通行编号或车牌号码检索"),
    status: str | None = Query(default=None, description="待放行、已放行、已拦截、已复核、待核实"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按关键字与状态过滤闸口通行列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条通行记录明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"通行记录 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条通行记录，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="通行记录已登记", entry=entry)


@router.post("/recognition", response_model=GateRecognitionResult)
def register_recognition(payload: EntryPayload) -> GateRecognitionResult:
    """闸口识别登记：车牌识别失败或关联箱号查不到时，记录标为待核实并保留，等待人工补录。"""
    entry, issues = service.register_recognition(payload.values)
    recognized = not issues
    if recognized:
        message = f"识别成功，通行记录 {entry['通行编号']} 已登记为待放行"
    else:
        message = (
            f"识别未通过（{'；'.join(issues)}），"
            f"记录 {entry['通行编号']} 已标记为待核实，请在待核实台账中人工补录"
        )
    return GateRecognitionResult(ok=True, message=message, entry=entry, recognized=recognized, reasons=issues)


@router.post("/{entry_id}/supplement", response_model=GateRecognitionResult)
def supplement_entry(entry_id: int, payload: EntryPayload) -> GateRecognitionResult:
    """人工补录：补全车牌、箱号等信息；核实通过转待放行，未通过保持待核实并说明原因。"""
    entry, message, issues = service.supplement_entry(entry_id, payload.values)
    if entry is None:
        raise HTTPException(status_code=404, detail=message)
    return GateRecognitionResult(ok=True, message=message, entry=entry, recognized=not issues, reasons=issues)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条通行记录执行确认放行、拦截车辆、复核通行；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
