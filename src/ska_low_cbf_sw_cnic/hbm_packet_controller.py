# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 CSIRO Space and Astronomy.
#
# Distributed under the terms of the CSIRO Open Source Software Licence
# Agreement. See LICENSE for more info.

# we use dynamic attributes that confuse pylint...
# pylint: disable=attribute-defined-outside-init
"""
HBM Packet Controller ICL (abstraction)
"""

import bisect
import math
import os
import typing
import warnings

import dpkt.pcapng
import numpy as np
from ska_low_cbf_fpga import ArgsFpgaInterface, FpgaPeripheral, IclField
from ska_low_cbf_fpga.args_map import ArgsFieldInfo

AXI_TRANSACTION_SIZE = 4096
BEAT_SIZE = 64


def _get_padded_size(packet_size: int) -> int:
    """
    Round up the packet size to the next 'beat's worth of data
    :param packet_size: bytes
    """
    pad_length = 0
    if packet_size % BEAT_SIZE:
        pad_length = BEAT_SIZE - (packet_size % BEAT_SIZE)
    return packet_size + pad_length


class HbmPacketController(FpgaPeripheral):
    """
    Class to represent an HbmPacketController FPGA Peripheral
    """

    def __init__(
        self,
        interfaces: typing.Union[
            ArgsFpgaInterface, typing.Dict[str, ArgsFpgaInterface]
        ],
        map_field_info: typing.Dict[str, ArgsFieldInfo],
        default_interface: str = "__default__",
    ) -> None:
        super().__init__(interfaces, map_field_info, default_interface)
        self._packets_to_transmit = 0
        """Number of packets to transmit"""

        # we don't have nice interface to find the actual size of the buffers...
        self._fpga_interface = self._interfaces[self._default_interface]
        # skip the first buffer (ARGS interchange),
        # get the sizes of all other shared buffers
        hbm_sizes = [
            _.size for _ in self._fpga_interface._mem_config[1:] if _.shared
        ]
        # convert sizes to a list of virtual end addresses of each buffer
        # e.g. [1000, 1000, 1000] => [1000, 2000, 3000]
        hbm_end_addresses = np.cumsum(hbm_sizes)
        # insert a zero for the first buffer's start address: [0, 1000, 2000, 3000]
        self._buffer_offsets = np.insert(hbm_end_addresses, 0, 0)
        """Virtual addresses of start/end of each HBM buffer
        (Note: n+1 elements, last element is end of last buffer)"""

    @property
    def packet_count(self) -> IclField[int]:
        """Get 64-bit total packet count"""
        return IclField(
            description="Total Packet Count",
            type_=int,
            value=(self.current_pkt_count_high.value << 32)
            + self.current_pkt_count_low.value,
        )

    def _virtual_write(self, data: bytes, address: int) -> None:
        """
        Simple virtual address mapper for writing to multiple HBM buffers.
        :param data: bytes object to write
        :param address: byte-based address
        :return:
        """
        data = np.frombuffer(data, dtype=np.uint8)
        # Note bisect works here because our first buffer to use is memory 1
        # (would need to add an offset if this was not the case)
        # e.g. if _buffer_offsets is [0, 1000, 2000, 3000]
        # address 50 will return 1; address 1500 will return 2
        start_buffer = bisect.bisect(self._buffer_offsets, address)
        end_buffer = bisect.bisect(self._buffer_offsets, address + len(data))
        if end_buffer >= len(self._buffer_offsets):
            raise RuntimeError(
                f"Cannot fit {len(data)} bytes "
                f"starting from virtual address {address}. "
                f"Buffers end at {self._buffer_offsets[-1]}."
            )

        start_offset = address - self._buffer_offsets[start_buffer - 1]
        if start_buffer == end_buffer:
            # the easy case - everything in one buffer
            self._fpga_interface.write_memory(start_buffer, data, start_offset)
        else:
            # split across buffers, assuming buffer size >> data size
            # how much room is left in the first buffer?
            first_size = (  # calculate buffer size from address map
                self._buffer_offsets[start_buffer]
                - self._buffer_offsets[start_buffer - 1]
            ) - start_offset
            self._fpga_interface.write_memory(
                start_buffer, data[:first_size], start_offset
            )
            self._fpga_interface.write_memory(
                start_buffer + 1, data[first_size:], 0
            )

    def dump_pcap(
        self,
        out_file: typing.BinaryIO,
        packet_size: int,
        ng: bool = True,
    ) -> None:
        """
        Dump a PCAP(NG) file from HBM
        :param out_file: File object to write to
        :param packet_size: Number of Bytes used for each packet
        :param ng: PCAP Next-Generation? (False = original pcap)
        """
        if ng:
            writer = dpkt.pcapng.Writer(out_file)
        else:
            writer = dpkt.pcap.Writer(out_file)

        # TODO - there will be an "end of data" value to give a stopping point...

        # start from 1 as our first buffer is #1
        for buffer in range(1, len(self._buffer_offsets)):
            raw = (
                self._interfaces[self._default_interface]
                .read_memory(buffer)
                .astype(np.uint8)
            )
            # ensure number of data bytes is an integer multiple of packet_size,
            # by discarding the remainder from the end
            if raw.nbytes % packet_size:
                raw = raw[: -(raw.nbytes % packet_size)]

            raw.shape = (raw.nbytes // packet_size, packet_size)
            for packet in raw:
                writer.writepkt(packet.tobytes())

    def load_pcap(self, in_file: typing.BinaryIO) -> None:
        """
        Load a PCAP(NG) file from disk to FPGA
        :param in_file: input PCAP(NG) file
        """
        # TODO is there a better way to detect the file format?
        if os.path.splitext(in_file.name)[1] == ".pcapng":
            reader = dpkt.pcapng.Reader
        else:
            reader = dpkt.pcap.Reader

        first_packet = True
        virtual_address = 0  # byte address to write to
        packet_padded_size = 0
        n_packets = 0
        packet_size = 0
        for timestamp, packet in reader(in_file):
            # assess first packet,
            # firmware assumes all packets are same size
            if first_packet:
                packet_size = len(packet)
                packet_padded_size = _get_padded_size(packet_size)
                first_packet = False

            # TODO do we need to check that it's a valid ethernet packet?
            #  - and verify the length?

            # not sure if writing each packet is better or worse than creating yet
            # another memory buffer...
            self._virtual_write(packet, virtual_address)
            n_packets += 1
            virtual_address += packet_padded_size

        self._packets_to_transmit = n_packets  # TODO move to FPGA?
        self.packet_size = packet_size
        self.expected_beats_per_packet = packet_padded_size // BEAT_SIZE
        self.expected_total_number_of_4k_axi = math.ceil(
            (n_packets * packet_padded_size) / AXI_TRANSACTION_SIZE
        )

    def configure_tx(
        self, n_loops: int = 1, burst_size: int = 1, burst_gap: int = 1000
    ) -> None:
        """
        Configure packet transmission parameters
        :param n_loops: number of loops
        :param burst_size: packets per burst
        :param burst_gap: time between bursts of packets (nanoseconds)
        """
        if burst_size != 1:
            warnings.warn("Packet burst not tested!")

        self.time_between_bursts_ns = burst_gap
        self.expected_packets_per_burst = burst_size
        self.expected_number_beats_per_burst = (
            self.expected_beats_per_packet * burst_size
        )
        # TODO - can we store number of packets in the FPGA?
        #  - this code won't work if "load_pcap" and "configure_tx" are called by
        #    different command-line utilities, for example
        self.expected_total_number_of_bursts = math.ceil(
            self._packets_to_transmit / burst_size
        )

        if n_loops > 1:
            self.loop_tx = True
            self.expected_number_of_loops = n_loops

    def start_tx(self) -> None:
        """
        Start transmitting packets
        """
        self.start_stop_tx = 0
        self.start_stop_tx = 1

    def start_rx(self, packet_size: int) -> None:
        """
        Start receiving packets into FPGA memory
        :param packet_size: only packets of this exact size are captured (bytes)
        """
        # TODO - register names not yet defined?
        # self.enable_capture = 0
        # self.rx_packet_size = packet_size
        # self.rx_reset = 1
        # self.rx_rest = 0
        # self.enable_capture = 1
