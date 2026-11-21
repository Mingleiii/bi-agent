"""应用配置：pydantic-settings 统一管理，含功能开关（灰度与排障的基础）。"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # ---- 环境与鉴权 ----
    app_name: str = "bi-agent"
    env: Literal["dev", "test", "prod"] = "dev"
    # 为空表示开发模式不鉴权；生产必须通过环境变量注入
    api_key: str = ""
    rate_limit_per_min: int = 60

    # ---- LLM 后端 ----
    llm_provider: Literal["mock", "openai"] = "mock"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    model_small: str = "gpt-4o-mini"
    model_large: str = "gpt-4o"
    model_multimodal: str = "gpt-4o"
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 2

    # ---- 功能开关 ----
    cache_on: bool = True
    cache_ttl_seconds: int = 300
    guardrail_on: bool = True
    audit_on: bool = True
    audit_path: str = "logs/audit.jsonl"

    # ---- 编排 ----
    session_max_turns: int = 10
    route_confidence_threshold: float = 0.6

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), env_prefix="BIAGENT_", extra="ignore"
    )

    @property
    def audit_file(self) -> Path:
        p = Path(self.audit_path)
        return p if p.is_absolute() else BASE_DIR / p


@lru_cache
def get_settings() -> Settings:
    return Settings()
