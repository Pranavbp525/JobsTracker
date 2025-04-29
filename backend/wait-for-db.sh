#!/bin/bash
# wait-for-db.sh

set -e

host="$1"
shift
cmd="$@"

# Use netcat (nc) which we install in the Dockerfile
echo "Waiting for database host $host using netcat..."
until nc -z "$host" 5432; do
  >&2 echo "Postgres is unavailable - sleeping"
  sleep 1
done

>&2 echo "Postgres is up - executing command"
exec $cmd
