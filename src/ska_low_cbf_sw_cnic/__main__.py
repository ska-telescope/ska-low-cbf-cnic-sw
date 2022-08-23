# -*- coding: utf-8 -*-
#
# (c) 2022 CSIRO Astronomy and Space.
#
# Distributed under the terms of the CSIRO Open Source Software Licence
# Agreement. See LICENSE for more info.

"""
ska-low-cbf-sw-cnic module main
(executed via `python3 -m ska_low_cbf_sw_cnic`)
"""
import argparse
import textwrap

from ska_low_cbf_fpga.fpga_cmdline import FpgaCmdline

import ska_low_cbf_sw_cnic.monitor as monitor
from ska_low_cbf_sw_cnic.cnic_fpga import CnicFpga


class CnicCmdline(FpgaCmdline):
    """CNIC Command Line class"""

    def configure_parser(self):
        """Add CNIC command-line arguments"""
        super().configure_parser()
        cnic_group = self.parser.add_argument_group(
            "CNIC", "CNIC-specific Arguments"
        )

        cnic_group.add_argument(
            "--monitor",
            "-o",
            action="store_true",
            help="Launch monitoring interface",
        )

        # PTP options
        cnic_group.add_argument(
            "--ptp-domain",
            type=int,
            help="PTP domain. Default: 24",
            default=24,
        )

        # TODO move command handling to base class
        #  (could be automatic by discovering user methods of the Personality?)

        # this setting lets us have multi-line help
        self.parser.formatter_class = argparse.RawTextHelpFormatter
        self.parser.add_argument(
            "command",
            nargs="*",
            type=str,
            help=textwrap.dedent(
                """
                EXPERIMENTAL COMMAND INTERFACE
                Available commands:
                \tmonitor
                \ttx <filename>
                \trx <filename> <packet size> <n packets>
                """
            ),
        )

    def set_personality_args(self):
        """Add CnicFpga personality extra arguments"""
        self.personality_args["ptp_domain"] = self.args.ptp_domain

    # TODO move command handling to base class?
    def run(self):
        super().run()
        command = self.args.command
        fpga = self.fpgas[self.args.cards[0]]
        if command:
            base_cmd = str.lower(command[0])
            if base_cmd == "monitor":
                monitor.display_status_forever(fpga)
            if base_cmd == "tx":
                assert (
                    2 <= len(command) <= 4
                ), "use 'tx <filename> [start_time [stop_time]]'"
                filename = command[1]
                print(f"Transmitting {filename}")
                start_time = None
                stop_time = None
                try:
                    start_time = command[2]
                    stop_time = command[3]
                except IndexError:
                    pass
                # TODO - other transmit parameters...
                fpga.transmit_pcap(
                    in_filename=filename,
                    start_time=start_time,
                    stop_time=stop_time,
                )
            elif base_cmd == "rx":
                assert (
                    len(command) == 4
                ), "use 'rx <filename> <packet size> <n packets>'"
                print(f"Writing to {command[1]}")
                print(f"{command[3]} packets, each of size {command[2]} B")
                fpga.receive_pcap(command[1], int(command[2]), int(command[3]))

            else:
                raise NotImplementedError(f"No such command {command[0]}")

            if self.args.monitor:
                monitor.display_status_forever(fpga)


def main():
    CnicCmdline(personality=CnicFpga)


if __name__ == "__main__":
    main()
