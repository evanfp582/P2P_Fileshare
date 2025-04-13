Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Tracker.py"

Start-Sleep -Seconds 3

Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5000 -S -f 2short_story_100x.txt -r2 0.2"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5005 -S -f 2short_story_100x.txt -r1 0.1 -r2 0.3"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5010 -S -f 2short_story_100x.txt -r1 0.2 -r2 0.4"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5015 -S -f 2short_story_100x.txt -r1 0.3 -r2 0.5"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5020 -S -f 2short_story_100x.txt -r1 0.4 -r2 0.6"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5025 -S -f 2short_story_100x.txt -r1 0.5 -r2 0.7"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5030 -S -f 2short_story_100x.txt -r1 0.6 -r2 0.8"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5035 -S -f 2short_story_100x.txt -r1 0.7 -r2 0.9"
Start-Sleep -Seconds 1
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 5045 -S -f 2short_story_100x.txt -r1 0.8"

Start-Sleep -Seconds 10

Start-Process powershell -ArgumentList "-NoExit", "-Command", "python .\Peer.py -i localhost -p 6000 -f 2short_story_100x.txt"
