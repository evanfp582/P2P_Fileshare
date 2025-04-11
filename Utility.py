import hashlib
import os

PIECE_BYTE_LENGTH = 128  # TODO we need to decide. Chose 128 because the docs say commonly powers of 2


def split_file(folder, filename):
    """Splits a file into chunks of a given size.
    Args:
        folder (str): Folder with file.
        filename (str): File to split.
    Returns:
        list: byte pieces of file
    """
    local_files = os.path.join(folder, filename)
    pieces = []
    with open(local_files, "rb") as file:
        while piece := file.read(PIECE_BYTE_LENGTH):
            # If < packet size, fill in with buffer '\0'
            pieces.append(piece.ljust(PIECE_BYTE_LENGTH, b'\0'))
    return pieces


def piece_hash(pieces):
    """Calculates the piecewise hashes of the provided file bytes.
    Args:
        pieces (list): list of byte segments corresponding to pieces.
    Returns:
        list: bytes corresponding to the hash of each piece
    """
    piece_hashes = []
    for piece in pieces:
        piece_hashes.append(hashlib.sha256(piece))
    return piece_hashes


def reassemble_file(pieces, folder, output_filename):
    """Reassemble file given byte chunks.
    Args:
        pieces (list): Byte list to be reassembled.
        folder (str): Directory to save new file.
        output_filename (str): Name of new file.
    """
    remote_files = os.path.join(folder, output_filename)
    with open(remote_files, "wb") as file:
        for piece in pieces:
            file.write(piece.rstrip(b'\x00'))

def find_missing_values(array, expected_range=135):
    """Given a list where values 0 - expected range are expected, return the set that is missing
        Used when testing random Seeders 
    Args:
        array (list): _description_
        expected_range (int, optional): _description_. Defaults to 135.
    Returns:
        list: Sorted list of missing numbers
    """
    expected = set(range(expected_range))
    actual = set(array)
    missing = expected - actual
    return sorted(missing)

def create_bitfield(pieces, file_length):
    """Create a bitfield for the pieces dictionary for the specified file
    Args:
        pieces (dictionary): (file, index) = string
        file_length (int): total length of the file (in terms of pieces)
    Returns:
        byte bitfield
    """
    bit_array = ["0"] * file_length
    for index in list(pieces.keys()):
        bit_array[index[1]] = "1"
    string_of_bits = "".join(bit_array)
    bitfield = string_of_bits.ljust((len(string_of_bits) + 7) // 8 * 8, '0')
    bitfield_bytes = bytearray()
    for i in range(0, len(bitfield), 8):
        byte = bitfield[i:i + 8]
        bitfield_bytes.append(int(byte, 2))
    return bytes(bitfield_bytes)

def sort_by_index(piece_dict):
    """Given the piece dict ({file_id, piece_index}: byte string)
        return the sorted list by piece_index
    Args:
        piece_dict (dict): piece dictionary
    Returns:
        list: sorted list by piece_index
    """
    return [piece_dict[key] for key in sorted(piece_dict, key=lambda x: x[1])]

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
    print(create_bitfield({(0,5): "test", (0, 1): "test2", (0, 4): "test3"}, 10))
    byte_array = split_file("Peer0", "short_story.txt")
    print(len(byte_array))
    print(byte_array)
    # Writing the hashes onto a local file, not sure if we care about making it
    # a readable format since it is just bytes
    hashes = piece_hash(byte_array)
    # hash_file = os.path.join("Peer0", "story-hashes.txt")
    # with open(hash_file, "wb") as file:
    #     for piece in hashes:
    #         file.write(piece.digest())
    #reassemble_file(byte_array, "Peer1", "short_story.txt")