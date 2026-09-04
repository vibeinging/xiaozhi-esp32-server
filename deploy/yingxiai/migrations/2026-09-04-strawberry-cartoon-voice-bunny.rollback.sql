START TRANSACTION;

UPDATE `ai_model_config`
SET
  `model_name` = '百炼 Qwen3 TTS 实时温柔音色',
  `config_json` = JSON_SET(
    `config_json`,
    '$.model', 'qwen3-tts-flash-realtime',
    '$.voice', 'Serena',
    '$.speech_rate', 1.0,
    '$.pitch_rate', 1.0,
    '$.cat_meow_enabled', TRUE,
    '$.cat_meow_probability', 0.5
  ),
  `doc_link` = 'https://help.aliyun.com/zh/model-studio/qwen-tts-voice-list',
  `remark` = '使用 Serena 音色塑造温柔、自然的布偶猫陪伴声音；普通轻松回复按 50% 概率追加猫叫。',
  `update_date` = NOW()
WHERE `id` = 'TTS_Qwen3Realtime';

UPDATE `ai_agent`
SET
  `tts_voice_id` = 'TTS_Qwen3Realtime_Serena',
  `updated_at` = NOW()
WHERE `tts_voice_id` = 'TTS_Qwen3Realtime_Bunny';

UPDATE `ai_agent_template`
SET
  `tts_voice_id` = 'TTS_Qwen3Realtime_Serena',
  `updated_at` = NOW()
WHERE `tts_voice_id` = 'TTS_Qwen3Realtime_Bunny';

DELETE FROM `ai_tts_voice`
WHERE `id` = 'TTS_Qwen3Realtime_Bunny';

COMMIT;
