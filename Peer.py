"""File to create and run a Peer in the P2P file share network"""
import argparse
import ipaddress
import os
import random
import socket
import struct
import threading
import hashlib
import time
import Packet
import Utility

# TODO after we get everything working, go back through and make sure we handle potential socket errors and concurrent access
# TODO this primarily means make sure the handle responses has a catch for disconnections so it does not cascade and also that we handle this in the handshake

# Threading event to close down the peer
shutdown_event = threading.Event()

# Global flag to prevent multiple copies
copied_file = False

# Dict holding the information about the other peers in the swarm
swarm = {}

# Id of this peer in the swarm
local_id = 0

# Flag indicating if the user has downloaded their target file yet
download_finished = False  # TODO a little weird that we use a mix of threading events and global flags

# List of current peers
current_peers = []

# Dict of the pieces remaining - (file, index) = bytes
pieces_remaining = {}

# total number of pieces we want to have
total_pieces = 0

# Dict of "downloaded" pieces (file, index) = bytes
pieces = {}

# Lock for managing local swarm list and file info
lock = threading.Lock()


def handshake(sock, target_id=0, initiate=True):
    """Handshake on a socket to confirm we are connected to a valid peer.
    Args:
        sock (socket.socket): Socket to connect to
        target_id (int, optional): ID of target socket. 
            Defaults to 0.
        initiate (bool, optional): Whether this peer initiated connection. 
            Defaults to True.
    Returns:
        bool: True on success, False on fail
    """
    global local_id
    try:
        handshake_packet = struct.pack('>I', 12)
        sync_hash = hashlib.sha256(
            "This is the synchronization message.".encode())
        sock.send(
            handshake_packet + "HW4 Protocol".encode() + sync_hash.digest())

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
        if initiate:
            # we expect the peer will respond with the correct ID value.
            received_id = sock.recv(4)
            peer_id, = struct.unpack('>I', received_id)
            if peer_id != target_id:
                return False
        else:
            # send back our ID to prove to the peer that we are the one it expects to connect to.
            id_packet = struct.pack('>I', local_id)
            sock.send(id_packet)

        time.sleep(1)  # Sleep to give other side chance to process.
        return True
    except ConnectionResetError:
        print("Connection reset by peer")
        # TODO do we need to call sock.close() here?
        return False


def update_swarm(s_ip: str, s_port:int):
    """Used for background threads that download updated versions of swarm.
    Args:
        s_ip (str): ip of tracker
        s_port (int): port of tracker_
    """
    global swarm
    global lock
    global shutdown_event
    while not shutdown_event.is_set():
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
            for i in range(length):
                peer_id, peer_port, peer_ip = (
                    struct.unpack('>HHI', response_packet[i * 8:i * 8 + 8]))
                swarm[peer_id] = peer_port, str(ipaddress.ip_address(peer_ip))
            lock.release()

            sock.close()  # TODO still somewhat inefficient that we open and close a TCP every time
            time.sleep(3)  # For now, update every 3 seconds
        except ConnectionResetError:
            print("Connection reset by tracker")
            shutdown_event.set()
            break
        except ConnectionRefusedError:
            print("Tracker unavailable for connection")
            shutdown_event.set()
            break


