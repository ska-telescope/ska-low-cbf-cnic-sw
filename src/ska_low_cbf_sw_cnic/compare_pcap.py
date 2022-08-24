import argparse
import json

from scapy.all import UDP, rdpcap


def compare_n_packets(
    max_packets, packets, packets_capture, dport
) -> (dict, int):
    """
    Compare a number of packets
    :param max_packets: maximum number of packets to compare
    :param packets: original source set of packets
    :param packets_capture: actual captured set of packets
    :param dport: destination port of interest (filter applied to `packets_capture`)
    :return: dict listing differences (key: packet index excluding dport mismatches),
    int number of packets compared
    """

    if len(packets) != len(packets_capture):
        print(
            "WARNING! Capture files not same length. "
            f"{len(packets)} packets vs {len(packets_capture)} packets"
        )
    index = 0
    results = {}
    for packet in packets_capture:
        if packet.haslayer(UDP):
            if packet.dport == dport:
                if packet != packets[index]:
                    results[index] = "Not matching"
                index = index + 1
                if index > max_packets:
                    break
    return results, index


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
        default=1000,
        help="Number of packets to compare. Default: 1000",
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

    print(f"Loading {args.input[0].name}")
    a = rdpcap(args.input[0])
    print(f"Loading {args.input[1].name}")
    b = rdpcap(args.input[1])
    print("Comparing...")
    differences, n_comp = compare_n_packets(args.packets, a, b, args.dport)
    if len(differences) == 0:
        print(f"Two files contain same packets ({n_comp} packets compared)")
    else:
        print("Files are different")
        args.report.write(json.dumps(differences))


if __name__ == "__main__":
    main()
