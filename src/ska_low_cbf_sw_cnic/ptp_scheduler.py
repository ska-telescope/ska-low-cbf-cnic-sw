# -*- coding: utf-8 -*-
#
# Copyright (c) 2022 CSIRO Space and Astronomy.
#
# Distributed under the terms of the CSIRO Open Source Software Licence Agreement
# See LICENSE for more info.
"""
PTP Peripheral ICL
"""
from datetime import datetime
from decimal import Decimal

from ska_low_cbf_fpga import IclField

from ska_low_cbf_sw_cnic.ptp import Ptp

TIME_STR_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

TIMESTAMP_BITS = 80
TIMESTAMP_NS_BITS = 32
# 48 bits integer, 32 bits of nanoseconds


def combine_ptp_registers(
    upper: IclField, lower: IclField, sub: IclField
) -> int:
    """Combine 3x PTP registers into an 80 bit PTP timestamp"""
    return (upper.value << 64) | (lower.value << 32) | sub.value


def datetime_from_str(time_str: str) -> datetime:
    """
    Convert user-supplied string to datetime object
    :param time_str: "%Y-%m-%d %H:%M:%S[.%f]"
    (microseconds is optional)
    """
    try:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")


def split_datetime(t: datetime) -> (int, int, int):
    """
    Split a datetime into 3 register values
    :param t: target time to be decoded
    :return: seconds upper 32 bits, seconds lower 32 bits, sub seconds (nanoseconds)
    """
    seconds, fractional_seconds = divmod(t.timestamp(), 1)
    seconds = int(seconds)
    upper = seconds >> 32
    lower = seconds & 0xFFFF_FFFF
    sub_seconds = int(fractional_seconds * 1e9)
    return upper, lower, sub_seconds


def time_str_from_registers(
    upper: IclField, lower: IclField, sub: IclField
) -> str:
    """Combine 3 PTP time registers and render as string"""
    timestamp = unix_ts_from_ptp(combine_ptp_registers(upper, lower, sub))
    dt = datetime.fromtimestamp(float(timestamp))
    return dt.strftime(TIME_STR_FORMAT)


def unix_ts_from_ptp(ptp_timestamp: int) -> Decimal:
    """Get UNIX timestamp from 80 bit PTP value"""
    ns_mask = (1 << TIMESTAMP_NS_BITS) - 1
    sub_seconds = Decimal(ptp_timestamp & ns_mask) / Decimal(1e9)
    seconds = ptp_timestamp >> TIMESTAMP_NS_BITS
    return seconds + sub_seconds


class PtpScheduler(Ptp):
    """
    PTP with Scheduling
    """

    @property
    def unix_timestamp(self) -> IclField[int]:
        """Get current time (UNIX ts)"""
        return IclField(
            value=(
                unix_ts_from_ptp(
                    combine_ptp_registers(
                        self.current_ptp_seconds_upper,
                        self.current_ptp_seconds_lower,
                        self.current_ptp_sub_seconds,
                    )
                )
            ),
            description="Current UNIX time",
            type_=int,
        )

    @property
    def time(self) -> IclField[str]:
        """Get current time"""
        return IclField(
            value=(
                time_str_from_registers(
                    self.current_ptp_seconds_upper,
                    self.current_ptp_seconds_lower,
                    self.current_ptp_sub_seconds,
                )
            ),
            description="Current time",
            type_=str,
        )

    @property
    def tx_start_time(self) -> IclField[str]:
        """Read the scheduled transmission start time"""
        return IclField(
            description="Transmit Start Time",
            type_=str,
            value=time_str_from_registers(
                self.tx_start_ptp_seconds_upper,
                self.tx_start_ptp_seconds_lower,
                self.tx_start_ptp_sub_seconds,
            ),
        )

    @tx_start_time.setter
    def tx_start_time(self, start_time: str) -> None:
        """
        Schedule a transmission start time
        :param start_time: time to start at, see datetime_from_str for string format
        use empty string or None to disable
        """
        if start_time:
            (
                self.tx_start_ptp_seconds_upper,
                self.tx_start_ptp_seconds_lower,
                self.tx_start_ptp_sub_seconds,
            ) = split_datetime(datetime_from_str(start_time))
        self.schedule_control_tx_start_time = bool(start_time)

    @property
    def tx_stop_time(self) -> IclField[str]:
        """Read the scheduled transmission stop time"""
        return IclField(
            description="Transmit Stop Time",
            type_=str,
            value=time_str_from_registers(
                self.tx_stop_ptp_seconds_upper,
                self.tx_stop_ptp_seconds_lower,
                self.tx_stop_ptp_sub_seconds,
            ),
        )

    @tx_stop_time.setter
    def tx_stop_time(self, stop_time: str) -> None:
        """
        Schedule a transmission stop time
        :param stop_time: time to stop at, see datetime_from_str for string format
        use empty string or None to disable
        """
        if stop_time:
            (
                self.tx_stop_ptp_seconds_upper,
                self.tx_stop_ptp_seconds_lower,
                self.tx_stop_ptp_sub_seconds,
            ) = split_datetime(datetime_from_str(stop_time))
        self.schedule_control_tx_stop_time = bool(stop_time)

    @property
    def rx_start_time(self) -> IclField[str]:
        """Read the scheduled reception start time"""
        return IclField(
            description="Receive Start Time",
            type_=str,
            value=time_str_from_registers(
                self.rx_start_ptp_seconds_upper,
                self.rx_start_ptp_seconds_lower,
                self.rx_start_ptp_sub_seconds,
            ),
        )

    @rx_start_time.setter
    def rx_start_time(self, start_time: str) -> None:
        """
        Schedule a reception start time
        :param start_time: time to start at, see datetime_from_str for string format
        use empty string or None to disable
        """
        if start_time:
            (
                self.rx_start_ptp_seconds_upper,
                self.rx_start_ptp_seconds_lower,
                self.rx_start_ptp_sub_seconds,
            ) = split_datetime(datetime_from_str(start_time))
        self.schedule_control_rx_start_time = bool(start_time)

    @property
    def rx_stop_time(self) -> IclField[str]:
        """Read the scheduled reception stop time"""
        return IclField(
            description="Receive Stop Time",
            type_=str,
            value=time_str_from_registers(
                self.rx_stop_ptp_seconds_upper,
                self.rx_stop_ptp_seconds_lower,
                self.rx_stop_ptp_sub_seconds,
            ),
        )

    @rx_stop_time.setter
    def rx_stop_time(self, stop_time: str) -> None:
        """
        Schedule a reception stop time
        :param stop_time: time to stop at, see datetime_from_str for string format
        use empty string or None to disable
        """
        if stop_time:
            (
                self.rx_stop_ptp_seconds_upper,
                self.rx_stop_ptp_seconds_lower,
                self.rx_stop_ptp_sub_seconds,
            ) = split_datetime(datetime_from_str(stop_time))
        self.schedule_control_rx_stop_time = bool(stop_time)
