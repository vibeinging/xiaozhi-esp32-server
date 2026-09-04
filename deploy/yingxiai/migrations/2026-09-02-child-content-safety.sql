START TRANSACTION;

SET @child_safety_marker = '[CHILD_SAFETY_PROFILE:v1]';

UPDATE ai_agent
SET system_prompt = CONCAT(@child_safety_marker, '\n', system_prompt),
    updated_at = NOW()
WHERE id = '4ab309f26dab4750ac20b101c333895e'
  AND LOCATE(
    CAST(@child_safety_marker AS BINARY),
    CAST(system_prompt AS BINARY)
  ) = 0;

DELETE FROM ai_agent_plugin_mapping
WHERE agent_id = '4ab309f26dab4750ac20b101c333895e'
  AND plugin_id = 'SYSTEM_PLUGIN_NEWS_NEWSNOW';

COMMIT;
