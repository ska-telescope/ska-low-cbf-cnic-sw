import argparse
import json

from scapy.all import UDP, rdpcap


def compare_n_packets(max_packets, packets, packets_capture, dport):

    if len(packets) != len(packets_capture):
        print(
            "WARNING! Capture files not same length. "
            f"{len(packets)} packets vs {len(packets_capture)} packets"
        )
    index_with_rebase = 0
    results = {}
    for packet in packets_capture:
        if packet.haslayer(UDP):
            if packet.dport == dport:
                if packet != packets[index_with_rebase]:
                    results[index_with_rebase] = "Not matching"
                index_with_rebase = index_with_rebase + 1
                if index_with_rebase > max_packets:
                    return results
    return results


def main():
    argparser = argparse.ArgumentParser(description="Perentie PCAP comparator.")
    argparser.add_argument(
        "input", type=argparse.FileType("r"), nargs=2, help="Input pcap trace files"
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

    differences = compare_n_packets(
        args.packets, rdpcap(args.input[0].name), rdpcap(args.input[1].name)
    )
    if len(differences) == 0:
        print("Two files contain same packets")
    else:
        print("Files are different")
        args.report.write(json.dumps(differences))


if __name__ == "__main__":
    main()
