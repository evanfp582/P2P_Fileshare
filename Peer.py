import argparse
import ipaddress
import os
import random
import socket
import struct
import threading
import hashlib
import time
import ssl
import Packet
import Utility

# TODO after we get everything working, go back through and make sure we handle potential socket errors and concurrent access.


# Dict holding the information about the other peers in the swarm
swarm = {}

# Id of this peer in the swarm
local_id = 0

# Flag indicating if the user has downloaded their target file yet
download_finished = False

# Flag indicating if we should exit subthreads and close the peer
exit_peer = False

# Dict of current peers - {id, RTT}
current_peers = {}

# Dict of the pieces remaining - (file, index) = bytes
pieces_remaining = {}

# total number of pieces we want to have
totalPieces = 0
# Dict of "downloaded" pieces (file, index) = bytes
pieces = {}

# Lock for managing local swarm list and file info
lock = threading.Lock()


# Does a handshake on a socket connection and closes it on failure
# After conducting the handshake, returns True on success, False otherwise.
def handshake(sock, target_id=0, initiate=True):
    global local_id
    handshake_packet = struct.pack('>I12s', 12, "HW4 Protocol")
    sync_hash = hashlib.sha256("This is the synchronization message.".encode())
    sock.send(handshake_packet + sync_hash.digest())
    # The other side should send the exact same thing, but read carefully.
    length_header = sock.recv(4)
    length, = struct.unpack('>I', length_header)
    if length != 12:
        sock.close()
        return False
    protocol_header = sock.recv(length)
    protocol, = struct.unpack('>12s', protocol_header)
    if protocol != "HW4 Protocol":
        sock.close()
        return False
    received_hash = sock.recv(32)
    if received_hash != sync_hash:
        sock.close()
        return False
    # This final step depends on if we are the initiator or the receiver.
    # If we are the initiator, we expect the peer will respond with the correct
    # ID value.
    if initiate:
        received_id = sock.recv(4)
        peer_id, = struct.unpack('>I', received_id)
        if peer_id != target_id:
            sock.close()
            return False
    # Otherwise, if we are the receiver, send back our ID to prove to the peer
    # that we are the one it expects to connect to.
    else:
        id_packet = struct.pack('>I', local_id)
        sock.send(id_packet)

    time.sleep(1)  # Sleep to give other side chance to process.
    return True


# Used for background threads that download updated versions of swarm.
def update_swarm(local_port, s_ip, s_port):
    global swarm
    global lock
    global download_finished
    while not download_finished:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('localhost', local_port))
            sock.connect((s_ip, s_port))
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
            # TODO there may be a better approach then completely replacing the swarm string every time we request a refresh.
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


# For now, do not account for the other side requesting any info, just act as
# if we are the only ones sending.
def handle_responses(sock, indexes_on_peer):
    global lock
    global pieces_remaining
    global pieces
    while len(indexes_on_peer) != 0:
        packet = sock.recv(4)
        length, = struct.unpack(">I", packet[:4])  # check length
        packet = packet + sock.recv(length)  # read rest of packet
        type, payload = Packet.parse_packet(packet)
        # will handle other types later
        if type == Packet.PacketType.PIECE:
            # Make sure the received value matches the hash we have stored.
            piece_hash = hashlib.sha256(payload["piece"])
            if (piece_hash.digest() !=
                    pieces_remaining[(0, payload["packet_index"])]):
                continue

            # If it matches, remove the index from our search and store the piece
            lock.acquire()
            indexes_on_peer.remove(payload["packet_index"])
            pieces_remaining.pop((0, payload["packet_index"]))
            pieces[(0, payload["packet_index"])] = payload["piece"]
            lock.release()
            # Then respond to the sender with a "have" message.
            response_packet = Packet.create_packet(4, payload["packet_index"])
            sock.send(response_packet)


# This attempts to create a connection to the target peer port
def create_sender(local_port, peer_ip, peer_port):
    context = ssl.create_default_context()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as sock:
        with context.wrap_socket(sock, server_hostname=peer_ip) as ssock:
            ssock.bind(('localhost', local_port))
            ssock.connect((peer_ip, peer_port))
            return ssock


