"""File to test little things intermittently while the big pieces are not connected yet"""
import socket
import struct
import threading
import time
from Peer import create_downloader, create_seeder, handle_responses
from Packet import create_packet, parse_packet
import Peer
import Utility

HOST = '127.0.0.1'
PORT = 3000
LOCAL_PORT = 3001

shutdown_event = threading.Event()

# Dict of "downloaded" pieces (file, index) = bytes
mock_file = [bytes([i] * 128) for i in range(5)]

#TODO I wanted to test the seeder and downloader peers in a controlled new file, but I can't even get a basic socket working with your create_seeder and create_downloader
#TODO You can take a look at this if you want, but it may not be worth your time, this is kinda just for my testing and comprehension

def seeder():
    pieces = {(0,0): mock_file[0], (0,2): mock_file[2], (0,4): mock_file[4]}
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, PORT))
        sock.listen()
        sock.settimeout(1)
        print("[seeder] Waiting for connections...")
        while not shutdown_event.is_set():
            try:
                conn, addr = sock.accept()
                with conn:
                    # packet = conn.recv(4)
                    # length, = struct.unpack(">I", packet[:4])  # check length
                    # packet = packet + conn.recv(length)  # read rest of packet
                    # payload = parse_packet(packet)
                    # print(f"[seeder] Received: {payload}")
                    # conn.sendall(b"Hello from seeder!")
                    # time.sleep(2)
                    packet = create_packet(0)
                    conn.send(packet)
                    packet = create_packet(1)
                    conn.send(packet)
                    packet = create_packet(2)
                    conn.send(packet)
                    packet = create_packet(3)
                    conn.send(packet)
                    #Unimplemented Seeder sending a have to downloader
                    # packet = create_packet(4, )
                    # conn.send(packet)
                    # Unimplemented Seeder requesting a piece from downloader
                    # packet = create_packet(6, 0, mock_file[0])
                    # conn.send(packet)
                    packet = create_packet(7, 0, mock_file[0]) #Currently breaks due to global
                    conn.send(packet)
                    print("[seeder]: Finished sending packets, staying open")

            except socket.timeout:
              continue  # Just try again to check shutdown_event
        print("[seeder] Shutdown complete.")            # packet = conn.recv(4)        
            

def downloader():
    indexes_on_peer = [0,2,4]
    seeder_bitfield = Utility.create_bitfield({(0,0): mock_file[0], (0,2): mock_file[2], (0,4): mock_file[4]}, 5)
    print("[downloader] Seeder Bitfield",Utility.bytes_to_binary(seeder_bitfield))
    time.sleep(1)  # Give the seeder time to start
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1)
        sock.connect((HOST, PORT))
        print("[downloader] Connected to seeder")
        while not shutdown_event.is_set():
            try:
                print("[downloader] Idling")
                time.sleep(3)
            except socket.timeout:
                continue  # Just try again to check shutdown_event
        # packet = create_packet(4, 5, 0)
        # print("[downloader] Created packet ", packet)
        # sock.send(packet)
        # data = sock.recv(1024)
        # print(f"[downloader] Received: {data.decode()}")
        # handle_responses(sock, indexes_on_peer)
        print("[downloader] Shutdown complete.") 

if __name__ == "__main__":
  seeder_thread = threading.Thread(target=seeder)
  downloader_thread = threading.Thread(target=downloader)

  seeder_thread.start()
  downloader_thread.start()

  # seeder_thread.join()
  # downloader_thread.join()
  #TODO make sure to uncomment lines 46-49 in Peer.py to test
  Peer.cli(shutdown_event, False)