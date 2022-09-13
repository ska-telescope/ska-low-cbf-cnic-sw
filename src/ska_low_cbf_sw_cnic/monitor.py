# -*- coding: utf-8 -*-
#
# (c) 2022 CSIRO Astronomy and Space.
#
# Distributed under the terms of the CSIRO Open Source Software Licence
# Agreement. See LICENSE for more info.
""" Monitor CNIC Operation """

import time
from datetime import datetime

from rich.box import SQUARE
from rich.layout import Layout
from rich.live import Live
from rich.table import Table
from rich.text import Text
from ska_low_cbf_fpga import FpgaPeripheral, FpgaPersonality

from ska_low_cbf_sw_cnic.hbm_packet_controller import HbmPacketController
from ska_low_cbf_sw_cnic.ptp_scheduler import TIME_STR_FORMAT, PtpScheduler

TX_STATUS_PARAMS = {
    "tx_enable": "Enabled",
    "tx_running": "Running",
    "tx_packet_size": "Packet Size",
    "tx_packet_to_send": "Packets to Send",
    "tx_packet_count": "Packets Sent",
    "tx_loop_enable": "Loop?",
    "tx_loops": "No. of Loops",
    "tx_loop_count": "Loop Count",
    "tx_complete": "Complete",
}
"""key: attribute to read from hbm_pktcontroller,
value: human-readable description"""
# TODO add units?
#  -- it might be better to add the descriptions to the FpgaPeripheral object
#     and read them from the IcField object..
#     -- or maybe there are some adequate descriptions in the FPGA map??
#     [not really]

RX_STATUS_PARAMS = {
    "rx_enable_capture": "Enabled",
    "rx_packet_size": "Packet Size",
    "rx_packets_to_capture": "Packets to Capture",
    "rx_packet_count": "Packets Captured",
    "rx_complete": "Complete",
    "rx_hbm_1_end_addr": "HBM 1 data bytes",
    "rx_hbm_2_end_addr": "HBM 2 data bytes",
    "rx_hbm_3_end_addr": "HBM 3 data bytes",
    "rx_hbm_4_end_addr": "HBM 4 data bytes",
}
"""key: attribute to read from hbm_pktcontroller,
value: human-readable description"""


def generate_tx_table(hpc: HbmPacketController) -> Table:
    """Create HBM packet controller status table."""
    table = Table(
        "Parameter",
        "Value",
        show_header=False,
        title="Tx Status",
        box=SQUARE,
    )

    for attr, desc in TX_STATUS_PARAMS.items():
        table.add_row(desc, f"{getattr(hpc, attr).value}")

    return table


def generate_rx_table(hpc: HbmPacketController) -> Table:
    """Create HBM packet controller status table."""
    table = Table(
        "Parameter",
        "Value",
        show_header=False,
        title="Rx Status",
        box=SQUARE,
    )

    for attr, desc in RX_STATUS_PARAMS.items():
        table.add_row(desc, f"{getattr(hpc, attr).value}")

    return table


def generate_100g_table(system: FpgaPeripheral) -> Table:
    """Create 100G Ethernet status table."""
    table = Table(
        "Parameter", "Value", title="100G", show_header=False, box=SQUARE
    )
    table.add_row("Tx", f"{system.eth100g_tx_total_packets.value}")
    table.add_row("Rx", f"{system.eth100g_rx_total_packets.value}")
    bad_fcs = system.eth100g_rx_bad_fcs.value
    bad_fcs_style = "red" if bad_fcs > 0 else None
    table.add_row("Bad FCS", Text(f"{bad_fcs}", style=bad_fcs_style))
    bad_code = system.eth100g_rx_bad_code.value
    bad_code_style = "red" if bad_code > 0 else None
    table.add_row("Bad Code", Text(f"{bad_code}", style=bad_code_style))
    locked = system.eth100g_locked.value
    locked_style = "red" if not locked else None
    table.add_row("Locked", Text(f"{locked}", style=locked_style))
    return table


def generate_ptp_table(ptp: PtpScheduler) -> Table:
    """Create PTP status table."""
    table = Table(
        "Parameter", "Value", title="PTP", show_header=False, box=SQUARE
    )
    table.add_row("Domain number", f"{hex(ptp.profile_domain_num.value)}")
    table.add_row("MAC address", f"{ptp.mac_address.value}")
    table.add_row("PTP Time", f"{ptp.time.value}")
    host_time = datetime.now()
    table.add_row("Host Time", f"{host_time.strftime(TIME_STR_FORMAT)}")
    table.add_row("Transmit start time", f"{ptp.tx_start_time.value}")
    table.add_row("Transmit stop time", f"{ptp.tx_stop_time.value}")
    table.add_row("Receive start time", f"{ptp.rx_start_time.value}")
    table.add_row("Receive stop time", f"{ptp.rx_stop_time.value}")
    table.add_row("Schedule Complete", f"{ptp.schedule_debug_complete.value}")
    # these are not really useful to end user but maybe for debugging
    # table.add_row("blk1_t1_sec", f"{ptp.blk1_t1_sec.value}")
    # table.add_row("blk1_t2_sec", f"{ptp.blk1_t2_sec.value}")
    # table.add_row("blk1_t3_sec", f"{ptp.blk1_t3_sec.value}")
    # table.add_row("blk1_t4_sec", f"{ptp.blk1_t4_sec.value}")
    return table


def create_layout():
    """Create a Layout object for the whole monitoring display"""
    layout = Layout()
    layout.split(
        Layout(name="head", size=2),
        Layout(name="body", ratio=1),
        Layout(name="foot", size=2),
    )
    layout["body"].split_row(Layout(name="left"), Layout(name="right"))
    layout["left"].split_column(
        Layout(name="top_left"),
        Layout(name="bot_left"),
    )
    layout["right"].split_column(
        Layout(name="top_right"),
        Layout(name="bot_right"),
    )
    return layout


def update_layout(layout: Layout, fpga: FpgaPersonality):
    """Update all dynamic portions of the display"""
    layout["top_left"].update(generate_tx_table(fpga.hbm_pktcontroller))
    layout["bot_left"].update(generate_rx_table(fpga.hbm_pktcontroller))
    layout["top_right"].update(generate_100g_table(fpga.system))
    layout["bot_right"].update(generate_ptp_table(fpga.timeslave))


def update_static_info(layout: Layout, fpga: FpgaPersonality):
    """Display the static pieces of information"""
    heading = Text("CNIC Monitor", justify="center")
    heading.stylize("bold cyan")
    layout["head"].update(heading)


def display_status_forever(fpga: FpgaPersonality):
    """Display status information until terminated (e.g. by Ctrl-C)"""
    layout = create_layout()
    update_layout(layout, fpga)
    update_static_info(layout, fpga)
    with Live(layout, refresh_per_second=1, screen=True):
        try:
            while True:
                time.sleep(1)
                update_layout(layout, fpga)
        except KeyboardInterrupt:
            # Ctrl-C is how the user exits, no need to print a traceback
            pass
