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
import logging
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
        cnic_group.add_argument(
            "--ptp-source-b",
            action="store_true",
            help="Use PTP B? (Default: No)",
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
                \ttx <filename> [rate [start_time [stop_time]]]
                \trx <filename> <packet size> <n packets>
                """
            ),
        )

    # TODO could some sensible default behaviour be moved upstream?
    def set_personality_args(self):
        """Add CnicFpga personality extra arguments"""
        self.personality_args["ptp_domain"] = self.args.ptp_domain
        self.personality_args["ptp_source_b"] = self.args.ptp_source_b

    # TODO move command handling to base class?
    def run(self):
        """Overload run to add extra sub-commands"""
        super().run()
        command = self.args.command
        fpga = self.fpgas[self.args.cards[0]]
        # TODO move logger config to ska-low-cbf-fpga
        display_log_handler = logging.StreamHandler()
        display_log_handler.setLevel(logging.DEBUG)
        display_log_handler.setFormatter(
            logging.Formatter("%(levelname)s: %(message)s")
        )
        self.logger.addHandler(display_log_handler)

        if command:
            base_cmd = str.lower(command[0])
            if base_cmd == "monitor":
                monitor.display_status_forever(fpga)
            elif base_cmd == "tx":
                assert (
                    2 <= len(command) <= 5
                ), "use 'tx <filename> [rate [start_time [stop_time]]]'"
                filename = command[1]
                self.logger.info(f"Will transmit {filename}")
                start_time = None
                stop_time = None
                rate = 50.0
                try:
                    rate = float(command[2])
                    start_time = command[3]
                    stop_time = command[4]
                except IndexError:
                    pass
                # TODO - other transmit parameters...
                fpga.transmit_pcap(
                    in_filename=filename,
                    start_time=start_time,
                    stop_time=stop_time,
                    rate=rate,
                )
            elif base_cmd == "rx":
                assert (
                    len(command) == 4
                ), "use 'rx <filename> <packet size> <n packets>'"
                self.logger.info(f"Writing to {command[1]}")
                self.logger.info(
                    f"{command[3]} packets, each of size {command[2]} B"
                )
                fpga.receive_pcap(command[1], int(command[2]), int(command[3]))

            else:
                raise NotImplementedError(f"No such command {command[0]}")

            if self.args.monitor:
                monitor.display_status_forever(fpga)


def main():
    """CNIC CLI main function"""
    CnicCmdline(personality=CnicFpga)


if __name__ == "__main__":
    main()
