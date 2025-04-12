Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Tracker.py"

Start-Sleep -Seconds 3

Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5010 -S -f short_story_10x.txt -m 20 30 40 50"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5020 -S -f short_story_10x.txt -m 10 20 50 60"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5030 -S -f short_story_10x.txt -m 10 30 40 60"

Start-Sleep -Seconds 3

Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 6000 -f short_story_10x.txt"
