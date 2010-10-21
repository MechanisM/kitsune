# Helper script to run a migration
# Just run ./migrate_clean.sh [$verbosity]
before="$(date +%s)"
case $1 in
[0-3]*)
    echo Chosen verbosity: $1
    mysql k_10_18 < clean_up.sql && ./manage.py migrate_kb --verbosity $1
    ;;
*)
    echo Using default verbosity: 2
    mysql k_10_18 < clean_up.sql && ./manage.py migrate_kb --verbosity 2
    ;;
esac
after="$(date +%s)"
elapsed_seconds="$(expr $after - $before)"
echo Done in $elapsed_seconds seconds.
