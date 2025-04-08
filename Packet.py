import struct
from enum import Enum
import Utility

PIECE_BYTE_LENGTH = 128


class PacketType(Enum):
    CHOKE = 0
    UNCHOKE = 1
    INTERESTED = 2
    NOT_INTERESTED = 3
    HAVE = 4
    BITFIELD = 5
    REQUEST = 6
    PIECE = 7


def create_packet(packet_type, *args):
    """Creates packets depending on what type you submit
  Args:
    packet_type (int): Integer 0 - 6 to indicate type of packet  
      0 Choke Message - No extra arguments  
      1 Unchoke Message - No extra arguments  
      2 Interested Message - No extra arguments  
      3 Not Interested Message - No extra arguments  
      4 Have Message - Piece index and file requested  
      5 Bitfield Message - file id, bitfield bytes (see Utility.create_bitfield)  
      6 Request Message - Packet index, file id  
      7 Piece Message - Piece index, bytes to send  
        (see Utility.split_file to create the byte list)  
  Raises:
      ValueError: In the event wrong length or invalid argument
  Returns:
      packet ready to be sent
  """
    packet = None
    if packet_type in [0, 1, 2, 3]:
        packet = struct.pack(">IB", 1, packet_type)
    elif packet_type == 4:
        if len(args) != 2:
            raise ValueError("Have type requires piece_index (int) and "
                             "file_num (int) argument")
        index = args[0]
        file_num = args[1]
        packet = struct.pack(">IBII", 9, packet_type, index, file_num)
    elif packet_type == 5:
        if len(args) != 2:
            raise ValueError("Bitfield type requires file_id (int) and bitfield(bytes) argument")
        file_id = args[0]
        bitfield_bytes = args[1]
        packet = struct.pack(">IBI", 5 + len(bitfield_bytes),
                             packet_type, file_id) + bitfield_bytes
    elif packet_type == 6:
        if len(args) != 2:
            raise ValueError(
                "Request type requires piece index (int) and file_id (int)")
        piece_index, file_id = args
        packet = struct.pack(">IBII", 9, packet_type, piece_index, file_id)
    elif packet_type == 7:
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
    """Function to return a parsed packet
  Args:
    packet (byte string): a byte string representation of the packet
  Raises:
    ValueError: If invalid length or packet_type code
  Returns:
    object: {"type": packet_type, "payload": None or data}  
    Choke, Unchoke, Interested Not Interested payload: None  
    Have, Request payload: {"packet_index": int, "file_id": int}  
    Piece payload: {"packet_index": int, "piece": byte string}  
  """
    length, = struct.unpack(">I", packet[:4])
    if len(packet) < length:
        raise ValueError("Packet length mismatch")

    packet_type, = struct.unpack(">B", packet[4:5])

    payload = None
    # Choke, Unchoke, Interested, Not Interested have no payload
    if packet_type in [0, 1, 2, 3]:
        payload = None
    elif packet_type == 4:  # Have Message
        packet_index, file_id = struct.unpack(">II", packet[5:13])
        payload = {"packet_index": packet_index, "file_id": file_id}
    elif packet_type == 5:  # Bitfield Message
        file_id, = struct.unpack(">I", packet[5:9])
        bit_string = Utility.bytes_to_binary(packet[9:length + 4])
        payload = {"file_id": file_id, "bitfield": bit_string}
    elif packet_type == 6:  # Request Message
        packet_index, file_id = struct.unpack(">II", packet[5:13])
        payload = {"packet_index": packet_index, "file_id": file_id}
    elif packet_type == 7:  # Piece Message
        packet_index, = struct.unpack(">I", packet[5:9])
        payload = {"packet_index": packet_index, "piece": packet[9:]}
    else:
        raise ValueError("Invalid packet type")
    return {
        "type": PacketType(packet_type).name,
        "payload": payload
    }


if __name__ == "__main__":
    index = 100
    file_num = 3
    example_packet = create_packet(4, index, file_num)  # Create a have packet
    print(example_packet)
    parsed_data = parse_packet(example_packet)
    print(parsed_data)

    # bitfield_bytes = Utility.create_bitfield(
    #     {5: "test", 1: "test2", 4: "test3"}, 10)
    # example_packet = create_packet(5, 0,
    #                                bitfield_bytes)  # Create a bitfield packet
    # parsed_data = parse_packet(example_packet)
    # print(parsed_data)

    # packet_index, file_id = 10, 15
    # example_packet = create_packet(6, packet_index,
    #                                file_id)  # Create a request packet
    # parsed_data = parse_packet(example_packet)
    # print(parsed_data)

    # print("Splitting up tiger.jpg")
    # byte_array = Utility.split_file("Peer0", "tiger.jpg")
    # print("First byte string:", byte_array[1])
    # print(f"Length: {len(byte_array[1])}")
    # example_packet = create_packet(7, 0, byte_array[1])
    # parsed_data = parse_packet(example_packet)
    # print(parsed_data)
    # print(f"Length: {len(parsed_data["payload"]["piece"])}")
