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
    ) -> None:
        """
        Constructor
        :param interfaces: see FpgaPersonality
        :param map_:  see FpgaPersonality
        :param logger: see FpgaPersonality
        """
        super().__init__(interfaces, map_, logger)
        self._rx_cancel = threading.Event()
        self._rx_thread = None

    def transmit_pcap(
        self,
        in_file: typing.BinaryIO,
        n_loops: int = 1,
        burst_size: int = 1,
        burst_gap: int = 1000,
    ) -> None:
        """
        Transmit packets from a PCAP file
        :param in_file: input PCAP(NG) file
        :param n_loops: number of loops
        :param burst_size: packets per burst
        :param burst_gap: time between bursts of packets (nanoseconds)
        :return:
        """
        self.hbm_pktcontroller.load_pcap(in_file)
        self.hbm_pktcontroller.configure_tx(n_loops, burst_size, burst_gap)
        self.hbm_pktcontroller.start_tx()

    def receive_pcap(
        self, out_file: typing.BinaryIO, packet_size: int
    ) -> None:
        """
        Receive packets into a PCAP file
        :param out_file: File object to write to
        :param packet_size: only packets of this exact size are captured (bytes)
        """
        # cancel any existing Rx wait thread
        if self._rx_thread:
            self._rx_cancel.set()
            self._rx_thread.join()
            self._rx_cancel.clear()

        self.hbm_pktcontroller.start_rx(packet_size)

        if self._rx_thread.is_alive():
            raise RuntimeError("Previous Rx thread didn't stop")

        # start a thread to wait for completion
        self._rx_thread = threading.Thread(
            target=self._dump_pcap_when_complete,
            args=(out_file, packet_size),
        )
        self._rx_thread.start()

    def _dump_pcap_when_complete(
        self,
        out_file: typing.BinaryIO,
        packet_size: int,
    ) -> None:
        """
        Wait for the FPGA to finish receiving packets then write them to disk
        :param out_file: File object to write to
        :param packet_size: Number of Bytes used for each packet
        """
        # TODO register name not yet defined ("capture_done" is a placeholder)
        while not self.hbm_pktcontroller.capture_done.value:
            if self._rx_cancel.wait(timeout=RX_SLEEP_TIME):
                break

        self.hbm_pktcontroller.dump_pcap(out_file, packet_size)
