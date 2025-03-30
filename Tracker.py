import argparse
import ipaddress
import socket
import struct
import threading
import hashlib

# Dict holding the information about the swarm
swarm = {}
# Peer id counter used to generate unique peers
peer_id = 1

# Lock for managing access to swarm
lock = threading.Lock()


def handle_peer(peer_sock, peer_addr):
    global swarm
    global peer_id
    global lock

    try:
        # Standard request format is 1 byte code, 2 byte id, 32 byte hash
        packet = peer_sock.recv(35)
        code_hash = hashlib.sha256(packet[:3])
        # Compare the hash generated from the code to the one we received
        # TODO 32 byte has for a 3 byte value seems a bit overkill, maybe use smaller digest hash function(we dont really need to worry about collisions b/c small input)
        # TODO we also need to figure out how we represent the info hash of the file and the pieces, right now just using hash for message integrity like is done for HTTP
        if code_hash.digest() != packet[3:]:
            # Use null byte return to indicate a message that was corrupted.
            peer_sock.send(b"\0")
            return
        # If we get here, the hash comparison was successful
        msg_code, msg_id = struct.unpack('>BH', packet[:3])
        # code 0 means that it is a new client, so here id = port range
        if msg_code == 0:
            lock.acquire()
            current_id = peer_id
            peer_id += 1  # Increment our peer ID
            # Store the provided port range and the IP of the peer
            swarm[current_id] = msg_id, peer_addr[0]
            # Just to avoid holding lock too long, copy current swarm.
            current_swarm = swarm.copy()
            lock.release()

            # Start of response packet is the assigned ID of the peer
            send_packet = struct.pack('>HH', current_id, len(current_swarm))
            # Use a hash to confirm length and id were sent correctly
            length_hash = hashlib.sha256(send_packet)
            peer_sock.send(send_packet + length_hash.digest())
            # Now, we confirm that the message arrived uncorrupted.
            while True:
                # Read at most 35 bytes, though an ack will be just 1 byte.
                response_packet = peer_sock.recv(35)
                if len(response_packet) > 1:
                    peer_sock.send(send_packet + length_hash.digest())
                else:
                    break

            swarm_packet = b''
            # Add each peer in the swarm as 2 byte id + 2 byte port + 4 byte IP
            for peer in current_swarm.keys():
                swarm_packet += struct.pack('>HHI', peer, current_swarm[peer][0], int(ipaddress.ip_address(current_swarm[peer][1])))
            # When done, also calculate the hash of the swarm packet
            swarm_hash = hashlib.sha256(swarm_packet)
            # Send out the message
            peer_sock.send(swarm_packet + swarm_hash.digest())
            # Now, we confirm that the message arrived uncorrupted.
            while True:
                response_packet = peer_sock.recv(35)
                if len(response_packet) > 1:
                    peer_sock.send(swarm_packet + swarm_hash.digest())
                else:
                    break

        elif msg_code == 1:  # code 1 means a returning client
            if msg_id == 0:  # If id is 0, it is just a refresh request
                lock.acquire()
                current_swarm = swarm.copy()
                lock.release()

                # Send and confirm length
                send_packet = struct.pack('>H', len(current_swarm))
                length_hash = hashlib.sha256(send_packet)
                peer_sock.send(send_packet + length_hash.digest())
                while True:
                    response_packet = peer_sock.recv(35)
                    if len(response_packet) > 1:
                        peer_sock.send(send_packet + length_hash.digest())
                    else:
                        break

                swarm_packet = b''
                for peer in current_swarm:
                    swarm_packet += struct.pack('>HHI', peer, current_swarm[peer][0], int(ipaddress.ip_address(current_swarm[peer][1])))
                swarm_hash = hashlib.sha256(swarm_packet)
                peer_sock.send(swarm_packet + swarm_hash.digest())
                while True:
                    # Read at most 35 bytes, though an ack will be just 1 byte.
                    response_packet = peer_sock.recv(35)
                    if len(response_packet) > 1:
                        peer_sock.send(swarm_packet + swarm_hash.digest())
                    else:
                        break

            else:  # Otherwise, the id is that of the client who wants to leave, so remove it from the swarm and confirm with the client
                lock.acquire()
                swarm.pop(msg_id)  # Remove client from swarm
                send_packet = struct.pack('>H', msg_id)
                # Just send back the number, we don't care if it is corrupted.
                peer_sock.send(send_packet)
                lock.release()

    except ConnectionResetError:
        print("Connection reset by a client")
    peer_sock.close()


def main():
    parser = argparse.ArgumentParser(
        prog="Tracker",
        description="Runs tracker server for managing swarm.")
    parser.add_argument("-p", metavar="source port", type=int, default=9999,
                        help="Local port to bind to.")

    args = parser.parse_args()
    host = 'localhost'
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((host, args.p))
    sock.listen()

    while True:
        peer_sock, peer_addr = sock.accept()
        thread = threading.Thread(target=handle_peer,
                                  args=(peer_sock, peer_addr))
        thread.start()

    # TODO not sure if we want to actually have a way of closing it, or just manually shut it off from terminal when done (leaning towards the latter)
    sock.close()


if __name__ == "__main__":
    main()
