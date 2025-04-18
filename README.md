# P2P_Fileshare
Work as a group of two students. The goal of this project is to develop a simple peer-to-peer (P2P) file-sharing application. This software will allow multiple users to share files without relying on a centralized server, similar to protocols used in BitTorrent.  
Group:
Evan Fisher-Perez (emf8602@rit.edu)
Griffin Danner-Doran (gtd6864@rit.edu)
# How to Install Dependencies
There are no added dependencies needed to run this code.  This code was made using Python 3.11/12.

# Notes:
Our P2P protocol is not tested on or designed to support images, videos, or any other format than basic text files (ex .txt, .py). You can add
your own files if necessary, but they must be prefixed 0-3 and will need to replace one of the provided text files since this was designed to be small scale.  
The peers use SSL/TLS to communicate with one another, with the required cert and key files included here. While it should not be a problem,
these authorizations were created on Windows, so there is a possibility that they do not work on other OSes. If this occurs, the message 
"Communication with peer failed." will be printed repeatedly to indicate the issue.   
The provided test files are also designed to run powershell terminals, so it is recommended to use Windows only. All tests and work shown here 
and in the report were done on Windows.  
Next, it is worth mentioning that there are no built-in protections against running 2 or more peers on the same port range. 
While this is designed to be tested on a single host, it is meant to emulate a system of remote peers and trackers with minimal coordination. Therefore,
submitting overlapping local port ranges or port ranges dedicated to other protocols will result in errors when the sockets attempt to bind on them.  
Finally, this system can support multiple devices with minimal effort, as each peer ends its local IP to the tracker. The only change needed
from the test code provided is to specify the IP location of the already running tracker. However, given the relatively short timeouts used in the program,
this is best suited for fairly close devices. You will also need to make sure that all Seeders have the same input files, and that all Downloaders use the same hash lists.

# How to Run
Explained below is how to run each component in the P2P Fileshare Software System.  
You may need to enable permission to run powershell scripts, as by default they tend to be blocked from direct execution.
Furthermore, before execution, make sure that you have an output and hashes folder created.  
All peers, regardless of type, must be run in the same location as the 2 helper libraries and the security files.

## Tracker
Acts as a central peer discovery mechanism for the P2P protocol. Stores and distributes the current peers in the swarm. Always running.  
Necessary for when peers first enter a swarm.
```cmd
python .\Tracker.py
```

## Peer
This is the file that creates each peer of each type within the network.  
There are two types of Peers, Seeders and Downloaders.  
Seeders have some or all pieces for each file in the swarm.  
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
-f filename: Name of the file that this peer is interested in. Needed for Downloader. Default of "0short_story.txt".  
-m pieces. List of missing pieces for this Seeder. Space separated group of ints.  
-r1 range: Optional lower range of pieces for this Seeder.  
-r2 range: Optional upper range of pieces for this Seeder.  
Note that the range option will be used even if only one bound is set, with the other defaulting to 0.0 or 1.0 for lower and upper respectively.  
Also if both missing pieces and ranges are provided, the missing pieces will be used.

## Test Cases
The execution of programs requires many commands with very specific arguments so to actually run the test cases, we will be running powershell scripts.  
You can run your own tests, but they should follow a similar format of setup to those provided.  

All the tests follow the same format.
First, open a terminal and run the Tracker.   
Sleep 3 seconds.  
Open a terminal and run Seeder peers with a specified amount of pieces.  
Sleep 1 second between Seeder Peers.  
Sleep 10 seconds.  
Open a terminal and run one or more Downloader peers on a specific file.   
Sleep 1 second between Downloader peers.  

This 10 seconds is meant to allow you to view the starting allotment of file pieces on Seeders using the 'prog' command, or to delete the local copies of the input files
to demonstrate that the P2P protocol allows Downloaders to re-assemble the file just from Seeders and the hash file even when the full file does not exist locally.

**Test 1**
```cmd
.\test.ps1
```
Basic test to distribute and download 1short_story_10x.txt.  
Runs 3 Seeder peers that have most of the pieces for each file (only missing 5 from each).  
Then runs a Downloader peer to get 1short_story_10x.txt from the previous 3 Seeder peers.
This test is expected to run slowly, as it demonstrates that our P2P system is least effective when the Seeders have overlapping pieces.

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