# TODO manage handle_responses and hand_requests and make it work for downloader and seeder
def handle_responses(sock: socket.socket, file_identifier, indexes_on_peer, is_seeder=False):
    """Handle responses for seeder and downloader
    Args:
        sock (socket.socket): Socket of peer that is talking to this peer
        file_identifier (int): id of the file being shared over this communication.
        indexes_on_peer (List): List of pieces that are both on the peer and that this peer needs.
        is_seeder (bool): Flag for if this is the seeder. Defaults to False.
    """
    global lock
    global pieces_remaining
    global pieces
    global shutdown_event
    global download_finished
    sent = {}  # format {(packet_index, file_id): time} used for acks
    while is_seeder or len(indexes_on_peer) != 0:
        packet = sock.recv(4)
        length, = struct.unpack(">I", packet[:4])  # check length
        packet = packet + sock.recv(length)  # read rest of packet
        parsed_packet = Packet.parse_packet(packet)
        type, payload = parsed_packet["type"], parsed_packet["payload"]
        print(f"Type: {type}, Payload: {payload}")

        if type == Packet.PacketType.PIECE.name:
            piece_hash = hashlib.sha256(payload["piece"])
            
            lock.acquire()
            if (0, payload["packet_index"]) in pieces_remaining and (piece_hash.digest() != pieces_remaining[(0, payload["packet_index"])]):
                continue
            if payload["packet_index"] in indexes_on_peer:
                indexes_on_peer.remove(payload["packet_index"])
            if (0, payload["packet_index"]) in pieces_remaining:
                pieces_remaining.pop((0, payload["packet_index"]))
                pieces[(0, payload["packet_index"])] = payload["piece"]
            lock.release()
            
            response_packet = Packet.create_packet(4, payload["packet_index"],
                                                   0)
            sock.send(response_packet)

            if not is_seeder and len(indexes_on_peer) != 0:
                sock.send(Packet.create_packet(6, indexes_on_peer[0],
                                               file_identifier))
        elif type == Packet.PacketType.HAVE.name:
            packet_index, file_id = payload["packet_index"], payload["file_id"]
            if (packet_index, file_id) in sent:
                # Received ack 
                sent.pop((packet_index, file_id))
            else:
                # TODO handle update pieces only when basically everything else is done
                # The other peer is simply announcing to me that they now have this piece
                print("Unimplemented")
        elif type == Packet.PacketType.REQUEST.name:
            packet_index, file_id = payload["packet_index"], payload["file_id"]
            piece_to_send = pieces[(file_id, packet_index)]
            response_packet = Packet.create_packet(7, packet_index,
                                                   piece_to_send)
            sock.send(response_packet)
            sent[(packet_index, file_id)] = time.time()
            if is_seeder and len(indexes_on_peer) != 0:
                sock.send(
                    Packet.create_packet(6, indexes_on_peer[0], file_id))
                # Unlike with the sender where we carefully track the indexes
                # on peer and only remove the item on confirmation, since the
                # seeder can only request a piece upon receiving a download
                # request, more aggressively request pieces to get what we can
                # while we are connected.
                indexes_on_peer.pop(0)

        elif type == Packet.PacketType.NOT_INTERESTED.name:
            # Clear indexes on peer so the outer loop stops looping.
            indexes_on_peer.clear()
            break

        # Check if we should exit communication
        if shutdown_event.is_set() or download_finished:
            sock.send(Packet.create_packet(3))
            time.sleep(2)
            break

        # Check if an ack hit a timeout
        if len(sent) > 0:
            packet_index, file_id = min(sent, key=sent.get)
            oldest_time = sent[(packet_index, file_id)]
            if oldest_time - time.time() > 2:
                # The oldest unacked piece took > 2 seconds, resend piece
                sent.pop((packet_index, file_id))
                piece_to_send = pieces[(file_id, packet_index)]
                response_packet = Packet.create_packet(7, packet_index,
                                                       piece_to_send)
                sock.send(response_packet)
                sent[(packet_index, file_id)] = time.time()

        # Refresh indexes on peer to ensure we only request things we need.
        set1 = set(indexes_on_peer)
        lock.acquire()
        set2 = set(p[1] for p in pieces.keys() if p[0] == file_identifier)
        lock.release()
        indexes_on_peer = list(set1 - set2)

