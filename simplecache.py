# List of standard library imports
from os import listdir, SEEK_SET, SEEK_CUR
from os.path import join, exists
from re import search

# List of local imports
from common import get_filename, read_http_response, content_to_file, hex_time_convert, get_data
from cachedata import Cache

# This script contains functions used only for data recovery from Chromium Simple Cache structure
# Functions shared with other scripts can be found in common.py


# Main class for Simple Cache structure reading data from cache entries
def read_simple_cache(discord_path, dump_dir):
    cache_list = []
    empty_entries = 0
    range_files = 0
    recovered = 0
    all_entries = 0
    cache_dir = join(discord_path, "Cache")

    # Begin extraction by iterating through all cache entries (based on number of files in Cache directory)
    for file in listdir(cache_dir):
        # Ensure that correct entry types are read
        if "_0" in file:
            all_entries += 1
            cache_entry = Cache()

            # Read content of a cache file
            with open(join(cache_dir, file), "rb") as cache_file:
                cache_entry.entry_location = (file, 0)
                eof1 = search(b"\xd8\x41\x0d\x97\x45\x6f\xfa\xf4\x01", cache_file.read())
                cache_file.seek(eof1.end() + 7, SEEK_SET)
                cache_entry.content_size = int(cache_file.read(4)[::-1].hex(), 16)

                cache_file.seek(0, SEEK_SET)
                eof3 = search(b"\xd8\x41\x0d\x97\x45\x6f\xfa\xf4\x03", cache_file.read())
                cache_file.seek(eof3.end() + 7, SEEK_SET)
                cache_entry.response_size = int(cache_file.read(4)[::-1].hex(), 16)
                cache_entry.response_location = (file, eof1.end() + 15)

                cache_file.seek(12, SEEK_SET)
                cache_entry.url_length = int(cache_file.read(4)[::-1].hex(), 16)
                cache_entry.url_location = (file, 24)
                cache_file.seek(cache_entry.url_location[1], SEEK_SET)
                cache_entry.url = cache_file.read(cache_entry.url_length).decode("ascii")

                # Get name of a cached file and recover its content
                if cache_entry.content_size == 0:
                    # Additional information is fetched if data is stored in separate file
                    content_location = (file[0:16] + "_s")
                    read_range_file(cache_entry, content_location, cache_dir)
                    range_files += 1
                else:
                    cache_entry.content_location = (file, 24 + cache_entry.url_length)

                # Fetch appropriate data from server HTTP response
                response_data = get_data(cache_dir, cache_entry.response_location, cache_entry.response_size)
                read_http_response(str(response_data), cache_entry)

                filename, extension = get_filename(cache_entry.content_type, cache_entry.url)

            # Save information to dictionary for further use
            if cache_entry.content_size != 0:
                # Extract files found within cache and calculate their hashes
                content = get_data(cache_dir, cache_entry.content_location, cache_entry.content_size)
                content_to_file(content, filename, extension, dump_dir, cache_entry)
                recovered += 1
            else:
                empty_entries += 1

            cache_list.append(cache_entry)

    # Read real index file containing all cache entry addresses
    cache_address_list = read_real_index(cache_dir)

    # Append information found in index file to the main list
    for cache_address in cache_address_list:
        for entry in cache_list:
            try:
                if cache_address[1] in entry.entry_location[0]:
                    entry.rankings_location = cache_address[0]
                    entry.last_accessed_time = cache_address[2]
                    entry.entry_created_time = cache_address[2]
                    break
            except ValueError:
                entry.last_accessed_time = ""
                entry.entry_created_time = ""

    reconstructed = range_files - empty_entries
    return cache_list, all_entries, recovered, empty_entries, reconstructed


# Read index file containing names of all cache files and control data about cache entries
def read_real_index(cache_dir):
    cache_address_list = []
    with open(join(cache_dir, "index-dir", "the-real-index"), "rb") as index_file:
        index_file.seek(20, SEEK_SET)
        entry_count = int(index_file.read(8)[::-1].hex(), 16)
        i = 0
        offset = 40
        while i < entry_count:
            index_file.seek(offset, SEEK_SET)
            cache_name = str(index_file.read(8)[::-1].hex())
            last_accessed = hex_time_convert(int(index_file.read(8)[::-1].hex(), 16))
            entry_location = ("the-real-index", offset)
            cache_address_list.append((entry_location, cache_name, last_accessed))
            i += 1
            offset += 24
    return cache_address_list


# Read data stored in #####_s format file
def read_range_file(cache_entry, content_location, cache_dir):
    # Get resource data when it is saved outside main cache file
    if exists(join(cache_dir, content_location)):
        with open(join(cache_dir, content_location), "rb") as file:
            file.seek(12, SEEK_SET)
            cache_entry.range_url_length = int(file.read(4)[::-1].hex(), 16)
            cache_entry.range_url_location = (content_location, 24)

            file.seek(cache_entry.range_url_location[1], SEEK_SET)
            cache_entry.range_url = file.read(cache_entry.range_url_length).decode("ascii")

            file.seek(16, SEEK_CUR)
            cache_entry.content_size = int(file.read(8)[::-1].hex(), 16)
            cache_entry.content_location = (content_location, 56 + cache_entry.range_url_length)
