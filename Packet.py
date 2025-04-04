import hashlib
import struct
from enum import Enum
import Utility

PIECE_BYTE_LENGTH = 128 #TODO we need to decide. Chose 128 because the docs say commonly powers of 2

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
      4 Have Message - Piece index requested   
      5 Bitfield Message - bitfield bytes (see Utility.create_bitfield)  
      6 Request Message - Packet index, file id  
      7 Piece Message - Piece index, bytes to send (see Utility.split_file to create the byte list)  
  Raises:
      ValueError: In the event wrong length or invalid argument  
  Returns:
      packet ready to be sent  
  """
    packet = None
    if packet_type in [0, 1, 2, 3]:
        packet = struct.pack(">IB", 1, packet_type)
    elif packet_type == 4:
        if len(args) != 1:
            raise ValueError("Have type requires piece_index (int) argument")
        index = args[0]
        packet = struct.pack(">IBI", 5, packet_type, index)
    elif packet_type == 5:
        if len(args) != 1:
            raise ValueError("Bitfield type requires bitfield(bytes) argument")
        bitfield_bytes = args[0]
        packet = struct.pack(">IB", 1 + len(bitfield_bytes),
                             packet_type) + bitfield_bytes
    elif packet_type == 6:
        if len(args) != 2:
            raise ValueError(
                "Request type requires piece index (int) and file_id (int)")
        piece_index, file_id = args
        packet = struct.pack(">IBII", 9, packet_type, piece_index, file_id)
    elif packet_type == 7:
        if len(args) != 2:
          raise ValueError("Request type requires piece index (int), byte string")
        piece_index, byte_string = args
        packet = struct.pack(">IBI", PIECE_BYTE_LENGTH + 5, packet_type, piece_index) + byte_string
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
      Packet object: {"type": packet_type, "payload": None or data, "valid_hash": boolean}
  """
    length, = struct.unpack(">I", packet[:4])
    if len(packet) < length:
        raise ValueError("Packet length mismatch")

    packet_type, = struct.unpack(">B", packet[4:5])

    payload = None
    if packet_type in [0, 1, 2,
                       3]:  # Choke, Unchoke, Interested, Not Interested have no payload
        payload = None
    elif packet_type == 4:  # Have Message
        payload = struct.unpack(">I", packet[5:9])[0]
    elif packet_type == 5:  # Bitfield Message
        bit_string = Utility.bytes_to_binary(packet[5:length + 4])
        payload = bit_string
    elif packet_type == 6:  # Request Message
        packet_index, file_id = struct.unpack(">II", packet[5:13])
        payload = {"packet_index": packet_index, "file_id": file_id}
    elif packet_type == 7:  # Piece Message
        payload = packet[9:]        
    else:
        raise ValueError("Invalid packet type")
    return {
        "type": PacketType(packet_type).name,
        "payload": payload
    }


if __name__ == "__main__":
    index = 100
    example_packet = create_packet(4, index)  # Create a have packet
    parsed_data = parse_packet(example_packet)
    print(parsed_data)

    bitfield_bytes = Utility.create_bitfield(
        {5: "test", 1: "test2", 4: "test3"}, 10)
    example_packet = create_packet(5,
                                   bitfield_bytes)  # Create a bitfield packet
    parsed_data = parse_packet(example_packet)
    print(parsed_data)

    packet_index, file_id = 10, 15
    example_packet = create_packet(6, packet_index,
                                   file_id)  # Create a request packet
    parsed_data = parse_packet(example_packet)
    print(parsed_data)

    print("Splitting up tiger.jpg")
    byte_array = Utility.split_file("Peer0", "tiger.jpg") 
    print("First byte string:", byte_array[1])
    print(f"Length: {len(byte_array[1])}") 
    example_packet = create_packet(7, 0, byte_array[1])
    parsed_data = parse_packet(example_packet)
    print(parsed_data) 
    print(f"Length: {len(parsed_data["payload"])}")