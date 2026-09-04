-- 增加 MemMe 本地长期记忆。user_id 和 agent_id 不在这里配置，
-- ConfigService 会按当前账号和智能体注入稳定身份。

DELETE FROM `ai_model_provider` WHERE `id` = 'SYSTEM_Memory_memme';
DELETE FROM `ai_model_config` WHERE `id` = 'Memory_memme';

INSERT INTO `ai_model_provider` (
  `id`, `model_type`, `provider_code`, `name`, `fields`, `sort`,
  `creator`, `create_date`, `updater`, `update_date`
) VALUES (
  'SYSTEM_Memory_memme',
  'Memory',
  'memme',
  'MemMe 本地长期记忆',
  '[{"key":"base_url","label":"MemMe 服务地址","type":"text"},{"key":"api_key","label":"服务密钥（建议填 ${MEMME_API_KEY}）","type":"password"},{"key":"app_id","label":"应用标识","type":"text"},{"key":"queue_path","label":"本地重试队列路径","type":"text"}]',
  5, 1, NOW(), 1, NOW()
);

INSERT INTO `ai_model_config` (
  `id`, `model_type`, `model_code`, `model_name`, `is_default`, `is_enabled`,
  `config_json`, `doc_link`, `remark`, `sort`, `updater`, `update_date`,
  `creator`, `create_date`
) VALUES (
  'Memory_memme',
  'Memory',
  'memme',
  'MemMe 本地长期记忆',
  0,
  1,
  '{"type":"memme","base_url":"http://127.0.0.1:8080","api_key":"${MEMME_API_KEY}","app_id":"xiaozhi","queue_path":"data/memme-retry.sqlite3","request_timeout_seconds":3,"retry_batch_size":2,"retry_base_seconds":10,"retry_max_seconds":3600,"queue_max_jobs":10000,"queue_max_bytes":268435456,"recall_limit":5,"recall_max_chars":4000,"compact_on_save":false,"include_device_id":false}',
  'https://github.com/vibeinging/MemMe',
  '自托管的 SQLite 长期记忆。账号和智能体身份由服务端自动注入；只需配置服务地址和服务密钥。建议聊天记录选择“仅文字”。',
  5,
  NULL,
  NULL,
  NULL,
  NULL
);
