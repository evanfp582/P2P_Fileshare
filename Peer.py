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

#Threading event to close down the peer
shutdown_event = threading.Event()

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
total_pieces = 0
# Dict of "downloaded" pieces (file, index) = bytes
pieces = {}

# Lock for managing local swarm list and file info
lock = threading.Lock()

# Mock data to test cli
mock_file = [bytes([i] * 128) for i in range(5)]
pieces = {(0,0): mock_file[0], (0,2): mock_file[2], (0,4): mock_file[4]} 
total_pieces = 5
pieces_remaining = 2

# Does a handshake on a socket connection and closes it on failure
# After conducting the handshake, returns True on success, False otherwise.
def handshake(sock, target_id=0, initiate=True):
    global local_id
    handshake_packet = struct.pack('>I', 12)
    sync_hash = hashlib.sha256("This is the synchronization message.".encode())
    sock.send(handshake_packet + "HW4 Protocol".encode() + sync_hash.digest())
    # The other side should send the exact same thing, but read carefully.
    length_header = sock.recv(4)
    length, = struct.unpack('>I', length_header)
    if length != 12:
        return False
    protocol_header = sock.recv(length)
    if protocol_header.decode() != "HW4 Protocol":
        return False
    received_hash = sock.recv(32)
    if received_hash != sync_hash.digest():
        return False
    # This final step depends on if we are the initiator or the seeder.
    # If we are the initiator, we expect the peer will respond with the correct
    # ID value.
    if initiate:
        received_id = sock.recv(4)
        peer_id, = struct.unpack('>I', received_id)
        if peer_id != target_id:
            return False
    # Otherwise, if we are the seeder, send back our ID to prove to the peer
    # that we are the one it expects to connect to.
    else:
        id_packet = struct.pack('>I', local_id)
        sock.send(id_packet)

    time.sleep(1)  # Sleep to give other side chance to process.
    return True


# Used for background threads that download updated versions of swarm.
def update_swarm(s_ip, s_port):
    global swarm
    global lock
    global download_finished
    while not download_finished:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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
                    struct.unpack('>HHI', response_packet[i * 8:i * 8 + 8]))
                swarm[peer_id] = peer_port, str(ipaddress.ip_address(peer_ip))
            lock.release()

            print("swarm: ", swarm)
            sock.close()
            time.sleep(3)  # For now, update every 3 seconds
        except ConnectionResetError:
            print("Connection reset by server")
        except ConnectionRefusedError:
            print("Server unavailable for connection")


