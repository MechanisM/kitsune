# Usage:
# ./migration_helper.sh <stage db (with wiki tables)> <migration db> <import tiki>

DB_STAGE="$1"
DB_MIGRATION="$2"

echo "Dumping skeleton from ${DB_STAGE} to wiki_tables.sql..."
mysqldump ${DB_STAGE} --no-data=TRUE wiki_document wiki_revision wiki_firefoxversion wiki_operatingsystem wiki_relateddocument wiki_helpfulvote gallery_image gallery_video > wiki_tables.sql

echo "Cleaning up AUTO_INCREMENT= stuff into wiki_tables_no_auto.sql..."
cat wiki_tables.sql | sed s/AUTO_INCREMENT=[0-9]*// > wiki_tables_no_auto.sql

echo "Importing skeleton to ${DB_MIGRATION}..."
mysql ${DB_MIGRATION} < wiki_tables_no_auto.sql

if [ "$3" ]; then
    echo "Dumping TikiWiki data from ${DB_STAGE} to wiki_data.sql..."
    mysqldump ${DB_STAGE} tiki_pages tiki_category_objects tiki_objects tiki_translated_objects tiki_content tiki_programmed_content tiki_freetagged_objects django_content_type auth_user > wiki_data.sql

    echo "Importing TikiWiki data to ${DB_MIGRATION}..."
    mysql ${DB_MIGRATION} < wiki_data.sql

    echo "Running prep for migration on ${DB_MIGRATION}..."
    mysql ${DB_MIGRATION} < migrations/66-migration-kb.sql
fi

echo "Removing traces..."
rm wiki_tables.sql
rm wiki_tables_no_auto.sql
if [ "$3" ]; then
    rm wiki_data.sql
fi
