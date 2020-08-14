#!/usr/bin/env python3

"""
Downloads Alpine latest iso for ARM, and builds a working headless filesystem
    for a Raspberry PI, with Ansible.
"""
import argparse
import sys

from elevate import elevate
import logging
import os
import os.path
import re
from urllib.parse import urlparse
import shutil
import tempfile
import urllib
import subprocess
from util import *

# Set up logging
logger = logging.getLogger('make_alpine_rpi')
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)


# For now use static URL
alpine_url = 'http://dl-cdn.alpinelinux.org/alpine/v3.12/releases/armhf/alpine-rpi-3.12.0-armhf.tar.gz'
alpine_sha256_url = 'http://dl-cdn.alpinelinux.org/alpine/v3.12/releases/armhf/alpine-rpi-3.12.0-armhf.tar.gz.sha256'
# in the future, maybe can scrape "latest" from here?
alpine_downloads_page_url = 'https://alpinelinux.org/downloads/'

sd_target_image_size = 4 * 1024 * 1024 * 1024 #  4 Gig, bytes
sd_part0_size = 32 * 1024 * 1024 # 32 MB, bytes
sd_part1_size = 32 * 1024 * 1024 # 32 MB, bytes
sd_part2_size = 4 * 1024 * 1024 * 1024 #  4 Gig, bytes


def curl_retrieve_if_newer(url: str, targetdir: str, check_newer: bool = True):
    """ Retrieve the specified URL and store to the specified target directory.  Uses the source file name.
        Wraps curl.
    """
    logger.debug('curl_retrieve_if_newer {} {} {}'.format(url, targetdir, check_newer))
    iso_urlpath = urlparse(url)
    os.makedirs(targetdir, exist_ok=True)
    # print("iso_urlpath={}".format(iso_urlpath))
    targetfile = os.path.join(targetdir, os.path.basename(iso_urlpath.path))

    if os.path.exists(targetfile) and check_newer:
        logger.info(" * Retrieving {} to {} if newer".format(url, targetfile))
        subprocess.run(['curl', '-z', targetfile, '-o', targetfile, url], capture_output=True)
    else:
        logger.info(" * Retrieving {} to {}".format(url, targetfile))
        subprocess.run(['curl', '-o', targetfile, url], capture_output=True)

    return os.path.abspath(targetfile)


def check_checksums(directory: str, sha256file: str):
    logger.debug('check_checksums {} {}'.format(directory, sha256file))
    os.chdir(directory)
    cp = subprocess.run(['sha256sum', '-c', sha256file], capture_output=True)
    logger.debug(cp.stdout)
    logger.debug(cp.stderr)
    return cp.returncode


def check_update_cached_alpine_iso(cachedir: str, iso_url: str, sha256_url: str):
    """
    Retrieve and pass filehandle for ISO.

    :param url: ISO image to download
    :return: filehandle for downloaded file
    """

    iso_urlpath = urlparse(iso_url)
    sha256_urlpath = urlparse(sha256_url)
    image_tarball_file = os.path.join(cachedir, os.path.basename(iso_urlpath.path))
    sha256file = os.path.join(cachedir, os.path.basename(sha256_urlpath.path))

    # print("Check: {} {} {}".format(os.path.exists(isofile),os.path.exists(sha256file),check_checksums(cachedir, sha256file)))
    if os.path.exists(image_tarball_file) and os.path.exists(sha256file) and check_checksums(cachedir, sha256file) == 0:
        print("Good integrity image file present: "+image_tarball_file)
        return image_tarball_file

    curl_retrieve_if_newer(iso_url, './cache')
    sha256file = curl_retrieve_if_newer(sha256_url, cachedir, check_newer=False)
    if check_checksums(cachedir, sha256file) != 0:
        print("Checksum problem!")
        raise Exception("Foo!")
    # check hash?
    print ("Returning {}".format(image_tarball_file))
    return image_tarball_file


