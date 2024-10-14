#!/bin/bash

set -e  # Exit immediately if a command exits with a non-zero status.

CONTAINER_NAME="valorsdb"
DB_USER="valorsuser"
BACKUP_FILE="valorsdb_backup_$(date +%Y%m%d_%H%M%S).sql"
CONTAINER_BACKUP_PATH="/tmp/$BACKUP_FILE"
LOCAL_BACKUP_PATH="./backups/$BACKUP_FILE"

# Ensure the local backup directory exists
mkdir -p ./backups

echo "Starting backup process..."

# Check if the container is running
if ! docker ps | grep -q $CONTAINER_NAME; then
    echo "Error: Container $CONTAINER_NAME is not running."
    exit 1
fi

# Create the backup
echo "Creating backup in container..."
if ! docker exec -t $CONTAINER_NAME pg_dumpall -c -U $DB_USER > $LOCAL_BACKUP_PATH; then
    echo "Error: Failed to create backup."
    exit 1
fi

echo "Backup created successfully."

# Check if the backup file exists and has content
if [ ! -s "$LOCAL_BACKUP_PATH" ]; then
    echo "Error: Backup file is empty or does not exist."
    exit 1
fi

# Compress the backup file
echo "Compressing backup file..."
gzip $LOCAL_BACKUP_PATH

echo "Backup completed and fetched locally: ${LOCAL_BACKUP_PATH}.gz"