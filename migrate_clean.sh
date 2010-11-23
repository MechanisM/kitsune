# Helper script to run a migration
# Just run ./migrate_clean.sh database [verbosity]
before="$(date +%s)"

DB=$1

case $2 in
[0-3]*)
    VERBOSITY=$2
    ;;
*)
    echo Using default verbosity: 2
    VERBOSITY=2
    ;;
esac

echo "Migrating videos and images first..."
./manage.py migrate_images --verbosity ${VERBOSITY} all
./manage.py migrate_videos --verbosity ${VERBOSITY} all

mysql ${DB} < clean_up.sql && ./manage.py migrate_kb --verbosity ${VERBOSITY}

echo "Re-rendering everything..."
./manage.py cron rebuild_kb

after="$(date +%s)"
elapsed_seconds="$(expr $after - $before)"
echo Done in $elapsed_seconds seconds.
echo "Don't forget to generate thumbnails for videos."
