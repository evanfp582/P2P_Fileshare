Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Tracker.py"

Start-Sleep -Seconds 3

Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5000 -S -r1 0.0"
Start-Sleep -Seconds 1

Start-Sleep -Seconds 10

Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 6000 -f 1short_story_10x.txt"

Start-Sleep -Seconds 1

Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 6005 -f 1short_story_10x.txt"
