# -*- coding: utf-8 -*-
#
# Copyright (c) 2021 CSIRO Space and Astronomy.
# Engineers:    Jason van Aardt, jason.vanaardt@csiro.au
#               Andrew Bolin
# Distributed under the terms of the CSIRO Open Source Software Licence Agreement
# See the file LICENSE for more info.

"""
Load a pcap file to HBM for playback.

Note: The pcap packets are 64B aligned in HBM memory, to make it easier to read out and
put directly on the 512bit Lbus towards the packetizer and on to the 100G CMAC.
"""
import argparse
import copy
import logging
import math
import os
import socket
import sys
import time
from datetime import datetime
from random import randint

import dpkt
import numpy as np
from ska_low_cbf_fpga.args_fpga import mem_parse, str_from_int_bytes
from ska_low_cbf_fpga.args_map import ArgsMap
from ska_low_cbf_fpga.args_xrt import ArgsXrt

from ska_low_cbf_sw_cnic.cnic_fpga import CnicFpga
from ska_low_cbf_sw_cnic.status_display import (
    DisplayStaticInfo,
    display_status_forever,
)

HBM_MEMORY_BUFFER = 1
MEM_FILL_VALUE = 0xCAFEF00D


def debug_to_memory(randomize, number_of_packets, pkt_len, hbm_size):
    if pkt_len % 64 != 0:
        aligned_packet_len = pkt_len + (64 - pkt_len % 64)
    else:
        aligned_packet_len = pkt_len
    fill_value = socket.htonl(MEM_FILL_VALUE)
    buffer = np.full(int(hbm_size / 4), fill_value, dtype=np.uint32).view(
        np.uint8
    )
    pkt = np.zeros(aligned_packet_len, dtype=np.uint8)

    for i in range(number_of_packets):
        for index in range(0, pkt_len, 2):
            if randomize:
                pkt[index] = randint(0, 255)
                pkt[index + 1] = randint(0, 255)
            else:
                # Create a 16 bit counter as the packet data
                if index == 0:
                    pkt[index] = (i & 0xFF00) >> 8
                    pkt[index + 1] = i & 0x00FF
                else:
                    pkt[index] = (index // 2 & 0xFF00) >> 8
                    pkt[index + 1] = index // 2 & 0x00FF

        pkt[pkt_len:] = 0xFF
        buffer[
            i * aligned_packet_len : i * aligned_packet_len
            + aligned_packet_len
        ] = pkt

    return buffer, pkt_len, aligned_packet_len, number_of_packets


def read_pcap_file_to_memory(file, hbm_size, logger):
    logger.info(f"Reading {file.name}")
    buffer = np.full(int(hbm_size / 4), MEM_FILL_VALUE, dtype=np.uint32).view(
        np.uint8
    )

    counter = 0
    ipcounter = 0
    tcpcounter = 0
    udpcounter = 0
    hbm_pkt_counter = 0
    first_packet = True

    index = 0
    if os.path.splitext(file.name)[1] == ".pcapng":
        reader = dpkt.pcapng.Reader
    else:
        reader = dpkt.pcap.Reader
    for ts, pkt in reader(file):

        counter += 1
        eth = dpkt.ethernet.Ethernet(pkt)
        if eth.type != dpkt.ethernet.ETH_TYPE_IP:
            logger.warning("Not an IP packet!")

        pkt_len = len(pkt)
        if pkt_len % 64 != 0:
            aligned_packet_len = pkt_len + (64 - pkt_len % 64)
        else:
            aligned_packet_len = pkt_len

        pkt_padded = np.zeros(aligned_packet_len, dtype=np.uint8)
        pkt_padded[:pkt_len] = copy.deepcopy(
            np.frombuffer(pkt, dtype=np.uint8)
        )
        pkt_padded[pkt_len:] = 0xFF

        if first_packet:
            logging.debug(
                f"First Packet Timestamp: {ts} : {datetime.utcfromtimestamp(ts)}"
            )
            logging.debug(f"First Packet len = {pkt_len}")
            logging.debug(f"aligned_packet_len = {aligned_packet_len}")
            first_packet = False

        # Calculate the next 512bit boundary to align the packet on
        # this is because the AXI bux from the HBM inside the FPGA is 512 bit wide,
        # and the 100G CMAC is also 512bit aligned
        if (index + aligned_packet_len) < hbm_size:
            buffer[index : index + aligned_packet_len] = copy.deepcopy(
                pkt_padded
            )
            index += aligned_packet_len
            hbm_pkt_counter += 1

        ip = eth.data
        ipcounter += 1

        if ip.p == dpkt.ip.IP_PROTO_TCP:
            tcpcounter += 1

        if ip.p == dpkt.ip.IP_PROTO_UDP:
            udpcounter += 1

    logger.info(
        f"{counter} total packets in the pcap file of which {udpcounter} are UDP"
    )

    return buffer, pkt_len, aligned_packet_len, hbm_pkt_counter


def calculate_pps_and_burstgap(linerate, percentage, pkts_per_burst, pkt_size):
    bps = linerate * 1e9
    bytes_per_sec = bps // 8
    pkt_size_extra = pkt_size + 20 + 4  # Interframe gap(20) and FCS(4)
    linerate_pps = bytes_per_sec // pkt_size_extra
    maxpps = (bytes_per_sec * percentage / 100) // pkt_size_extra
    burst_per_sec = (bytes_per_sec * percentage / 100) // (
        pkt_size_extra * pkts_per_burst
    )
    burst_gap_ns = 1e9 // burst_per_sec
    packet_rate = burst_per_sec * pkts_per_burst * pkt_size * 8
    print("")
    print(f"100G  absolute maxpps = {linerate_pps}")
    print("")
    print(f"100G at {percentage}%  maxpps = {maxpps}")

    print(f"\t{packet_rate/1e9}Gbps less InterFrameGap and FCS")

    print(f"\tpkt_size:{pkt_size}")
    print(f"\tpkts_per_burst:{pkts_per_burst}")
    print(f"\tburst_per_sec = {burst_per_sec}")
    print(f"\tburst_gap_ns  = {burst_gap_ns}ns")


