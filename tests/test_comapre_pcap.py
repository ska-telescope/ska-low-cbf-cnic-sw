# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 CSIRO Space and Astronomy.
#
# Distributed under the terms of the CSIRO Open Source Software Licence
# Agreement. See LICENSE for more info
"""compare_packet utility tests"""

from ska_low_cbf_sw_cnic.compare_pcap import compare_n_packets
from ska_low_cbf_sw_cnic.pcap import get_reader


def test_same_file_compares_equal():
    """If we compare a file to itself, it must have no differences!"""
    differences, n_compared = compare_n_packets(
        1_000_000,
        get_reader(open("tests/codif_sample.pcapng", "rb")),
        get_reader(open("tests/codif_sample.pcapng", "rb")),
        36001,
    )
    assert len(differences) == 0
