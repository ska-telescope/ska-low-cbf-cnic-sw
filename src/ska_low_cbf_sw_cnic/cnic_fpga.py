import typing

from ska_low_cbf_fpga import FpgaPersonality

from ska_low_cbf_sw_cnic.hbm_packet_controller import HbmPacketController
from ska_low_cbf_sw_cnic.ptp import Ptp


class CnicFpga(FpgaPersonality):
    _peripheral_class = {
        "timeslave": Ptp,
        "timeslave_b": Ptp,
        "hbm_pktcontroller": HbmPacketController,
    }

    def transmit_pcap(
        self, file: typing.BinaryIO, n_loops: int = 1, burst_size: int = 1
    ):
        self.hbm_pktcontroller.load_pcap(file)
        self.hbm_pktcontroller.configure_tx(n_loops, burst_size)
        self.hbm_pktcontroller.start_tx()