#TODO manage handle_responses and hand_requests and make it work for downloader and seeder
def handle_responses(sock, indexes_on_peer={}, is_seeder=False):
    """Handle responses for seeder and downloader
    Args:
        sock (socket): Socket of peer that is talking to this peer
        indexes_on_peer (dict): Set of pieces that are both on the peer and that this peer needs. Defaults to Empty Dict
        is_seeder (bool): Flag for if this is the seeder. Defaults to False.
    """
    global lock
    global pieces_remaining
    global pieces
    # TODO make sure this condition is handled properly so we never have cases where it keeps going after the outer loop stops (ie indexes_on_peer not emptied properly)
    sent = {} # format {(packet_index, file_id): time} used for acks
    while is_seeder or len(indexes_on_peer) != 0:
        packet = sock.recv(4)
        length, = struct.unpack(">I", packet[:4])  # check length
        packet = packet + sock.recv(length)  # read rest of packet
        parsed_packet = Packet.parse_packet(packet)
        type, payload = parsed_packet["type"], parsed_packet["payload"]
        print(f"Type: {type}, Payload: {payload}")
        # will handle other types later
        if type == Packet.PacketType.PIECE.name:
            # Make sure the received value matches the hash we have stored.
            piece_hash = hashlib.sha256(payload["piece"])
            if (piece_hash.digest() !=
                    pieces_remaining[(0, payload["packet_index"])]):
                continue
            lock.acquire()
            indexes_on_peer.remove(payload["packet_index"])
            # Only update the global lists if the piece is still needed.
            if (0, payload["packet_index"]) in pieces_remaining:
                pieces_remaining.pop((0, payload["packet_index"]))
                pieces[(0, payload["packet_index"])] = payload["piece"]
            lock.release()
            # Then respond to the downloader with a "have" message.
            response_packet = Packet.create_packet(4, payload["packet_index"])
            sock.send(response_packet)
        elif type == Packet.PacketType.HAVE.name:
            print("Received HAVE")
            packet_index, file_id = payload["packet_index"], payload["file_id"]
            if (packet_index, file_id) in sent:
                #Received ack
                sent.pop((packet_index, file_id))
            else:
                #The other peer is simply announcing to me that they now have this piece
                print("Unimplemented")
        elif type == Packet.PacketType.REQUEST.name:
            # Since peers never lose packets,
            # (file_id, packet_index) in pieces: is always True
            packet_index, file_id = payload["packet_index"], payload["file_id"]
            piece_to_send = pieces[(file_id, packet_index)]
            response_packet = Packet.create_packet(7, packet_index, piece_to_send)
            sock.send(response_packet)
            sent[(packet_index, file_id)] = time.time()
        elif type == Packet.PacketType.NOT_INTERESTED.name:
            # This is the seeder and the downloader is not interested
            # TODO elegantly quit
            print("Unimplemented")
        
        #Check if an ack hit a timeout        
        if len(sent) > 0:
            packet_index, file_id = min(sent, key=sent.get)
            oldest_time = sent[(packet_index, file_id)]
            if oldest_time-time.time() > 5:
                #The oldest unacked piece took > 5 seconds, resend piece
                sent.pop((packet_index, file_id))
                piece_to_send = pieces[(file_id, packet_index)]
                response_packet = Packet.create_packet(7, packet_index, piece_to_send)
                sock.send(response_packet)
                sent[(packet_index, file_id)] = time.time()
            

# This attempts to create a connection to the target peer port
def create_downloader(local_port, peer_ip, peer_port):
    #context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    #print(context.get_ciphers())
    #context = ssl.create_default_context()

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    #with context.wrap_socket(sock, server_hostname=peer_ip) as ssock:
    sock.bind(('localhost', local_port))
    sock.connect((peer_ip, peer_port))
    return sock


# Creates a server side listener on the given port
def create_seeder(port):
    #context = ssl.create_default_context()
    #context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    #print(context.get_ciphers())

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as sock:
        sock.bind(('localhost', port))
        sock.listen()
        #with context.wrap_socket(sock, server_hostname='localhost') as ssock:
        conn, addr = sock.accept()
        return conn
            

# work in progress function for seeder thread
def seeder(local_port):
    global pieces
    # Wait until some downloader comes along
    # TODO do we want seeders to have some way to shut off or do they go infinitely like the tracker -Evan I am thinking infinitely like the tracker until the user just force stops it
    while not shutdown_event.is_set():
        peer_sock = create_seeder(local_port)
        # Handshake with new peer.
        connected = handshake(peer_sock)
        if not connected:
            continue
        # Then, do the reverse process of the downloader.
        # Main difference is that we need to track what file the pieces are on
        # since we are not downloading a single file.
        indexes_on_peer = []
        packet = peer_sock.recv(4)
        length, = struct.unpack(">I", packet[:4])
        packet = packet + peer_sock.recv(length)
        _, payload = Packet.parse_packet(packet)
        file_id = payload["file_id"]
        # Read in all the pieces the other peer has.
        for i in range(len(payload["bitfield"])):
            if payload["bitfield"][i] == '1':
                indexes_on_peer.append(i)

        # The downloader will only broadcast the file type it has/needs, so
        # take the set of pieces we have for that file.
        relevant_pieces = {}
        for p in pieces.keys():
            if p[0] == file_id:
                relevant_pieces[p] = pieces[p]

        # This seeder does not know the full length of the file, but can get it
        # from the bitfield sent by the downloader
        file_len = len(payload["bitfield"])
        seeder_bitfield = Utility.create_bitfield(relevant_pieces, file_len)
        bitfield_packet = Packet.create_packet(5,
                                               (file_id, seeder_bitfield))
        peer_sock.send(bitfield_packet)

        # Now normal communication occurs
        # Should obviously be able to handle request messages( those are easy
        # just send back the piece it requested), though we also need to check
        # if we get a have in response and resend after some period if we do
        # not get one.
        # TODO how do we want the seeder to download from the downloader? Should it just get any pieces the downloader has that it does not during the communication?
        # TODO how will we handle choking and unchoking, though this also relates heavily to the downloader?
    print("[Seeder] Shutting down.")

