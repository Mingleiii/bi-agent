"""LLM 审计：JSONL 追加落盘（生产可替换为数据库/数仓表，字段保持一致）。"""
import json
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.logging import get_logger, get_trace_id

log = get_logger(__name__)


def write_audit(record: dict) -> None:
    """记录一次 LLM 调用/一次请求的审计信息；失败只告警不阻断主链路。"""
    settings = get_settings()
    if not settings.audit_on:
        return
    record.update(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "trace_id": get_trace_id(),
        }
    )
    try:
        path = settings.audit_file
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 审计失败不影响业务
        log.warning("audit write failed", exc_info=True)
