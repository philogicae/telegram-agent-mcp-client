#!/bin/zsh
source ~/.zshrc

dkr compose -f compose-extended.yaml cp docker-envs/trackers.txt rqbit:/home/rqbit/cache/trackers.txt
dkr compose -f compose-extended.yaml up -d --build --remove-orphans