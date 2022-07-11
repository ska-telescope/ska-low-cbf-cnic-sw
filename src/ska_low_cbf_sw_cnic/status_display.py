import time
from dataclasses import dataclass
from datetime import datetime

from fxpmath import Fxp
from rich.box import SQUARE
from rich.layout import Layout
from rich.live import Live
from rich.table import Table
from rich.text import Text
from ska_low_cbf_fpga import FpgaPeripheral, FpgaPersonality

from ska_low_cbf_sw_cnic.hbm_packet_controller import HbmPacketController
from ska_low_cbf_sw_cnic.ptp import Ptp


@dataclass
class DisplayStaticInfo:
    pps: float  # packets per second
    transmit_rate: float
    filename: str
    packet_size_on_wire: int
    total_hbm_usage: int
    aligned_packet_size: int
    beats_per_packet: int
    beats_total: int
    tx_time: float
    total_loop_time_ns: int
    ptp_enabled: bool


PACKET_CRTL_PARAMETERS = {
    # pcap file
    "running": "Running",
    "packet_size": "Packet Size",
    # total_packetsize_on_wire
    # aligned_packet_len
    "number_of_packets_in_burst": "No. of packets in burst",
    "time_between_bursts_ns": "Time between bursts",
    ###
    # total_hbm_memory_usage
    ###
    "expected_total_number_of_4k_axi": "expected_total_number_of_4k_axi",
    "current_axi_4k_count": "current_axi_4k_count",
    "expected_total_number_of_bursts": "expected_total_number_of_bursts",
    "burst_count": "fpga_burst_count",
    "expected_packets_per_burst": "expected_packets_per_burst",
    "fpga_pkt_count_in_this_burst": "fpga_pkt_count_in_this_burst",
    # expected_beats_per_packet
    "beat_count": "fpga_beat_count",
    "expected_number_beats_per_burst": "expected_number_beats_per_burst",
    "fpga_beat_in_burst_counter": "fpga_beat_in_burst_counter",
    # expected_total_beats
    "total_beat_count": "fpga_total_beat_count",
    ###
    "fifo_prog_full": "fifo_prog_full",
    "fifo_full": "fifo_full",
    "axi_rvalid_but_fifo_full": "axi_rvalid_but_fifo_full",
    ###
    "fifo_rddatacount": "fifo_rddatacount",
    "fifo_wrdatacount": "fifo_wrdatacount",
    ###
    "rd_fsm_debug": "rd_fsm_debug",
    "output_fsm_debug": "output_fsm_debug",
    ###
    "ns_burst_timer": "ns_burst_timer",
    ###
    "packet_count": "Total Packets",
    "total_number_tx_packets": "total_number_tx_packets per loop",
    # total_time_per_loop
    ###
    "loop_tx": "Loop_tx",
    "expected_number_of_loops": "expected_loops",
    "loop_cnt": "fpga_loop_cnt",
    ###
    # sending_rate
    # mac_tx_rate
    # pps_rate
    # mac_tx_pps_rate
    ###
    # expected_tx_time_s
    # "elapsedtime_ts": "elapsedtime_ts",
    "tx_complete": "tx_complete",
}
"""key: attribute to read from hbm_pktcontroller, value: human-readable description"""
# TODO add units?
#  -- it might be better to add the descriptions to the FpgaPeripheral object and read
#     them from the IcField object..
#     -- or maybe there are some adequate descriptions in the FPGA map?? [not really]


def generate_hpc_table(hpc: HbmPacketController) -> Table:
    """Create HBM packet controller status table."""
    table = Table(
        "Parameter", "Value", show_header=False, title="HBM Pkt Ctrl", box=SQUARE
    )

    for attr, desc in PACKET_CRTL_PARAMETERS.items():
        table.add_row(desc, f"{getattr(hpc, attr).value}")

    return table


def generate_100g_table(system: FpgaPeripheral, hpc: HbmPacketController) -> Table:
    table = Table("Parameter", "Value", title="100G", show_header=False, box=SQUARE)
    table.add_row("Tx", f"{system.eth100g_tx_total_packets.value}")
    table.add_row("Rx", f"{system.eth100g_rx_total_packets.value}")
    bad_fcs = system.eth100g_rx_bad_fcs.value
    bad_fcs_style = "red" if bad_fcs > 0 else None
    table.add_row("Bad FCS", f"{bad_fcs}", style=bad_fcs_style)
    bad_code = system.eth100g_rx_bad_code.value
    bad_code_style = "red" if bad_code > 0 else None
    table.add_row("Bad Code", Text(f"{bad_code}", style=bad_code_style))
    table.add_row("Total", f"{hpc.packet_count.value}", style="bold")
    return table


