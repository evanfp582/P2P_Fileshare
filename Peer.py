import argparse
import ipaddress
import socket
import struct
import threading
import hashlib
import time
import ssl

# Dict holding the information about the other peers in the swarm
swarm = {}

# Id of this peer in the swarm
local_id = 0

# Flag indicating if the user has downloaded their target file yet
download_finished = False

# Flag indicating if we should exit subthreads and close the peer
exit_peer = False

# List of current peer connections (or dict not sure yet)
current_peers = {}

# List of download pieces remaining (again also maybe a dict)
pieces_remaining = {}

# List of downloaded pieces (file, index, string)
#TODO I think this should be a dictionary. It's a little messy, but an embedded dictionary that look like this 
# pieces = { file_name: {index: string? I am not sure what string is supposed to be, the binary string of data?}}
pieces = {}

# TODO depending on how we discover other peers and their pieces, we may want to store a dict showing what users have what pieces

# Lock for managing local swarm list and file info
lock = threading.Lock()


def update_swarm(ip, port):
    global swarm
    global lock
    global download_finished
    while not download_finished:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((ip, port))
            # Refresh message is code 1, id 0
            send_packet = struct.pack('>BH', 1, 0)
            send_hash = hashlib.sha256(send_packet)
            sock.send(send_packet + send_hash.digest())
            while True:
                response_packet = sock.recv(34)
                if len(response_packet) == 1:
                    sock.send(send_packet + send_hash.digest())
                    continue
                verify_hash = hashlib.sha256(response_packet[:2])
                if verify_hash.digest() != response_packet[2:]:
                    sock.send(send_packet + send_hash.digest())
                else:
                    sock.send(b"\0")
                    break

            length, = struct.unpack('>H', response_packet[:2])
            while True:
                response_packet = sock.recv(8 * length + 32)
                verify_hash = hashlib.sha256(response_packet[:8 * length])
                if verify_hash.digest() != response_packet[8 * length:]:
                    sock.send(send_packet + send_hash.digest())
                else:
                    sock.send(b"\0")
                    break

            lock.acquire()
            for i in range(length):
                peer_id, peer_port, peer_ip = (
                    struct.unpack('>HHI', response_packet[i:i + 8]))
                swarm[peer_id] = peer_port, str(ipaddress.ip_address(peer_ip))
            lock.release()

            print(swarm)
            sock.close()
            time.sleep(3)  # For now, update every 3 seconds
        except ConnectionResetError:
            print("Connection reset by server")
        except ConnectionRefusedError:
            print("Server unavailable for connection")


def handle_responses():
    print("stuff")
    # This function should handle a response and return information about it
    # ie if it is a have, dont need to resend a piece (and also return to the
    # calling function so we can send the next piece) or if it is a request,
    # send a piece in response


# Just drafting out some protocol ideas

# Thoughts for this function, if we are currently looking for a file, we will
# have our 4 main connectors querying peers in random order to get files, with
# it still up for decision how we prioritize chunks
# This will require 2 global lists - one for the current communication links
# (so other connectors dont try to connect to the same peer) and the chunks left
# to be queried. When a connector finds someone with chunks we need, they will
# figure out which ports are open, connect to that port, then record the port
# they connected to and remove the chunks to be searched from the list.
# If the chunks are all received and verified correctly, then they will remain off
# however, if something happens, then the chunks will be re-added to the list.
# Once the size of the list hits 0, connectors will go into waiting mode.
# A seeder will always be in waiting mode (though whether we have designated seeders
# and loaders is up for debate)

# the thread for choking and unchoking will not be designated, most likely it will
# simply check the list of communicators, and if there are 4 it will say I am the
# thread for unchoking - the same thing occurs when something gets kicked off
# it will now see there are 4 items, and it will start the unchoking protocol

# currently, I imagine each connector having 2 threads, one for each direction,
# though it is also true that in addition to transferring information, we will
# also need to handle acks and the like, so we may want 1 thread instead.
def sharing():
    global download_finished
    global lock
    global swarm
    global current_peers
    global pieces_remaining
    global exit_peer

    while not download_finished:
        if len(current_peers) < 4:
            # Even if we are not using all 4 connections, we cannot download
            # anything if there is nothing left to get
            if len(pieces_remaining) < 1:
                print("waiting to see if a peer wants to download")
                time.sleep(.5)
            else: # This where the real work happens, communicate with peer
                # TODO figure out how we will figure out which peer to comm with and which index to request
                print("Sending data")
        else:
            # TODO optimistic unchoking procedure
            print("waiting to unchoke a peer")

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
    index = 5  # file and index would be whatever piece we just downloaded.
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

    while not exit_peer:
        print("waiting to see if a peer wants to download")
        time.sleep(.5)


def main():
    global swarm
    global local_id
    global download_finished
    global exit_peer

    parser = argparse.ArgumentParser(
        prog="Peer",
        description="Acts as a peer in the P2P swarm.")
    parser.add_argument("-p", metavar="port range", type=int, default=9000,
                        help="Port range used by this peer. For a given i, "
                             "port i to i + 4 are used for peers.")
    parser.add_argument("-i", metavar="tracker ip", type=str,
                        required=True, help="IP address of tracker server.")
    parser.add_argument("-d", metavar="tracker port", type=int,
                        default=9999, help="Port of tracker server.")

    args = parser.parse_args()

    # TODO populate this peer with whatever pieces we want them to have
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
                sock.send(b"\0")  # On success, ACK by sending a null byte.
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
            peer_id, peer_port, peer_ip = (
                struct.unpack('>HHI', response_packet[i:i + 8]))
            swarm[peer_id] = peer_port, str(ipaddress.ip_address(peer_ip))

        sock.close()
    except ConnectionResetError:
        print("Connection reset by server")
    except ConnectionRefusedError:
        print("Server unavailable for connection")

    print(swarm)
    time.sleep(1)
    # Start the background tracker sync function.
    update_thread = threading.Thread(target=update_swarm,
                                     args=(args.i, args.d))
    update_thread.start()

    time.sleep(10)
    download_finished = True
    exit_peer = True

    # TODO figure out how we are checking which users have what chunks

    # TODO actual P2P stuff like making the 4 main threads (and sometimes 5th unchoking thread)
    # Assume that we have a peer we want to connect to here(using localhost)
    # 2 recommended ways of making a socket, not sure which is better.
    #context = ssl.create_default_context()
    #with socket.create_connection((swarm[1][1], swarm[1][0])) as sock:
        #with context.wrap_socket(sock, server_hostname=swarm[1][1]) as ssock:
            #print(ssock.version())

    #context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    #with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as sock:
        #with context.wrap_socket(sock, server_hostname=swarm[1][1]) as ssock:
            #print(ssock.version())


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
