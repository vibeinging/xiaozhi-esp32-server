"""长期记忆写入过滤（对接合同 docs/design/2026-09-02_memme-xiaozhi-integration-contract.md §9）。

进入 MemMe 的文字分两级处理：

1. 脱敏（PII 与凭据）：电话、邮箱、验证码、密钥、网址、身份证、门牌、
   学校/幼儿园名称、班级——替换成「已隐藏」占位，其余内容保留；
2. 整条排除（类别）：自伤/正在发生的危险/侵害、医疗细节、成人内容——
   这些只应进入家长安全流程，不进入长期记忆。

关键词取高精度子集，宁可漏掉可疑也不大量误伤正常童言。
「家长明确标为不记住」的标记能力未实现，接入 UI 后在此挂钩。
"""

import re
from typing import Any, Optional

_MOBILE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_LANDLINE_RE = re.compile(r"(?<!\d)(?:0\d{2,3}[-—\s]?)?\d{7,8}(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_VERIFICATION_CODE_RE = re.compile(
    r"(验证码|校验码|动态码)[^\d]{0,6}(\d{4,8})"
)
_API_KEY_RE = re.compile(r"\b(?:sk-|ak-)[A-Za-z0-9_-]{12,}\b", re.IGNORECASE)
_PASSWORD_RE = re.compile(
    r"((?:Wi[- ]?Fi|无线网|账号|登录|支付|手机|电脑|平板)?\s*"
    r"(?:密码|口令|PIN码?)\s*(?:是|为|：|:|=)?\s*)"
    r"([A-Za-z0-9_@#%+!.$*-]{4,64})",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_ID_CARD_RE = re.compile(r"(?<!\d)\d{17}[0-9Xx](?!\d)")

# 路名+门牌：「幸福路12号」「中山大道88号院」
_ROAD_PLATE_RE = re.compile(r"[\u4e00-\u9fa5]{1,10}(?:路|街|道|巷)\s*\d{1,5}\s*号(?:院|区)?")
# 楼栋门牌：「3栋2单元501室」「5号楼2层」
_BUILDING_PLATE_RE = re.compile(
    r"(?<!\d)\d{1,3}\s*(?:栋|号楼)\s*\d{0,3}\s*单元?\s*\d{0,4}\s*(?:号|室|楼)?"
)
_DISTRICT_ADDRESS_RE = re.compile(
    r"(?:北京市|天津市|上海市|重庆市|"
    r"[一-龥]{2,8}(?:省|自治区))?"
    r"[一-龥]{2,10}(?:市|区|县)"
    r"[一-龥A-Za-z0-9]{2,24}(?:小区|花园|家园|公寓|社区|村|镇)"
)
_COMMUNITY_ADDRESS_RE = re.compile(
    r"[一-龥A-Za-z0-9]{2,20}(?:小区|花园|家园|公寓|社区)"
    r"(?:\s*\d{1,3}\s*(?:栋|号楼))?"
    r"(?:\s*\d{1,3}\s*单元)?"
    r"(?:\s*\d{1,4}\s*室)?"
)
_LOCAL_MEDIA_PATH_RE = re.compile(
    r"(?:^|\s)(?:/|[A-Za-z]:[\\/])[^\s]{0,160}"
    r"(?:camera|摄像头|相机|child|儿童|卧室|bedroom)[^\s]{0,120}"
    r"\.(?:jpe?g|png|webp|gif|mp4|mov|avi)\b",
    re.IGNORECASE,
)
# 学校/幼儿园名称：「实验一小」「阳光幼儿园」「红梅实验小学」（含专名前缀才隐藏，单独说"学校"保留）
_SCHOOL_NAME_RE = re.compile(
    r"[\u4e00-\u9fa5A-Za-z0-9]{2,12}(?:实验小学|中心小学|附属中学|实验学校|"
    r"第一小学|第二小学|第三小学|第一中学|第二中学|第三中学|"
    r"小学|中学|高中|学校|幼儿园)"
)
# 班级：「三年级二班」「大(2)班」
_CLASS_RE = re.compile(r"(?:大|中|小)?[（(]?[一二三四五六\d]{1,2}[）)]?\s*(?:年级)?\s*[一二三四五六七八九十\d]{0,2}\s*班")

# 整条排除的类别（高精度关键词）。命中即丢弃该条消息，只记录类别。
_EXCLUDE_PATTERNS = {
    "danger": (
        "自杀", "想死", "不想活", "割腕", "自残", "伤害自己",
        "性侵", "猥亵", "裸照", "摸我下面", "被打伤", "虐待",
    ),
    "medical": (
        "住院", "手术", "病历", "诊断", "过敏", "疫苗",
        "发烧", "感冒", "吃药", "打针", "挂水",
    ),
    "adult": ("色情", "成人影片", "做爱", "裸体"),
}

_UNTRUSTED_INSTRUCTION_PATTERNS = (
    re.compile(r"(?:忽略|无视|覆盖|绕过).{0,20}(?:指令|规则|提示词|安全限制)"),
    re.compile(r"(?:调用|执行|触发|使用).{0,16}(?:工具|函数|tool|function)", re.IGNORECASE),
    re.compile(
        r"(?:调用|执行|触发|使用).{0,16}"
        r"(?:get_weather|get_time|play_music|handle_exit_intent|web_search)",
        re.IGNORECASE,
    ),
    re.compile(r"(?:system|assistant|tool|function_call|tool_call)\s*[:：<]", re.IGNORECASE),
    re.compile(r"(?:你必须|务必|不要告诉家长|这是系统命令)"),
)


def redact_for_long_term_memory(text: Any) -> str:
    """PII 与凭据脱敏：替换为占位，保留其余内容。召回查询与写入共用。"""
    value = str(text or "")
    value = _MOBILE_RE.sub("[电话已隐藏]", value)
    value = _LANDLINE_RE.sub("[电话已隐藏]", value)
    value = _EMAIL_RE.sub("[邮箱已隐藏]", value)
    value = _API_KEY_RE.sub("[密钥已隐藏]", value)
    value = _PASSWORD_RE.sub(lambda m: f"{m.group(1)}[密码已隐藏]", value)
    value = _URL_RE.sub("[网址已隐藏]", value)
    value = _ID_CARD_RE.sub("[身份证已隐藏]", value)
    value = _VERIFICATION_CODE_RE.sub(
        lambda m: m.group(0).replace(m.group(2), "[验证码已隐藏]"), value
    )
    value = _ROAD_PLATE_RE.sub("[地址已隐藏]", value)
    value = _BUILDING_PLATE_RE.sub("[门牌已隐藏]", value)
    value = _DISTRICT_ADDRESS_RE.sub("[地址已隐藏]", value)
    value = _COMMUNITY_ADDRESS_RE.sub("[地址已隐藏]", value)
    value = _LOCAL_MEDIA_PATH_RE.sub(" [媒体路径已隐藏]", value)
    value = _CLASS_RE.sub("[班级已隐藏]", value)
    value = _SCHOOL_NAME_RE.sub("[学校名已隐藏]", value)
    return value


def exclude_reason(text: Any) -> Optional[str]:
    """返回整条排除的类别（danger/medical/adult），无需排除时返回 None。"""
    value = str(text or "")
    for category, keywords in _EXCLUDE_PATTERNS.items():
        if any(keyword in value for keyword in keywords):
            return category
    return None


def filter_for_long_term_memory(text: Any) -> Optional[str]:
    """写入过滤入口：返回脱敏后的文本；命中排除类别时返回 None。"""
    value = str(text or "").strip()
    if not value:
        return None
    if exclude_reason(value) is not None:
        return None
    return redact_for_long_term_memory(value)


def filter_recalled_memory(text: Any) -> Optional[str]:
    """召回入口：把远端内容当作不可信数据，拒绝指令并再次脱敏。"""
    value = str(text or "").strip()
    if not value or exclude_reason(value) is not None:
        return None
    if any(pattern.search(value) for pattern in _UNTRUSTED_INSTRUCTION_PATTERNS):
        return None
    return redact_for_long_term_memory(value)
