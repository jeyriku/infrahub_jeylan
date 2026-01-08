#!/bin/bash
# ================================
# Reset InfraHub 1.6.x schema with CLI login
# WARNING: This deletes all existing schema/data!
# ================================

# === Neo4j credentials (default for InfraHub 1.6.x) ===
NEO4J_USER="neo4j"
NEO4J_PASSWORD="admin"

# === Postgres credentials ===
POSTGRES_USER="postgres"
POSTGRES_DB="infrahub"

# === Containers ===
API_SERVER="infrahub_infrahub-server_1"
WORKER1="infrahub_task-worker_1"
WORKER2="infrahub_task-worker_2"
TASK_MANAGER="infrahub_task-manager_1"
POSTGRES="infrahub_task-manager-db_1"
NEO4J="infrahub_database_1"
CACHE="infrahub_cache_1"
MESSAGE_QUEUE="infrahub_message-queue_1"

# === 1️⃣ Stop API & workers ===
echo "Stopping API and workers..."
docker stop $API_SERVER $WORKER1 $WORKER2 $TASK_MANAGER

# === 2️⃣ Flush Neo4j ===
echo "Flushing Neo4j..."
docker exec -i $NEO4J bin/cypher-shell -u $NEO4J_USER -p $NEO4J_PASSWORD "MATCH (n) DETACH DELETE n;"

# === 3️⃣ Flush Postgres metadata ===
echo "Flushing Postgres metadata..."
docker exec -i $POSTGRES psql -U $POSTGRES_USER -d $POSTGRES_DB -c "TRUNCATE TABLE node CASCADE;"
docker exec -i $POSTGRES psql -U $POSTGRES_USER -d $POSTGRES_DB -c "TRUNCATE TABLE attribute CASCADE;"
docker exec -i $POSTGRES psql -U $POSTGRES_USER -d $POSTGRES_DB -c "TRUNCATE TABLE relationship CASCADE;"

# === 4️⃣ Restart all containers ===
echo "Starting InfraHub containers..."
docker start $NEO4J $POSTGRES $CACHE $MESSAGE_QUEUE $TASK_MANAGER $WORKER1 $WORKER2 $API_SERVER

# === 5️⃣ Wait for containers to be healthy (skipping if no healthcheck) ===
echo "Waiting for containers to be healthy..."
CONTAINERS=($NEO4J $POSTGRES $CACHE $MESSAGE_QUEUE $TASK_MANAGER $WORKER1 $WORKER2 $API_SERVER)
for c in "${CONTAINERS[@]}"; do
  STATUS=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' $c)
  until [ "$STATUS" = "healthy" ] || [ "$STATUS" = "unknown" ]; do
    echo "Waiting for $c..."
    sleep 2
    STATUS=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}}' $c)
  done
done
echo "✅ All containers are healthy (or skipped if no healthcheck)"

# === 6️⃣ Login via CLI ===
echo "Please login to InfraHub CLI..."
infrahubctl auth login

# === 7️⃣ Reload schema ===
echo "Reloading schema..."
infrahubctl schema load --branch main infrahub/models/base/jeylan.yml

echo "🎉 InfraHub schema reset and reloaded successfully!"