This is a more stressful test on the Downloaders' ability to get pieces from more peers at the same time and demonstrates the increased
total volume of data transmitted by using more Seeders (and thus more parallel connections) as well as having less overlap.

**Test 3**
```cmd
.\test3.ps1
```
Test 3 once again ramps up the number of peers in the networks and the range of pieces each peer has.  
Now there are 9 peers each with very specific lower and upper ranges. The ranges between peers also overlap, handling 
the case where the Downloader receives multiples of pieces.     
Furthermore, the file size is increased with us testing on 2short_story_100x.txt rather than 1short_story_10x.txt.  

Seeder 1 gets the 0th through 20th percent of pieces.  
Seeder 2 gets the 10th through 30th percent of pieces.  
Seeder 3 gets the 20th through 40th percent of pieces.  
Seeder 4 gets the 30th through 50th percent of pieces.  
Seeder 5 gets the 40th through 60th percent of pieces.   
Seeder 6 gets the 50th through 70th percent of pieces.  
Seeder 7 gets the 60th through 80th percent of pieces.  
Seeder 8 gets the 70th through 90th percent of pieces.  
Seeder 9 gets the 80th through 100 percent of pieces. 

This is meant as a stress test to simulate the types of large files a real P2P system would need to handle.
It should also demonstrate that a Downloader does not connect to all Seeders if it does not have to, as some Seeders will have
no connections, which can be seen by them still having ~4664 files after the test completes.

**Test 4**  
```cmd
.\test4.ps1
```
Test 4 is a similar test as test 3, but on a different text file, 3lorem_ipsum.txt, which is slightly smaller.

**Test 5**  
```cmd
.\test5.ps1
```
Test 5 tests multiple Downloaders all trying to download the same file, 3lorem_ipsum.txt.  
This test has the same Seeder set up as test 3 and 4.  
Once the Seeders are running, the three Downloaders run, with their expected times similar to that of test 4.
This test demonstrates that adding more concurrent Downloaders does not significantly increase the time to get a file.  
It is worth mentioning here that if you have a lower-resource system, there may be some slowdown from the overhead of running more shell scripts. This was not
observed in our documented tests as we were testing on sufficiently powerful hardware.

**Test 6**  
```cmd
.\test6.ps1
```
Test 6 is testing multiple peers running at the same time on a swarm all requesting different files.
This test has the same Seeder set up as test 3, 4, and 5.  
Once the Seeders are running, 4 Downloaders run individually, requesting 2short_story_100x.txt, 3lorem_ipsum.txt, 1short_story_10x.txt, 0short_story.txt.  
This test demonstrates our P2P systems ability to support multiple clients requesting multiple kinds of files at the same time.

**Test 7**  
```cmd
.\test7.ps1
```
Test 7 starts 1 Seeder that contains all pieces, supplying pieces for 5 Downloaders all requesting 1short_story_10x.txt. 
This is another test demonstrating that adding more peers to the system does not slow down the P2P process, as peers can supply pieces to each other.
This test is a good example of the powerful use cases of P2P file sharing vs the usual client-server paradigm.

**Test 8**  
```cmd
.\test8.ps1
```
Test 8 is meant as a comparison between test 7. We can see that this test runs at a similar speed to test 7 even with fewer peers. 
As a result, we can see that adding more peers to a P2P file sharing system does not decrease the rate at which files can be transmitted, 
as opposed to a standard client-server system where adding more clients would be expected to slow down execution.


# Command Line Usage 
We have developed a simple command line interface so users can check the progress of their download, be told when it is done, and exit if needed.  
While the peers are running you can type `prog` to see the current progress of the download.  
Or if you are done, you can exit by typing `exit`.  
When the Downloader is done `"Successfully Downloaded {output_file} to output/{output_file}"`.  
Note: If a critical error with the tracker is encountered (which should really only occur when intentionally turning off the tracker mid-test),
you should print prog or exit to cycle the client to check the exit state, otherwise it will hang waiting for your input.