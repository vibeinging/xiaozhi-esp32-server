START TRANSACTION;

INSERT INTO ai_model_provider (
    id, model_type, provider_code, name, fields, sort,
    creator, create_date, updater, update_date
) VALUES (
    'SYSTEM_ASR_Qwen3Realtime',
    'ASR',
    'qwen3_asr_realtime',
    '百炼 Qwen3 实时语音识别',
    '[{"key":"api_key","label":"API密钥","type":"password"},{"key":"base_url","label":"业务空间地址","type":"string"},{"key":"model","label":"模型","type":"string"},{"key":"sample_rate","label":"采样率","type":"number"},{"key":"language","label":"语言","type":"string"},{"key":"output_dir","label":"输出目录","type":"string"}]',
    1, 1, NOW(), 1, NOW()
)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    fields = VALUES(fields),
    update_date = NOW();

INSERT IGNORE INTO ai_model_config (
    id, model_type, model_code, model_name, is_default, is_enabled,
    config_json, doc_link, remark, sort,
    creator, create_date, updater, update_date
) VALUES (
    'ASR_Qwen3Realtime',
    'ASR',
    'Qwen3Realtime',
    '百炼 Qwen3 ASR 实时版',
    0,
    1,
    '{"type":"qwen3_asr_realtime","api_key":"","base_url":"https://dashscope.aliyuncs.com/compatible-mode/v1","model":"qwen3-asr-flash-realtime-2026-02-10","sample_rate":16000,"language":"zh","output_dir":"tmp/"}',
    'https://help.aliyun.com/zh/model-studio/qwen-asr-realtime-interaction-process',
    '设备 PCM 音频边说边上传；本地 VAD 判定结束后 commit，收到最终文字后再 finish。',
    1, 1, NOW(), 1, NOW()
);

UPDATE ai_model_config AS target
JOIN ai_model_config AS source ON source.id = 'LLM_AliLLM'
SET target.model_name = '百炼 Qwen3 ASR 实时版',
    target.is_enabled = 1,
    target.config_json = JSON_SET(
        target.config_json,
        '$.type', 'qwen3_asr_realtime',
        '$.api_key', JSON_UNQUOTE(JSON_EXTRACT(source.config_json, '$.api_key')),
        '$.base_url', JSON_UNQUOTE(JSON_EXTRACT(source.config_json, '$.base_url')),
        '$.model', 'qwen3-asr-flash-realtime-2026-02-10',
        '$.sample_rate', 16000,
        '$.language', 'zh',
        '$.output_dir', 'tmp/'
    ),
    target.update_date = NOW()
WHERE target.id = 'ASR_Qwen3Realtime';

INSERT INTO ai_model_provider (
    id, model_type, provider_code, name, fields, sort,
    creator, create_date, updater, update_date
) VALUES (
    'SYSTEM_TTS_Qwen3Realtime',
    'TTS',
    'qwen3_tts_realtime',
    '百炼 Qwen3 实时语音合成',
    '[{"key":"api_key","label":"API密钥","type":"password"},{"key":"base_url","label":"业务空间地址","type":"string"},{"key":"model","label":"模型","type":"string"},{"key":"voice","label":"音色","type":"string"},{"key":"language_type","label":"语言","type":"string"},{"key":"volume","label":"音量","type":"number"},{"key":"speech_rate","label":"语速","type":"number"},{"key":"pitch_rate","label":"音调","type":"number"},{"key":"cat_meow_enabled","label":"启用随机猫叫","type":"boolean"},{"key":"cat_meow_probability","label":"猫叫概率","type":"number"},{"key":"max_segment_chars","label":"最大分段字数","type":"number"}]',
    1, 1, NOW(), 1, NOW()
)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    fields = VALUES(fields),
    update_date = NOW();

INSERT IGNORE INTO ai_model_config (
    id, model_type, model_code, model_name, is_default, is_enabled,
    config_json, doc_link, remark, sort,
    creator, create_date, updater, update_date
) VALUES (
    'TTS_Qwen3Realtime',
    'TTS',
    'Qwen3Realtime',
    '百炼 Qwen3 TTS 实时版',
    0,
    1,
    '{"type":"qwen3_tts_realtime","api_key":"","base_url":"https://dashscope.aliyuncs.com/compatible-mode/v1","model":"qwen3-tts-flash-realtime","voice":"Momo","language_type":"Chinese","volume":50,"speech_rate":1.0,"pitch_rate":1.0,"cat_meow_enabled":true,"cat_meow_probability":0.5,"max_segment_chars":18,"output_dir":"tmp/"}',
    'https://help.aliyun.com/zh/model-studio/qwen3-tts-flash-realtime',
    '使用 Momo 音色塑造轻柔、俏皮的布偶猫伙伴声音；PCM 分片立即转换为设备 Opus。',
    1, 1, NOW(), 1, NOW()
);

UPDATE ai_model_config AS target
JOIN ai_model_config AS source ON source.id = 'LLM_AliLLM'
SET target.model_name = '百炼 Qwen3 TTS 实时版',
    target.is_enabled = 1,
    target.config_json = JSON_SET(
        target.config_json,
        '$.type', 'qwen3_tts_realtime',
        '$.api_key', JSON_UNQUOTE(JSON_EXTRACT(source.config_json, '$.api_key')),
        '$.base_url', JSON_UNQUOTE(JSON_EXTRACT(source.config_json, '$.base_url')),
        '$.model', 'qwen3-tts-flash-realtime',
        '$.voice', 'Momo',
        '$.language_type', 'Chinese',
        '$.volume', 50,
        '$.speech_rate', 1.0,
        '$.pitch_rate', 1.0,
        '$.cat_meow_enabled', TRUE,
        '$.cat_meow_probability', 0.5,
        '$.max_segment_chars', 18,
        '$.output_dir', 'tmp/'
    ),
    target.update_date = NOW()
WHERE target.id = 'TTS_Qwen3Realtime';

INSERT INTO ai_tts_voice (
    id, tts_model_id, name, tts_voice, languages, voice_demo,
    remark, sort, creator, create_date, updater, update_date
) VALUES (
    'TTS_Qwen3Realtime_Cherry',
    'TTS_Qwen3Realtime',
    'Cherry-温暖活泼女声',
    'Cherry',
    '中文及中英文混合',
    NULL,
    '适合小布的温暖、活泼陪伴语气',
    1, 1, NOW(), 1, NOW()
)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    tts_voice = VALUES(tts_voice),
    languages = VALUES(languages),
    remark = VALUES(remark),
    update_date = NOW();

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

UPDATE ai_model_config
SET is_default = CASE WHEN id = 'ASR_Qwen3Realtime' THEN 1 ELSE 0 END
WHERE model_type = 'ASR';

UPDATE ai_model_config
SET is_default = CASE WHEN id = 'TTS_Qwen3Realtime' THEN 1 ELSE 0 END
WHERE model_type = 'TTS';

UPDATE ai_agent
SET asr_model_id = 'ASR_Qwen3Realtime',
    tts_model_id = 'TTS_Qwen3Realtime',
    tts_voice_id = 'TTS_Qwen3Realtime_Momo',
    updated_at = NOW()
WHERE id = '4ab309f26dab4750ac20b101c333895e';

UPDATE ai_agent_template
SET asr_model_id = 'ASR_Qwen3Realtime',
    tts_model_id = 'TTS_Qwen3Realtime',
    tts_voice_id = 'TTS_Qwen3Realtime_Momo',
    updated_at = NOW();

COMMIT;
