import os
import re
import stat
import subprocess
import logging


def humanbytes(B: int):
    """Return the given bytes as a human friendly KB, MB, GB, or TB string"""
    # from https://stackoverflow.com/questions/12523586/python-format-size-application-converting-b-to-kb-mb-gb-tb
    B = float(B)
    KB = float(1024)
    MB = float(KB ** 2) # 1,048,576
    GB = float(KB ** 3) # 1,073,741,824
    TB = float(KB ** 4) # 1,099,511,627,776

    if B < KB:
        return '{0} {1}'.format(B,'Bytes' if 0 == B > 1 else 'Byte')
    elif KB <= B < MB:
        return '{0:.2f} KB'.format(B/KB)
    elif MB <= B < GB:
        return '{0:.2f} MB'.format(B/MB)
    elif GB <= B < TB:
        return '{0:.2f} GB'.format(B/GB)
    elif TB <= B:
        return '{0:.2f} TB'.format(B/TB)


# based on https://stackoverflow.com/a/42865957/2002471
units = {"B": 1, "KB": 2**10, "MB": 2**20, "GB": 2**30, "TB": 2**40, "K": 2**10, "M": 2**20, "G": 2**30, "T": 2**40}


def parse_size(size):
    size = size.upper()
    #print("parsing size ", size)
    if not re.match(r' ', size):
        size = re.sub(r'([KMGT]?B?)', r' \1', size)
    number, unit = [string.strip() for string in size.split()]
    return int(float(number)*units[unit])




def legal_block_dev_file(dev: str):
    """Answers True when the given path exists and is a block file."""
    return os.path.exists(dev) and stat.S_ISBLK(os.stat(dev).st_mode)


def devicename_from_dev_file(dev: str):
    m = re.match("\/dev\/(\w+)", dev)
    if m:
        return m.group(1)
    raise Exception("Unparseable device name {}".format(dev))


def block_device_size_sectors(dev: str):
    """ Retrieves the device size from linux block device, in 512 byte sectors. """
    devname = devicename_from_dev_file(dev)
    with open('/sys/class/block/'+devname+'/size', 'r') as p:
        return int(p.readline().rstrip('\n'))


def block_device_info(dev: str):

    # thanks to https://rainbow.chard.org/2013/01/30/how-to-align-partitions-for-best-performance-using-parted/
    devname = devicename_from_dev_file(dev)
    blockvals = {}
    with open('/sys/class/block/'+devname+'/size', 'r') as p:
        size_sectors = int(p.readline().rstrip('\n'))
        blockvals['size'] = size_sectors

    with open('/sys/block/'+devname+'/queue/optimal_io_size', 'r') as p:
        optimal_io_size = int(p.readline().rstrip('\n'))
        blockvals['optimal_io_size'] = optimal_io_size

    with open('/sys/block/'+devname+'/queue/minimum_io_size', 'r') as p:
        minimum_io_size = int(p.readline().rstrip('\n'))
        blockvals['minimum_io_size'] = minimum_io_size

    if not os.path.exists('/sys/block/'+devname+'/queue/alignment_offset'):
        blockvals['alignment_offset'] = 0
    else:
        with open('/sys/block/'+devname+'/queue/alignment_offset', 'r') as p:
            alignment_offset = int(p.readline().rstrip('\n'))
            blockvals['alignment_offset'] = alignment_offset

    with open('/sys/block/'+devname+'/queue/physical_block_size', 'r') as p:
        physical_block_size = int(p.readline().rstrip('\n'))
        blockvals['physical_block_size'] = physical_block_size

    # hopefully this is right:
    # https://access.redhat.com/documentation/en-us/red_hat_enterprise_linux/7/html/storage_administration_guide/iolimpartitionfstools
    if blockvals['optimal_io_size'] == 0:
        blockvals['alignment_boundary'] = 1024 * 1024
    else:
        blockvals['alignment_boundary'] = blockvals['optimal_io_size'] + blockvals['alignment_offset']

    blockvals['alignment_boundary_sectors'] = int( blockvals['alignment_boundary'] /
                                                   blockvals['physical_block_size'] )
    blockvals['first_partition_offset_sectors'] = int(blockvals['alignment_boundary'] /
                                                      blockvals['physical_block_size'])

    return blockvals


def logged_subcommand_run(cmdline: list, logger: logging.Logger, log_level: int):
    """
    Run the specified command using subcommand.run(), and push any Standard Out/Error to the specified logger and level.
    :param cmdline: The command line to execute, in the form expected by subcommand.run()
    :param logger: a logging.Logger instance
    :param log_level: the (integer) logging level, as defined in Logger
    :return: the command result returned from run()
    """
    logger.log("Running subcommand: {}").format(cmdline)
    cp = subprocess.run(cmdline, capture_output=True)
    logger.log(log_level, "{} STDOUT {}".format(cmdline[0], str(cp.stdout.decode('utf-8'))))
    logger.log(log_level, "{} STDERR {}".format(cmdline[0], str(cp.stderr.decode('utf-8'))))
    return cp