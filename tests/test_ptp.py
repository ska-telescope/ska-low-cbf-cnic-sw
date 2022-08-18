# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 CSIRO Space and Astronomy.
#
# Distributed under the terms of the CSIRO Open Source Software Licence
# Agreement. See LICENSE for more info
"""PTP (Precision Time Protocol) Peripheral Tests"""
from datetime import datetime

import pytest
from ska_low_cbf_fpga import ArgsMap, ArgsSimulator

from ska_low_cbf_sw_cnic.ptp import Ptp, unix_ts_from_ptp

from .fpgamap_22032914 import FPGAMAP


@pytest.fixture
def ptp():
    return Ptp(ArgsSimulator(fpga_map=FPGAMAP), ArgsMap(FPGAMAP)["timeslave"])


class TestPtp:
    def test_mac(self, ptp):
        """Check MAC address byte ordering"""
        TEST_ADDRESS = 0xFE_DC_BA
        ptp.user_mac_address = TEST_ADDRESS
        assert (ptp.profile_mac_hi.value & 0xFF000000) >> 24 == 0xFE
        assert (ptp.profile_mac_lo.value & 0xFF00) >> 8 == 0xBA
        assert (ptp.profile_mac_lo.value & 0xFF) == 0xDC
        assert ptp.user_mac_address.value == TEST_ADDRESS


# PTP ts has 32 bits of nanoseconds, top 48 bits are seconds.
@pytest.mark.parametrize(
    "ptp_ts, unix_ts",
    [
        (100_000_000, 0.1),
        (900_000_000, 0.9),
        (0x1234_0000_0000, 0x1234),
        (0x1234_0000_0000 + 250_000_000, 0x1234 + 0.25),
    ],
)
class TestTimestampConversion:
    def test_unix_ts_from_ptp(self, ptp_ts, unix_ts):
        """Test UNIX timestamp derivation from PTP 80-bit value"""
        assert unix_ts_from_ptp(ptp_ts) == unix_ts

    def test_start_time(self, ptp, ptp_ts, unix_ts):
        """Test setting PTP start time & read-back thereof"""
        start_dt = datetime.fromtimestamp(unix_ts)
        ptp.set_start_time(start_dt)
        assert ptp._scheduled_ptp_ts == ptp_ts
        assert ptp.scheduled_time.value == unix_ts
