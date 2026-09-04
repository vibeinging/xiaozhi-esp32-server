ALTER TABLE ai_agent_chat_history
ADD INDEX idx_ai_agent_chat_history_agent_created (agent_id, created_at);
