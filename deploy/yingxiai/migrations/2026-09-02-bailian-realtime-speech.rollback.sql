START TRANSACTION;

UPDATE ai_model_config
SET is_default = CASE WHEN id = 'ASR_Qwen3Flash' THEN 1 ELSE 0 END
WHERE model_type = 'ASR';

UPDATE ai_model_config
SET is_default = CASE WHEN id = 'TTS_EdgeTTS' THEN 1 ELSE 0 END
WHERE model_type = 'TTS';

UPDATE ai_agent
SET asr_model_id = 'ASR_Qwen3Flash',
    tts_model_id = 'TTS_EdgeTTS',
    tts_voice_id = 'TTS_EdgeTTS0008',
    updated_at = NOW()
WHERE id = '4ab309f26dab4750ac20b101c333895e';

UPDATE ai_agent_template
SET asr_model_id = 'ASR_Qwen3Flash',
    tts_model_id = 'TTS_EdgeTTS',
    tts_voice_id = 'TTS_EdgeTTS0001',
    updated_at = NOW();

COMMIT;
