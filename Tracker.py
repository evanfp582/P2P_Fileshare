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
        if code_hash.digest() != packet[3:]:
            # TODO what do we do when a tracker request is corrupted, for now just end connection
            peer_sock.close()
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
            # Start of response packet is the assigned ID of the peer
            send_packet = struct.pack('>H', current_id)
            # Add size of swarm list
            send_packet += struct.pack('>H', len(swarm))
            # Add each peer in the swarm as 2 byte port + 4 byte IP
            for peer in swarm:
                send_packet += struct.pack('>HI', peer[0],
                                           int(ipaddress.ip_address(peer[1])))
            lock.release()
            # When done, also calculate the hash of the packet
            swarm_hash = hashlib.sha256(send_packet)
            # Send out the message
            peer_sock.send(send_packet + swarm_hash.digest())
            # Now, we confirm that the message arrived uncorrupted.
            while True:
                response_packet = peer_sock.recv(34)
                id_hash = hashlib.sha256(response_packet[:2])
                # The response will just be user echoing their id + the hash, so if that matches then we are good
                if id_hash.digest() != packet[2:]:
                    peer_sock.send(send_packet + swarm_hash.digest())
                else:
                    break

        elif msg_code == 1:  # code 1 means a returning client
            if msg_id == 0:  # If id is 0, it is just a refresh request
                lock.acquire()
                # Send length and then whole swarm list
                send_packet = struct.pack('>H', len(swarm))
                for peer in swarm:
                    send_packet += struct.pack('>HI', peer[0],
                                               int(ipaddress.ip_address(
                                                   peer[1])))
                lock.release()
                swarm_hash = hashlib.sha256(send_packet)
                peer_sock.send(send_packet + swarm_hash.digest())
                # TODO currently set up so we don't care if regular updates are received successfully, but we can change that if needed
                # My thinking was just that if we already get an update every 1 or 2 seconds, we can afford to miss an update rather than doing a whole back and forth
            else:  # Otherwise, the id is that of the client who wants to leave, so remove it from the swarm and confirm with the client
                lock.acquire()
                swarm.pop(msg_id)  # Remove client from swarm
                # just echo back the id as confirmation, it does not matter if it gets corrupted since anything being sent indicates success
                send_packet = struct.pack('>H', msg_id)
                peer_sock.send(send_packet)
                lock.release()

    except ConnectionResetError:
        print("Connection reset by a client")
    peer_sock.close()


def main():
    parser = argparse.ArgumentParser(
        prog="Tracker",
        description="Runs tracker server for managing swarm.")
    parser.add_argument("-p", metavar="source port", type=int, default=9990,
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

    server_sock.close()  # TODO not sure if we want to actually have a way of closing it, or just manually shut it off from terminal when done (leaning towards the latter)


if __name__ == "__main__":
    main()
