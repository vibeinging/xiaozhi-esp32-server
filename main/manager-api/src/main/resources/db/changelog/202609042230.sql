-- 将小草莓的语音改为低延迟卡通小猫音色。
UPDATE `ai_model_config`
SET
  `model_name` = '百炼 Qwen3 TTS 实时卡通小猫音色',
  `config_json` = JSON_SET(
    `config_json`,
    '$.model', 'qwen3-tts-flash-realtime',
    '$.voice', 'Bunny',
    '$.speech_rate', 1.0,
    '$.pitch_rate', 1.0,
    '$.cat_meow_enabled', TRUE,
    '$.cat_meow_probability', 0.5
  ),
  `doc_link` = 'https://help.aliyun.com/zh/model-studio/qwen-tts-voice-list',
  `remark` = '使用 Bunny 卡通萌系女声塑造小草莓的小猫伙伴声音；保持正常语速和音调，普通轻松回复按 50% 概率追加猫叫。',
  `update_date` = NOW()
WHERE `id` = 'TTS_Qwen3Realtime';

INSERT INTO `ai_tts_voice` (
  `id`, `tts_model_id`, `name`, `tts_voice`, `languages`, `voice_demo`,
  `remark`, `sort`, `creator`, `create_date`, `updater`, `update_date`
) VALUES (
  'TTS_Qwen3Realtime_Bunny',
  'TTS_Qwen3Realtime',
  'Bunny-卡通小猫伙伴',
  'Bunny',
  '中文及中英文混合',
  NULL,
  '用于小草莓的萌系、友好、不刻意撒娇的卡通小猫语气',
  1, 1, NOW(), 1, NOW()
)
ON DUPLICATE KEY UPDATE
  `name` = VALUES(`name`),
  `tts_voice` = VALUES(`tts_voice`),
  `languages` = VALUES(`languages`),
  `remark` = VALUES(`remark`),
  `sort` = VALUES(`sort`),
  `update_date` = NOW();

UPDATE `ai_agent`
SET
  `tts_voice_id` = 'TTS_Qwen3Realtime_Bunny',
  `updated_at` = NOW()
WHERE `system_prompt` LIKE '%[CHILD_SAFETY_PROFILE:v1]%'
  AND `tts_model_id` = 'TTS_Qwen3Realtime';

UPDATE `ai_agent_template`
SET
  `tts_voice_id` = 'TTS_Qwen3Realtime_Bunny',
  `updated_at` = NOW()
WHERE `system_prompt` LIKE '%[CHILD_SAFETY_PROFILE:v1]%'
  AND `tts_model_id` = 'TTS_Qwen3Realtime';
