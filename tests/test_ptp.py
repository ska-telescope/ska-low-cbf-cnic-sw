# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 CSIRO Space and Astronomy.
#
# Distributed under the terms of the CSIRO Open Source Software Licence
# Agreement. See LICENSE for more info
"""PTP (Precision Time Protocol) Peripheral Tests"""

import pytest
from ska_low_cbf_fpga import ArgsMap, ArgsSimulator, IclField

from ska_low_cbf_sw_cnic.ptp import (
    Ptp,
    datetime_from_str,
    split_datetime,
    unix_ts_from_ptp,
)

from .fpgamap_22081921 import FPGAMAP


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


class TestTimestampConversion:
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
    def test_unix_ts_from_ptp(self, ptp_ts, unix_ts):
        """Test UNIX timestamp derivation from PTP 80-bit value"""
        assert unix_ts_from_ptp(ptp_ts) == unix_ts

    # Note time strings are interpreted as being in local time zone.
    # ("1970-01-01 00:00:01" in Australia gives a -ve unix timestamp!)
    @pytest.mark.parametrize(
        "string", ["1970-01-01 20:00:01", "2022-08-19 17:22:33"]
    )
    @pytest.mark.parametrize(
        "param",
        [
            "tx_start",
            "tx_stop",
            "rx_start",
            "rx_stop",
        ],
    )
    def test_time_control_params(self, ptp, param, string):
        """Check that the time string goes into the registers and comes out the same"""
        # ICL interface uses, for example, "tx_start_time"
        icl_attr = param + "_time"
        setattr(ptp, icl_attr, string)

        # Check the 3 registers are set
        # (guards against use of wrong registers in ICL)
        upper, lower, sub = split_datetime(datetime_from_str(string))
        print(upper, lower, sub)
        assert upper == getattr(ptp, param + "_ptp_seconds_upper").value
        assert lower == getattr(ptp, param + "_ptp_seconds_lower").value
        assert sub == getattr(ptp, param + "_ptp_sub_seconds").value

        # Check read-back as str
        assert getattr(ptp, icl_attr) == string