def create_loopback_image(out_dir: str, target_size_bytes: int, tarfile=None, leave_tempfiles=False):
    target_img = os.path.join(out_dir, 'image.img')
    sd_part0_image_size = 1024 * 1024 # 1MB, aligned for disk label
    sd_part1_image = os.path.join(out_dir, 'part_01.img')
    sd_part1_image_size = 256 * 1024 * 1024 # 256MB for now -
    sd_part2_image = os.path.join(out_dir, 'part_02.img')
    sd_part2_image_size = 1 * 1024 * 1024 * 1024 # 1GB for now
    part1_contents_dir = os.path.join(out_dir, 'part1_contents')
    if not tarfile:
        raise Exception("No good tarfile")

    print("Creating Partition 1, FAT32, file={}, size={}".format(sd_part1_image, humanbytes(sd_part1_size)))
    if os.path.exists(sd_part1_image):
        print("Clearing existing tempfile: {}".format(sd_part1_image))
        os.remove(sd_part1_image)

    # Filesystem size is given in kB by default
    cmd = ['mkfs.fat', '-C', '-F32', '-n', '\"BOOT\"', sd_part1_image, str(int(sd_part1_image_size / 1024))]
    print("Using: "+' '.join(cmd))
    cp = subprocess.run(cmd)

    print("Creating Partition 2, ext4, file={}, size={}".format(sd_part2_image, humanbytes(sd_part2_size)))
    if os.path.exists(sd_part2_image):
        print("Clearing existing tempfile: {}".format(sd_part2_image))
        os.remove(sd_part2_image)
    # Filesystem size is given in kB by default
    cmd = ['mkfs.ext4', '-t', 'ext4', '-L', '\"root\"', sd_part2_image, str(int(sd_part2_image_size / 1024))]
    print("Using: "+' '.join(cmd))
    cp = subprocess.run(cmd)

    # cmd = ['dd', 'if=/dev/zero', 'of='+target_iso, 'bs=1024', 'count='+str(int(target_size_bytes / 1024))]
    #cp = subprocess.run(cmd)

    print("Extracting Alpine image contents...")
    os.makedirs(part1_contents_dir, exist_ok=True)
    cmd = ['tar', '-xzf', tarfile, '-C', part1_contents_dir]
    print("Using: "+' '.join(cmd))
    cp = subprocess.run(cmd)

    print("Populating Partition 1 with Alpine content")
    cmd = ['mcopy', '-mvns', '-i', sd_part1_image, part1_contents_dir, '::']
    print("Using: "+' '.join(cmd))
    cp = subprocess.run(cmd)

    # https://unix.stackexchange.com/questions/281589/how-to-run-mkfs-on-file-image-partitions-without-mounting

    print("Building disk image,,,")

    #size=$((260*(1<<20))) # desired size in bytes, 260MB in this case
    #alignment=1048576  # align to next MB (https://www.thomas-krenn.com/en/wiki/Partition_Alignment)
    #size=$(( (size + alignment - 1)/alignment * alignment ))  # ceil(size, 1MB)

    # mkfs.fat requires size as an (undefined) block-count; seem to be units of 1k
    #mkfs.fat -C -F32 -n "volname" "${diskimg}".fat $((size >> 10))

    # insert the filesystem to a new file at offset 1MB
    #dd if="${diskimg}".fat of="${diskimg}" conv=sparse obs=512 seek=$((alignment/512))
    # extend the file by 1MB
    #truncate -s "+${alignment}" "${diskimg}"

    # apply partitioning
    #parted --align optimal "${diskimg}" mklabel gpt mkpart ESP "${offset}B" '100%' set 1 boot on

    if not leave_tempfiles:
        print(" ... removing {}".format(part1_contents_dir))
        shutil.rmtree(part1_contents_dir)

    for f in [sd_part1_image, sd_part2_image]:
        print(" ... tempfile {}".format(f))
        if not leave_tempfiles:
            print(" ... removing {}".format(f))
            os.remove(f)


