# Local .env with secrets
if [ -f .env ]; then
    # Load Environment Variables
    export $(cat .env | grep -v '#' | awk '/=/ {print $1}')
fi

# Redefine Mongo variables
export MONGO_HOST=localhost
export MONGO_PORT=27017
export MONGO_INITDB_ROOT_USERNAME=root
export MONGO_INITDB_ROOT_PASSWORD=rootpassword
export RAINDROPBOT_DEV=true

python src/main.py