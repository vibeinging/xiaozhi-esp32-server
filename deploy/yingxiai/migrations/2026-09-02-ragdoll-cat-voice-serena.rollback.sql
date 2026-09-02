START TRANSACTION;

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

UPDATE ai_agent
SET tts_voice_id = 'TTS_Qwen3Realtime_Momo',
    updated_at = NOW()
WHERE id = '4ab309f26dab4750ac20b101c333895e';

UPDATE ai_agent_template
SET tts_voice_id = 'TTS_Qwen3Realtime_Momo',
    updated_at = NOW()
WHERE tts_model_id = 'TTS_Qwen3Realtime';

DELETE FROM ai_tts_voice WHERE id = 'TTS_Qwen3Realtime_Serena';

COMMIT;
