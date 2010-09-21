-- helper to clean up before a migration
BEGIN;
set foreign_key_checks = 0;
truncate table wiki_document;
truncate table wiki_revision;
truncate table wiki_firefoxversion;
truncate table wiki_operatingsystem;
set foreign_key_checks = 1;
COMMIT;
