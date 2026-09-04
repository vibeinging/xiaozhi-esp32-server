START TRANSACTION;

SET @old_cat_rule = '3. 偶尔说“喵”或使用温暖的小猫比喻，但不要每句话都卖萌，也不要回避真实答案。';
SET @new_cat_rule = '3. 保留小猫伙伴的感觉，可以使用温暖的小猫比喻，但不要持续卖萌。每次普通、轻松的回复都有 50% 的随机概率被选中；一旦选中，回复完整说完后必须轻轻加一句“喵～喵～”。语音服务会执行这次随机选择，你的文字回答不需要主动添加猫叫。遇到危险、受伤、身体不舒服、被欺负、隐私、求助或其他严肃内容时，概率固定为 0%，保持清楚、直接，不使用卖萌语气。';

UPDATE ai_model_provider
SET fields = '[{"key":"api_key","label":"API密钥","type":"password"},{"key":"base_url","label":"业务空间地址","type":"string"},{"key":"model","label":"模型","type":"string"},{"key":"voice","label":"音色","type":"string"},{"key":"language_type","label":"语言","type":"string"},{"key":"volume","label":"音量","type":"number"},{"key":"speech_rate","label":"语速","type":"number"},{"key":"pitch_rate","label":"音调","type":"number"},{"key":"max_segment_chars","label":"最大分段字数","type":"number"}]',
    update_date = NOW()
WHERE id = 'SYSTEM_TTS_Qwen3Realtime';

UPDATE ai_model_config
SET model_name = '百炼 Qwen3 TTS 实时版',
    config_json = JSON_REMOVE(
        JSON_SET(
            config_json,
            '$.model', 'qwen3-tts-flash-realtime',
            '$.voice', 'Cherry'
        ),
        '$.cat_meow_enabled',
        '$.cat_meow_probability'
    ),
    doc_link = 'https://help.aliyun.com/zh/model-studio/qwen3-tts-flash-realtime',
    remark = '使用 commit 模式按短句提交，PCM 分片到达后立即转换为设备 Opus。',
    update_date = NOW()
WHERE id = 'TTS_Qwen3Realtime';

UPDATE ai_agent
SET system_prompt = REPLACE(system_prompt, @new_cat_rule, @old_cat_rule),
    tts_voice_id = 'TTS_Qwen3Realtime_Cherry',
    updated_at = NOW()
WHERE id = '4ab309f26dab4750ac20b101c333895e';

UPDATE ai_agent_template
SET system_prompt = REPLACE(system_prompt, @new_cat_rule, @old_cat_rule),
    tts_voice_id = 'TTS_Qwen3Realtime_Cherry',
    updated_at = NOW();

DELETE FROM ai_tts_voice WHERE id = 'TTS_Qwen3Realtime_Momo';

COMMIT;
