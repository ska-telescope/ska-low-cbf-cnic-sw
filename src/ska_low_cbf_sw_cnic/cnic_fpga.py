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
import time
import typing

from ska_low_cbf_fpga import (
    ArgsFpgaInterface,
    ArgsMap,
    FpgaPersonality,
    IclField,
)

from ska_low_cbf_sw_cnic.hbm_packet_controller import HbmPacketController
from ska_low_cbf_sw_cnic.ptp import Ptp

RX_SLEEP_TIME = 5  # wait this many seconds between checking if Rx is finished
LOAD_SLEEP_TIME = (
    5  # wait this many seconds between checking if Load is finished
)


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
        self._load_thread = None
        self._requested_pcap = None

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

    def prepare_transmit(
        self,
        in_filename: str,
        n_loops: int = 1,
        burst_size: int = 1,
        burst_gap: typing.Union[int, None] = None,
        rate: float = 100.0,
    ) -> None:
        """
        Prepare for transmission
        :param in_filename: input PCAP(NG) file path
        :param n_loops: number of loops
        :param burst_size: packets per burst
        :param burst_gap: packet burst period (ns), overrides rate
        :param rate: transmission rate (Gigabits per sec), ignored if burst_gap given
        """
        if self._load_thread_active:
            raise RuntimeError(
                f"Loading {self._requested_pcap} still in progress!"
            )
        self._requested_pcap = in_filename

        self.hbm_pktcontroller.tx_enable = False
        self.timeslave.schedule_control_reset = 1
        self.hbm_pktcontroller.configure_tx(
            n_loops, burst_size, burst_gap, rate
        )

        if self.hbm_pktcontroller.loaded_pcap.value != self._requested_pcap:
            self._load_thread = threading.Thread(
                target=self.hbm_pktcontroller.load_pcap, args=(in_filename,)
            )
            self._load_thread.start()

    @property
    def _load_thread_active(self) -> bool:
        """Is the PCAP load thread active?"""
        if self._load_thread:
            if self._load_thread.is_alive():
                return True
            else:
                self._load_thread.join()
                self._load_thread = None
        return False

    @property
    def ready_to_transmit(self) -> IclField[bool]:
        """Can we transmit? i.e. Is our PCAP file loaded?"""
        value = False
        if self._requested_pcap and not self._load_thread_active:
            value = (
                self.hbm_pktcontroller.loaded_pcap.value
                == self._requested_pcap
            )
        return IclField(
            description="CNIC Ready to Transmit", type_=bool, value=value
        )

    def begin_transmit(
        self,
        start_time: typing.Union[str, None] = None,
        stop_time: typing.Union[str, None] = None,
    ) -> None:
        """
        Begin Transmission (either now or later)
        :param start_time: optional time to begin transmission at
        (start now if not otherwise specified)
        :param stop_time: optional time to end transmission at
        """
        print(f"Scheduling Tx stop time: {stop_time}")
        self.timeslave.tx_stop_time = stop_time
        print(f"Scheduling Tx start time: {start_time}")
        self.timeslave.tx_start_time = start_time
        self.timeslave.schedule_control_reset = 0

        if not start_time:
            print("Starting transmission")
            self.hbm_pktcontroller.start_tx()

    def transmit_pcap(
        self,
        in_filename: str,
        n_loops: int = 1,
        burst_size: int = 1,
        burst_gap: typing.Union[int, None] = None,
        rate: float = 100.0,
        start_time: typing.Union[str, None] = None,
        stop_time: typing.Union[str, None] = None,
    ) -> None:
        """
        Transmit packets from a PCAP file
        :param in_filename: input PCAP(NG) file path
        :param n_loops: number of loops
        :param burst_size: packets per burst
        :param burst_gap: packet burst period (ns), overrides rate
        :param rate: transmission rate (Gigabits per sec), ignored if burst_gap given
        :param start_time: optional time to begin transmission at
        (start now if not otherwise specified)
        :param stop_time: optional time to end transmission at
        """
        self.prepare_transmit(
            in_filename, n_loops, burst_size, burst_gap, rate
        )
        while not self.ready_to_transmit:
            time.sleep(LOAD_SLEEP_TIME)
        self.begin_transmit(start_time, stop_time)

    def receive_pcap(
        self,
        out_filename: str,
        packet_size: int,
        n_packets: int = 0,
        start_time: typing.Union[str, None] = None,
        stop_time: typing.Union[str, None] = None,
    ) -> None:
        """
        Receive packets into a PCAP file
        :param out_filename: File path to write to
        :param packet_size: only packets of this exact size are captured (bytes)
        :param n_packets: number of packets to receive
        :param start_time: optional time to begin reception at
        :param stop_time: optional time to end reception at
        """
        self.timeslave.schedule_control_reset = 1
        # cancel any existing Rx wait thread
        if self._rx_thread:
            self._rx_cancel.set()
            self._rx_thread.join()
            self._rx_cancel.clear()
            if self._rx_thread.is_alive():
                raise RuntimeError("Previous Rx thread didn't stop")

        print(f"Scheduling Rx stop time: {stop_time}")
        self.timeslave.rx_stop_time = stop_time
        print(f"Scheduling Rx start time: {start_time}")
        self.timeslave.rx_start_time = start_time
        self.timeslave.schedule_control_reset = 0

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

        print("")
        self.hbm_pktcontroller.dump_pcap(out_filename, packet_size)
