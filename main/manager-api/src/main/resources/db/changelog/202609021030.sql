-- liquibase formatted sql

-- changeset vibeinging:202609021030
UPDATE `sys_params`
SET `param_value` = REPLACE(`param_value`, '喵喵同学', '小布布')
WHERE `param_code` = 'wakeup_words';

-- rollback UPDATE `sys_params` SET `param_value` = REPLACE(`param_value`, '小布布', '喵喵同学') WHERE `param_code` = 'wakeup_words';