# Big function for handling download thread behavior
def downloader(local_port):
    global download_finished
    global lock
    global swarm
    global current_peers
    global pieces_remaining
    global exit_peer
    global local_id
    global total_pieces

    while not download_finished or not shutdown_event.is_set():
        # Make sure all the lists are synced
        if len(pieces_remaining) == 0 and len(pieces) == total_pieces:
            download_finished = True
            break
        if len(current_peers) < 4:
            # Even if we are not using all 4 connections, we cannot download
            # anything if there is nothing left to get
            if len(pieces_remaining) == 0:
                # TODO do we even need seeder mode here?
                print("Waiting to see if we need to handle downloads")
                time.sleep(.5)
            else:  # This where the real work happens, communicate with peer
                # Continue to iterate while we can still form a connection
                test_peer = 0
                while len(current_peers) < 4:
                    # Randomize list of peers, and choose the first one.
                    swarm_peers = list(swarm.keys())
                    random.shuffle(swarm_peers)
                    test_peer = swarm_peers[0]
                    if test_peer != local_id and test_peer not in current_peers.keys():
                        # Claim the peer so no one else tries
                        lock.acquire()
                        if test_peer in current_peers.keys() or len(
                                current_peers) >= 4:
                            lock.release()
                            continue
                        # If so, claim the peer by putting in the shared dict.
                        current_peers[test_peer] = -1.0
                        lock.release()
                        # Try connecting on the 4 primary ports of the target.
                        peer_port, peer_ip = swarm[test_peer]
                        port_offset = 0
                        while port_offset < 4:
                            try:
                                sock = create_downloader(local_port,
                                                     peer_ip,
                                                     peer_port + port_offset)
                                break
                            except ConnectionRefusedError:  # TODO make sure this is actually the error that shows up when a TCP seeder is already communicating with someone else
                                port_offset += 1
                                sock.close()
                                continue
                        if port_offset == 4:
                            lock.acquire()
                            current_peers.pop(test_peer)
                            lock.release()
                            continue
                        # TODO this behavior currently makes it so we can only have one peer to peer connection for each peer. Do we want to allow parallel pipelining? -Evan I do not think that is necessary
                        # Now, we have a peer, so try to handshake.
                        connected = handshake(sock)
                        if not connected:
                            sock.close()
                            # If for some reason handshake failed, release peer
                            lock.acquire()
                            current_peers.pop(test_peer)
                            lock.release()
                            continue
                        else:  # Otherwise move to further sending steps.
                            break
                    else:
                        continue

                if len(current_peers) >= 4:
                    continue
                # At this point, we have successfully handshaked with a peer.
                # Since we are handshaking, send bitfield to peer to determine
                # what pieces they have (though it could be none).
                indexes_on_peer = []
                # Note here that we just use pieces since we assume we only
                # ever download one file type.
                file_id = 0  # TODO again have a better way of setting file id
                current_bitfield = Utility.create_bitfield(pieces, total_pieces)
                bitfield_packet = Packet.create_packet(5,
                                                       (file_id,
                                                        current_bitfield))
                sock.send(bitfield_packet)
                start_time = time.time()
                packet = sock.recv(4)
                end_time = time.time()
                # Store the "RTT" of this particular peer.
                lock.acquire()
                current_peers[test_peer] = end_time - start_time
                lock.release()
                length, = struct.unpack(">I", packet[:4])
                packet = packet + sock.recv(length)
                # It can only be a bitfield, so dont even bother checking type.
                # The seeder will also only ever send back the type we send
                # them, so don't check the file id either.
                _, payload = Packet.parse_packet(packet)
                # Read in all the pieces the other peer has.
                for i in range(total_pieces):
                    if payload["bitfield"][i] == '1':
                        indexes_on_peer.append(i)

                # Perform set difference on the indexes on peer with the
                # pieces we already have so that we only request those we need.
                set1 = set(indexes_on_peer)
                set2 = set(p[1] for p in pieces.keys())
                indexes_on_peer = list(set1 - set2)
                # Start handler thread in the background.
                thread = threading.Thread(target=handle_responses,
                                          args=(sock, indexes_on_peer))
                thread.start()
                while True:
                    if len(indexes_on_peer) == 0:
                        break
                    lock.acquire()
                    set1 = set(indexes_on_peer)
                    set2 = set(p[1] for p in pieces.keys())
                    remaining_indexes = list(set1 - set2)
                    lock.release()
                    for index in remaining_indexes:
                        # Spam requests at target peer
                        sock.send(Packet.create_packet(6, (index, file_id)))
                    time.sleep(2)  # allow some time to receive responses.
                # Sever connection when we have gotten all the files we can.
                lock.acquire()
                current_peers.pop(test_peer)
                lock.release()
                sock.close()
        else:
            # TODO optimistic unchoking procedure
            print("waiting to unchoke a peer")

    # for now
    exit_peer = True
    # TODO figure out exactly what we want to do when we are done downloading
    # probably just be a seeder until the user exits
    while not exit_peer:
        print("waiting to see if a peer wants to download")
        time.sleep(.5)

