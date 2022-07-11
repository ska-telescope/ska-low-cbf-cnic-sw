# -*- coding: utf-8 -*-

"""Change the port in a pcap file"""

import argparse

from scapy.all import UDP, rdpcap, wrpcap


def change_port(packets, port, output_file):
    for packet in packets:
        if packet.haslayer(UDP):
            packet[UDP].dport = port
            wrpcap(output_file, packet, append=True)


def main():
    argparser = argparse.ArgumentParser(description="pcap Port Change")
    argparser.add_argument(
        "input", type=argparse.FileType("r"), help="Input pcap trace file"
    )
    argparser.add_argument(
        "--port", "-p", type=int, default=36001, help="Port to use. Default: 36001"
    )
    argparser.add_argument(
        "--output",
        "-o",
        type=argparse.FileType("w"),
        help="Output pcap file name. Default: new_port.pcap",
        default="new_port.pcap",
    )
    args = argparser.parse_args()
    change_port(rdpcap(args.input.name), args.port, args.output.name)


if __name__ == "__main__":
    main()
