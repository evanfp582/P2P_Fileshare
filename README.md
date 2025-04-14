# P2P_Fileshare
Work as a group of two students. The goal of this project is to develop a simple peer-to-peer (P2P) file-sharing application. This software will allow multiple users to share files without relying on a centralized server, similar to protocols used in BitTorrent.  

# How to Install Dependencies
There are no added dependencies needed to run this code.  

# How to Run
Explained below is how to run each component in the P2P Fileshare Software System.  

## Tracker
Acts as as central server for the bit torrent. Stores and distributes the current peers in the swarm. Always running.  
Necessary for when peers first enter a swarm.  
```cmd
python .\Tracker.py
```

## Peer
This is the file that creates each peer of each type within the network.  
There are two types of Peers. Seeders and Downloaders.  
Seeders some or all pieces for a specific file.  
Downloaders have no parts of the file upon joining the swarm and their goal is to get all the pieces of the file.  
Running a peer  
```cmd
python .\Peer -i tracker ip [-S] [-p port range] [-d tracker port] [-f file] [-m [M ...]] [-r1 R1] [-r2 R2]
```
Arguments:
-p port range: An integer signifying the first port number the peer uses. Using all ports from port range to port range + 4. Default of 9000.  
-i tracker ip: A required string indicating the IP address of the Tracker. Usually "localhost".  
-d tracker port: The port of the Tracker. Default of 9999.  
-S: Boolean flag that if used indicated that this peer is a Seeder. Default False.  
-f filename: Name of the file that this peer is interested in. Needed for downloader. Default of "0short_story.txt".  
-m pieces. List of missing pieces for this Seeder. Space separated group of ints.  
-r1 range: Optional lower range of pieces this Seeder has.  
-r2 range: Optional upper range of pieces for this peer.  

## Test Cases
The execution of programs requires many commands with very specific arguments so to actually run the test cases, we will be running powershell scripts.

Test 1
```cmd
.\test.ps1
```
This test runs a central Tracker.  
Waits 3 seconds.  
Then runs 3 Seeder peers that have most pieces of 1short_story_10x.txt.  
Waits 3 seconds.  
Then runs a Downloader peer to get 1short_story_10x.txt from the previous 3 Seeder peers.  

Test 2
```cmd
.\test.ps2
```
This test does similar things to test 1, but ir gets ranges of pieces from 1short_story_10x.txt rather than having specific pieces missing.  
Another difference is the use of 5 Seeder peers rather than 3.  
This is a more stressful test on the Downloader's ability to get pieces from multiple peers at the same time.  

Test 3
```cmd
.\test.ps3
```
Test 3 once again ramps up the number of peers in the networks and the specificity of which peer has what.  
Now there are 9 peers each with very specific lower and upper ranges of what pieces of the file they have.  
Also the file size is increased with us testing on 2short_story_100x.txt rather than 1short_story_10x.txt.  

Test 4- Test with multiple downloader peers?  
Test 5- test where not all the peers have all the pieces needed? Do we need this case?  
Test 6- Test with multiple files going at the same time?  

# Command Line Usage 
We have developed a simple command line interface so users can check the progress of their download, be told when it is done, and exit if needed.  
While the peers are running you can type `prog` to see the current progress of the download.  
Or if you are done, you can exit by typing `exit`.  
When the downloader is done `"Successfully Downloaded {output_file} to output/{output_file}"`.  