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
from ska_low_cbf_fpga.args_fpga import str_from_int_bytes
from ska_low_cbf_fpga.args_map import ArgsFieldInfo

from ska_low_cbf_sw_cnic.ptp import TIMESTAMP_BITS, unix_ts_from_ptp

# These sizes are all in Bytes
IFG_SIZE = 20  # Ethernet Inter-Frame Gap
FCS_SIZE = 4  # Ethernet Frame Check Sequence
AXI_TRANSACTION_SIZE = 4096
BEAT_SIZE = 64
MEM_ALIGN_SIZE = 64  # data in HBM aligned to multiples of this
TIMESTAMP_SIZE = TIMESTAMP_BITS // 8


def _get_padded_size(data_size: int) -> int:
    """
    Round up the packet size to the next 'beat's worth of data
    :param data_size: bytes
    """
    pad_length = 0
    if data_size % MEM_ALIGN_SIZE:
        pad_length = MEM_ALIGN_SIZE - (data_size % MEM_ALIGN_SIZE)
    return data_size + pad_length


def _gap_from_rate(packet_size: int, rate: float, burst_size: int = 1) -> int:
    """
    Calculate packet burst gap (really a period) in nanoseconds
    :param packet_size: bytes
    :param rate: Gigabits per second
    :param burst_size: number of packets in a burst
    """
    # Effective packet size on wire
    line_bytes = packet_size + IFG_SIZE + FCS_SIZE
    # Desired packets/s
    packet_rate = (rate * 1e9) / (line_bytes * 8)
    # Convert to nanoseconds and apply burst size factor
    return math.ceil(1e9 * burst_size / packet_rate)


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
    def tx_packet_count(self) -> IclField[int]:
        """Get 64-bit total Tx packet count"""
        return IclField(
            description="Transmitted Packet Count",
            type_=int,
            value=(self.tx_packet_count_hi.value << 32)
            | self.tx_packet_count_lo.value,
        )

    @property
    def rx_packet_count(self) -> IclField[int]:
        """Get 64-bit total Rx packet count"""
        return IclField(
            description="Received Packet Count",
            type_=int,
            value=(self.rx_packet_count_hi.value << 32)
            | self.rx_packet_count_lo.value,
        )

    def _virtual_write(self, data: np.ndarray, address: int) -> None:
        """
        Simple virtual address mapper for writing to multiple HBM buffers.
        :param data: numpy array to write
        :param address: byte-based address
        """
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
        timestamped: bool = True,
    ) -> None:
        """
        Dump a PCAP(NG) file from HBM
        :param out_file: File object to write to.
        File type determined by extension, use .pcapng for next-gen.
        :param packet_size: Number of Bytes used for each packet
        :param timestamped: does the data in HBM contain timestamps?
        (Rx data will have timestamps, but data loaded for Tx will not)
        """
        if os.path.splitext(out_file.name)[1] == ".pcapng":
            writer = dpkt.pcapng.Writer(out_file)
        else:
            writer = dpkt.pcap.Writer(out_file, nano=True)

        padded_packet_size = _get_padded_size(packet_size)
        data_chunk_size = (
            padded_packet_size  # we need to process this much at a time
        )
        if timestamped:
            padded_timestamp_size = _get_padded_size(TIMESTAMP_SIZE)
            data_chunk_size += padded_timestamp_size

        last_partial_packet = None
        first_packet = True
        n_packets = 0
        # start from 1 as our first buffer is #1
        for buffer in range(1, len(self._buffer_offsets)):
            end = getattr(self, f"rx_hbm_{buffer}_end_addr").value
            print(
                f"Reading {end} B from HBM buffer {buffer} ",
                end="",
                flush=True,
            )
            if end == 0:
                # No data in this buffer, so we have already processed the last packet
                break

            # WORKAROUND for weird bug when reading 2GB+ on some machines
            # hopefully we can remove this later
            raw = np.empty(end, dtype=np.uint8)
            page_size = 1 << 30  # read 1GB
            for this_read_start in range(0, end, page_size):
                this_read_end = min(this_read_start + page_size, end)
                n_bytes = this_read_end - this_read_start
                raw[this_read_start:this_read_end] = (
                    self._interfaces[self._default_interface]
                    .read_memory(buffer, n_bytes, this_read_start)
                    .view(dtype=np.uint8)
                )
                print(".", end="", flush=True)
            # END WORKAROUND
            # below is the code that would work if not for the bug!
            # raw = (
            #     self._interfaces[self._default_interface]
            #     .read_memory(buffer, end)
            #     .view(dtype=np.uint8)
            # )
            print(f"\nWriting buffer {buffer} packets to file")

            if last_partial_packet is not None:
                # insert tail of last buffer into head of this one
                raw = np.insert(raw, 0, last_partial_packet)

            # ensure number of data bytes is an integer multiple of
            # data_chunk_size, by discarding the remainder from the end
            if raw.nbytes % data_chunk_size:
                discard_bytes = raw.nbytes % data_chunk_size
                # save the partial packet for next loop
                last_partial_packet = raw[-discard_bytes:]
                raw = raw[:-discard_bytes]
            else:
                last_partial_packet = None

            raw.shape = (raw.nbytes // data_chunk_size, data_chunk_size)
            for data in raw:
                if timestamped:
                    packet_data = data[:packet_size].tobytes()
                    timestamp = unix_ts_from_ptp(
                        int.from_bytes(
                            data[
                                padded_packet_size : padded_packet_size
                                + TIMESTAMP_SIZE
                            ].tobytes(),
                            "big",
                        )
                    )
                    writer.writepkt(packet_data, timestamp)
                    if first_packet:
                        first_ts = timestamp
                        first_packet = False
                else:
                    writer.writepkt(data[:packet_size].tobytes())
                n_packets += 1

        # end for each buffer loop
        print("Finished writing\n")
        total_bytes = n_packets * packet_size
        if timestamped:
            duration = timestamp - first_ts
            data_rate_gbps = (8 * total_bytes / duration) / 1e9
            print(f"Capture duration {duration:.9f} s")
            print(f"Average data rate {data_rate_gbps:.3f} Gbps")
        print(
            (
                f"Wrote {n_packets} packets, "
                f"{str_from_int_bytes(total_bytes)} "
                f"to {out_file.name}"
            )
        )

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
        dot_print_increment = 128 << 20  # print progress every 128MiB
        print_next_dot = 0
        n_packets = 0
        packet_size = 0
        for timestamp, packet in reader(in_file):
            # assess first packet,
            # firmware assumes all packets are same size
            if first_packet:
                packet_size = len(packet)
                packet_padded_size = _get_padded_size(packet_size)
                first_packet = False
                padded_packet = np.zeros(packet_padded_size, dtype=np.uint8)

            # TODO do we need to check that it's a valid ethernet packet?
            #  - and verify the length?

            padded_packet[:packet_size] = np.frombuffer(packet, dtype=np.uint8)
            self._virtual_write(padded_packet, virtual_address)
            n_packets += 1
            virtual_address += packet_padded_size
            if virtual_address >= print_next_dot:
                print(".", end="", flush=True)
                print_next_dot += dot_print_increment

        print(
            f"\nLoaded {n_packets - 1} packets, {virtual_address - packet_padded_size} Bytes"
        )
        self.tx_total_number_tx_packets = n_packets
        self.tx_packet_size = packet_size
        self.tx_beats_per_packet = packet_padded_size // BEAT_SIZE
        self.tx_axi_transactions = math.ceil(
            (n_packets * packet_padded_size) / AXI_TRANSACTION_SIZE
        )

    def configure_tx(
        self,
        n_loops: int = 1,
        burst_size: int = 1,
        burst_gap: typing.Union[int, None] = None,
        rate: float = 100.0,
    ) -> None:
        """
        Configure packet transmission parameters
        :param n_loops: number of loops
        :param burst_size: packets per burst
        :param burst_gap: packet burst period (ns), overrides rate
        :param rate: transmission rate (Gigabits per sec), ignored if burst_gap given
        """
        if burst_size != 1:
            warnings.warn("Packet burst not tested!")

        if burst_gap:
            self.tx_burst_gap = burst_gap
        else:
            self.tx_burst_gap = _gap_from_rate(
                self.tx_packet_size, rate, burst_size
            )
            print(
                (
                    f"{rate} Gbps with {self.tx_packet_size.value} B packets "
                    f"in bursts of {burst_size} "
                    f"gives a burst period of {self.tx_burst_gap.value} ns"
                )
            )
        self.tx_packets_per_burst = burst_size
        self.tx_beats_per_burst = self.tx_beats_per_packet * burst_size
        self.tx_bursts = math.ceil(
            self.tx_total_number_tx_packets / burst_size
        )

        if n_loops > 1:
            self.tx_loop_enable = True
            self.tx_loops = n_loops

    def start_tx(self) -> None:
        """
        Start transmitting packets
        """
        self.tx_enable = 0
        self.tx_enable = 1

    def start_rx(self, packet_size: int, n_packets: int = 0) -> None:
        """
        Start receiving packets into FPGA memory
        :param packet_size: only packets of this exact size are captured (bytes)
        :param n_packets: number of packets to receive
        """
        self.rx_enable_capture = 0
        self.rx_packet_size = packet_size
        self.rx_packets_to_capture = n_packets
        self.rx_reset_capture = 1
        self.rx_reset_capture = 0
        self.rx_enable_capture = 1
