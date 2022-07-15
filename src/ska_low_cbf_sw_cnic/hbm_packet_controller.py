import dpkt.pcapng
import numpy as np
from ska_low_cbf_fpga import FpgaPeripheral, IclField


class HbmPacketController(FpgaPeripheral):
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
        buffer: int = 1,
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

            raw = self._default_interface.read_memory(buffer).astype(np.uint8)
            # ensure number of data bytes is an integer multiple of packet_size,
            # by discarding the remainder from the end
            if raw.nbytes % packet_size:
                raw = raw[: -(raw.nbytes % packet_size)]

            raw.shape = (raw.nbytes // packet_size, packet_size)
            for packet in raw:
                writer.writepkt(packet.tobytes())
