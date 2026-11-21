"""会话上下文：内存实现（M0/M1 阶段），接口不变的前提下可替换为 Redis。"""
from app.core.config import get_settings

# 全局存储：生产替换为 Redis 时仅改本模块
_sessions: dict[str, list[dict]] = {}


def get_history(session_id: str | None) -> list[dict]:
    if not session_id:
        return []
    return _sessions.get(session_id, [])[-get_settings().session_max_turns * 2:]


def append_turn(session_id: str | None, user: str, assistant: str) -> None:
    if not session_id:
        return
    turns = _sessions.setdefault(session_id, [])
    turns.append({"role": "user", "content": user})
    turns.append({"role": "assistant", "content": assistant})
    # 截断控制：只保留最近 N 轮
    max_items = get_settings().session_max_turns * 2
    if len(turns) > max_items:
        _sessions[session_id] = turns[-max_items:]


def reset() -> None:
    """测试辅助。"""
    _sessions.clear()