def calculate_sending_rate(
    pkt_size, pkts_per_burst, burst_gap_ns, number_of_packets, loop, logger
):
    sending_rate = (
        ((pkt_size + 4 + 12 + 8) * 8 * pkts_per_burst) / (burst_gap_ns * 1e-9)
    ) / 1e9
    pps_rate = (1 / (burst_gap_ns * 1e-9)) / 1e6
    logger.info(
        "--------------------------------------------------------------"
    )
    logger.info(f"Packet size       : {pkt_size}B")
    logger.info(f"Packet per burst  : {pkts_per_burst}")
    logger.info(f"Burst Gap ns      : {burst_gap_ns} ns")
    logger.info(f"Number of packets : {number_of_packets}")
    logger.info(f"Loop              : {loop}")
    logger.info(
        "--------------------------------------------------------------"
    )
    logger.info(f"Sending rate      : {sending_rate:.5} Gbps")
    logger.info(f"PPS rate          : {pps_rate:.5} MPPS")

    logger.info(
        "--------------------------------------------------------------"
    )

    return pps_rate, sending_rate


def main():
    parser = create_argument_parser()
    args = parser.parse_args()

    my_logger = create_logger(args)

    my_logger.info("Kernel: " + args.kernel)
    my_logger.info("Card: " + str(args.card))
    memory = None
    if args.memory:
        memory = mem_parse(args.memory)
        mem_info = "Memories: "
        for m in memory:
            mem_info += str_from_int_bytes(m.size)
            mem_info += " shared" if m.shared else " internal"
            mem_info += ", "
        logging.info(mem_info[:-2])

    # creating the driver object loads the xclbin file to the card (if needed)
    driver = ArgsXrt(
        xcl_file=args.kernel,
        mem_config=memory,
        card=args.card,
        logger=my_logger,
    )
    map_dir = os.path.dirname(args.kernel)

    args_map = ArgsMap.create_from_file(driver.get_map_build(), map_dir)
    fpga = CnicFpga(driver, args_map, logger=my_logger)

    if args.debugpkts:
        my_logger.info(
            f"Creating {args.numpackets} Debug Packets of size {args.debugpkts} bytes"
        )
        pkt_len = int(args.debugpkts)
        # Load a running sequence for debugging
        (
            hbm_memory,
            packet_bytes,
            aligned_packet_len,
            number_of_packets,
        ) = debug_to_memory(
            randomize=False,
            number_of_packets=args.numpackets,
            pkt_len=pkt_len,
            hbm_size=memory[HBM_MEMORY_BUFFER].size,
        )
    else:
        my_logger.info(f"Reading PCAP Packets from file {args.pcap.name}")
        # Load pcap file
        (
            hbm_memory,
            packet_bytes,
            aligned_packet_len,
            number_of_packets,
        ) = read_pcap_file_to_memory(
            args.pcap, memory[HBM_MEMORY_BUFFER].size, my_logger
        )
    my_logger.info(
        f"{number_of_packets} packets of size {packet_bytes} B "
        f"aligned to {aligned_packet_len} B "
        f"using {str_from_int_bytes(aligned_packet_len*number_of_packets)}"
        " to write into "
        f"{str_from_int_bytes(memory[HBM_MEMORY_BUFFER].size)} HBM memory"
    )

    # Write to HBM
    write_and_verify_memory(driver, hbm_memory)

    alveo_macs = [_["address"] for _ in fpga.info["platform"]["macs"]]
    alveo_mac = alveo_macs[0]
    # MAC are reported as a string of colon-separated hex bytes "01:02:03:04:05:06"
    my_logger.info("Alveo MAC address:", alveo_mac)
    # take low 3 bytes of mac, convert to int
    alveo_mac_low = int("".join(alveo_mac.split(":")[-3:]), 16)

    # FIXME - a guard until PTP is in the 'latest release' firmware image...
    #  (can remove the guard later)
    ptp_enabled = not args.ptp_disable and "timeslave" in fpga.peripherals
    if ptp_enabled:
        # configure the PTP core to use the same low 3 MAC bytes
        # (high bytes are set by the PTP core)
        fpga.timeslave.startup(alveo_mac_low, args.ptp_domain)
        my_logger.info(
            "  PTP MAC address:",
            "DC:3C:F6:"  # top 3 bytes are hard coded in PTP core
            + ":".join(
                f"{alveo_mac_low:06x}"[_ : _ + 2] for _ in range(0, 6, 2)
            ).upper(),
        )

        # process start time, if specified
        if args.start_time:
            my_logger.info(f"start time specified: {args.start_time}")
            fpga.timeslave.set_start_time(args.start_time)

    else:
        my_logger.warning(
            "PTP disabled or not available in this firmware image"
        )

    # Calculate the total number of AXI 64 byte transactions from the HBM that are
    # required for a complete burst
    expected_packets_per_burst = args.burst_size - 1
    expected_beats_per_packet = int(aligned_packet_len // 64) - 1
    expected_number_beats_per_burst = int(
        expected_beats_per_packet * args.burst_size
    )
    expected_total_number_of_bursts = (
        number_of_packets // args.burst_size
    ) - 1
    # Round it to an integer multiple
    number_of_packets = expected_total_number_of_bursts * args.burst_size
    total_time_per_loop_ns = expected_total_number_of_bursts * args.burst_gap
    expected_number_of_loops = (
        int(args.total_time * 1e9 // total_time_per_loop_ns) + 1
    )
    expected_total_beats = (
        expected_number_beats_per_burst * expected_total_number_of_bursts
    ) - 1

    total_hbm_memory_usage = number_of_packets * aligned_packet_len

    # configure the HBM Packet Controller
    configure_hpc(
        fpga,
        aligned_packet_len,
        args,
        expected_beats_per_packet,
        expected_number_beats_per_burst,
        expected_number_of_loops,
        expected_packets_per_burst,
        expected_total_number_of_bursts,
        number_of_packets,
        packet_bytes,
    )

    # Hardware build date
    my_logger.info(f"FPGA Build Date = {fpga.system.build_date.value:02x}")

    # Reset the 100G CMAC statistics
    my_logger.info("Resetting the 100G CMAC Stats \n")
    fpga.cmac.cmac_stat_reset = 1
    fpga.cmac.cmac_stat_reset = 0

    my_logger.debug(f"100G locked = {fpga.system.eth100g_locked.value} \n")
    if not fpga.system.eth100g_locked.value:
        my_logger.error("\n*** The 100G interface is not locked")
        my_logger.error(
            "*** Connect up to other device. No traffic will be generated."
        )
        sys.exit(1)

    if not args.start_time:
        fpga.hbm_pktcontroller.start_stop_tx = 0
        my_logger.debug(
            f"Resetting the TX State machine= {fpga.hbm_pktcontroller.start_stop_tx.value}"
        )

    expected_tx_time_s = (
        expected_number_of_loops * total_time_per_loop_ns / 1e9
    )

    if args.pcap:
        my_logger.info(f"Playing packets from file: {args.pcap.name}")
    my_logger.info(
        "Total HBM memory usage: "
        f"{str_from_int_bytes(total_hbm_memory_usage)}"
    )
    my_logger.info(f"Number of Loops: {expected_number_of_loops}")
    my_logger.info(f"Total transmit time: {expected_tx_time_s:.3f}s")

    pps_rate, sending_rate = calculate_sending_rate(
        packet_bytes,
        args.burst_size,
        args.burst_gap,
        number_of_packets,
        fpga.hbm_pktcontroller.loop_tx.value,
        my_logger,
    )

    my_logger.debug(f"Running = {fpga.hbm_pktcontroller.running.value}")
    my_logger.debug(f"loop_tx = {fpga.hbm_pktcontroller.loop_tx.value}")
    my_logger.debug(
        f"increase_header_frame_number = {fpga.hbm_pktcontroller.increase_header_frame_number.value}"
    )
    my_logger.debug(
        f"inplace_header_update = {fpga.hbm_pktcontroller.inplace_header_update.value}"
    )

    starttime = datetime.now()
    starttime_ts = starttime.timestamp()

    if not args.start_time:
        # Kick off the TX
        fpga.hbm_pktcontroller.start_stop_tx = 1
        my_logger.debug(
            f"Starting the TX = {fpga.hbm_pktcontroller.start_stop_tx.value}"
        )

    static_info = DisplayStaticInfo(
        pps=pps_rate,
        transmit_rate=sending_rate,
        filename=getattr(args.pcap, "name", "No PCAP File"),
        packet_size_on_wire=packet_bytes + 4 + 8 + 12,
        total_hbm_usage=total_hbm_memory_usage,
        aligned_packet_size=aligned_packet_len,
        beats_per_packet=expected_beats_per_packet,
        beats_total=expected_total_beats,
        tx_time=expected_tx_time_s,
        total_loop_time_ns=total_time_per_loop_ns,
        ptp_enabled=ptp_enabled,
    )

    try:
        display_status_forever(fpga, static_info)
        # TODO - this display stuff is not yet ported to the new UI
        # tx_bytes = 0
        # tx_packets = 0
        # newtime = starttime
        #
        # while True:
        #     prevtime = newtime
        #     newtime = datetime.now()
        #     newtime_ts = newtime.timestamp()
        #     prevtime_ts = prevtime.timestamp()
        #     elapsedtime_ts = newtime_ts - starttime_ts
        #
        #     timediff_ts = newtime_ts - prevtime_ts
        #
        #     prev_tx_bytes = tx_bytes
        #     prev_tx_packets = tx_packets
        #
        #
        #     tx_packets = fpga.system.eth100g_tx_total_packets.value
        #     tx_bytes = tx_packets * total_packetsize_on_wire
        #
        #     mac_tx_rate = ((tx_bytes - prev_tx_bytes) * 8 / timediff_ts) / 1e9
        #
        #     mac_tx_pps_rate = ((tx_packets - prev_tx_packets) / timediff_ts) / 1e6
        #
        #     print(
        #         f"| total_time_per_loop                 : {total_time_per_loop_ns/1E6:.1f}ms"
        #     )

        #     print(f"| expected TX rate                    : {sending_rate:.5} Gbps")
        #     print(f"| MAC TX rate                         : {mac_tx_rate:.5} Gbps")
        #     print(f"| expected TX PPS rate                : {pps_rate:.4} MPPS")
        #     print(f"| MAC TX PPS rate                     : {mac_tx_pps_rate:.4} MPPS")
        #
        #     print(f"|-----------------------------------------------------")
        #     print(f"| expected_tx_time                    : {expected_tx_time_s:.3f}s")
        #     print(f"| Elapsed time                        : {elapsedtime_ts:.3f}s")
        #

    except KeyboardInterrupt:
        print("Exiting...")
        pass

    stoptime = datetime.now()
    total_packets = fpga.hbm_pktcontroller.packet_count

    # make sure that enough time has passed for MAC to transmit all buffered packets
    time.sleep(1)
    if not args.start_time:
        my_logger.info(
            f"Stopping the TX = {fpga.hbm_pktcontroller.start_stop_tx.value}"
        )
        fpga.hbm_pktcontroller.start_stop_tx = 0
    fpga.timeslave.schedule_control = 4

    stoptime_ts = stoptime.timestamp()
    total_timediff_ts = stoptime_ts - starttime_ts

    my_logger.info("--------------------------------------------")
    my_logger.info(f"* Totaltime_ts         : {total_timediff_ts:.3f}s")
    my_logger.info(
        f"* MAC Packets TX       : {fpga.system.eth100g_tx_total_packets.value}"
    )
    my_logger.info(f"* Total Packets TX     : {total_packets.value}")


def create_logger(args):
    if args.verbose is None:
        log_level = logging.WARNING
    elif args.verbose == 1:
        log_level = logging.INFO
    elif args.verbose >= 2:
        log_level = logging.DEBUG

    my_logger = logging.getLogger()
    output_file_handler = logging.FileHandler("pcap_to_hbm.log")
    stdout_handler = logging.StreamHandler(sys.stdout)
    my_logger.addHandler(output_file_handler)
    my_logger.addHandler(stdout_handler)
    my_logger.setLevel(log_level)
    # my_logger.removeHandler(my_logger.handlers[0])  # remove default stderr output

    return my_logger


def configure_hpc(
    fpga,
    aligned_packet_len,
    args,
    expected_beats_per_packet,
    expected_number_beats_per_burst,
    expected_number_of_loops,
    expected_packets_per_burst,
    expected_total_number_of_bursts,
    number_of_packets,
    packet_bytes,
):
    """Configure the HBM Packet Controller"""
    fpga.hbm_pktcontroller.loop_tx = int(args.loop)
    # Size of the ethernet packets
    fpga.hbm_pktcontroller.packet_size = packet_bytes
    # Total number of packets to transmit
    fpga.hbm_pktcontroller.total_number_tx_packets = number_of_packets
    # Number of packets to send back to back in a burst
    fpga.hbm_pktcontroller.number_of_packets_in_burst = args.burst_size
    # Time in ns between bursts of packets
    fpga.hbm_pktcontroller.time_between_bursts_ns = args.burst_gap
    # Calculate the total number of AXI 64 byte transactions from the HBM are required
    fpga.hbm_pktcontroller.expected_total_number_of_4k_axi = math.ceil(
        (((number_of_packets + 1) * aligned_packet_len) / 4096) - 1
    )
    fpga.hbm_pktcontroller.expected_packets_per_burst = (
        expected_packets_per_burst
    )
    fpga.hbm_pktcontroller.expected_beats_per_packet = (
        expected_beats_per_packet
    )
    fpga.hbm_pktcontroller.expected_number_beats_per_burst = (
        expected_number_beats_per_burst
    )
    fpga.hbm_pktcontroller.expected_number_of_loops = expected_number_of_loops
    fpga.hbm_pktcontroller.expected_total_number_of_bursts = (
        expected_total_number_of_bursts
    )
    # Packet type is Passthrough (Dont attached Ethernet headers or SPEAD/CODIF headers)
    fpga.hbm_pktcontroller.packet_type = 0
    # Generate the ethernet frame number and increment it every
    # number_of_packets_in_burst packets
    fpga.hbm_pktcontroller.increase_header_frame_number = 0
    # Generate and attach the ethernet and SPEAD/CODIF header
    # or modify in place in the stream
    fpga.hbm_pktcontroller.inplace_header_update = 0


def write_and_verify_memory(driver, buffer):
    driver.write_memory(HBM_MEMORY_BUFFER, buffer.view(np.uint8))
    driver_read = driver.read_memory(
        HBM_MEMORY_BUFFER, size_bytes=buffer.nbytes
    ).view(dtype=np.uint8)
    logging.debug(
        f"n_bytes read from driver: {driver_read.nbytes}, input buffer: {buffer.nbytes}"
    )
    logging.debug(
        f"dtype read from driver: {driver_read.dtype}, input buffer: {buffer.dtype}"
    )
    logging.debug(
        f"shape read from driver: {driver_read.shape}, input buffer: {buffer.shape}"
    )
    # Now verify the whole memory
    # (this will raise an exception and exit if a difference is found)
    np.testing.assert_array_equal(
        buffer.view(np.uint32), driver_read.view(np.uint32)
    )


def create_argument_parser():
    """Configure command-line"""
    parser = argparse.ArgumentParser(description="CNIC")

    # FPGA driver options
    parser.add_argument(
        "-f", "--kernel", type=str, help="path to xclbin kernel file"
    )
    parser.add_argument(
        "-d", "--card", default=0, type=int, help="index of card to use"
    )
    # TODO - can we remove mem arg as it should be static in final release?
    parser.add_argument(
        "-m",
        "--memory",
        type=str,
        help="""HBM memory configuration <size><unit><s|i>
             size: int
             unit: k, M, G (powers of 1024)
             s: shared
             i: FPGA internal
             Default: 2Gs""",
        default="2Gs",
    )

    # Packet playback options
    parser.add_argument(
        "--burst-size",
        type=positive_int,
        help="Number of packets in a burst. Default: 1",
        default=1,
    )
    parser.add_argument(
        "--burst-gap",
        type=int,
        help="Time between bursts of packets (nanoseconds). Default: 1000",
        default=1000,
    )
    parser.add_argument(
        "--total-time",
        type=float,
        help="Total time to transmit for (seconds). Default: 1",
        default=1.0,
    )
    parser.add_argument(
        "--numpackets",
        type=positive_int,
        help="Total number of packets to transmit. Default: 10",
        default=10,
    )
    parser.add_argument("--loop", action="store_true", help="Loop")

    # Input packets - either a pcap file or the debug mode flag
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "pcap",
        nargs="?",
        type=argparse.FileType("rb"),
        help="path and filename of .pcap(ng) file to load into HBM memory",
    )
    input_group.add_argument(
        "--debugpkts",
        type=positive_int,
        help="Generate debug packets of specified size",
    )

    # PTP options
    parser.add_argument(
        "--ptp-disable", action="store_true", help="Disable PTP"
    )
    parser.add_argument(
        "--ptp-domain", type=int, help="PTP domain. Default: 24", default=24
    )
    parser.add_argument(
        "--start-time",
        type=time_str,
        help='PTP Start trigger. e.g. "2022-03-30 13:47:30.123"',
    )

    # Log verbosity
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        help="Increase log verbosity. One v for info, two for debug.",
    )
    return parser


def positive_int(value):
    try:
        assert int(value) > 0
    except (ValueError, AssertionError):
        raise argparse.ArgumentTypeError(f"{value} is not a positive integer")
    return int(value)


def time_str(value):
    # TODO - we can possibly assume today's date? (or tomorrow if time in past?)
    TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
    try:
        return datetime.strptime(value, TIME_FORMAT)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{value} is not a time like {TIME_FORMAT}"
        )


if __name__ == "__main__":
    main()
