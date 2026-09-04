-- 将儿童陪伴角色和唯一唤醒词统一为“小草莓”。
UPDATE `sys_params`
SET `param_value` = '小草莓'
WHERE `param_code` = 'wakeup_words';

UPDATE `ai_agent`
SET
  `agent_name` = '小草莓',
  `system_prompt` = REPLACE(
    REPLACE(`system_prompt`, '蓝色眼睛', '宝石绿色眼睛'),
    '小布一下',
    '小草莓一下'
  )
WHERE `system_prompt` LIKE '%[CHILD_SAFETY_PROFILE:v1]%';

UPDATE `ai_agent_template`
SET
  `agent_name` = '小草莓',
  `system_prompt` = REPLACE(
    REPLACE(`system_prompt`, '蓝色眼睛', '宝石绿色眼睛'),
    '小布一下',
    '小草莓一下'
  )
WHERE `system_prompt` LIKE '%[CHILD_SAFETY_PROFILE:v1]%';
