import hashlib
import struct

import Utility


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
  Raises:
      ValueError: In the event wrong length or invalid argument  
  Returns:
      packet + packet hashcode ready to be sent  
  """
  packet = None
  if packet_type in [0,1,2,3]:
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
    packet = struct.pack(">IB", 1 + len(bitfield_bytes), packet_type) + bitfield_bytes
  elif packet_type == 6:
    if len(args) != 2:
      raise ValueError("Request type requires piece index (int) and file_id (int)")
    piece_index, file_id = args
    packet = struct.pack(">IBII", 9, packet_type, piece_index, file_id)
  else:
    raise ValueError("Not valid packet type")
  
  packet_hash = hashlib.sha256(packet[1:]).digest()
  
  return packet + packet_hash


if __name__ == "__main__":
  
  #Example of creating a bitfield packet
  bitfield_bytes = Utility.create_bitfield({5: "test", 1: "test2", 4:"test3"}, 10)
  print(create_packet(5 ,bitfield_bytes))
  
  packet_index = 12 #Example of creating a packet for request
  file_id = 1 
  print(create_packet(6, packet_index, file_id))