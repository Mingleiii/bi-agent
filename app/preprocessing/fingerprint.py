"""数据指纹：缓存键 = md5(裁剪后数据 + skill + 用户消息)。"""
import hashlib
import json


def fingerprint(slimmed: dict, skill: str, message: str) -> str:
    raw = json.dumps(
        {"data": slimmed, "skill": skill, "message": message},
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.md5(raw).hexdigest()
