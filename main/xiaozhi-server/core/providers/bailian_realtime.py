"""百炼实时语音接口的公用工具。"""

import uuid
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def build_realtime_ws_url(base_url: str, model: str, ws_url: str = None) -> str:
    """将 OpenAI 兼容地址转成同一个百炼业务空间的实时 WebSocket 地址。"""
    source_url = ws_url or base_url or "https://dashscope.aliyuncs.com"
    if "{model}" in source_url:
        source_url = source_url.format(model=model)

    parsed = urlparse(source_url)
    if not parsed.netloc:
        raise ValueError("百炼 base_url/ws_url 格式不正确")

    scheme = "wss" if parsed.scheme in ("https", "wss", "") else "ws"
    path = parsed.path if ws_url else "/api-ws/v1/realtime"
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["model"] = model
    return urlunparse((scheme, parsed.netloc, path, "", urlencode(query), ""))


def realtime_event(event_type: str, **payload) -> dict:
    """生成带唯一事件 ID 的百炼实时协议消息。"""
    return {
        "event_id": f"event_{uuid.uuid4().hex}",
        "type": event_type,
        **payload,
    }
