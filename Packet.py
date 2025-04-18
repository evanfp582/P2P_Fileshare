"""File containing Packed related functions"""
import struct
from enum import Enum
import Utility

PIECE_BYTE_LENGTH = 128


class PacketType(Enum):
    """
    Codes that corelate with a packet type
    """
    NOT_INTERESTED = 0
    HAVE = 1
    BITFIELD = 2
    REQUEST = 3
    PIECE = 4


def create_packet(packet_type, *args):
    """
    Creates message packets depending on the provided type, with each expecting
    different arguments. All packets are length prefixed since the P2P protocol
    uses TCP, hence byte streams rather than pure packets.

    Args:
        packet_type (int): Integer 0 - 4 to indicate type of packet.
            * 0 Not Interested Message - No extra arguments.
            * 1 Have Message - Piece index and file requested.
            * 2 Bitfield Message - file id, bitfield bytes.
            * 3 Request Message - Packet index, file id.
            * 4 Piece Message - Piece index, bytes to send.
    Raises:
        ValueError: In the event wrong length or invalid argument.
    Returns:
        bytes: Packet ready to be sent.
    """
    packet = None
    if packet_type == PacketType.NOT_INTERESTED.value:
        packet = struct.pack(">IB", 1, packet_type)
    elif packet_type == PacketType.HAVE.value:
        if len(args) != 2:
            raise ValueError("Have type requires piece_index (int) and "
                             "file_num (int) argument")
        index = args[0]
        file_num = args[1]
        packet = struct.pack(">IBII", 9, packet_type, index, file_num)
    elif packet_type == PacketType.BITFIELD.value:
        if len(args) != 2:
            raise ValueError("Bitfield type requires file_id (int) and "
                             "bitfield(bytes) argument")
        file_id = args[0]
        bitfield_bytes = args[1]
        packet = struct.pack(">IBI", 5 + len(bitfield_bytes),
                             packet_type, file_id) + bitfield_bytes
    elif packet_type == PacketType.REQUEST.value:
        if len(args) != 2:
            raise ValueError(
                "Request type requires piece index (int) and file_id (int)")
        piece_index, file_id = args
        packet = struct.pack(">IBII", 9, packet_type, piece_index, file_id)
    elif packet_type == PacketType.PIECE.value:
        if len(args) != 2:
            raise ValueError(
                "Piece type requires piece index (int), byte string")
        piece_index, byte_string = args
        packet = struct.pack(">IBI", PIECE_BYTE_LENGTH + 5, packet_type,
                             piece_index) + byte_string
    else:
        raise ValueError("Not valid packet type")
    return packet


def parse_packet(packet):
    """
    Parses a valid packet using the P2P protocol message types. Again, all
    packets are length prefixed.

    Args:
        packet (bytes): A byte string representation of the packet.
    Raises:
        ValueError: If invalid length or packet_type code.
    Returns:
        - object: {"type": packet_type, "payload": None or data}
        * Not Interested payload: None
        * Have, Request payload: {"packet_index": int, "file_id": int}
        * Piece payload: {"packet_index": int, "piece": byte string}
    """
    length, = struct.unpack(">I", packet[:4])
    if len(packet) < length:
        raise ValueError("Packet length mismatch")

    packet_type, = struct.unpack(">B", packet[4:5])

    payload = None
    if packet_type == PacketType.NOT_INTERESTED.value:
        payload = None
    elif packet_type == PacketType.HAVE.value:
        packet_index, file_id = struct.unpack(">II", packet[5:13])
        payload = {"packet_index": packet_index, "file_id": file_id}
    elif packet_type == PacketType.BITFIELD.value:
        file_id, = struct.unpack(">I", packet[5:9])
        bit_string = Utility.bytes_to_binary(packet[9:length + 4])
        payload = {"file_id": file_id, "bitfield": bit_string}
    elif packet_type == PacketType.REQUEST.value:
        packet_index, file_id = struct.unpack(">II", packet[5:13])
        payload = {"packet_index": packet_index, "file_id": file_id}
    elif packet_type == PacketType.PIECE.value:
        packet_index, = struct.unpack(">I", packet[5:9])
        payload = {"packet_index": packet_index, "piece": packet[9:]}
    else:
        raise ValueError("Invalid packet type")
    return {
        "type": PacketType(packet_type).name,
        "payload": payload
    }
