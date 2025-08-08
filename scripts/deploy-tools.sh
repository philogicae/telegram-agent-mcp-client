docker compose -f extended.yaml cp docker-envs/trackers.txt rqbit:/home/rqbit/cache/trackers.txt
docker compose -f extended.yaml up -d --build --remove-orphans