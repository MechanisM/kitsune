# Usage:
# ./migration_helper.sh <stage db (with wiki tables)> <migration db>

DB_STAGE="$1"
DB_MIGRATION="$2"

echo "Dumping skeleton from ${DB_STAGE}..."
mysqldump ${DB_STAGE} --no-data=TRUE wiki_document wiki_revision wiki_firefoxversion wiki_operatingsystem wiki_relateddocument wiki_helpfulvote gallery_image gallery_video > wiki_tables.sql

echo "Cleaning up AUTO_INCREMENT= stuff..."
cat wiki_tables.sql | sed s/AUTO_INCREMENT=[0-9]*// > wiki_tables.sql

echo "Importing skeleton to ${DB_MIGRATION}..."
mysql ${DB_MIGRATION} < wiki_tables.sql

echo "Removing traces..."
rm wiki_tables.sql

echo "Don't forget to run migration-specific migration on ${DB_MIGRATION}..."
echo "mysql ${DB_MIGRATION} < migrations/66-migration-kb.sql"

