"""模型分级路由：按任务选择模型档位，控制成本。

路由策略（可在 config 调整模型名）：
- interpret   -> large  深度解读需要推理能力
- briefing    -> small  槽位填数是低复杂度任务
- preview     -> multimodal 需要视觉理解
- intent 路由 -> small
"""
from app.core.config import get_settings


def resolve_model(purpose: str) -> str:
    s = get_settings()
    mapping = {
        "interpret": s.model_large,
        "briefing": s.model_small,
        "preview": s.model_multimodal,
        "routing": s.model_small,
    }
    return mapping.get(purpose, s.model_large)
