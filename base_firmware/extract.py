#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tool for extracting an iCord HD firmware root filesystem.

Extracted filesystem is created in './extracted_root'.

Needed binary files are stored in
    * './original_firmware' (Humax firmware file)
    * './bin' (humidify-linux-i386)
    * './firmware-mod-kit-read-only/trunk/src/squashfs-3.0/' (unsquashfs)

"""
import sys
import os
import zipfile
import urllib2
import logging
import logging.config
import shutil
import tempfile
import traceback
from subprocess import call

#: project root path
PROJECT_ROOT = os.path.abspath(".")

#: temporary files
TEMP_DIR = tempfile.mkdtemp()

#: directory to store extracted firmware_root
EXTRACTED_ROOT = os.path.join(PROJECT_ROOT, "extracted_root")

# logging config
LOGGING_CFG = {
    'version': 1,
    'disable_existing_loggers': True,
    'formatters': {
        'short' : {
            'format': '%(asctime)s %(levelname)-8s %(module)s %(message)s',
            'datefmt':'%Y-%m-%d %H:%M'
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'stream': 'ext://sys.stdout',
            'formatter': 'short',
        },
    },
    'loggers': {
        'extract': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    }
}

# initialise logging
logging.config.dictConfig(LOGGING_CFG)

# logger
LOG = logging.getLogger("extract")

class MissingPrerequisite(BaseException):
    pass

def prereq_hmx(source_url="http://www.humax-digital.de/products/hdpvr.zip"):
    """
    Make sure that a Humax iCord HD firmware archive is available.
    """
    filename = os.path.join(PROJECT_ROOT, "original_firmware", "hdpvr.hmx")

    LOG.info("HMX: %s" % filename)

    if os.path.isfile(filename):
        LOG.debug("[HMX] existing")
        return filename

    dest_dir = os.path.dirname(filename)
    zip_source = os.path.join(TEMP_DIR, "hdpvr.zip")

    if not os.path.isdir(dest_dir):
        LOG.debug("creating path: %s" % dest_dir)
        os.makedirs(dest_dir)

    dl_source = urllib2.urlopen(source_url)
    with open(zip_source, "wb") as dest:
        dest.write(dl_source.read())

    with zipfile.ZipFile(zip_source) as source:
        source.extract("hdpvr.hmx", dest_dir)

    if os.path.isfile(filename):
        LOG.debug("[HMX] fetched")
        return filename

    raise MissingPrerequisite(filename)

def prereq_humidify():
    """
    Make sure that the humidify tool by af123 is available.
    """
    filename = os.path.join(PROJECT_ROOT, "bin", "humidify-linux-i386")
    source_urls = (
                "http://hummy.tv/forum/threads/humidify-hdf-file-utility.235/",
                "http://www20.zippyshare.com/v/27034196/file.html")

    LOG.info("HUMIDIFY: %s" % filename)

    if os.path.isfile(filename):
        LOG.debug("existing")
        return filename
    else:
        LOG.info("Please visit following URLs to retrieve humidify tool:")
        LOG.info(", ".join(source_urls))

    raise MissingPrerequisite(filename)

def prereq_unsquashfs():
    """
    Make sure an unsquashfs (provided by firmware-mod-kit) is available.

    Needs subversion(svn) and a compiler (e.g. gcc).
    """
    filename = os.path.join(PROJECT_ROOT,
                        "firmware-mod-kit-read-only/trunk/src/squashfs-3.0/",
                        "unsquashfs")

    LOG.info("UNSQUASHFS: %s" % filename)

    if os.path.isfile(filename):
        LOG.debug("existing")
        return filename

    commands = [
                ("svn checkout http://firmware-mod-kit.googlecode.com/svn/ firmware-mod-kit-read-only", 
                 PROJECT_ROOT),
                ("./configure",
                 os.path.join(PROJECT_ROOT,
                              "firmware-mod-kit-read-only/trunk/src")),
                ("make", os.path.join(PROJECT_ROOT,
                                      "firmware-mod-kit-read-only/trunk/src")),
                ]

    # save current working dir
    old_cwd = os.getcwd()
    for (cmd, pwd) in commands:
        os.chdir(pwd)
        call(cmd, shell=True)
    # restore working dir
    os.chdir(old_cwd)

    if os.path.isfile(filename):
        LOG.debug("created")
        return filename

    raise MissingPrerequisite(filename)

def extract(hmx_file, unsquashfs, humidify, extracted_root=EXTRACTED_ROOT,
            destroy=False):
    """
    Extract the contained root filesystem of a hmx file *hmx_file* to 
    *extracted_root* using *unsquashfs* and *humidify*.
    If *extracted_root* is existing and *destroy* is not set an IOError
    exception is thrown.

    Needs a user with sudo privileges.
    """

    if os.path.isdir(extracted_root) and (destroy is False):
        LOG.error("extracted_root dir %s exists and destroy=False" % repr(
                                                                extracted_root))
        raise IOError("Existing: %s" % extracted_root)

    if os.path.isdir(extracted_root):
        shutil.rmtree(extracted_root)

    cmd = "%s -x %s" % (humidify, hmx_file)
    raw_filename = os.path.join(TEMP_DIR, "3.hdfbin-3-700000.raw")

    LOG.info("STEP 1: Extract hmx %s" % repr(hmx_file))
    LOG.debug(" cmd     : %s" % cmd)
    LOG.debug(" expected: %s" % raw_filename)

    if not os.path.isfile(raw_filename):
        os.chdir(TEMP_DIR)
        call(cmd, shell=True)

        if not os.path.isfile(raw_filename):
            raise MissingPrerequisite(raw_filename)
    else:
        LOG.debug("skipped")

    LOG.info("STEP 2: [sudo] unsquashfs")

    cmd = "sudo %s -n %s" % (unsquashfs, raw_filename)
    squashfs_root = os.path.join(TEMP_DIR, "squashfs-root")
    os.chdir(TEMP_DIR)
    call(cmd, shell=True)
    
    if not os.path.isdir(squashfs_root):
        raise MissingPrerequisite(squashfs_root)

    LOG.info("STEP 3: [sudo] chown")
    my_gid = os.getegid()
    my_uid = os.geteuid()
    cmd = "sudo chown %d:%d -R %s" % (my_uid, my_gid, squashfs_root)
    call(cmd, shell=True)

    LOG.info("STEP 4: move tree")
    LOG.debug(" %s -> %s" % (squashfs_root, extracted_root))
    shutil.move(squashfs_root, extracted_root)

    if not os.path.isdir(extracted_root):
        raise MissingPrerequisite(extracted_root)

    return extracted_root

def prereq_programs():
    """
    Make sure that needed executables are available.
    """
    try:
        hmx_file = prereq_hmx()
        unsquashfs = prereq_unsquashfs()
        humidify = prereq_humidify()
    except MissingPrerequisite, what:
        LOG.error("Missing prerequisite: %s" % what)
        raise

    return (hmx_file, unsquashfs, humidify)

def run_extraction():
    """
    Extract the contained root filesystem of a hmx file.
    """
    try:
        (hmx_file, unsquashfs, humidify) = prereq_programs()
        return extract(hmx_file, unsquashfs, humidify)
    except MissingPrerequisite, what:
        LOG.error("Missing prerequisite: %s" % what)

if __name__ == '__main__':
    try:
        extracted_root = run_extraction()
    except MissingPrerequisite, what:
        LOG.error("Missing prerequisite: %s" % what)
    except Exception, exception:
        traceback.print_exc(file=sys.stdout)

    # delete temporary directory
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
