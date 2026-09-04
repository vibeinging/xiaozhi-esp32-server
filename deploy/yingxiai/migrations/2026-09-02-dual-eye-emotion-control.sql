START TRANSACTION;

SET @eye_rule = '【眼睛表情】\n每次回复的第一个字符必须是一个情绪符号，而且只能从下面选择一个。这个符号只控制玩偶的眼睛，不会被朗读：\n😶平静、🙂开心、😆大笑、🤩兴奋或星星眼、😍喜欢、😔难过、😭哭泣、😠生气、😲惊讶、🤔思考、😴困倦、🙄疑惑、😳害羞、😎自信。\n符号要符合当下内容。普通说明不确定时用😶，不要总用🙂。危险、受伤、身体不舒服、被欺负、隐私或求助等严肃内容，只能用😶或😔，不能使用搞笑、兴奋或卖萌表情。情绪符号之后直接说正文，不要解释符号，也不要再添加第二个表情符号。';

UPDATE ai_agent
SET system_prompt = CONCAT(system_prompt, '\n\n', @eye_rule),
    updated_at = NOW()
WHERE id = '4ab309f26dab4750ac20b101c333895e'
  AND system_prompt NOT LIKE '%【眼睛表情】%';

UPDATE ai_agent_template
SET system_prompt = CONCAT(system_prompt, '\n\n', @eye_rule),
    updated_at = NOW()
WHERE system_prompt NOT LIKE '%【眼睛表情】%';

COMMIT;
