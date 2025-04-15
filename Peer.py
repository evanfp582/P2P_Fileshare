"""File to create and run a Peer in the P2P file share network"""
import argparse
import ipaddress
import math
import os
import random
import socket
import ssl
import struct
import threading
import hashlib
import time
import Packet
import Utility

# TODO after we get everything working, go back through and make sure we handle potential socket errors and concurrent access
# TODO this primarily means make sure the handle responses has a catch for disconnections so it does not cascade and also that we handle this in the handshake

# Threading event to close down the peer.
shutdown_event = threading.Event()

# Global flag to prevent multiple copies.
copied_file = False

# Dict holding the information about the other peers in the swarm.
swarm = {}

# Id and ip of this peer in the swarm.
local_id = 0
local_ip = ''

# Flag indicating if the user has downloaded their target file yet.
download_finished = False  # TODO a little weird that we use a mix of threading events and global flags, I would prefer to remove the threading event of the 2

# List of current peers.
current_peers = []

# Dict of the pieces remaining - (file, index) = bytes.
pieces_remaining = {}

# total number of pieces we want to have.
total_pieces = 0

# Dict of "downloaded" pieces (file, index) = bytes.
pieces = {}

# Lock for managing local swarm list and file info.
lock = threading.Lock()


def handshake(sock, target_id=0, initiate=True):
    """Handshake on a socket to confirm we are connected to a valid peer.
    Args:
        sock (socket.socket): Socket to connect to.
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
            # We expect the peer will respond with the correct ID value.
            received_id = sock.recv(4)
            peer_id, = struct.unpack('>I', received_id)
            if peer_id != target_id:
                return False
        else:
            # Send back our ID to prove we match the tracker.
            id_packet = struct.pack('>I', local_id)
            sock.send(id_packet)

        time.sleep(1)  # Sleep to give other side chance to process
        return True
    except ConnectionResetError:
        print("Connection reset by peer.")
        return False
    except ssl.SSLError:
        print("Communication with peer failed.")
        return False
    except struct.error:
        print("Communication was severed early by peer.")
        return False
    except TimeoutError:
        print("Peer became unresponsive.")
        return False


def update_swarm(s_ip, s_port):
    """Used for background threads that maintains an updated versions of swarm.
    Args:
        s_ip (str): ip of tracker
        s_port (int): port of tracker
    """
    global swarm
    global lock
    global shutdown_event
    while not shutdown_event.is_set():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((s_ip, s_port))
            # Refresh message is code 1, id 0.
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

            sock.close()
            time.sleep(3)  # For now, update every 3 seconds
        except ConnectionResetError:
            print("Connection reset by tracker.")
            shutdown_event.set()
            break
        except ConnectionRefusedError:
            print("Tracker unavailable for connection.")
            shutdown_event.set()
            break
        except struct.error:
            print("Communication was severed early by tracker.")
            shutdown_event.set()
            break
        except TimeoutError:
            print("Tracker became unresponsive.")
            shutdown_event.set()
            break


def handle_responses(sock, file_identifier, indexes_on_peer, is_seeder=False):
    """Handle responses for seeder and downloader
    Args:
        sock (socket.socket): Socket between this peer and another
        file_identifier (int): id of the file being shared over this communication.
        indexes_on_peer (list): Pieces that are needed by this peer and found on the current connected peer.
        is_seeder (bool): Flag for if this is the seeder. Defaults to False.
    """
    global lock
    global pieces_remaining
    global pieces
    global shutdown_event
    global download_finished
    sent = {}  # format {(packet_index, file_id): time} ack dictionary
    lock.acquire()
    prev_pieces = set(p[1] for p in pieces.keys() if p[0] == file_identifier)
    lock.release()
    while is_seeder or len(indexes_on_peer) != 0:
        packet = sock.recv(4)
        length, = struct.unpack(">I", packet[:4])  # check length
        packet = packet + sock.recv(length)  # read rest of packet
        parsed_packet = Packet.parse_packet(packet)
        type, payload = parsed_packet["type"], parsed_packet["payload"]
        # print(f"Type: {type}, Payload: {payload}") # TODO What do we want to print out while this is going?

        if type == Packet.PacketType.PIECE.name:
            piece_hash = hashlib.sha256(payload["piece"])

            current_ack = file_identifier, payload["packet_index"]
            lock.acquire()
            if (current_ack in pieces_remaining
                    and 
                (piece_hash.digest() != pieces_remaining[current_ack])):
                continue
            if payload["packet_index"] in indexes_on_peer:
                indexes_on_peer.remove(payload["packet_index"])
            if (current_ack) in pieces_remaining:
                pieces_remaining.pop((current_ack))
                pieces[current_ack] = payload["piece"]
                prev_pieces.add(payload["packet_index"])
            lock.release()

            response_packet = Packet.create_packet(4, payload["packet_index"],
                                                   file_identifier)
            sock.send(response_packet)

            if not is_seeder and len(indexes_on_peer) != 0:
                sock.send(Packet.create_packet(6, indexes_on_peer[0],
                                               file_identifier))
        elif type == Packet.PacketType.HAVE.name:
            packet_index, file_id = payload["packet_index"], payload["file_id"]
            if (packet_index, file_id) in sent:
                sent.pop((packet_index, file_id))
            else: # Other peer is announcing they have a piece
                indexes_on_peer.append(packet_index)
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
                indexes_on_peer.pop(0)

        elif type == Packet.PacketType.NOT_INTERESTED.name:
            # Clear indexes on peer so the outer loop stops looping.
            indexes_on_peer.clear()
            break

        # Check if we should exit communication.
        if shutdown_event.is_set() or (not is_seeder and download_finished):
            sock.send(Packet.create_packet(3))
            time.sleep(1)
            break

        # Check if an ack hit a timeout.
        if len(sent) > 0:
            packet_index, file_id = min(sent, key=sent.get)
            oldest_time = sent[(packet_index, file_id)]
            if oldest_time - time.time() > 2:
                # The oldest unacked piece took > 2 seconds, resend piece.
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
        new_pieces = list(set2 - prev_pieces)
        if not len(new_pieces) == 0:
            # Announce to peer new pieces
            for index in new_pieces:
                response_packet = Packet.create_packet(4, index,
                                                       file_identifier)
                sock.send(response_packet)
        prev_pieces = set2


def create_downloader(local_port, peer_ip, peer_port):
    """Create a Downloader socket for a peer
    Args:
        local_port (int): Port number for Downloader.
        peer_ip (str): Peer IP.
        peer_port (int): Peer port.
    Returns:
        socket.socket: Socket for Downloader.
    """
    hostname = "P2Pproject"
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations('cert.pem')

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    ssock = context.wrap_socket(sock, server_hostname=hostname)
    ssock.connect((peer_ip, peer_port))
    return ssock


def create_seeder(port):
    """Creates a Seeder socket for a peer.
    Args:
        port (int): Port number for Seeder.
    Returns:
        socket.socket: Socket for Seeder.
    """
    global shutdown_event
    global local_ip
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain('cert.pem', 'key.pem')
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    sock.bind((local_ip, port))
    sock.settimeout(1)
    sock.listen()
    ssock = context.wrap_socket(sock, server_side=True)
    while True:
        try:
            conn, _ = ssock.accept()
            return conn
        except socket.timeout:
            if shutdown_event.is_set():
                ssock.close()
                return None


def seeder(local_port):
    """Seeder peer thread.
    Args:
        local_port (int): Port for Seeder.
    """
    global pieces
    global shutdown_event
    while not shutdown_event.is_set():
        # TODO do we want this to be in a try like everything else?
        peer_sock = create_seeder(local_port)
        if peer_sock is None:
            break
        connected = handshake(peer_sock, initiate=False)
        if not connected:
            # TODO do we need to close peer_sock here? Maybe test with doing so to see if it breaks anything
            continue
        try:
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

            set1 = set(indexes_on_peer)
            lock.acquire()
            set2 = set(p[1] for p in pieces.keys() if p[0] == file_id)
            lock.release()
            indexes_on_peer = list(set1 - set2)
            handle_responses(peer_sock, file_id, indexes_on_peer,
                             is_seeder=True)
        except ConnectionResetError:
            print("Connection reset by peer.")
        except struct.error:
            print("Communication was severed early by peer.")
        except ssl.SSLError:
            print("Communication with peer failed.")
        except socket.timeout:
            print("Socket timed out.")
        peer_sock.close()
    print("[Seeder] Shutting down.")


def downloader(local_port, output_file, file_indicator):
    """Downloader peer thread.
    Args:
        local_port (int): Port number corresponding to this channel.
        output_file (str): Name of output file to write to.
        file_indicator (int): Internal id corresponding to the target file.
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
            print("Waiting to see if we need to handle downloads.")
            time.sleep(.5)
            continue
        else:
            test_peer = 0
            sock = None
            while not download_finished and not shutdown_event.is_set():
                # Randomize list of peers, and choose the first one.
                swarm_peers = list(swarm.keys())
                random.shuffle(swarm_peers)
                test_peer = swarm_peers[0]
                if test_peer != local_id and test_peer not in current_peers:
                    lock.acquire()
                    if test_peer in current_peers:  # TODO maybe we can combine this and the above check
                        lock.release()
                        continue
                    current_peers.append(test_peer)
                    lock.release()
                    # Try connecting on the 4 primary ports of the target.
                    # Note that we also check the 5th in case the peer is a
                    # downloader with an open seeder port.
                    peer_port, peer_ip = swarm[test_peer]
                    port_offset = 0
                    while port_offset < 5:
                        try:
                            sock = create_downloader(local_port,
                                                     peer_ip,
                                                     peer_port + port_offset)
                            break
                        except ConnectionRefusedError:
                            port_offset += 1
                            continue
                        # This is thrown if the ssl handshake fails.
                        except ConnectionResetError:
                            port_offset += 1
                            continue
                    if port_offset == 5:
                        lock.acquire()
                        current_peers.remove(test_peer)
                        lock.release()
                        continue

                    connected = handshake(sock, test_peer)
                    if not connected:
                        sock.close()
                        lock.acquire()
                        current_peers.remove(test_peer)
                        lock.release()
                        continue
                    else:
                        break
                else:
                    continue
            if sock is None:
                break
            # print("Started download!")
            indexes_on_peer = []

            current_bitfield = Utility.create_bitfield(pieces,
                                                       total_pieces)
            bitfield_packet = Packet.create_packet(5, file_indicator,
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
                # Find what pieces downloader needs from peer.
                set1 = set(indexes_on_peer)
                lock.acquire()
                set2 = set(p[1] for p in pieces.keys())
                lock.release()
                indexes_on_peer = list(set1 - set2)
                if len(indexes_on_peer) == 0:
                    sock.send(Packet.create_packet(3))
                    lock.acquire()
                    current_peers.remove(test_peer)
                    lock.release()
                    sock.close()
                    continue
                # Initial request.
                sock.send(Packet.create_packet(6, indexes_on_peer[0],
                                               file_indicator))
                handle_responses(sock, file_indicator, indexes_on_peer)
                # Send not interested when done.
                sock.send(Packet.create_packet(3))
                time.sleep(1)
            except ConnectionResetError:
                print("Connection reset by peer.")
            except ssl.SSLError:
                print("Communication with peer failed.")
            except struct.error:
                print("Communication was severed early by peer.")
            except TimeoutError:
                print("Peer became unresponsive.")
            lock.acquire()
            current_peers.remove(test_peer)
            lock.release()
            sock.close()
    if shutdown_event.is_set():
        return
    lock.acquire()
    if not copied_file:
        copied_file = True
        assemble_pieces = Utility.sort_by_index(pieces)
        Utility.reassemble_file(assemble_pieces, "output", output_file)
        print(f"Successfully Downloaded {output_file} to output/{output_file}.")
    lock.release()
    # When we are done downloading, act as a seeder until exit.
    if not shutdown_event.is_set():
        seeder(local_port)


def cli(shutdown_event, is_seeder, filename):
    """Runs the command line interface for a peer.
    Args:
        shutdown_event (Event): Callable event to stop peer.
        is_seeder (bool): Changes output depending on if 
            current peer is Seeder or a Downloader.
        filename (str): file to download 
    """
    print("Welcome to Bit Torrent!")
    if is_seeder:
        print("Running Seeder Peer.")
        print("Type 'exit' to quit or 'prog' to see number of pieces Seeder has.")
    else:
        print(f"Running Downloader Peer on {filename}.")
        print("Type 'exit' to quit or 'prog' to see download progress.")
    while not shutdown_event.is_set():
        cmd = input("[CLI]: ").strip().lower()
        if cmd == 'exit':
            shutdown_event.set()
            break
        elif cmd == "prog":
            percent = round(len(pieces) / total_pieces * 100, 2)
            if is_seeder:
                print(f"Pieces on Seeder: {len(pieces)} "
                      f"({percent}%).")
            elif download_finished:
                print("Download Finished!")
            else:
                print("Download in Progress...")
                print(f"{len(pieces)}/{total_pieces} "
                      f"({percent}%) downloaded.\n")           


def main():
    """Main function to run file share Peer."""
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
                        default='0short_story.txt',
                        help="file for peer, required for downloader.")
    parser.add_argument("-m", nargs='*', type=int, default=None,
                        help="Optional list of missing pieces for this peer.")
    parser.add_argument("-r1", type=float, default=None,
                        help="Optional lower range of pieces for this peer.")
    parser.add_argument("-r2", type=float, default=None,
                        help="Optional upper range of pieces for this peer.")
    args = parser.parse_args()

    try:
        host = socket.gethostname()
        local_ip = socket.gethostbyname(host)
    except socket.gaierror:
        return "Cannot retrieve local device IP."

    tracker_ip, seeder_bool = args.i, args.S
    # If we are using localhost, bind to the actual address instead.
    if tracker_ip == 'localhost' or tracker_ip == '127.0.0.1':
        tracker_ip = local_ip
    first_port, tracker_port = args.p, args.d
    missing_pieces, p2p_file = args.m, args.f
    lower_range, upper_range =args.r1, args.r2

    if seeder_bool:
        for filename in os.listdir("input"):
            if filename[0].isdigit() and int(filename[0]) < 4:
                file_indicator = int(filename[0])
            else:
                print("Please provide only well formatted files in input.")
                return
            base_name = os.path.splitext(filename)[0]  # strips extension
            hash_path = os.path.join("hashes", f"{base_name}-hashes.txt")
            # Create relevant hashes if they are missing.
            if not os.path.isfile(hash_path):
                Utility.create_hash_file(filename)

            file_split = Utility.split_file("input", filename)
            full_file_dict = dict(enumerate(file_split))
            if missing_pieces is not None:
                file_dict = {key: full_file_dict[key] for key in full_file_dict
                             if
                             key not in missing_pieces}

            elif lower_range is not None or upper_range is not None:
                lower = 0.0 if lower_range is None else lower_range
                upper = 1.0 if upper_range is None else upper_range

                sampled_keys = list(
                    range(math.floor(len(full_file_dict) * lower),
                          math.ceil(len(full_file_dict) * upper)))
                file_dict = {key: full_file_dict[key] for key in sampled_keys}
            else:
                # Get a random 95% of the pieces.
                sampled_keys = random.sample(list(full_file_dict.keys()),
                                             math.ceil(
                                                 len(full_file_dict) * 0.95))

                file_dict = {key: full_file_dict[key] for key in sampled_keys}
            # Just for some variability, load pieces in random order.
            load_keys = list(file_dict.keys())
            random.shuffle(load_keys)
            for key in load_keys:
                pieces[(file_indicator, key)] = file_dict[key]

            with open(hash_path, "rb") as file:
                index = 0
                while piece_hash := file.read(32):
                    if (file_indicator, index) not in pieces:
                        pieces_remaining[(file_indicator, index)] = piece_hash
                    index += 1
                total_pieces += index
    else:
        if p2p_file[0].isdigit() and int(p2p_file[0]) < 4:
            file_indicator = int(p2p_file[0])
        else:
            print("Please provide a supported file to download.")
            return
        base_name = os.path.splitext(p2p_file)[0]  # strips extension
        hash_path = os.path.join("hashes", f"{base_name}-hashes.txt")
        if not os.path.isfile(hash_path):
            Utility.create_hash_file(p2p_file)

        with open(hash_path, "rb") as file:
            index = 0
            while piece_hash := file.read(32):
                pieces_remaining[(file_indicator, index)] = piece_hash
                index += 1
            total_pieces = index

    # Receive swarm peers from tracker.
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((tracker_ip, tracker_port))
        # Initial message should just be code 0, id = given port range.
        send_packet = struct.pack('>BH', 0, first_port)
        send_hash = hashlib.sha256(send_packet)
        sock.send(send_packet + send_hash.digest())
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
        print("Connection reset by tracker.")
        return
    except ConnectionRefusedError:
        print("Tracker unavailable for connection.")
        return
    except struct.error:
        print("Communication was severed early by peer.")
        return
    except TimeoutError:
        print("Tracker became unresponsive.")
        return

    time.sleep(1)
    update_thread = threading.Thread(target=update_swarm,
                                     args=(tracker_ip, tracker_port))
    update_thread.start()

    threads = []
    if not seeder_bool:
        for i in range(4):
            threads.append(
                threading.Thread(target=downloader, args=(
                    first_port + i, p2p_file, file_indicator)))
            threads[i].start()
        # Seeder thread to accept communication from downloaders
        threads.append(
            threading.Thread(target=seeder, args=(first_port + 4,)))
        threads[4].start()
    else:
        for i in range(4):
            threads.append(
                threading.Thread(target=seeder, args=(first_port + i,)))
            threads[i].start()

    cli(shutdown_event, seeder_bool, p2p_file)

    for thread in threads:
        thread.join()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((tracker_ip, tracker_port))
        send_packet = struct.pack('>BH', 1, local_id)
        send_hash = hashlib.sha256(send_packet)
        sock.send(send_packet + send_hash.digest())
        while True:
            response_packet = sock.recv(4)
            if len(response_packet) == 1:
                sock.send(send_packet + send_hash.digest())
                continue
            else:
                break
        print("Exited swarm.")
        sock.close()
        print("Shutdown complete.")
    except ConnectionResetError:
        print("Connection reset by server.")
    except ConnectionRefusedError:
        print("Server unavailable for connection.")
    except struct.error:
        print("Communication was severed early by peer.")
    except TimeoutError:
        print("Tracker became unresponsive.")


if __name__ == "__main__":
    main()
