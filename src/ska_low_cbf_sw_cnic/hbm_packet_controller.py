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