def generate_static_table(static_info: DisplayStaticInfo):
    table = Table(
        "Parameter", "Value", title="Static Info", show_header=False, box=SQUARE
    )
    table.add_row("HBM Usage", f"{static_info.total_hbm_usage}")
    table.add_row("Packet size on wire", f"{static_info.packet_size_on_wire}")
    table.add_row("Aligned Packet size", f"{static_info.aligned_packet_size}")
    table.add_row("Expected beats per packet", f"{static_info.beats_per_packet}")
    table.add_row("Expected beats in total", f"{static_info.beats_total}")
    table.add_row("---", "---")
    table.add_row("Expected Tx Rate", f"{static_info.transmit_rate:.3f}")
    # MAC Tx Rate
    table.add_row("Expected Packets/s", f"{static_info.pps:.3f}")
    # MAC Tx PPS
    table.add_row("Expected Tx time", f"{static_info.tx_time:.3f}")
    table.add_row("Time per loop (ms)", f"{static_info.total_loop_time_ns/1e6:.1f}")
    # Elapsed time

    return table


def generate_ptp_table(ptp: Ptp) -> Table:
    table = Table("Parameter", "Value", title="PTP", show_header=False, box=SQUARE)
    table.add_row("Domain number", f"{hex(ptp.profile_domain_num.value)}")
    table.add_row("MAC address", f"{ptp.mac_address.value}")
    date_time = datetime.fromtimestamp(int(ptp.time.value))
    table.add_row("Date", f"{date_time.strftime('%Y-%m-%d')}")
    table.add_row("Time", f"{date_time.strftime('%H:%M:%S')}")
    sched_time = datetime.fromtimestamp(ptp.scheduled_time.value)
    table.add_row("Scheduled start time", f"{sched_time.strftime('%H:%M:%S.%f')}")
    table.add_row("Scheduled start time (UNIX)", f"{sched_time.timestamp()}")
    # these are not really useful to end user but maybe for debugging
    # table.add_row("blk1_t1_sec", f"{ptp.blk1_t1_sec.value}")
    # table.add_row("blk1_t2_sec", f"{ptp.blk1_t2_sec.value}")
    # table.add_row("blk1_t3_sec", f"{ptp.blk1_t3_sec.value}")
    # table.add_row("blk1_t4_sec", f"{ptp.blk1_t4_sec.value}")
    table.add_row(
        "schedule_ptp_seconds_upper", f"{ptp.schedule_ptp_seconds_upper.value}"
    )
    table.add_row(
        "schedule_ptp_seconds_lower", f"{ptp.schedule_ptp_seconds_lower.value}"
    )
    table.add_row(
        "schedule_ptp_sub_seconds", f"{hex(ptp.schedule_ptp_sub_seconds.value)}"
    )
    return table


def create_layout():
    layout = Layout()
    layout.split(
        Layout(name="head", size=2),
        Layout(name="body", ratio=1),
        Layout(name="foot", size=2),
    )
    layout["body"].split_row(Layout(name="left"), Layout(name="right"))
    layout["right"].split_column(
        Layout(name="top_right"), Layout(name="mid_right"), Layout(name="bot_right")
    )
    return layout


def update_layout(
    layout: Layout, fpga: FpgaPersonality, static_info: DisplayStaticInfo
):
    layout["left"].update(generate_hpc_table(fpga.hbm_pktcontroller))
    layout["top_right"].update(generate_100g_table(fpga.system, fpga.hbm_pktcontroller))
    if static_info.ptp_enabled:
        layout["mid_right"].update(generate_ptp_table(fpga.timeslave))


def update_static_info(layout: Layout, static_info: DisplayStaticInfo):
    heading = Text("Alveo Burst NIC Monitor", justify="center")
    heading.stylize("bold cyan")
    layout["head"].update(heading)
    layout["foot"].update(Text(static_info.filename))
    layout["bot_right"].update(generate_static_table(static_info))


def display_status_forever(fpga: FpgaPersonality, static_info: DisplayStaticInfo):
    layout = create_layout()
    update_layout(layout, fpga, static_info)
    update_static_info(layout, static_info)
    with Live(layout, refresh_per_second=1, screen=True):
        while True:
            time.sleep(1)
            update_layout(layout, fpga, static_info)
            if fpga.hbm_pktcontroller.tx_complete.value:
                break
