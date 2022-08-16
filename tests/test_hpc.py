# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 CSIRO Space and Astronomy.
#
# Distributed under the terms of the CSIRO Open Source Software Licence
# Agreement. See LICENSE for more info
"""HBM Packet Controller Tests"""

import pytest

from ska_low_cbf_sw_cnic.hbm_packet_controller import (
    MEM_ALIGN_SIZE,
    _gap_from_rate,
    _get_padded_size,
)


class TestFunctions:
    @pytest.mark.parametrize(
        "raw, padded",
        [
            (1, MEM_ALIGN_SIZE),
            (MEM_ALIGN_SIZE, MEM_ALIGN_SIZE),
            (3 * MEM_ALIGN_SIZE + 1, 4 * MEM_ALIGN_SIZE),
            (500 * MEM_ALIGN_SIZE - 1, 500 * MEM_ALIGN_SIZE),
        ],
    )
    def test_padded_size(self, raw, padded):
        """
        Data should be padded to the smallest multiple of MEM_ALIGN_SIZE that it fits
        into
        :param raw: size of actual data
        :param padded: expected size after padding
        """
        assert _get_padded_size(raw) == padded

    @pytest.mark.parametrize(
        "packet_size, rate, burst_size, period",
        [
            (101, 100, 1, 1e-08),  # 101 Byte packet = 1000 bits on wire
            (101, 1, 1, 1e-06),
            (101, 100, 10, 1e-07),
            (101, 10, 10, 1e-06),
            (7976, 10, 1, 6.4e-06),
        ],
    )
    def test_gap(self, packet_size, rate, burst_size, period):
        """
        'Gap' is really the packet (burst) period.
        i.e. time between successive packet starts.
        :param packet_size: bytes
        :param rate: Gbps
        :param burst_size: number of packets sent together in a burst
        :param period: seconds
        """
        # _gap_from_rate returns nanoseconds
        assert _gap_from_rate(
            packet_size, rate, burst_size=burst_size
        ) == pytest.approx(period * 1e9)
