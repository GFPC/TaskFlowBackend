-- =============================================================================
-- Миграция таблицы users: Telegram -> email-верификация (MySQL / MariaDB)
-- Сделайте бэкап БД перед запуском: mysqldump ...
-- Выполняйте в клиенте MySQL по шагам; при ошибке "Duplicate column" — шаг уже был.
-- =============================================================================

-- Шаг 1: новые колонки (обязательно для текущего кода приложения)
ALTER TABLE `users`
  ADD COLUMN `email_verified` TINYINT(1) NOT NULL DEFAULT 0 AFTER `email`,
  ADD COLUMN `email_code` VARCHAR(6) NULL DEFAULT NULL,
  ADD COLUMN `email_code_expires` DATETIME NULL DEFAULT NULL,
  ADD COLUMN `email_code_attempts` INT NOT NULL DEFAULT 0;

-- Шаг 2: перенести флаг верификации со старых полей (если колонки tg_* ещё есть)
-- Раскомментируйте, если в таблице есть tg_verified:
-- UPDATE `users` SET `email_verified` = IFNULL(`tg_verified`, 0);

-- Шаг 3 (по желанию): удалить старые поля Telegram после проверки приложения
-- Раскомментируйте по одному или все вместе:
-- ALTER TABLE `users` DROP COLUMN `tg_username`;
-- ALTER TABLE `users` DROP COLUMN `tg_id`;
-- ALTER TABLE `users` DROP COLUMN `tg_chat_id`;
-- ALTER TABLE `users` DROP COLUMN `tg_code`;
-- ALTER TABLE `users` DROP COLUMN `tg_code_expires`;
-- ALTER TABLE `users` DROP COLUMN `tg_code_attempts`;
-- ALTER TABLE `users` DROP COLUMN `tg_verified`;

-- =============================================================================
-- Если Шаг 1 уже частично применён и падает на дубликате колонки — добавьте
-- только недостающие колонки вручную, например:
-- ALTER TABLE `users` ADD COLUMN `email_verified` TINYINT(1) NOT NULL DEFAULT 0 AFTER `email`;
-- =============================================================================
