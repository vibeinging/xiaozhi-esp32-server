import asyncio
import base64
import mimetypes
import os
from typing import Optional, Tuple, List
import dashscope
import openai
from config.logger import setup_logging
from core.providers.asr.base import ASRProviderBase
from core.providers.asr.dto.dto import InterfaceType

tag = __name__
logger = setup_logging()


class ASRProvider(ASRProviderBase):
    def __init__(self, config: dict, delete_audio_file: bool):
        super().__init__()
        # 音频文件上传类型，流式文本识别输出
        self.interface_type = InterfaceType.NON_STREAM
        """Qwen3-ASR-Flash ASR初始化"""
        
        # 配置参数
        self.api_key = config.get("api_key")
        if not self.api_key:
            raise ValueError("Qwen3-ASR-Flash 需要配置 api_key")
            
        self.model_name = config.get("model_name", "qwen3-asr-flash")
        self.base_url = config.get("base_url")
        self.output_dir = config.get("output_dir", "./audio_output")
        self.delete_audio_file = delete_audio_file
        self.openai_client = None
        if self.base_url:
            self.openai_client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )
        
        # ASR选项配置
        self.enable_lid = config.get("enable_lid", True)  # 自动语种检测
        self.enable_itn = config.get("enable_itn", True)  # 逆文本归一化
        self.language = config.get("language", None)  # 指定语种，默认自动检测
        self.context = config.get("context", "")  # 上下文信息，用于提高识别准确率
        
        # 确保输出目录存在
        os.makedirs(self.output_dir, exist_ok=True)

    def prefers_temp_file(self) -> bool:
        return True

    def requires_file(self) -> bool:
        return True

    async def speech_to_text(
        self, opus_data: List[bytes], session_id: str, artifacts=None
    ) -> Tuple[Optional[str], Optional[str]]:
        """将语音数据转换为文本"""
        temp_file_path = None
        file_path = None
        try:
            if artifacts is None:
                return "", None
            temp_file_path = artifacts.temp_path
            file_path = artifacts.file_path
            if not temp_file_path:
                return "", file_path

            if self.openai_client:
                full_text = await asyncio.to_thread(
                    self._speech_to_text_openai, temp_file_path
                )
                return full_text, file_path

            # 构造请求消息
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"audio": temp_file_path}
                    ]
                }
            ]
            
            # 如果有上下文信息，添加system消息
            if self.context:
                messages.insert(0, {
                    "role": "system", 
                    "content": [
                        {"text": self.context}
                    ]
                })
            
            # 准备ASR选项
            asr_options = {
                "enable_lid": self.enable_lid,
                "enable_itn": self.enable_itn
            }
            
            # 如果指定了语种，添加到选项中
            if self.language:
                asr_options["language"] = self.language
            
            # 设置API密钥
            dashscope.api_key = self.api_key
            
            # 发送流式请求
            response = dashscope.MultiModalConversation.call(
                model=self.model_name,
                messages=messages,
                result_format="message",
                asr_options=asr_options,
                stream=True
            )
            
            # 处理流式响应
            full_text = ""
            for chunk in response:
                try:
                    text = chunk["output"]["choices"][0]["message"].content[0]["text"]
                    # 更新为最新的完整文本
                    full_text = text.strip()
                except:
                    pass
            
            return full_text, file_path
                
        except Exception as e:
            logger.bind(tag=tag).error(f"语音识别失败: {e}")
            return "", file_path

    def _speech_to_text_openai(self, audio_path: str) -> str:
        """通过百炼业务空间的 OpenAI 兼容接口识别音频。"""
        mime_type = mimetypes.guess_type(audio_path)[0] or "audio/wav"
        with open(audio_path, "rb") as audio_file:
            audio_base64 = base64.b64encode(audio_file.read()).decode("ascii")
        audio_data_uri = f"data:{mime_type};base64,{audio_base64}"

        messages = []
        if self.context:
            messages.append({"role": "system", "content": self.context})
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_data_uri},
                    }
                ],
            }
        )

        asr_options = {"enable_itn": self.enable_itn}
        if self.language:
            asr_options["language"] = self.language

        response = self.openai_client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            stream=False,
            extra_body={"asr_options": asr_options},
        )
        content = response.choices[0].message.content
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict)
            ).strip()
        return str(content or "").strip()
