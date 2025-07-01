#!/bin/zsh
source ~/.zshrc

dkr compose -f docker/compose-extended.yaml cp docker/trackers.txt rqbit:/home/rqbit/cache/trackers.txt
dkr compose -f docker/compose-extended.yaml up -d --build --remove-orphans