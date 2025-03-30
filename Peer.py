import argparse
import ipaddress
import socket
import struct
import threading
import hashlib

# Dict holding the information about the other peers in the swarm
swarm = {}
local_id = 0

# Lock for managing local swarm list and file info
lock = threading.Lock()


# Just drafting out some protocol ideas
def sharing():
    # TODO as you saw in the tracker file, confirming message length using a hash is kind of ugly, for here, thinking we send a fixed length message and just pad with 0s to avoid
    # having any issues
    print("stuff")
    # Flag messages are just payload and hash
    # We can change the numbers, just using 0-3 here
    # Choke
    send_packet = struct.pack('>B', 0)
    send_hash = hashlib.sha256(send_packet)
    # Unchoke
    send_packet = struct.pack('>B', 1)
    send_hash = hashlib.sha256(send_packet)
    # Interested
    send_packet = struct.pack('>B', 2)
    send_hash = hashlib.sha256(send_packet)
    # Not interested
    send_packet = struct.pack('>B', 3)
    send_hash = hashlib.sha256(send_packet)
    # Have basically is just an ACK with the file name and index
    file = 3
    index = 5 # file and index would be whatever piece we just downloaded.
    send_packet = struct.pack('>BHH', 4, file, index)
    send_hash = hashlib.sha256(send_packet)
    # Request is more or less the same as have
    send_packet = struct.pack('>BHH', 5, file, index)
    send_hash = hashlib.sha256(send_packet)
    # Piece would likely be the one to set the total message size, since it has
    # actual data in it, so we should figure out what size we want to use.
    data = "test part of a file".encode()
    send_packet = struct.pack('>BHH', 6, file, index)
    send_packet += data
    send_hash = hashlib.sha256(send_packet)
    # TODO skipped the bitfield one since I am not sure how we are handling that

def main():
    global swarm
    global local_id
    global lock

    parser = argparse.ArgumentParser(
        prog="Peer",
        description="Acts as a peer in the P2P swarm.")
    parser.add_argument("-p", metavar="port range", type=int, default=9000,
                        help="Port range used by this peer. For a given i, "
                             "port i is used to communicate with tracker "
                             "while i + 1 to i + 5 are used for peers.")
    parser.add_argument("-i", metavar="tracker ip", type=str,
                        required=True, help="IP address of tracker server.")
    parser.add_argument("-d", metavar="tracker port", type=int,
                        default=9999, help="Port of tracker server.")

    args = parser.parse_args()

    # TODO not sure if we want to do the setup here or in a function
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((args.i, args.d))
        # Initial message should just be code 0, id = given port range
        send_packet = struct.pack('>BH', 0, args.p)
        send_hash = hashlib.sha256(send_packet)
        sock.send(send_packet + send_hash.digest())
        # As on tracker side, make sure we get a correct hash
        while True:
            response_packet = sock.recv(36)
            if len(response_packet) == 1:
                sock.send(send_packet + send_hash.digest())
                continue
            verify_hash = hashlib.sha256(response_packet[:4])
            if verify_hash.digest() != response_packet[4:]:
                sock.send(send_packet + send_hash.digest())
            else:
                sock.send(b"\0") # On success, ACK by sending a null byte.
                break

        # Read out our new id, then the length of the swarm list to expect
        local_id, length = struct.unpack('>HH', response_packet[:4])
        while True:
            response_packet = sock.recv(8 * length + 32)
            verify_hash = hashlib.sha256(response_packet[:8 * length])
            if verify_hash.digest() != response_packet[8 * length:]:
                sock.send(send_packet + send_hash.digest())
            else:
                sock.send(b"\0")
                break

        # Now that we have confirmed swarm is successfully received, read it.
        for i in range(length):
            peer_id, peer_port, peer_ip = struct.unpack('>HHI', response_packet[i:i + 8])
            swarm[peer_id] = peer_port, ipaddress.ip_address(peer_ip)

        sock.close()


    except ConnectionResetError:
        print("Connection reset by server")
    except ConnectionRefusedError:
        print("Server unavailable for connection")

    print(swarm)

    # TODO actual P2P stuff like making the 4 main threads (and sometimes 5th unchoking thread)

    # At the end of downloading (or whenever we decided to stop)
    try:
        # TODO right now we open a new TCP connection each tracker message, may be inefficient but not sure if we care at the scales we are at
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((args.i, args.d))
        send_packet = struct.pack('>BH', 1, local_id)
        send_hash = hashlib.sha256(send_packet)
        sock.send(send_packet + send_hash.digest())
        while True:
            response_packet = sock.recv(4)
            # if we get anything other than a null, it succeeded.
            if len(response_packet) == 1:
                sock.send(send_packet + send_hash.digest())
                continue
            else:
                break
        print("Exited swarm.")
        sock.close()
    except ConnectionResetError:
        print("Connection reset by server")
    except ConnectionRefusedError:
        print("Server unavailable for connection")


if __name__ == "__main__":
    main()
