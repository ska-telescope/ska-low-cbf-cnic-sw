# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 CSIRO Space and Astronomy.
#
# Distributed under the terms of the CSIRO Open Source Software Licence
# Agreement. See LICENSE for more info
"""PCAP(NG) file handling tests"""
import pytest

import ska_low_cbf_sw_cnic.pcap as pcap


def test_count_packets_in_pcap():
    """Verify packet counting"""
    assert pcap.count_packets_in_pcap("tests/codif_sample.pcapng") == 20


@pytest.mark.parametrize("extension", ["pcap", "pcapng"])
def test_writers(extension):
    """Make sure that multiple writers play nicely together"""
    with open(f"twenty.{extension}", "wb") as blah:
        writer_20 = pcap.get_writer(blah)
        with open(f"ten.{extension}", "wb") as foo:
            writer_10 = pcap.get_writer(foo)
            with open("tests/codif_sample.pcapng", "rb") as sample:
                reader = pcap.get_reader(sample)
                for n, (ts, pkt) in enumerate(reader):
                    writer_20.writepkt(pkt, ts)
                    if n % 2:
                        # write every second packet
                        writer_10.writepkt(pkt, ts)
                    if n >= 19:
                        break

    assert pcap.count_packets_in_pcap(f"twenty.{extension}") == 20
    assert pcap.count_packets_in_pcap(f"ten.{extension}") == 10
