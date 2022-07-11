import pytest
from ska_low_cbf_fpga import ArgsMap, ArgsSimulator

from ska_low_cbf_sw_cnic.ptp import Ptp

from .fpgamap_22032914 import FPGAMAP


@pytest.fixture
def ptp():
    return Ptp(ArgsSimulator(fpga_map=FPGAMAP), ArgsMap(FPGAMAP)["timeslave"])


class TestPtp:
    def test_mac(self, ptp):
        TEST_ADDRESS = 0xFE_DC_BA
        ptp.user_mac_address = TEST_ADDRESS
        assert (ptp.profile_mac_hi.value & 0xFF000000) >> 24 == 0xFE
        assert (ptp.profile_mac_lo.value & 0xFF00) >> 8 == 0xBA
        assert (ptp.profile_mac_lo.value & 0xFF) == 0xDC
        assert ptp.user_mac_address.value == TEST_ADDRESS

    # TODO test start time conversions...
