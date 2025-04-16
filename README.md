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

**Running a peer**  
```cmd
python .\Peer -i Tracker ip [-S] [-p port range] [-d Tracker port] [-f file] [-m [M ...]] [-r1 R1] [-r2 R2]
```
Arguments:
-p port range: An integer signifying the first port number the peer uses. Using all ports from port range to port range + 4. Default of 9000.  
-i Tracker ip: A required string indicating the IP address of the Tracker. Usually "localhost".  
-d Tracker port: The port of the Tracker. Default of 9999.  
-S: Boolean flag that if used indicated that this peer is a Seeder. Default False.  
-f filename: Name of the file that this peer is interested in. Needed for downloader. Default of "0short_story.txt".  
-m pieces. List of missing pieces for this Seeder. Space separated group of ints.  
-r1 range: Optional lower range of pieces for this Seeder.  
-r2 range: Optional upper range of pieces for this Seeder.  

## Test Cases
The execution of programs requires many commands with very specific arguments so to actually run the test cases, we will be running powershell scripts.  

All the tests follow the same format.
First, open a terminal and run the Tracker.   
Sleep 3 seconds.  
Open a terminal and run Seeder peers with a specified amount of pieces.  
Sleep 1 second between Seeder Peers.  
Sleep 10 seconds.  
Open a terminal and run one or more Downloader peers on a specific file.   
Sleep 1 second between Downloader peers.  

**Test 1**
```cmd
.\test.ps1
```
Basic test to distribute and download 1short_story_10x.txt.  
Runs 3 Seeder peers that have most pieces of 1short_story_10x.txt.  
Then runs a Downloader peer to get 1short_story_10x.txt from the previous 3 Seeder peers.  

**Test 2**
```cmd
.\test2.ps1
```
This test does similar things to test 1, but it gets ranges of pieces from 1short_story_10x.txt rather than having specific pieces missing.  
Another difference is the use of 5 Seeder peers rather than 3.  
Seeder 1 gets the 0th through 20th percent of pieces.  
Seeder 2 gets the 20th through 40th percent of pieces.  
Seeder 3 gets the 40th through 60th percent of pieces.  
Seeder 4 gets the 60th through 80th percent of pieces.  
Seeder 5 gets the 80th through 100 percent of pieces.  

This is a more stressful test on the Downloader's ability to get pieces from more peers at the same time.  

**Test 3**
```cmd
.\test3.ps1
```
Test 3 once again ramps up the number of peers in the networks and the specificity of what pieces each peer has.  
Now there are 9 peers each with very specific lower and upper ranges. The ranges between peers also overlap, handling the case where the Downloader receives multiples of pieces.   
Also the file size is increased with us testing on 2short_story_100x.txt rather than 1short_story_10x.txt.  

Seeder 1 gets the 0th through 20th percent of pieces.  
Seeder 2 gets the 10th through 30th percent of pieces.  
Seeder 3 gets the 20th through 40th percent of pieces.  
Seeder 4 gets the 30th through 50th percent of pieces.  
Seeder 5 gets the 40th through 60 percent of pieces.   
Seeder 6 gets the 50th through 70th percent of pieces.  
Seeder 7 gets the 60th through 80th percent of pieces.  
Seeder 8 gets the 70th through 90th percent of pieces.  
Seeder 9 gets the 80th through 100 percent of pieces. 

**Test 4**  
```cmd
.\test4.ps1
```
Test 4 is a similar test as test 3, but on a different text file, 3lorem_ipsum.txt

**Test 5**  
```cmd
.\test5.ps1
```
Test 5 tests multiple Downloaders all trying to download the same file, 3lorem_ipsum.txt.  
This test has the same Seeder set up as test 3 and 4.  
Once the Seeders are running, the three Downloaders get ran.  

**Test 6**  
```cmd
.\test6.ps1
```
Test 6 is testing multiple peers running at the same time on a swarm all requesting different files.
This test has the same Seeder set up as test 3, 4, and 5.  
Once the Seeders are running, 4 downloaders get ran individually requesting 2short_story_100x.txt, 3lorem_ipsum.txt, 1short_story_10x.txt, 0short_story.txt.  

**Test 7**  
```cmd
.\test7.ps1
```
Test 7 is showing 1 Seeder, that contains all pieces, supplying pieces for a bunch of  Downloaders. This demonstrates that once a Downloader peer gets pieces that other Downloaders need, it supplies pieces to them. This test is a good example of the powerful use cases of P2P file download. 

**Test 8**  
```cmd
.\test8.ps1
```
Test 8 is meant as a comparison between test 7. Test 8 somewhat mimics the client-server paradigm that we want to improve on with P2P. We can see that this test runs much more slowly because there are only 2 downloader peers. 


# Command Line Usage 
We have developed a simple command line interface so users can check the progress of their download, be told when it is done, and exit if needed.  
While the peers are running you can type `prog` to see the current progress of the download.  
Or if you are done, you can exit by typing `exit`.  
When the downloader is done `"Successfully Downloaded {output_file} to output/{output_file}"`.  