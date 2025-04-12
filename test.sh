#!/bin/bash

gnome-terminal -- bash -c "python3 ./Tracker.py; exec bash"

sleep 3

gnome-terminal -- bash -c "python3 ./Peer.py -i localhost -p 5010 -S -f short_story_10x.txt -m 20 30 40 50; exec bash"
sleep 1

gnome-terminal -- bash -c "python3 ./Peer.py -i localhost -p 5020 -S -f short_story_10x.txt -m 10 20 50 60; exec bash"
sleep 1

gnome-terminal -- bash -c "python3 ./Peer.py -i localhost -p 5030 -S -f short_story_10x.txt -m 10 30 40 60; exec bash"

sleep 3

gnome-terminal -- bash -c "python3 ./Peer.py -i localhost -p 6000 -f short_story_10x.txt; exec bash"
