"""测试公共夹具：每用例重置缓存与会话，保证隔离。"""
import pytest

from app.agent import session
from app.cache import response_cache


@pytest.fixture(autouse=True)
def reset_state():
    response_cache.reset()
    session.reset()
    yield
    response_cache.reset()
    session.reset()
