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

from Packet import PacketType

# Global flag to indicate that we should exit all threads.
exit_peer = False

# Global flag to prevent multiple copies.
copied_file = False

# Dict holding the information about the other peers in the swarm.
swarm = {}

# ID and IP of this peer in the swarm.
local_id = 0
local_ip = ''

# Flag indicating if the user has downloaded their target file yet.
download_finished = False

# List of currently connected peers (records connections we initiate).
current_peers = []

# Dict of the pieces remaining - (file, index) = bytes.
pieces_remaining = {}

# Total number of pieces we want to have.
total_pieces = 0

# Dict of "downloaded" pieces (file, index) = bytes.
pieces = {}

# Lock for managing local swarm list and file info.
lock = threading.Lock()


def handshake(sock, target_id=0, initiate=True):
    """
    Handshake on a socket to confirm we are connected to a valid peer. When
    initiating, verify that target returns expected ID.

    Args:
        sock (SSLSocket): Socket used for this P2P connection.
        target_id (int, optional): ID of target peer. Defaults to 0.
        initiate (bool, optional):
            Whether this peer initiated connection. Defaults to True.

    Returns:
        bool: True on success, False on fail.
    """
    global local_id
    try:
        # This imitates the protocol used by bittorrent.
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
            # Send back our ID to prove we match the ID expected.
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
    """
    Periodically requests the most recent version of the swarm from the
    tracker. Run as a background thread on all peers.

    Args:
        s_ip (str): IP of tracker.
        s_port (int): Port of tracker.
    """
    global swarm
    global lock
    global exit_peer
    while not exit_peer:
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
            # Reset list so we can learn which peers have exited.
            swarm.clear()
            for i in range(length):
                peer_id, peer_port, peer_ip = (
                    struct.unpack('>HHI', response_packet[i * 8:i * 8 + 8]))
                swarm[peer_id] = peer_port, str(ipaddress.ip_address(peer_ip))
            lock.release()

            sock.close()
            time.sleep(3)  # Get fresh data every 3 seconds
        # Any communication issue with the tracker is considered a fatal issue.
        except ConnectionResetError:
            print("Connection reset by tracker.")
            exit_peer = True
            break
        except ConnectionRefusedError:
            print("Tracker unavailable for connection.")
            exit_peer = True
            break
        except struct.error:
            print("Communication was severed early by tracker.")
            exit_peer = True
            break
        except TimeoutError:
            print("Tracker became unresponsive.")
            exit_peer = True
            break


