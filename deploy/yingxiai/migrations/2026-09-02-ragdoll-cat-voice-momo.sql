START TRANSACTION;

SET @old_cat_rule = '3. 偶尔说“喵”或使用温暖的小猫比喻，但不要每句话都卖萌，也不要回避真实答案。';
SET @new_cat_rule = '3. 保留小猫伙伴的感觉，可以使用温暖的小猫比喻，但不要持续卖萌。每次普通、轻松的回复都有 50% 的随机概率被选中；一旦选中，回复完整说完后必须轻轻加一句“喵～喵～”。语音服务会执行这次随机选择，你的文字回答不需要主动添加猫叫。遇到危险、受伤、身体不舒服、被欺负、隐私、求助或其他严肃内容时，概率固定为 0%，保持清楚、直接，不使用卖萌语气。';

UPDATE ai_model_provider
SET fields = '[{"key":"api_key","label":"API密钥","type":"password"},{"key":"base_url","label":"业务空间地址","type":"string"},{"key":"model","label":"模型","type":"string"},{"key":"voice","label":"音色","type":"string"},{"key":"language_type","label":"语言","type":"string"},{"key":"volume","label":"音量","type":"number"},{"key":"speech_rate","label":"语速","type":"number"},{"key":"pitch_rate","label":"音调","type":"number"},{"key":"cat_meow_enabled","label":"启用随机猫叫","type":"boolean"},{"key":"cat_meow_probability","label":"猫叫概率","type":"number"},{"key":"max_segment_chars","label":"最大分段字数","type":"number"}]',
    update_date = NOW()
WHERE id = 'SYSTEM_TTS_Qwen3Realtime';

UPDATE ai_model_config
SET model_name = '百炼 Qwen3 TTS 实时布偶猫音色',
    config_json = JSON_SET(
        config_json,
        '$.model', 'qwen3-tts-flash-realtime',
        '$.voice', 'Momo',
        '$.cat_meow_enabled', TRUE,
        '$.cat_meow_probability', 0.5
    ),
    doc_link = 'https://help.aliyun.com/zh/model-studio/qwen3-tts-flash-realtime',
    remark = '使用 Momo 音色塑造轻柔、俏皮的布偶猫伙伴声音；普通轻松回复按 50% 概率追加猫叫。',
    update_date = NOW()
WHERE id = 'TTS_Qwen3Realtime';

INSERT INTO ai_tts_voice (
    id, tts_model_id, name, tts_voice, languages, voice_demo,
    remark, sort, creator, create_date, updater, update_date
) VALUES (
    'TTS_Qwen3Realtime_Momo',
    'TTS_Qwen3Realtime',
    'Momo-轻柔布偶猫伙伴',
    'Momo',
    '中文及中英文混合',
    NULL,
    '用于小布的轻柔、温暖、俏皮宠物语气',
    2, 1, NOW(), 1, NOW()
)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    tts_voice = VALUES(tts_voice),
    languages = VALUES(languages),
    remark = VALUES(remark),
    update_date = NOW();

UPDATE ai_agent
SET system_prompt = REPLACE(system_prompt, @old_cat_rule, @new_cat_rule),
    tts_voice_id = 'TTS_Qwen3Realtime_Momo',
    updated_at = NOW()
WHERE id = '4ab309f26dab4750ac20b101c333895e';

UPDATE ai_agent_template
SET system_prompt = REPLACE(system_prompt, @old_cat_rule, @new_cat_rule),
    tts_voice_id = 'TTS_Qwen3Realtime_Momo',
    updated_at = NOW();

COMMIT;
