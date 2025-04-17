"""File to create the central Tracker in the P2P file share network."""
import argparse
import ipaddress
import socket
import struct
import threading
import hashlib

swarm = {}

# Counter used to generate unique peers ids.
peer_id = 1

# Lock for managing access to swarm.
lock = threading.Lock()


def handle_peer(peer_sock, peer_addr):
    """
    Handle communication with a connecting peer, who can either be a new peer
    or one already in the swarm. Message integrity is verified using hashes
    to ensure peer data is correctly recorded.

    Args:
        peer_sock (socket.socket): Socket used for peer communication.
        peer_addr (str): Address of peer.
    """
    global swarm
    global peer_id
    global lock

    try:
        # Standard request format is 1 byte code, 2 byte id, 32 byte hash.
        packet = peer_sock.recv(35)
        code_hash = hashlib.sha256(packet[:3])
        if code_hash.digest() != packet[3:]:
            peer_sock.send(b"\0")  # Message corrupted
            return
        msg_code, msg_id = struct.unpack('>BH', packet[:3])
        # Code 0 means that it is a new client, so here id = port range.
        if msg_code == 0:
            lock.acquire()
            current_id = peer_id
            peer_id += 1
            swarm[current_id] = msg_id, peer_addr[0]
            # Just to avoid holding lock too long, copy current swarm.
            current_swarm = swarm.copy()
            lock.release()
            send_packet = struct.pack('>HH', current_id, len(current_swarm))
            length_hash = hashlib.sha256(send_packet)
            peer_sock.send(send_packet + length_hash.digest())
            while True:
                response_packet = peer_sock.recv(35)  # Ack will be just 1 byte
                if len(response_packet) > 1:
                    peer_sock.send(send_packet + length_hash.digest())
                else:
                    break

            swarm_packet = b''
            # Add each peer as 2 byte id + 2 byte port + 4 byte IP.
            for peer in current_swarm.keys():
                swarm_packet += struct.pack('>HHI', peer,
                                            current_swarm[peer][0],
                                            int(ipaddress.ip_address(
                                                current_swarm[peer][1])))
            swarm_hash = hashlib.sha256(swarm_packet)
            peer_sock.send(swarm_packet + swarm_hash.digest())
            while True:
                # Check that messaged arrived uncorrupted.
                response_packet = peer_sock.recv(35)
                if len(response_packet) > 1:
                    peer_sock.send(swarm_packet + swarm_hash.digest())
                else:
                    break

        elif msg_code == 1:  # Code 1 means a returning client
            if msg_id == 0:  # If id is 0, it is just a refresh request
                lock.acquire()
                current_swarm = swarm.copy()
                lock.release()

                # Send and confirm length.
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
                    swarm_packet += struct.pack('>HHI', peer,
                                                current_swarm[peer][0],
                                                int(ipaddress.ip_address(
                                                    current_swarm[peer][1])))
                swarm_hash = hashlib.sha256(swarm_packet)
                peer_sock.send(swarm_packet + swarm_hash.digest())
                while True:
                    response_packet = peer_sock.recv(35)
                    if len(response_packet) > 1:  # ACK is one byte
                        peer_sock.send(swarm_packet + swarm_hash.digest())
                    else:
                        break
            else:  # Otherwise, remove it from the swarm and ACK
                lock.acquire()
                swarm.pop(msg_id)  # Remove client from swarm
                send_packet = struct.pack('>H', msg_id)
                # Just send back the number, we don't care if it is corrupted.
                peer_sock.send(send_packet)
                lock.release()

    except ConnectionResetError:
        print("Connection reset by a client")
    except struct.error:
        print("Communication was severed early by peer.")
    except TimeoutError:
        print("Peer became unresponsive.")
    peer_sock.close()


def main():
    """Main function for creating and starting a Tracker."""
    parser = argparse.ArgumentParser(
        prog="Tracker",
        description="Runs tracker server for managing swarm.")
    parser.add_argument("-p", metavar="source port", type=int, default=9999,
                        help="Local port to bind to.")

    args = parser.parse_args()
    source_port = args.p

    try:
        host = socket.gethostname()
        ip = socket.gethostbyname(host)
    except socket.gaierror:
        print("Cannot retrieve local device IP.")
        exit(1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((ip, source_port))
    sock.listen()

    while True:
        peer_sock, peer_addr = sock.accept()
        thread = threading.Thread(target=handle_peer,
                                  args=(peer_sock, peer_addr))
        thread.start()
    # The tracker would be long-running in a real scenario, weather there are
    # peers sending requests or not. Therefore, it is never exited naturally,
    # so just close the terminal window.


if __name__ == "__main__":
    main()
