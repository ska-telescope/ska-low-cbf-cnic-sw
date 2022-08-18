# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 CSIRO Space and Astronomy.
#
# Distributed under the terms of the CSIRO Open Source Software Licence
# Agreement. See LICENSE for more info.

"""
CNIC FPGA Firmware ICL (Instrument Control Layer)
"""
import logging
import threading
import typing
from datetime import datetime

from ska_low_cbf_fpga import ArgsFpgaInterface, ArgsMap, FpgaPersonality

from ska_low_cbf_sw_cnic.hbm_packet_controller import HbmPacketController
from ska_low_cbf_sw_cnic.ptp import Ptp

RX_SLEEP_TIME = 5  # wait this many seconds between checking if Rx is finished


class CnicFpga(FpgaPersonality):
    """
    CNIC FPGA Personality ICL Class
    """

    _peripheral_class = {
        "timeslave": Ptp,
        "timeslave_b": Ptp,
        "hbm_pktcontroller": HbmPacketController,
    }

    def __init__(
        self,
        interfaces: typing.Union[
            ArgsFpgaInterface, typing.Dict[str, ArgsFpgaInterface]
        ],
        map_: ArgsMap,
        logger: logging.Logger = None,
        ptp_domain: int = 24,
    ) -> None:
        """
        Constructor
        :param interfaces: see FpgaPersonality
        :param map_:  see FpgaPersonality
        :param logger: see FpgaPersonality
        :param ptp_domain: PTP domain number
        """
        super().__init__(interfaces, map_, logger)
        self._configure_ptp(ptp_domain)
        self._rx_cancel = threading.Event()
        self._rx_thread = None

    def _configure_ptp(self, ptp_domain: int):
        alveo_macs = [_["address"] for _ in self.info["platform"]["macs"]]
        alveo_mac = alveo_macs[0]
        # MAC is str, colon-separated hex bytes "01:02:03:04:05:06"
        self._logger.info(f"Alveo MAC address: {alveo_mac}")
        # take low 3 bytes of mac, convert to int
        alveo_mac_low = int("".join(alveo_mac.split(":")[-3:]), 16)
        # configure the PTP core to use the same low 3 MAC bytes
        # (high bytes are set by the PTP core)
        self.timeslave.startup(alveo_mac_low, ptp_domain)
        self._logger.info(
            f"  PTP MAC address: {self.timeslave.mac_address.value}"
        )

    def transmit_pcap(
        self,
        in_filename: str,
        n_loops: int = 1,
        burst_size: int = 1,
        burst_gap: typing.Union[int, None] = None,
        rate: float = 100.0,
        start_time: typing.Union[datetime, None] = None,
    ) -> None:
        """
        Transmit packets from a PCAP file
        :param in_filename: input PCAP(NG) file path
        :param n_loops: number of loops
        :param burst_size: packets per burst
        :param burst_gap: packet burst period (ns), overrides rate
        :param rate: transmission rate (Gigabits per sec), ignored if burst_gap given
        :param start_time: optional time to begin transmission at
        (default None means begin immediately)
        """
        self.hbm_pktcontroller.tx_enable = False
        with open(in_filename, "rb") as in_file:
            print("Loading file")
            self.hbm_pktcontroller.load_pcap(in_file)
            print("Loading complete")
        print("Configuring Tx params")
        self.hbm_pktcontroller.configure_tx(
            n_loops, burst_size, burst_gap, rate
        )
        if start_time:
            print("Setting scheduled start time")
            self.timeslave.set_start_time(start_time)
        else:
            print("Starting transmission")
            self.hbm_pktcontroller.start_tx()

    def receive_pcap(
        self, out_filename: str, packet_size: int, n_packets: int = 0
    ) -> None:
        """
        Receive packets into a PCAP file
        :param out_filename: File path to write to
        :param packet_size: only packets of this exact size are captured (bytes)
        :param n_packets: number of packets to receive
        """
        # cancel any existing Rx wait thread
        if self._rx_thread:
            self._rx_cancel.set()
            self._rx_thread.join()
            self._rx_cancel.clear()
            if self._rx_thread.is_alive():
                raise RuntimeError("Previous Rx thread didn't stop")

        print("Setting receive parameters")
        self.hbm_pktcontroller.start_rx(packet_size, n_packets)

        # start a thread to wait for completion
        print("Starting thread to wait for completion")
        self._rx_thread = threading.Thread(
            target=self._dump_pcap_when_complete,
            args=(out_filename, packet_size),
        )
        self._rx_thread.start()

    def _dump_pcap_when_complete(
        self,
        out_filename: str,
        packet_size: int,
    ) -> None:
        """
        Wait for the FPGA to finish receiving packets then write them to disk
        :param out_filename: File object to write to
        :param packet_size: Number of Bytes used for each packet
        """
        while not (
            self.hbm_pktcontroller.rx_complete.value
            or (
                self.hbm_pktcontroller.rx_packet_count
                >= self.hbm_pktcontroller.rx_packets_to_capture
            )
        ):
            if self._rx_cancel.wait(timeout=RX_SLEEP_TIME):
                break
            print(".", end="", flush=True)

        print("\nWriting to file")
        with open(out_filename, "wb") as out_file:
            self.hbm_pktcontroller.dump_pcap(out_file, packet_size)
