START TRANSACTION;

UPDATE ai_model_config
SET model_name = '百炼 Qwen3 TTS 实时温柔音色',
    config_json = JSON_SET(
        config_json,
        '$.model', 'qwen3-tts-flash-realtime',
        '$.voice', 'Serena',
        '$.cat_meow_enabled', TRUE,
        '$.cat_meow_probability', 0.5
    ),
    doc_link = 'https://help.aliyun.com/zh/model-studio/qwen3-tts-flash-realtime',
    remark = '使用 Serena 音色塑造温柔、自然的布偶猫陪伴声音；普通轻松回复按 50% 概率追加猫叫。',
    update_date = NOW()
WHERE id = 'TTS_Qwen3Realtime';

INSERT INTO ai_tts_voice (
    id, tts_model_id, name, tts_voice, languages, voice_demo,
    remark, sort, creator, create_date, updater, update_date
) VALUES (
    'TTS_Qwen3Realtime_Serena',
    'TTS_Qwen3Realtime',
    'Serena-温柔布偶猫陪伴',
    'Serena',
    '中文及中英文混合',
    NULL,
    '用于小布的温柔、自然、不刻意撒娇的陪伴语气',
    1, 1, NOW(), 1, NOW()
)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    tts_voice = VALUES(tts_voice),
    languages = VALUES(languages),
    remark = VALUES(remark),
    sort = VALUES(sort),
    update_date = NOW();

UPDATE ai_agent
SET tts_voice_id = 'TTS_Qwen3Realtime_Serena',
    updated_at = NOW()
WHERE id = '4ab309f26dab4750ac20b101c333895e';

UPDATE ai_agent_template
SET tts_voice_id = 'TTS_Qwen3Realtime_Serena',
    updated_at = NOW()
WHERE tts_model_id = 'TTS_Qwen3Realtime';

COMMIT;
