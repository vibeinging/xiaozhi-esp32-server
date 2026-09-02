START TRANSACTION;

SET @child_safety_marker = '[CHILD_SAFETY_PROFILE:v1]\n';

UPDATE ai_agent
SET system_prompt = SUBSTRING(
      system_prompt,
      CHAR_LENGTH(@child_safety_marker) + 1
    ),
    updated_at = NOW()
WHERE id = '4ab309f26dab4750ac20b101c333895e'
  AND LEFT(
    CAST(system_prompt AS BINARY),
    OCTET_LENGTH(@child_safety_marker)
  ) = CAST(@child_safety_marker AS BINARY);

INSERT INTO ai_agent_plugin_mapping (agent_id, plugin_id, param_info)
VALUES (
    '4ab309f26dab4750ac20b101c333895e',
    'SYSTEM_PLUGIN_NEWS_NEWSNOW',
    JSON_OBJECT('url', 'https://newsnow.busiyi.world/api/s?id=')
)
ON DUPLICATE KEY UPDATE param_info = VALUES(param_info);

COMMIT;