def handle_responses(sock, file_identifier, indexes_on_peer, is_seeder=False):
    """
    Handles responses for both seeder and downloader channels. This includes
    facilitating 2 way connection, propagating stored data updates, and its
    main function, piecewise data transfer and hash validation.

    Args:
        sock (SSLSocket): Socket used for this P2P connection.
        file_identifier (int):
            ID of the file being shared over this communication.
        indexes_on_peer (list):
            Pieces that are needed by this peer and found on the currently
            connected peer.
        is_seeder (bool): Flag for if this is a seeder. Defaults to False.
    """
    global lock
    global pieces_remaining
    global pieces
    global exit_peer
    global download_finished
    sent = {}  # Format {(packet_index, file_id): time} ACK dictionary
    lock.acquire()
    prev_pieces = set(p[1] for p in pieces.keys() if p[0] == file_identifier)
    lock.release()
    while is_seeder or len(indexes_on_peer) != 0:
        packet = sock.recv(4)
        length, = struct.unpack(">I", packet[:4])  # Check length
        packet = packet + sock.recv(length)  # Read rest of packet
        parsed_packet = Packet.parse_packet(packet)
        type, payload = parsed_packet["type"], parsed_packet["payload"]
        if type == Packet.PacketType.PIECE.name:
            piece_hash = hashlib.sha256(payload["piece"])

            recv_piece = file_identifier, payload["packet_index"]
            lock.acquire()
            # Refuse to accept the piece if it does not match the known hash.
            if (recv_piece in pieces_remaining and
                    (piece_hash.digest() != pieces_remaining[recv_piece])):
                lock.release()
                continue
            if payload["packet_index"] in indexes_on_peer:
                indexes_on_peer.remove(payload["packet_index"])
            if recv_piece in pieces_remaining:
                pieces_remaining.pop(recv_piece)
                pieces[recv_piece] = payload["piece"]
                prev_pieces.add(payload["packet_index"])
            lock.release()

            response_packet = Packet.create_packet(PacketType.HAVE.value,
                                                   payload["packet_index"],
                                                   file_identifier)
            sock.send(response_packet)

            if not is_seeder and len(indexes_on_peer) != 0:
                sock.send(Packet.create_packet(PacketType.REQUEST.value,
                                               indexes_on_peer[0],
                                               file_identifier))
        elif type == Packet.PacketType.HAVE.name:
            packet_index, file_id = payload["packet_index"], payload["file_id"]
            if (packet_index, file_id) in sent:
                sent.pop((packet_index, file_id))
            else:  # Other peer is announcing they have a piece
                indexes_on_peer.append(packet_index)
        elif type == Packet.PacketType.REQUEST.name:
            packet_index, file_id = payload["packet_index"], payload["file_id"]
            piece_to_send = pieces[(file_id, packet_index)]
            response_packet = Packet.create_packet(PacketType.PIECE.value,
                                                   packet_index, piece_to_send)
            sock.send(response_packet)
            sent[(packet_index, file_id)] = time.time()
            if is_seeder and len(indexes_on_peer) != 0:
                sock.send(
                    Packet.create_packet(PacketType.REQUEST.value,
                                         indexes_on_peer[0], file_id))
                indexes_on_peer.pop(0)

        elif type == Packet.PacketType.NOT_INTERESTED.name:
            # Clear indexes on peer so the outer loop stops looping.
            indexes_on_peer.clear()
            break

        # Check if we should exit communication.
        if exit_peer or (not is_seeder and download_finished):
            sock.send(Packet.create_packet(PacketType.NOT_INTERESTED.value))
            time.sleep(1)
            break

        # Check if an ACK hit a timeout.
        if len(sent) > 0:
            packet_index, file_id = min(sent, key=sent.get)
            oldest_time = sent[(packet_index, file_id)]
            if oldest_time - time.time() > 2:
                # The oldest unACKed piece took > 2 seconds, resend piece.
                sent.pop((packet_index, file_id))
                piece_to_send = pieces[(file_id, packet_index)]
                response_packet = Packet.create_packet(PacketType.PIECE.value,
                                                       packet_index,
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
            # Announce new pieces to connected peer.
            for index in new_pieces:
                response_packet = Packet.create_packet(PacketType.HAVE.value,
                                                       index, file_identifier)
                sock.send(response_packet)
        prev_pieces = set2


def create_downloader(peer_ip, peer_port):
    """
    Create a Downloader socket for on a peer using SSL. This socket expects to
    connect to an open and listening seeder socket.

    Args:.
        peer_ip (str): Peer IP.
        peer_port (int): Peer port.

    Returns:
        SSLSocket: Socket with secure connection to seeder.
    """
    hostname = "P2Pproject"
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations('cert.pem')

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
    ssock = context.wrap_socket(sock, server_hostname=hostname)
    ssock.connect((peer_ip, peer_port))
    return ssock


def create_seeder(port):
    """
    Creates a Seeder socket for a peer using SSL. This socket waits until a
    downloader peer connects, checking every second if it needs to exit.

    Args:
        port (int): Port number for Seeder channel.

    Returns:
        SSLSocket: Socket with secure connection to downloader.
    """
    global exit_peer
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
            if exit_peer:
                ssock.close()
                return None


def seeder(local_port):
    """
    Runs a passive seeder channel which waits for a downloader to initiate a
    connection. Once connected, communication commences until the downloader
    ends the communication or an error in the communication occurs. The seeder
    then resets and waits for a new connection.

    Args:
        local_port (int): Port for Seeder.
    """
    global pieces
    global exit_peer
    while not exit_peer:
        try:
            peer_sock = create_seeder(local_port)
        except ConnectionResetError:
            print("Connection reset by peer.")
            continue
        except struct.error:
            print("Communication was severed early by peer.")
            continue
        except ssl.SSLError:
            print("Communication with peer failed.")
            continue
        except socket.timeout:
            print("Socket timed out.")
            continue

        if peer_sock is None:
            break
        connected = handshake(peer_sock, initiate=False)
        if not connected:
            peer_sock.close()
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
            lock.acquire()
            for p in pieces.keys():
                if p[0] == file_id:
                    relevant_pieces[p] = pieces[p]
            lock.release()
            file_len = len(payload["bitfield"])
            seeder_bitfield = Utility.create_bitfield(relevant_pieces,
                                                      file_len)
            bitfield_packet = Packet.create_packet(PacketType.BITFIELD.value,
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
    """
    Manages an active Downloader channel which continuously opens connections
    with peers in the swarm until it receives all pieces of the indicated file.
    Initiates connection with a random peer, gets all the files it needs, then
    ends the connection.

    Once it or another downloader channel obtains the full file, switches to
    a seeder to facilitate downloads by other peers.

    Args:
        local_port (int): Port number corresponding to this channel.
        output_file (str): Name of output file to write to.
        file_indicator (int): Internal ID corresponding to the target file.
    """
    global download_finished
    global lock
    global swarm
    global current_peers
    global pieces_remaining
    global local_id
    global total_pieces
    global copied_file

    while not download_finished and not exit_peer:
        # Make sure all the piece lists are synced.
        if len(pieces_remaining) == 0 and len(pieces) == total_pieces:
            download_finished = True
            break

        test_peer = 0
        sock = None
        while not download_finished and not exit_peer:
            # Randomize list of peers, and choose the first one.
            swarm_peers = list(swarm.keys())
            random.shuffle(swarm_peers)
            test_peer = swarm_peers[0]
            lock.acquire()
            peers = current_peers.copy()
            lock.acquire()
            if test_peer != local_id and test_peer not in peers:
                # If we can get the peer, add them to the reserved list.
                lock.acquire()
                if test_peer in current_peers:
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
                    if sock is not None:
                        sock.close()
                    try:
                        sock = create_downloader(peer_ip,
                                                 peer_port + port_offset)
                        break
                    except ConnectionRefusedError:
                        port_offset += 1
                        continue
                    # This is thrown if the ssl handshake fails.
                    except ConnectionResetError:
                        port_offset += 1
                        continue
                    # This occurs when attempts are firewalled.
                    # Note: This only occurs when the 2 peers are on
                    # different devices, and will take much longer to
                    # resolve than local cases due to the timeout window.
                    # It also only occurs when intentionally closing a
                    # peer, so it is not seen in regular use cases.
                    except TimeoutError:
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
        indexes_on_peer = []

        current_bitfield = Utility.create_bitfield(pieces,
                                                   total_pieces)
        bitfield_packet = Packet.create_packet(PacketType.BITFIELD.value,
                                               file_indicator,
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
                sock.send(Packet.create_packet(
                    PacketType.NOT_INTERESTED.value))
                lock.acquire()
                current_peers.remove(test_peer)
                lock.release()
                sock.close()
                continue
            # Initial request.
            sock.send(Packet.create_packet(PacketType.REQUEST.value,
                                           indexes_on_peer[0], file_indicator))
            handle_responses(sock, file_indicator, indexes_on_peer)
            # Send not interested message when done.
            sock.send(Packet.create_packet(PacketType.NOT_INTERESTED.value))
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
        # Double check in case an unexpected issue was encountered.
        if sock is not None:
            sock.close()

    if exit_peer:
        return
    # Only initiate the download if we are the first peer to get here.
    lock.acquire()
    if not copied_file:
        copied_file = True
        assemble_pieces = Utility.sort_by_index(pieces)
        Utility.reassemble_file(assemble_pieces, "output", output_file)
        print(f"Successfully Downloaded",
              f"{output_file} to output/{output_file}.")
        print(time.strftime("%H:%M:%S", time.localtime()))
    lock.release()
    # When we are done downloading, act as a seeder until exit.
    if not exit_peer:
        seeder(local_port)


def cli(is_seeder, filename):
    """
    Runs the command line interface for a peer. Supports the exit command to
    end the operations of this peer, and prog to show download state.

    Args:
        is_seeder (bool):
            Changes output depending on the state of the current peer.
        filename (str): File being downloaded if downloader.
    """
    global exit_peer
    print("Welcome to Bit Torrent!")
    if is_seeder:
        print("Running Seeder Peer.")
        print("Type 'exit' to quit or 'prog'",
              "to see number of pieces Seeder has.")
    else:
        print(f"Running Downloader Peer on {filename}.")
        print("Type 'exit' to quit or 'prog' to see download progress.")
    while not exit_peer:
        cmd = input("[CLI]: ").strip().lower()
        if cmd == 'exit':
            exit_peer = True
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
    """
    Main function to run file share Peer. Initiates connection with tracker to
    get initial ID and swarm list. Then starts downloader or seeder threads
    before initiating the user interface. Upon exiting the interface, the
    tracker is contacted one last time to remove the peer from the swarm list.

    """
    global swarm
    global local_id
    global local_ip
    global pieces_remaining
    global total_pieces
    global exit_peer

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
        print("Cannot retrieve local device IP.")
        exit(1)

    tracker_ip, seeder_bool = args.i, args.S
    # If we are using localhost, bind to the actual address instead.
    if tracker_ip == 'localhost' or tracker_ip == '127.0.0.1':
        tracker_ip = local_ip
    first_port, tracker_port = args.p, args.d
    missing_pieces, p2p_file = args.m, args.f
    lower_range, upper_range = args.r1, args.r2

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
                file_dict = {key: full_file_dict[key]
                             for key in full_file_dict
                             if key not in missing_pieces}

            elif lower_range is not None or upper_range is not None:
                lower = 0.0 if lower_range is None else lower_range
                upper = 1.0 if upper_range is None else upper_range

                sampled_keys = list(
                    range(math.floor(len(full_file_dict) * lower),
                          math.ceil(len(full_file_dict) * upper)))
                file_dict = {key: full_file_dict[key] for key in sampled_keys}
            else:
                # Get a random 95% of the pieces as default.
                sampled_keys = random.sample(list(full_file_dict.keys()),
                                             math.ceil(
                                                 len(full_file_dict) * 0.95))

                file_dict = {key: full_file_dict[key] for key in sampled_keys}
            # Just for some variability, load pieces in random order.
            load_keys = list(file_dict.keys())
            random.shuffle(load_keys)
            for key in load_keys:
                pieces[(file_indicator, key)] = file_dict[key]
            # For each file, read the whole hash list, so we can determine what
            # we need and verify pieces when sent.
            with open(hash_path, "rb") as file:
                index = 0
                while piece_hash := file.read(32):
                    if (file_indicator, index) not in pieces:
                        pieces_remaining[(file_indicator, index)] = piece_hash
                    index += 1
                total_pieces += index
    else:
        # Downloader only reads the hashes for a file.
        if p2p_file[0].isdigit() and int(p2p_file[0]) < 4:
            file_indicator = int(p2p_file[0])
        else:
            print("Please provide a supported file to download.")
            return
        # This is just a backup in case no local seeders have already generated
        # the hash file. If the hash file already exists, then the downloader
        # does not need to have any copy of the input file to work.
        base_name = os.path.splitext(p2p_file)[0]
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
                sock.send(b"\0")  # On success, ACK by sending a null byte
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
        exit(1)
    except ConnectionRefusedError:
        print("Tracker unavailable for connection.")
        exit(1)
    except struct.error:
        print("Communication was severed early by peer.")
        exit(1)
    except TimeoutError:
        print("Tracker became unresponsive.")
        exit(1)

    time.sleep(1)
    update_thread = threading.Thread(target=update_swarm,
                                     args=(tracker_ip, tracker_port))
    update_thread.start()

    threads = []
    if not seeder_bool:
        # Print the time when the first downloader thread starts.
        print(time.strftime("%H:%M:%S", time.localtime()))
        for i in range(4):
            threads.append(
                threading.Thread(target=downloader, args=(
                    first_port + i, p2p_file, file_indicator)))
            threads[i].start()
        # Seeder thread to accept communication from downloaders.
        # As per conversation with professor, this replaces the need for
        # optimistic unchoking in our greedy connection system by allowing
        # downloaders to connect to each other as needed.
        # Note: Since seeders do not care who connects to them, in some cases
        # the seeder channel accepts a connection from a fellow downloader
        # to whom we are already downloading from.
        threads.append(
            threading.Thread(target=seeder, args=(first_port + 4,)))
        threads[4].start()
    else:
        for i in range(4):
            threads.append(
                threading.Thread(target=seeder, args=(first_port + i,)))
            threads[i].start()
    cli(seeder_bool, p2p_file)

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
        exit(1)
    except ConnectionRefusedError:
        print("Server unavailable for connection.")
        exit(1)
    except struct.error:
        print("Communication was severed early by peer.")
        exit(1)
    except TimeoutError:
        print("Tracker became unresponsive.")
        exit(1)


if __name__ == "__main__":
    main()