def cli(shutdown_event, is_seeder: bool):
    """Runs the command line interface for a peer
    Args:
        is_seeder (bool): Changes output depending on if 
            current peer is seeder or a downloader
    """
    print("Welcome to Bit Torrent")
    if is_seeder: 
            print("Running Seeder Peer")
            print("Type 'exit' to quit")
    else:
        print("Running Downloader Peer")
        print("Type 'exit' to quit or 'prog' to see download progress")
    while not shutdown_event.is_set():
        cmd = input("[CLI]: ").strip().lower()
        if cmd == 'exit':
            shutdown_event.set()
            break
        elif cmd == 'prog' and not is_seeder:
            if download_finished:
                print("Download Finished")
            else:
                print("Download in Progress")
                print(f"Pieces Remaining: {pieces_remaining}")
                print(f"{len(pieces)}/{total_pieces} ({len(pieces)/total_pieces * 100}%) downloaded\n")
    print("[CLI] Shutdown complete.")


def main():
    global swarm
    global local_id
    global download_finished
    global exit_peer
    global pieces_remaining
    global total_pieces

    parser = argparse.ArgumentParser(
        prog="Peer",
        description="Acts as a peer in the P2P swarm.")
    parser.add_argument("-p", metavar="port range", type=int, default=9000,
                        help="Port range used by this peer. For a given i, "
                             "i to i + 4 are used for peers.")
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
            total_pieces = index
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
                struct.unpack('>HHI', response_packet[i*8:i*8 + 8]))
            swarm[peer_id] = peer_port, str(ipaddress.ip_address(peer_ip))

        sock.close()
    except ConnectionResetError:
        print("Connection reset by server")
    except ConnectionRefusedError:
        print("Server unavailable for connection")

    time.sleep(1)
    # Start the background tracker sync function.
    update_thread = threading.Thread(target=update_swarm,
                                     args=(args.i, args.d))
    update_thread.start()

    cli_thread = threading.Thread(target=cli, args=(shutdown_event, args.S))
    cli_thread.start()
    
    threads = []
    if not args.S:
        for i in range(4):
            threads.append(
                threading.Thread(target=downloader, args=(args.p + i,)))
            threads[i].start()

        # TODO make a thread to handle optimistic unchoking, should start offset
        # from the others to avoid race condition
    else:
        for i in range(4):
            threads.append(
                threading.Thread(target=seeder, args=(args.p + i,)))
            threads[i].start()
    # TODO again what is the exit condition for a seeder here? Maybe allow for user input that allows you to print the current pieces or exit by setting the global flags

    for thread in threads:
        thread.join()

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
