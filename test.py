"""File to test little things intermittently while the big pieces are not connected yet"""
import socket
import struct
import threading
import time
from Peer import create_downloader, create_seeder, handle_responses
from Packet import create_packet, parse_packet
import Utility

HOST = '127.0.0.1'
PORT = 3000
LOCAL_PORT = 3001

# Dict of "downloaded" pieces (file, index) = bytes
mock_file = [bytes([i] * 128) for i in range(5)]

#TODO I wanted to test the seeder and downloader peers in a controlled new file, but I can't even get a basic socket working with your create_seeder and create_downloader
#TODO You can take a look at this if you want, but it may not be worth your time, this is kinda just for my testing and comprehension

def seeder():
    pieces = {(0,0): mock_file[0], (0,2): mock_file[2], (0,4): mock_file[4]}    
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, PORT))
        sock.listen()
        print("[seeder] Waiting for connection...")
        conn, addr = sock.accept()
        with conn:
          print(f"[seeder] Connected by {addr}")
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
        
            

def downloader():
    indexes_on_peer = [0,2,4]
    seeder_bitfield = Utility.create_bitfield({(0,0): mock_file[0], (0,2): mock_file[2], (0,4): mock_file[4]}, 5)
    print("[downloader] Seeder Bitfield",Utility.bytes_to_binary(seeder_bitfield))
    time.sleep(1)  # Give the seeder time to start
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.connect((HOST, PORT))
        print("[downloader] Connected to seeder")
        # packet = create_packet(4, 5, 0)
        # print("[downloader] Created packet ", packet)
        # sock.send(packet)
        # data = sock.recv(1024)
        # print(f"[downloader] Received: {data.decode()}")
        handle_responses(sock, indexes_on_peer)

if __name__ == "__main__":
  seeder_thread = threading.Thread(target=seeder)
  downloader_thread = threading.Thread(target=downloader)

  seeder_thread.start()
  downloader_thread.start()

  seeder_thread.join()
  downloader_thread.join()