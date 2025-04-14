Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Tracker.py"

Start-Sleep -Seconds 3

Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5000 -S  -r2 0.2"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5005 -S  -r1 0.2 -r2 0.4"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5010 -S  -r1 0.4 -r2 0.6"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5015 -S  -r1 0.6 -r2 0.8"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5020 -S  -r1 0.8"

Start-Sleep -Seconds 10

Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 6000 -f 1short_story_10x.txt"
