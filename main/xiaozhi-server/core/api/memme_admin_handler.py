import hmac
import os
import re

from aiohttp import web

from core.providers.memory.memme.memme import MemoryProvider


_USER_ID_RE = re.compile(r"xiaozhi-user-\d+")


class MemMeAdminHandler:
    """仅供同机 manager-api 使用的 MemMe 数据权利入口。"""

    def __init__(self, config: dict):
        self.provider = None
        for memory_config in (config.get("Memory") or {}).values():
            if isinstance(memory_config, dict) and memory_config.get("type") == "memme":
                self.provider = MemoryProvider(memory_config, worker_only=True)
                break
        # manager-api 的 server-base 响应通常不包含具体智能体的记忆模型。
        # 数据权利接口只使用同机环境变量补齐，不接受外部请求传入服务地址或密钥。
        if self.provider is None and os.getenv("MEMME_API_KEY", "").strip():
            self.provider = MemoryProvider(
                {
                    "type": "memme",
                    "base_url": os.getenv(
                        "MEMME_BASE_URL", "http://127.0.0.1:8080"
                    ),
                    "api_key": "${MEMME_API_KEY}",
                    "app_id": os.getenv("MEMME_APP_ID", "xiaozhi"),
                    "queue_path": os.getenv(
                        "MEMME_QUEUE_PATH", "data/memme-retry.sqlite3"
                    ),
                    "retry_batch_size": 2,
                    "retry_poll_seconds": 1,
                    "retry_base_seconds": 10,
                    "retry_max_seconds": 3600,
                    "dead_letter_max_jobs": 1000,
                },
                worker_only=True,
            )
        if self.provider is not None:
            self.provider.ensure_global_worker()

    def _authorized(self, request: web.Request) -> bool:
        if (
            request.remote not in {"127.0.0.1", "::1"}
            or self.provider is None
            or not self.provider.use_memme
        ):
            return False
        expected = f"Bearer {self.provider.api_key}"
        supplied = request.headers.get("Authorization", "")
        return bool(self.provider.api_key) and hmac.compare_digest(supplied, expected)

    @staticmethod
    def _user_id(request: web.Request) -> str:
        user_id = request.match_info.get("user_id", "")
        if not _USER_ID_RE.fullmatch(user_id):
            raise web.HTTPBadRequest(text="invalid user id")
        return user_id

    async def export_user(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            raise web.HTTPUnauthorized()
        try:
            data = await self.provider.export_user_data(self._user_id(request))
            return web.json_response({"success": True, "data": data})
        except web.HTTPException:
            raise
        except Exception:
            return web.json_response(
                {"success": False, "error": "MemMe export failed"}, status=502
            )

    async def delete_user(self, request: web.Request) -> web.Response:
        if not self._authorized(request):
            raise web.HTTPUnauthorized()
        try:
            allow_future = request.query.get("allow_future", "").lower() == "true"
            data = await self.provider.delete_user_data(
                self._user_id(request), allow_future=allow_future
            )
            return web.json_response({"success": True, "data": data})
        except web.HTTPException:
            raise
        except Exception:
            return web.json_response(
                {"success": False, "error": "MemMe deletion failed"}, status=502
            )
