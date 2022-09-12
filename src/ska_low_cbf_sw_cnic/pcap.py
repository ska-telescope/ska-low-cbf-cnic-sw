# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 CSIRO Space and Astronomy.
#
# Distributed under the terms of the CSIRO Open Source Software Licence
# Agreement. See LICENSE for more info.
"""
PCAP Processing Helper Functions
"""
import os
import typing

import dpkt


def get_reader(
    file: typing.BinaryIO,
) -> typing.Union[dpkt.pcap.Reader, dpkt.pcapng.Reader]:
    """Create a reader for a PCAP(NG) file"""
    # TODO is there a better way to detect the file format?
    if os.path.splitext(file.name)[1] == ".pcapng":
        reader = dpkt.pcapng.Reader
    else:
        reader = dpkt.pcap.Reader
    return reader(file)


def get_writer(
    file: typing.BinaryIO,
) -> typing.Union[dpkt.pcap.Writer, dpkt.pcapng.Writer]:
    """Create a writer for a PCAP(NG) file"""
    if os.path.splitext(file.name)[1] == ".pcapng":
        writer = dpkt.pcapng.Writer(file)
    else:
        writer = dpkt.pcap.Writer(file, nano=True)
    return writer


def packet_size_from_pcap(in_filename: str) -> int:
    """
    Get the packet size from a given PCAP(NG) file.
    Note: only inspects the first packet!
    :param in_filename: path to file
    :return: packet size (Bytes)
    """
    with open(in_filename, "rb") as in_file:
        reader = get_reader(in_file)
        for timestamp, packet in reader:
            # assess first packet,
            # assume all packets are same size
            return len(packet)
