"""不依赖外部审核服务的儿童内容安全基础策略。

这层只处理高确定性风险和服务端权限，不尝试代替完整的语义审核。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

CHILD_SAFETY_PROFILE_MARKER = "[CHILD_SAFETY_PROFILE:v1]"


class SafetyAction(str, Enum):
    ALLOW = "allow"
    SAFE_REDIRECT = "safe_redirect"
    PRIVACY_GUARD = "privacy_guard"
    CRISIS_HANDOFF = "crisis_handoff"
    BLOCK_TOOL = "block_tool"
    BLOCK_OUTPUT = "block_output"


@dataclass(frozen=True)
class SafetyDecision:
    action: SafetyAction
    category: str
    response: str | None = None
    display_text: str | None = None
    safe_text: str | None = None

    @property
    def allowed(self) -> bool:
        return self.action == SafetyAction.ALLOW


CRISIS_RESPONSE = (
    "😔先离开危险，马上去找爸爸妈妈、老师或身边可信任的大人。"
    "现在很紧急的话，请大人拨打110、120或119。"
)
ABUSE_RESPONSE = (
    "😔这不是你的错，我很重视你说的话。"
    "请现在就告诉爸爸妈妈、老师或其他可信任的大人。"
)
PRIVACY_RESPONSE = (
    "😶这个不用告诉我。住址、学校、电话、照片、密码和验证码，"
    "只告诉爸爸妈妈或可信任的大人。"
)
DANGEROUS_REQUEST_RESPONSE = (
    "😶这个做法可能会伤到人，我不能教。我们一起换个安全的办法。"
)
PARENT_REQUIRED_RESPONSE = "😶这个功能需要爸爸妈妈来操作，请先找他们帮忙。"
OUTPUT_BLOCK_RESPONSE = "😶这个回答不适合现在播放。我们换一个安全的话题。"


_MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_VERIFICATION_CODE_RE = re.compile(
    r"(?:(?:验证码|校验码|短信码|密码)[^\d]{0,8})(\d{4,8})(?!\d)", re.IGNORECASE
)
_API_KEY_RE = re.compile(r"\b(?:sk-|ak-)[A-Za-z0-9_-]{12,}\b", re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_CONTROL_MARKER_RE = re.compile(
    r"</?(?:system|assistant|user|tool|tool_call|function_call)[^>]*>",
    re.IGNORECASE,
)
_PROMPT_INJECTION_RE = re.compile(
    r"(?:忽略|无视|覆盖).{0,12}(?:之前|以上|系统).{0,8}(?:指令|规则|提示词)",
    re.IGNORECASE,
)


def _compact(text: Any) -> str:
    return re.sub(
        r"[\s，。！？!?；;、,.：:'\"“”‘’（）()【】\[\]]+", "", str(text or "")
    )


def _contains_any(text: str, patterns: Iterable[re.Pattern]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def summarize_text_for_log(text: Any) -> str:
    """只记录长度和不可逆短摘要，不把孩子原话写进日志。"""

    value = str(text or "")
    digest = hashlib.sha256(value.encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"chars={len(value)}, sha256={digest}"


class ChildContentSafetyPolicy:
    """儿童模式的本地风险路由、工具权限和输出兜底。"""

    ALLOWED_TOOLS = frozenset(
        {
            "get_weather",
            "get_time",
            "play_music",
            "handle_exit_intent",
        }
    )

    _SELF_HARM_PATTERNS = (
        re.compile(r"不想活(?:了|下去)?"),
        re.compile(r"活着没意思"),
        re.compile(r"想(?:去)?死"),
        re.compile(r"自杀|自伤|伤害自己|杀掉自己"),
        re.compile(r"从(?:楼|窗|阳台).*(?:跳|下去)"),
    )
    _ABUSE_PATTERNS = (
        re.compile(r"有人.*(?:摸|碰|脱).*(?:身体|屁股|胸|内裤|衣服)"),
        re.compile(r"(?:叔叔|阿姨|老师|哥哥|姐姐|陌生人|大人).*(?:摸我|碰我|亲我|脱我)"),
        re.compile(r"(?:他|她|有人).*(?:威胁我|打我|欺负我|不让我告诉)"),
        re.compile(r"(?:这是|当成).*(?:秘密).*(?:别|不要).*(?:告诉)"),
    )
    _IMMEDIATE_DANGER_PATTERNS = (
        re.compile(r"救命|着火了|起火了|漏电了|触电了"),
        re.compile(r"我(?:迷路|走失|找不到爸爸妈妈|找不到妈妈|找不到爸爸)"),
        re.compile(r"有人(?:跟着|追着|抓住|锁住)我"),
        re.compile(r"我(?:受伤|流血|被刀划|掉进水里|溺水)"),
        re.compile(r"我(?:吃了|吞了|喝了).*(?:药|药片|清洁剂|洗衣液|酒精|毒)"),
    )
    _PRIVACY_DISCLOSURE_PATTERNS = (
        re.compile(r"(?:我家|我的|家里).*(?:住址|地址|门牌号|定位)"),
        re.compile(r"(?:我在|我读|我的).*(?:学校|幼儿园).*(?:叫|是|地址|位于)"),
        re.compile(r"(?:我的|我家|爸爸|妈妈).*(?:电话|手机号|号码)(?:是|为|：|:)?"),
        re.compile(r"(?:我的|账号|银行卡|手机).*(?:密码|验证码)(?:是|为|：|:)?"),
        re.compile(r"(?:发给你|给你看|上传).*(?:照片|定位|二维码|身份证)"),
    )
    _DANGEROUS_REQUEST_PATTERNS = (
        re.compile(r"(?:怎么|如何|教我|告诉我).*(?:做|制造).*(?:炸弹|爆炸物|武器|毒药)"),
        re.compile(r"(?:怎么|如何|教我).*(?:伤害|打|杀|毒).*(?:自己|别人|人|动物|小猫|小狗)"),
        re.compile(r"(?:怎么|如何|教我).*(?:点火|放火|偷|骗|开锁)"),
        re.compile(r"(?:怎么|如何).*(?:偷偷|自己).*(?:吃药|用药|拿药)"),
        re.compile(r"(?:敢不敢|挑战|试试).*(?:跳楼|跳窗|摸插座|碰电线|憋气|吞药)"),
        re.compile(r"(?:给我|讲讲|描述).*(?:色情|成人影片|成人视频)"),
    )
    _PARENT_ONLY_PATTERNS = (
        re.compile(r"(?:帮我|替我).*(?:付款|支付|转账|充值|打赏|下单|买东西)"),
        re.compile(r"(?:帮我|替我).*(?:开门|发消息|上传照片|打开摄像头|拨打电话)"),
        re.compile(r"(?:访问|打开|点击).*(?:链接|网址|二维码)"),
    )

    _UNSAFE_OUTPUT_PATTERNS = (
        re.compile(r"(?:别|不要).{0,8}(?:告诉|跟).{0,8}(?:爸爸|妈妈|家长|老师|其他人)"),
        re.compile(r"这是(?:我们|你和我|咱们)(?:两个人)?的秘密"),
        re.compile(r"(?:替我|帮我|给小布).{0,4}保密"),
        re.compile(r"(?:只有我|只需要我|只和我).{0,10}(?:懂你|陪你|说话|聊天|就够了)"),
        re.compile(r"(?:不需要|不用理|离开).{0,8}(?:爸爸|妈妈|家人|老师|朋友)"),
        re.compile(r"告诉我.{0,12}(?:住址|地址|学校|电话|手机号|密码|验证码|定位|照片)"),
        re.compile(r"把(?:手|手指).{0,6}(?:伸进|放进).{0,6}(?:插座|电线)"),
        re.compile(r"(?:从|往).{0,4}(?:窗户|阳台|楼上).{0,6}(?:跳|爬出去)"),
        re.compile(r"(?:自己|偷偷).{0,6}(?:吃药|用药|吞药)"),
        re.compile(r"(?:第一步|步骤一).{0,30}(?:炸弹|爆炸物|武器|毒药)"),
        re.compile(r"(?:点击|打开).{0,12}https?://", re.IGNORECASE),
        re.compile(r"<tool_call>|<function_call>", re.IGNORECASE),
    )

    def __init__(self, enabled: bool = False):
        self.enabled = bool(enabled)

    @classmethod
    def from_config(
        cls, config: dict[str, Any] | None
    ) -> ChildContentSafetyPolicy:
        config = config or {}
        safety_config = config.get("content_safety") or {}
        explicit = safety_config.get("child_mode")
        if explicit is not None:
            if isinstance(explicit, str):
                enabled = explicit.strip().lower() in {"1", "true", "yes", "on"}
            else:
                enabled = bool(explicit)
            return cls(enabled=enabled)
        prompt = str(config.get("prompt") or "")
        return cls(enabled=CHILD_SAFETY_PROFILE_MARKER in prompt)

    def evaluate_input(self, text: Any) -> SafetyDecision:
        original = str(text or "")
        if not self.enabled:
            return SafetyDecision(SafetyAction.ALLOW, "disabled", safe_text=original)

        compact = _compact(original)
        if _contains_any(compact, self._SELF_HARM_PATTERNS):
            return SafetyDecision(
                SafetyAction.CRISIS_HANDOFF,
                "self_harm",
                response=CRISIS_RESPONSE,
                display_text="[安全求助内容已收到]",
            )
        if _contains_any(compact, self._ABUSE_PATTERNS):
            return SafetyDecision(
                SafetyAction.CRISIS_HANDOFF,
                "abuse_or_bullying",
                response=ABUSE_RESPONSE,
                display_text="[安全求助内容已收到]",
            )
        if _contains_any(compact, self._IMMEDIATE_DANGER_PATTERNS):
            return SafetyDecision(
                SafetyAction.CRISIS_HANDOFF,
                "immediate_danger",
                response=CRISIS_RESPONSE,
                display_text="[紧急求助内容已收到]",
            )

        privacy_hit = bool(
            _MOBILE_RE.search(original)
            or _VERIFICATION_CODE_RE.search(original)
            or _API_KEY_RE.search(original)
            or _contains_any(compact, self._PRIVACY_DISCLOSURE_PATTERNS)
        )
        if privacy_hit:
            return SafetyDecision(
                SafetyAction.PRIVACY_GUARD,
                "privacy",
                response=PRIVACY_RESPONSE,
                display_text=self.redact_private_text(original),
            )
        if _contains_any(compact, self._DANGEROUS_REQUEST_PATTERNS):
            return SafetyDecision(
                SafetyAction.SAFE_REDIRECT,
                "dangerous_request",
                response=DANGEROUS_REQUEST_RESPONSE,
                display_text="[危险请求已安全处理]",
            )
        if _contains_any(compact, self._PARENT_ONLY_PATTERNS):
            return SafetyDecision(
                SafetyAction.BLOCK_TOOL,
                "parent_only_action",
                response=PARENT_REQUIRED_RESPONSE,
                display_text="[需要家长操作的请求]",
            )
        return SafetyDecision(SafetyAction.ALLOW, "normal", safe_text=original)

    def evaluate_output(self, text: Any) -> SafetyDecision:
        original = str(text or "")
        if not self.enabled:
            return SafetyDecision(SafetyAction.ALLOW, "disabled", safe_text=original)

        if _contains_any(original, self._UNSAFE_OUTPUT_PATTERNS):
            return SafetyDecision(
                SafetyAction.BLOCK_OUTPUT,
                "unsafe_assistant_output",
                response=OUTPUT_BLOCK_RESPONSE,
                safe_text=OUTPUT_BLOCK_RESPONSE,
            )

        safe_text = self.redact_private_text(original)
        return SafetyDecision(SafetyAction.ALLOW, "normal", safe_text=safe_text)

    def guard_assistant_text(self, text: Any) -> str:
        decision = self.evaluate_output(text)
        return decision.safe_text or decision.response or OUTPUT_BLOCK_RESPONSE

    def can_execute_tool(self, tool_name: str) -> bool:
        if not self.enabled:
            return True
        return tool_name in self.ALLOWED_TOOLS

    def filter_function_descriptions(self, functions):
        if not self.enabled:
            return functions
        filtered = []
        for function in functions or []:
            name = (function.get("function") or {}).get("name") or function.get("name")
            if name in self.ALLOWED_TOOLS:
                filtered.append(function)
        return filtered

    def sanitize_tool_result(self, tool_name: str, value: Any) -> str:
        text = str(value or "")
        if not self.enabled:
            return text
        text = _CONTROL_MARKER_RE.sub("[控制标记已移除]", text)
        text = _PROMPT_INJECTION_RE.sub("[可疑指令已移除]", text)
        text = _API_KEY_RE.sub("[密钥已隐藏]", text)
        text = self.redact_private_text(text)
        return text[:3000]

    @staticmethod
    def redact_private_text(text: Any) -> str:
        value = str(text or "")
        value = _MOBILE_RE.sub("[电话号码已隐藏]", value)
        value = _VERIFICATION_CODE_RE.sub(
            lambda match: match.group(0).replace(match.group(1), "[验证码已隐藏]"),
            value,
        )
        value = _API_KEY_RE.sub("[密钥已隐藏]", value)
        return value

    @staticmethod
    def safe_tool_argument_keys(arguments: Any):
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments else {}
            except (TypeError, json.JSONDecodeError):
                return []
        if not isinstance(arguments, dict):
            return []
        return sorted(str(key) for key in arguments)