# TODO fix this when I get around to generating certificates and key files
def create_downloader(peer_ip: str, peer_port: int):
    """Create a connection to target peer port
    Args:
        peer_ip (str): Peer IP
        peer_port (int): Peer Port

    Returns:
        socket: Socket that is a connection to peer port
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    # TODO if we ever start getting errors about 2 things not being able to bind on the same port + protocol, comment this out or qualify with an IP check
    if peer_ip != '127.0.0.1' and peer_ip != local_ip:
        sock.bind(('localhost', local_port))
    ssock = context.wrap_socket(sock, server_hostname=hostname)
    ssock.connect((peer_ip, peer_port))
    return ssock


def create_seeder(port):
    """Creates a server side listener on given port
    Args:
        port (int): Peer port number
    Returns:
        socket: _description_
    """
    global shutdown_event
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as sock:
        sock.bind(('localhost', port))
        sock.settimeout(1)
        sock.listen()
        # TODO make sure this does not cause any issues when a peer tries to connect
        while True:
            try:
                conn, _ = sock.accept()
                return conn
            except socket.timeout:
                if shutdown_event.is_set():
                    sock.close()
                    return None


def seeder(local_port):
    """Seeder peer thread
    Args:
        local_port (int): port
    """
    global pieces
    global shutdown_event
    while not shutdown_event.is_set():
        peer_sock = create_seeder(local_port)
        if peer_sock is None:
            break
        connected = handshake(peer_sock, initiate=False)
        if not connected:
            continue
        try:
            # track what file the pieces are on
            indexes_on_peer = []
            packet = peer_sock.recv(4)
            length, = struct.unpack(">I", packet[:4])
            packet = packet + peer_sock.recv(length)
            parsed_packet = Packet.parse_packet(packet)
            payload = parsed_packet["payload"]
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

            file_len = len(payload["bitfield"])
            seeder_bitfield = Utility.create_bitfield(relevant_pieces,
                                                      file_len)
            bitfield_packet = Packet.create_packet(5,
                                                   file_id, seeder_bitfield)
            peer_sock.send(bitfield_packet)
            # Now normal communication occurs

            # Update the list of indexes on peer to only include items we need.
            set1 = set(indexes_on_peer)
            lock.acquire()
            set2 = set(p[1] for p in pieces.keys() if p[0] == file_id)
            lock.release()
            indexes_on_peer = list(set1 - set2)
            handle_responses(peer_sock, file_id, indexes_on_peer,
                             is_seeder=True)
        except ConnectionResetError:
            print("Connection reset by peer.")
        peer_sock.close()
    print("[Seeder] Shutting down.")


# Big function for handling download thread behavior
def downloader(local_port, output_file):
    """Downloader peer thread
    Args:
        local_port (int): port number corresponding to this channel.
    """
    global download_finished
    global lock
    global swarm
    global current_peers
    global pieces_remaining
    global local_id
    global total_pieces
    global copied_file

    while not download_finished and not shutdown_event.is_set():
        # Make sure all the lists are synced        
        if len(pieces_remaining) == 0 and len(pieces) == total_pieces:
            download_finished = True
            break

        if len(pieces_remaining) == 0:
            print("Waiting to see if we need to handle downloads")
            time.sleep(.5)
            continue
        else:  
            test_peer = 0
            while not download_finished and not shutdown_event.is_set():
                # Randomize list of peers, and choose the first one.
                swarm_peers = list(swarm.keys())
                random.shuffle(swarm_peers)
                test_peer = swarm_peers[0]
                if test_peer != local_id and test_peer not in current_peers:
                    # Claim the peer so no one else tries
                    lock.acquire()
                    if test_peer in current_peers: # TODO maybe we can combine this and the above check
                        lock.release()
                        continue
                    # Claim the peer by putting in the shared list.
                    current_peers.append(test_peer)
                    lock.release()
                    # Try connecting on the 4 primary ports of the target.
                    peer_port, peer_ip = swarm[test_peer]
                    port_offset = 0
                    while port_offset < 4:
                        try:
                            sock = create_downloader(peer_ip,
                                                     peer_port + port_offset)
                            break
                        except ConnectionRefusedError:
                            port_offset += 1
                            continue
                    if port_offset == 4:
                        lock.acquire()
                        current_peers.remove(test_peer)
                        lock.release()
                        continue

                    connected = handshake(sock, test_peer)
                    if not connected:
                        sock.close()  # TODO make sure there is no error for closing a socket that encountered an error.
                        lock.acquire()
                        current_peers.remove(test_peer)
                        lock.release()
                        continue
                    else:
                        break
                else:
                    continue
            if download_finished or shutdown_event.is_set():
                break
            print("started download")
            # Successful handshake with peer
            indexes_on_peer = []
            # Note here that we just use pieces since we assume we only
            # ever download one file type.
            file_id = 0  # TODO again have a better way of setting file id
            current_bitfield = Utility.create_bitfield(pieces,
                                                       total_pieces)
            bitfield_packet = Packet.create_packet(5,
                                                   file_id,
                                                   current_bitfield)
            try:
                sock.send(bitfield_packet)
                packet = sock.recv(4)
                length, = struct.unpack(">I", packet[:4])
                packet = packet + sock.recv(length)

                parsed_packet = Packet.parse_packet(packet)
                payload = parsed_packet["payload"]
                # Read in all the pieces the other peer has.
                for i in range(total_pieces):
                    if payload["bitfield"][i] == '1':
                        indexes_on_peer.append(i)
                # Find what pieces downloader needs from peer
                set1 = set(indexes_on_peer)
                lock.acquire()
                set2 = set(p[1] for p in pieces.keys())
                lock.release()
                indexes_on_peer = list(set1 - set2)
                # If there is nothing on the peer that we want, disconnect.
                if len(indexes_on_peer) == 0:
                    sock.send(Packet.create_packet(3))
                    lock.acquire()
                    current_peers.remove(test_peer)
                    lock.release()
                    sock.close()
                    continue
                # Initial request
                sock.send(Packet.create_packet(6, indexes_on_peer[0], file_id))
                handle_responses(sock, file_id, indexes_on_peer)
                # Send not interested when done
                sock.send(Packet.create_packet(3))
                time.sleep(1)
            except ConnectionResetError:
                print("Connection reset by peer")
            lock.acquire()
            current_peers.remove(test_peer)
            lock.release()
            sock.close()
    # Don't try to download a file if we are stopping via a CLI exit.
    if shutdown_event.is_set():
        return
    lock.acquire()
    if not copied_file:
        copied_file = True
        assemble_pieces = Utility.sort_by_index(pieces)
        Utility.reassemble_file(assemble_pieces, "output", output_file)
        print(f"Successfully Downloaded {output_file} to output/{output_file}")
    lock.release()
    # TODO do we want the user to be able to enter a new file? Probably not unless we have extra time
    if not shutdown_event.is_set():
        seeder(local_port)


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
                print(
                    f"{len(pieces)}/{total_pieces} ({len(pieces) / total_pieces * 100}%) downloaded\n")
        elif cmd == 'prog':
            # TODO we can take this out or leave it, just using it to see if the seeder gets any new pieces during a transmission.
            print(f"{len(pieces)}")
    print("[CLI] Shutdown complete.")


def main():
    """Main function to run file share Peer"""
    global swarm
    global local_id
    global local_ip
    global pieces_remaining
    global total_pieces
    global shutdown_event

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
    parser.add_argument("-f", metavar="file", type=str,
                        required=True, help="file for peer.")
    parser.add_argument("-m", nargs='*', type=int, default=None, help="Optional list of missing pieces for this peer.")
    args = parser.parse_args()

    # TODO have some way of indicating which file we want to download
    # For now, we just have the file 0, so we read all the index hashes.
    first_port, tracker_ip, tracker_port, seeder_bool = args.p, args.i, args.d, args.S
    missing_pieces, p2p_file = args.m, args.f
    
    #Check if {p2p_file}-hashes.txt exists in hashes folder. If not, create it
    base_name = os.path.splitext(p2p_file)[0] # strips extension
    hash_path = os.path.join("hashes", f"{base_name}-hashes.txt")
    if not os.path.isfile(hash_path):
        Utility.create_hash_file(p2p_file)
    
    with open(hash_path, "rb") as file:
        index = 0
        while piece_hash := file.read(32):
            pieces_remaining[(0, index)] = piece_hash
            index += 1
        total_pieces = index
        
    if seeder_bool:
        file_path = os.path.join("input", p2p_file)
        if not os.path.isfile(file_path):
            print(f"Error: File '{args.file}' does not exist so seeder can't use.")
            return
        file_split = Utility.split_file("input", p2p_file)
        full_file_dict = dict(enumerate(file_split))
        if missing_pieces:
            file_dict = {key: full_file_dict[key] for key in full_file_dict if key not in missing_pieces}
        else:
        # Get a random 95% of the pieces
            sampled_keys = random.sample(list(full_file_dict.keys()),
                                        int(len(full_file_dict) * 0.95))

            # TODO this is the testing scheme I used to ensure that all of the files would be perfectly evenly distributed among 5 peers
            #sampled_keys = list(range(int(len(full_file_dict) * .8), int(len(full_file_dict) * 1)))
            file_dict = {key: full_file_dict[key] for key in sampled_keys}

        print("Missing Values: ",
              Utility.find_missing_values(list(file_dict.keys())))

        while len(pieces) < len(file_dict):
            load_piece = random.choice(list(file_dict.keys()))
            pieces[(0, load_piece)] = file_dict[load_piece]
        # TODO this is an addition I just made that we should have thought of earlier
        # TODO the seeders are also supposed to be clients as well, therefore, they should have their pieces remaining populated with the hashes
        # TODO as well so they can verify they are being sent real pieces (ie everything needs to read the meta info file before it joins the swarm)

    # Receive swarm peers from tracker.
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((tracker_ip, tracker_port))
        # Initial message should just be code 0, id = given port range
        send_packet = struct.pack('>BH', 0, first_port)
        send_hash = hashlib.sha256(send_packet)
        sock.send(send_packet + send_hash.digest())
        # Make sure we get a correct hash
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

        local_id, length = struct.unpack('>HH', response_packet[:4])
        while True:
            response_packet = sock.recv(8 * length + 32)
            verify_hash = hashlib.sha256(response_packet[:8 * length])
            if verify_hash.digest() != response_packet[8 * length:]:
                sock.send(send_packet + send_hash.digest())
            else:
                sock.send(b"\0")
                break

        # Confirmed swarm is received, read it.
        for i in range(length):
            peer_id, peer_port, peer_ip = (
                struct.unpack('>HHI', response_packet[i * 8:i * 8 + 8]))
            swarm[peer_id] = peer_port, str(ipaddress.ip_address(peer_ip))

        sock.close()
    except ConnectionResetError:
        print("Connection reset by tracker")
    except ConnectionRefusedError:
        print("Tracker unavailable for connection")

    time.sleep(1)
    # Start the background tracker sync function.
    update_thread = threading.Thread(target=update_swarm,
                                     args=(tracker_ip, tracker_port))
    update_thread.start()

    threads = []
    if not seeder_bool:
        for i in range(4):
            threads.append(
                threading.Thread(target=downloader, args=(first_port + i, p2p_file,)))
            threads[i].start()

        # Also make a seeder thread that can accept communication from other
        # downloaders. Only one port is used since the number of seeders is
        # expected to outnumber downloaders, and most downloaders will leave
        # right after they finish downloading.
        threads.append(
            threading.Thread(target=seeder, args=(first_port + 4,)))
        threads[4].start()
    # For a seeder only 4 ports of connection.
    else:
        for i in range(4):
            threads.append(
                threading.Thread(target=seeder, args=(first_port + i,)))
            threads[i].start()

    # TODO minor problem here for the downloader is that if the exit event is set by finishing a download, we will never exit since we wait for input
    # TODO may have solved this by forcing the user to exit manually anyway
    cli(shutdown_event, seeder_bool)

    for thread in threads:
        thread.join()

    try:
        # TODO right now we open a new TCP connection each tracker message, may be inefficient but not sure if we care at the scales we are at
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((tracker_ip, tracker_port))
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
