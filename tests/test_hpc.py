"""HBM Packet Controller Tests"""
from datetime import datetime

import pytest

from ska_low_cbf_sw_cnic.hbm_packet_controller import (
    BEAT_SIZE,
    _gap_from_rate,
    _get_padded_size,
)


class TestFunctions:
    @pytest.mark.parametrize(
        "raw, padded",
        [
            (1, BEAT_SIZE),
            (BEAT_SIZE, BEAT_SIZE),
            (3 * BEAT_SIZE + 1, 4 * BEAT_SIZE),
            (500 * BEAT_SIZE - 1, 500 * BEAT_SIZE),
        ],
    )
    def test_padded_size(self, raw, padded):
        """
        Data should be padded to the smallest multiple of BEAT_SIZE that it fits into
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
