"""错误码体系：E1xxx 输入类（用户可读）/ E2xxx 模型类（降级提示）/ E3xxx 系统类。"""


class ErrorCode:
    # E1xxx 输入类
    INVALID_INPUT = ("E1001", "请求参数不合法", 422)
    MISSING_SCREENSHOT = ("E1002", "数据预览需要页面截图", 422)
    UNAUTHORIZED = ("E1003", "鉴权失败", 401)
    RATE_LIMITED = ("E1004", "请求过于频繁，请稍后再试", 429)

    # E2xxx 模型类
    MODEL_TIMEOUT = ("E2001", "模型响应超时", 504)
    MODEL_UNAVAILABLE = ("E2002", "模型服务暂不可用", 503)
    INVALID_STRUCTURED_OUTPUT = ("E2003", "模型结构化输出解析失败", 502)

    # E3xxx 系统类
    INTERNAL = ("E3001", "内部错误", 500)


class AppError(Exception):
    """业务异常：code + 用户可读信息 + HTTP 状态码，SSE 阶段转为 error 事件。

    用法：AppError(*ErrorCode.XXX, detail="仅进日志的细节")
    """

    def __init__(self, code: str, user_message: str, http_status: int = 500, detail: str = ""):
        self.code = code
        self.user_message = user_message
        self.http_status = http_status
        # detail 仅进日志/审计，不暴露给用户
        self.detail = detail
        super().__init__(f"[{self.code}] {self.user_message}: {detail}")