# Creates a server side listener on the given port
def create_receiver(port):
    context = ssl.create_default_context()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as sock:
        sock.bind(('localhost', port))
        sock.settimeout(2)
        sock.listen()
        with context.wrap_socket(sock, server_side=True) as ssock:
            return ssock


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
def sharing(local_port):
    global download_finished
    global lock
    global swarm
    global current_peers
    global pieces_remaining
    global exit_peer
    global local_id
    global totalPieces

    while not download_finished:
        if len(current_peers) < 4:
            # Even if we are not using all 4 connections, we cannot download
            # anything if there is nothing left to get
            if len(pieces_remaining) == 0:
                # TODO do we even need receiver mode here?
                print("Waiting to see if we need to handle downloads")
                time.sleep(.5)
            else:  # This where the real work happens, communicate with peer
                # Continue to iterate while we can still form a connection
                while len(current_peers) < 4:
                    # Randomize list of peers, and choose the first one.
                    swarm_peers = list(swarm.keys())
                    random.shuffle(swarm_peers)
                    test_peer = swarm_peers[0]
                    if test_peer != local_id and test_peer not in current_peers.keys():
                        # Try connecting on the 4 primary ports of the target.
                        peer_port, peer_ip = swarm[test_peer]
                        port_offset = 1
                        while port_offset < 5:
                            try:
                                sock = create_sender(local_port, peer_port, peer_ip)
                            except ConnectionRefusedError: # TODO make sure this is actually the error that shows up when a TCP receiver is already communicating with someone else
                                port_offset += 1
                                continue
                            break
                        if port_offset == 5:
                            continue
                        # Now, we have a peer, so try to handshake.
                        connected = handshake(sock)
                        if not connected:
                            continue
                        else:
                            break
                    else:
                        continue

                # At this point, we have successfully handshaked with a peer.
                # Since we are handshaking, send bitfield to peer to determine
                # what pieces they have (though it could be none).
                indexes_on_peer = []
                # Note here that we just use pieces since we assume we only
                # ever download one file type.
                file_id = 0 # TODO again have a better way of setting file id
                current_bitfield = Utility.create_bitfield(pieces, totalPieces)
                bitfield_packet = Packet.create_packet(5, (0, current_bitfield))
                sock.send(bitfield_packet)
                start_time = time.time()
                packet = sock.recv(4)
                end_time = time.time()
                length, = struct.unpack(">I", packet[:4])
                packet = packet + sock.recv(length)
                # It can only be a bitfield, so dont even bother checking type.
                # The receiver will also only ever send back the type we send
                # them, so don't check the file id either.
                _, payload = Packet.parse_packet(packet)
                # Read in all the pieces the other peer has.
                for i in range(totalPieces):
                    if payload["bitfield"][i] == '1':
                        indexes_on_peer.append(i)

                # Start handler thread in the background.
                thread = threading.Thread(target=handle_responses,
                                          args=(sock, indexes_on_peer))
                thread.start()
                while True:
                    if len(indexes_on_peer) == 0:
                        break
                    lock.acquire()
                    # Perform set difference on the indexes on peer with the
                    # pieces we already have so that we only request those we need.
                    set1 = set(indexes_on_peer)
                    set2 = set(p[1] for p in pieces.keys())
                    remaining_indexes = list(set1 - set2)
                    lock.release()
                    for index in remaining_indexes:
                        # Spam requests at target peer
                        sock.send(Packet.create_packet(6, (index, file_id)))
                    time.sleep(2)  # allow some time to receive responses.
                # Sever connection when we have gotten all the files we can.
                sock.close()
                # If we now have all the pieces, downloading is done.
                if len(pieces) < totalPieces:
                    download_finished = True
                    break
                else:
                    continue
        else:
            # TODO optimistic unchoking procedure
            print("waiting to unchoke a peer")

    # TODO figure out exactly what we want to do when we are done downloading
    # probably just be a reciever until the user exits
    while not exit_peer:
        print("waiting to see if a peer wants to download")
        time.sleep(.5)


def main():
    global swarm
    global local_id
    global download_finished
    global exit_peer
    global pieces_remaining
    global totalPieces

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
    parser.add_argument("-S", action="store_true",
                        help="If enabled, this peer acts as a seeder.")

    args = parser.parse_args()

    # TODO have some way of indicating which file we want to download

    # Have this peer "read the metainfo file" upon joining the swarm, ie just
    # read the hashes of each piece so we can check for corruption.
    # For now, we just have the file 0, so we read all the index hashes.
    if not args.S:
        with open(os.path.join("Peer0", "tiger-hashes.txt"), "rb") as file:
            index = 0
            while piece := file.read(32):
                pieces_remaining[(0, index)] = piece
                index += 1
            totalPieces = index
    # Otherwise, let them be populated with (for now) a random 20% of the file.
    # Also currently only gets file 0
    else:
        full_file = Utility.split_file("Peer0", "tiger.jpg")
        full_file_dict = dict(enumerate(full_file))
        while len(pieces) < len(full_file_dict) / 5:
            load_piece = random.choice(list(full_file_dict.keys()))
            pieces[(0, load_piece)] = full_file_dict[load_piece]

    # Receive swarm peers from tracker.
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('localhost', args.p))
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

    time.sleep(1)
    # Start the background tracker sync function.
    update_thread = threading.Thread(target=update_swarm,
                                     args=(args.p, args.i, args.d))
    update_thread.start()

    # TODO setup stuff here
    # Make 4 threads for each of the download streams when we can

    # TODO make a thread to handle optimistic unchoking, should start offset
    # from the others to avoid race condition
    time.sleep(10)

    # Maybe something like this to choose the first random peer to connect to
    # Note that this should probably be done in each peer so they don't need to
    # wait for the others before connecting (just thinking ahead since we said
    # we wanted to add variable times to receiving peers)
    swarm_peers = list(swarm.keys())
    random.shuffle(swarm_peers)  # randomize list order for each peer

    # TODO actual P2P stuff like making the 4 main threads (and sometimes 5th unchoking thread)
    # Assume that we have a peer we want to connect to here(using localhost)
    # 2 recommended ways of making a socket, not sure which is better.
    # context = ssl.create_default_context()
    # with socket.create_connection((swarm[1][1], swarm[1][0])) as sock:
    # with context.wrap_socket(sock, server_hostname=swarm[1][1]) as ssock:
    # print(ssock.version())

    # context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as sock:
    # with context.wrap_socket(sock, server_hostname=swarm[1][1]) as ssock:
    # print(ssock.version())

    # At the end of downloading (or whenever we decided to stop)
    download_finished = True
    exit_peer = True
    try:
        # TODO right now we open a new TCP connection each tracker message, may be inefficient but not sure if we care at the scales we are at
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(('localhost', args.p))
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
