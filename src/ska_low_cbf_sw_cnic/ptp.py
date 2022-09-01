# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 CSIRO Space and Astronomy.
#
# Distributed under the terms of the CSIRO Open Source Software Licence Agreement
# See LICENSE for more info.
"""
PTP Peripheral ICL
"""
from enum import IntEnum

from ska_low_cbf_fpga import FpgaPeripheral, IclField


class PtpCommand(IntEnum):
    RELOAD_PROFILE = 0
    ENABLE = 1
    DISABLE = 2
    SERVO_STOP = 3
    SERVO_RESUME = 4
    PPS_MODE = 5
    PTP_MODE = 6


class Ptp(FpgaPeripheral):
    """
    Base PTP Configuration
    """

    _cfg_properties = {
        "seconds_lo": 0x8040,
        "seconds_hi": 0x8041,
        "nsec": 0x8042,
        "valid_time": 0x8043,
        "profile_announce_intvl": 0x8044,
        "profile_delay_intvl": 0x8045,
        "profile_announce_rcpt_timeout": 0x8046,
        "profile_domain_num": 0x8047,
        "profile_delay_mechanism": 0x8048,
        "profile_report_period": 0x8049,
        "profile_mac_hi": 0x804A,  # HH------
        "profile_mac_lo": 0x804B,  # ----LLXX
        "profile_this_ip_addr": 0x804C,
        "profile_transport_proto": 0x804D,
        "cmd": 0x804E,
        "cmd_seq": 0x804F,
        "seq_id": 0x8100,
        "blk1_pathdly_lo": 0x8114,
        "blk1_pathdly_hi": 0x8115,
        "blk1_unk1": 0x8116,
        "blk1_seq_id": 0x8117,
        "blk1_time_secs": 0x8118,
        "blk1_time_frac_secs": 0x8119,
        "blk1_last_delta": 0x811A,
        "blk1_last_phaseinc_lo": 0x811B,
        "blk1_last_phaseinc_hi": 0x811C,
        "blk1_seq_errs": 0x811D,
        "blk1_packet_drop": 0x811E,
        "blk1_t1_sec": 0x811F,
        "blk1_t1_nano": 0x8120,
        "blk1_t2_sec": 0x8121,
        "blk1_t2_nano": 0x8122,
        "blk1_t3_sec": 0x8123,
        "blk1_t3_nano": 0x8124,
        "blk1_t4_sec": 0x8125,
        "blk1_t4_nano": 0x8126,
        "blk1_t4_ref_clk_per_pps": 0x8127,
    }
    """key: name, value: offset"""

    def __getattr__(self, item) -> IclField:
        """Get config param from ram buffer"""
        if item in self._cfg_properties:
            offset = self._cfg_properties[item]
            return IclField(
                address=self["data"].address + offset,
                description=item,
                value=self["data"][offset],
                type_=int,
            )

        return super().__getattr__(item)

    def __setattr__(self, key, value):
        """Set config param in ram buffer"""
        if key in self._cfg_properties:
            self["data"][self._cfg_properties[key]] = value
            return

        super().__setattr__(key, value)

    def __dir__(self):
        """Add our config params to the directory"""
        return list(super().__dir__()) + list(self._cfg_properties.keys())

    @property
    def user_mac_address(self) -> IclField[int]:
        """Get the user-configurable portion of the MAC address (lower 3 bytes)"""
        a = (self.profile_mac_hi.value & 0xFF000000) >> 24
        b = self.profile_mac_lo.value & 0xFF
        c = (self.profile_mac_lo.value & 0xFF00) >> 8
        return IclField(
            description="Low 3 bytes of MAC address",
            value=(a << 16) | (b << 8) | c,
            type_=int,
        )

    @user_mac_address.setter
    def user_mac_address(self, mac_address) -> None:
        """
        Set the user-configurable portion of the MAC address (lower 3 bytes)
        :param mac_address: MAC address, only the low 3 bytes are used.
        """
        original_hi = self.profile_mac_hi.value
        original_lo = self.profile_mac_lo.value
        # shift by 8 is equivalent to shifting down 16 then up 24
        self.profile_mac_hi = (original_hi & 0x00FFFFFF) | (
            (mac_address & 0xFF0000) << 8
        )
        # swap lower two bytes
        self.profile_mac_lo = (original_lo & 0xFFFF0000) | (
            ((mac_address & 0xFF) << 8) | ((mac_address & 0xFF00) >> 8)
        )

    @property
    def mac_address(self) -> IclField[str]:
        """Get MAC address"""
        return IclField(
            value="DC:3C:F6:"  # top 3 bytes are hard coded in PTP core
            + ":".join(
                f"{self.user_mac_address.value:06x}"[_ : _ + 2]
                for _ in range(0, 6, 2)
            ).upper(),
            description="Full MAC address",
            type_=str,
        )

    def command(self, cmd: PtpCommand) -> None:
        """Execute a PTP command"""
        self.cmd = cmd.value
        self.cmd_seq += 1

    def startup(self, mac_address: int = 0x010203, domain: int = 1) -> None:
        """
        Start PTP
        :param domain: PTP domain
        :param mac_address: MAC address, only the low 3 bytes are used.
        """
        self.profile_domain_num = domain
        self.user_mac_address = mac_address
        self.command(PtpCommand.RELOAD_PROFILE)
