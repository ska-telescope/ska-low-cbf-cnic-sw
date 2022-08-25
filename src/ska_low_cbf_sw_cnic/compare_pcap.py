import argparse
import os
import sys
import typing

import dpkt


def compare_n_packets(
    max_packets, packets, packets_capture, dport
) -> (list, int):
    """
    Compare a number of packets
    :param max_packets: maximum number of packets to compare (None => compare all)
    :param packets: original source set of packets
    :param packets_capture: actual captured set of packets
    :param dport: destination port of interest (filter applied to `packets_capture`)
    :return: listing of differing packet indices (dport mismatches not counted),
    int number of packets compared
    :raises StopIteration: if packets_capture runs out before packets
    """

    index = 0
    differences = []
    for (src_ts, src_packet) in packets:
        # skip over captured packets with the wrong dport
        while True:
            (cap_ts, cap_packet) = next(packets_capture)
            eth_cap = dpkt.ethernet.Ethernet(cap_packet)
            if (
                eth_cap.type == dpkt.ethernet.ETH_TYPE_IP
                and eth_cap.data.p == dpkt.ip.IP_PROTO_UDP
                and eth_cap.data.data.dport == dport
            ):
                break

        if cap_packet != src_packet:
            differences.append(index)
        index += 1
        if max_packets and index > max_packets:
            break
    return differences, index


def create_reader(file: typing.BinaryIO):
    if os.path.splitext(file.name)[1] == ".pcapng":
        reader = dpkt.pcapng.Reader
    else:
        reader = dpkt.pcap.Reader

    return reader(file)


def main():
    argparser = argparse.ArgumentParser(
        description="Perentie PCAP comparator."
    )
    argparser.add_argument(
        "input",
        type=argparse.FileType("rb"),
        nargs=2,
        help="Input pcap trace files. Second file (only) is filtered by dport.",
    )
    argparser.add_argument(
        "--packets",
        type=int,
        help="Number of packets to compare. Default: all",
    )
    argparser.add_argument(
        "--dport",
        type=int,
        default=4660,
        help="Destination Port of interest. Default: 4660",
    )
    argparser.add_argument(
        "--report",
        type=argparse.FileType("w"),
        default="differences.txt",
        help="Differences report file. Default: differences.txt",
    )

    args = argparser.parse_args()

    try:
        differences, n_comp = compare_n_packets(
            args.packets,
            create_reader(args.input[0]),
            create_reader(args.input[1]),
            args.dport,
        )
    except StopIteration:
        print(
            f"{args.input[1].name} does not have enough packets to finish comparison"
        )
        sys.exit(2)

    if n_comp > 0 and len(differences) == 0:
        print(f"Two files contain same packets ({n_comp} packets compared)")
    elif n_comp == 0:
        print("No packets compared! (check dport)")
        sys.exit(3)
    else:
        print(
            (
                f"Files are different.\n"
                f"{n_comp} packets compared, {len(differences)} differences.\n"
                f"Writing packet indices of differences to {args.report.name}."
            )
        )
        for line in differences:
            args.report.write(f"{line}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
