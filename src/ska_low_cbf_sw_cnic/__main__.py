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

from ska_low_cbf_fpga.fpga_cmdline import FpgaCmdline

from ska_low_cbf_sw_cnic.cnic_fpga import CnicFpga


class CnicCmdline(FpgaCmdline):
    """CNIC Command Line class"""

    def configure_parser(self):
        """Add CNIC command-line arguments"""
        super().configure_parser()
        cnic_group = self.parser.add_argument_group(
            "CNIC", "CNIC-specific Arguments"
        )

        # PTP options
        cnic_group.add_argument(
            "--ptp-domain",
            type=int,
            help="PTP domain. Default: 24",
            default=24,
        )

    def set_personality_args(self):
        """Add CnicFpga personality extra arguments"""
        self.personality_args["ptp_domain"] = self.args.ptp_domain


def main():
    CnicCmdline(personality=CnicFpga)


if __name__ == "__main__":
    main()
