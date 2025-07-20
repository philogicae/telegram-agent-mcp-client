#!/bin/zsh
source ~/.zshrc

dkr compose -f compose.yaml -f extended.yaml cp docker-envs/trackers.txt rqbit:/home/rqbit/cache/trackers.txt
dkr compose -f compose.yaml -f extended.yaml up -d --build --remove-orphans