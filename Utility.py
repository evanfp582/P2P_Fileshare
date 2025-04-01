import os

def split_file(folder, filename, packet_size):
  """Splits a file into chunks of a given size.
  Args:
    folder (str): Folder with file.
    filename (str): File to split.
  Returns:
      list: byte chunks of file
  """
  local_files = os.path.join(folder, filename)
  chunks = []
  with open(local_files, "rb") as file:
    while chunk := file.read(packet_size):
      chunks.append((chunk).ljust(packet_size, b'\0')) # If < packet size, fill in with buffer '\0'
  return chunks

def reassemble_file(pieces, folder, output_filename):
  """Reassemble file given byte chunks.
  Args:
    pieces (list): Byte list to be reassembled.
    folder (str): Directory to save new file.
    output_filename (str): Name of new file.
  """
  remote_files = os.path.join(folder, output_filename)
  #TODO maybe check total hash in this function before actually writing it locally
  with open(remote_files, "wb") as file:
    for piece in pieces:
      file.write(piece)
      
def create_bitfield(pieces, file_length):
  """Create a bitfield for the pieces dictionary for the specified file 
  Args:
    pieces (dictionary): file = {index: string}
    file_length (int): total length of the file
  Returns:
    byte bitfield
  """
  bit_array = ["0"] * file_length
  for index in list(pieces.keys()):
    bit_array[index] = "1"
  string_of_bits = "".join(bit_array)
  
  bitfield = string_of_bits.ljust((len(string_of_bits) + 7) // 8 * 8, '0')
    
  bitfield_bytes = bytearray()
  for i in range(0, len(bitfield), 8):
    byte = bitfield[i:i+8]
    bitfield_bytes.append(int(byte, 2))
  
  return bytes(bitfield_bytes)

def bytes_to_binary(byte_data):
  """Converts byte into bit string. Used for bitfield
  Args:
      byte_data (byte): bytes

  Returns:
      string: string of bits from bytes
  """
  return ''.join(f'{byte:08b}' for byte in byte_data)

if __name__ == "__main__":
  """Just in here for testing purposes, not the cleanest, but can be deleted before we submit"""
  print(create_bitfield({5: "test", 1: "test2", 4:"test3"}, 10))