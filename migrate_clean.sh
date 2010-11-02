# Helper script to run a migration
# Just run ./migrate_clean.sh database [verbosity]
before="$(date +%s)"
case $2 in
[0-3]*)
    echo Chosen verbosity: $2
    mysql $1 < clean_up.sql && ./manage.py migrate_kb --verbosity $2
    ;;
*)
    echo Using default verbosity: 2
    mysql $1 < clean_up.sql && ./manage.py migrate_kb --verbosity 2
    ;;
esac
after="$(date +%s)"
elapsed_seconds="$(expr $after - $before)"
echo Done in $elapsed_seconds seconds.