def partition_device(blockdev: str):

    logger.info('partition_device({})'.format(blockdev))

    if not legal_block_dev_file(blockdev):
        raise Exception('Block device is not legal block dev: {} '.format(blockdev))
    blockdev_info = block_device_info(blockdev)
    logger.debug("Block Device Info: {}".format(blockdev_info))

    # constraints to calc partition sizes
    # get size of device
    total_size_sectors = block_device_size_sectors(blockdev)

    # need x sectors for MBR
    sd_part0_size: int = 1024 # 1 MiB label
    sd_part0_size_sectors = int(sd_part0_size / blockdev_info['physical_block_size'])

    # need y megabytes for Alpine image (start w/ 64)
    sd_part1_offset_sectors = blockdev_info['first_partition_offset_sectors']
    sd_part1_size_bytes: int = 64 * 1024 * 1024
    sd_part1_size_sectors = int(sd_part1_size_bytes / blockdev_info['physical_block_size'])

    # use remainder for
    sd_part2_alignment_remainder = (sd_part0_size_sectors + sd_part1_size_sectors) % blockdev_info['alignment_boundary_sectors']
    sd_part2_alignment_fix = blockdev_info['alignment_boundary_sectors'] - sd_part2_alignment_remainder
    sd_part2_offset_sectors = sd_part0_size_sectors + sd_part1_size_sectors + sd_part2_alignment_fix
    sd_part2_size_sectors = total_size_sectors - sd_part0_size_sectors - sd_part1_size_sectors
    sd_part2_size_bytes = int(sd_part2_size_sectors * blockdev_info['physical_block_size'])
    logger.debug('sd_part2_alignment_offset={}, sd_part2_alignment_fix={}'.format(sd_part2_alignment_remainder, sd_part2_alignment_fix))

# parted commands
    # call parted: 'sudo parted --script <devname> --script <script>'
    parted_script = 'mklabel msdos '
    parted_script = parted_script + "mkpart primary fat32 {}s {}s ".format(sd_part1_offset_sectors, sd_part1_size_sectors)
    parted_script = parted_script + "mkpart primary ext4 {}s {}s ".format(sd_part2_offset_sectors, sd_part2_size_sectors)
    parted_script = parted_script + "set 1 boot on "
    parted_script = parted_script + "set 1 lba on "
    logger.debug('partition_device parted command: {}'.format(parted_script))

    # elevate()
    # if not elevate.is_root():
    #     logger.error("Unable to elevate privileges to root")
    #     raise Exception("Unable to elevate privileges to root")
    # else:
    #     logger.debug("Privs elevated.")
    parted_cmdline = ['sudo', 'parted', '--script', blockdev, "{}".format(parted_script)]
    logger.debug('partition_device parted command: {}'.format(parted_cmdline))
    cp = subprocess.run(parted_cmdline, capture_output=True)
    logger.info("parted STDOUT {}".format(str(cp.stdout.decode('utf-8'))))
    logger.info("parted STDERR {}".format(str(cp.stderr.decode('utf-8'))))
    logger.info('partition_device({}) COMPLETE'.format(blockdev))

def makedirs():
    cwd = os.path.abspath(os.path.curdir)
    out = os.path.join(cwd, 'out')
    os.makedirs(out, exist_ok=True)
    cache = os.path.join(cwd, 'cache')
    os.makedirs(out, exist_ok=True)
    return cwd, out, cache


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     prog='make_alpine_rpi',
                                     usage='%(prog)s <command> [options]')
    parser.add_argument("command", type=str, help="Specify the action: \n  init - retrieves files but takes no action\n  liveimage - writes image directly to specified device")
    parser.add_argument("--imagesize", help="Target image size in bytes", type=str)
    parser.add_argument("--device", help="Target device handle", type=str)
    args = parser.parse_args()
    target_image_size = sd_target_image_size
    cwd, out, cache = makedirs()
    blockdev = None

    if args.imagesize:
        target_image_size = parse_size(args.imagesize)
        print("Setting target image size to: {}".format(args.imagesize))

    if args.device:
        blockdev = args.device
        print('Directly setting up device {}'.format(blockdev))

    if not args.command:
        parser.print_help()
        parser.print_usage()
        sys.exit(0)

    if args.command == 'init':
        alpinefile = check_update_cached_alpine_iso(cache, alpine_url, alpine_sha256_url)
        sys.exit(0)

    if args.command == 'file':
        alpinefile = check_update_cached_alpine_iso(cache, alpine_url, alpine_sha256_url)
        create_loopback_image(out, target_image_size, leave_tempfiles=False, tarfile=alpinefile)
        sys.exit(0)

    if args.command == 'liveimage':
        if not blockdev:
            print("ERROR: Please specify valid target block device, (set to {})".format(blockdev))
            sys.exit(-1)

        alpinefile = check_update_cached_alpine_iso(cache, alpine_url, alpine_sha256_url)
        partition_device(blockdev)
        sys.exit(0)


if __name__ == "__main__":
    main()
