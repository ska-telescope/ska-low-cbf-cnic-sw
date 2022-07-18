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


def _get_padded_size(packet_size: int):
    """
    Round up the packet size to the next 'beat's worth of data
    :param packet_size: bytes
    :return:
    """
    pad_length = 0
    if packet_size % BEAT_SIZE:
        pad_length = BEAT_SIZE - (packet_size % BEAT_SIZE)
    packet_padded_size = packet_size + pad_length
    return packet_padded_size


class HbmPacketController(FpgaPeripheral):
    def __init__(
        self,
        interfaces: typing.Union[
            ArgsFpgaInterface, typing.Dict[str, ArgsFpgaInterface]
        ],
        map_field_info: typing.Dict[str, ArgsFieldInfo],
        default_interface: str = "__default__",
    ):
        super().__init__(interfaces, map_field_info, default_interface)
        self._packets_to_transmit = 0
        """Number of packets to transmit"""

    @property
    def packet_count(self):
        return IclField(
            description="Total Packet Count",
            type_=int,
            value=(self.current_pkt_count_high.value << 32)
            + self.current_pkt_count_low.value,
        )

    def dump_pcap(
        self,
        filename: str,
        buffer: int = 1,  # TODO, remove arg, add rollover between 4x buffers
        packet_size: int = 8192,
        ng: bool = True,
    ):
        """
        Dump a PCAP(NG) file from HBM
        :param filename: Output file path
        :param buffer: HBM buffer index
        :param packet_size: Number of Bytes used for each packet
        :param ng: PCAP Next-Generation? (False = original pcap)
        :return:
        """
        with open(filename, "wb") as out_file:
            if ng:
                writer = dpkt.pcapng.Writer(out_file)
            else:
                writer = dpkt.pcap.Writer(out_file)

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

    def load_pcap(self, file: typing.BinaryIO):
        """

        :param file: input PCAP(NG) file
        :return:
        """
        # TODO is there a better way to detect the file format?
        if os.path.splitext(file.name)[1] == ".pcapng":
            reader = dpkt.pcapng.Reader
        else:
            reader = dpkt.pcap.Reader

        buffer = 1  # TODO rollover between 4x buffers
        first_packet = True
        offset = 0  # byte address to write to
        packet_padded_size = 0
        n_packets = 0
        packet_size = 0
        for timestamp, packet in reader(file):
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
            self._interfaces[self._default_interface].write_memory(
                buffer, packet, offset
            )
            n_packets += 1
            offset += packet_padded_size

        self._packets_to_transmit = n_packets  # TODO move to FPGA?
        self.packet_size = packet_size
        self.expected_beats_per_packet = packet_padded_size // BEAT_SIZE
        self.expected_total_number_of_4k_axi = math.ceil(
            (n_packets * packet_padded_size) / AXI_TRANSACTION_SIZE
        )

    def configure_tx(self, n_loops: int = 1, burst_size: int = 1):
        if burst_size != 1:
            warnings.warn("Packet burst not tested!")

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

        # TODO -
        #  time_between_bursts_ns

    def start_tx(self):
        self.start_stop_tx = 0
        self.start_stop_tx = 1
