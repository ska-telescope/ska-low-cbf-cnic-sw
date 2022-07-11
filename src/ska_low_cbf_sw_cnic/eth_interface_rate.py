import argparse
import os
import time
from datetime import datetime


def screen_clear():
    # for mac and linux(here, os.name is 'posix')
    if os.name == "posix":
        _ = os.system("clear")


def main():
    # command line arguments
    parser = argparse.ArgumentParser(description="Interface Rate Monitor")
    parser.add_argument(
        "interface",
        type=str,
        help="Ethernet Interface to monitor",
        default="1",
    )
    args = parser.parse_args()

    prev_rx_bytes = 0
    prev_rx_packets = 0
    prev_tx_bytes = 0
    prev_tx_packets = 0
    newtime = datetime.now()

    ifconfig = os.popen(f"sudo ifconfig {args.interface} promisc")
    ifconfig.close()

    while True:
        screen_clear()
        rate = os.popen(
            f"ethtool -S {args.interface} | grep -E 'rx_packets:|rx_bytes:'"
        )
        stream = rate.read()
        rx_bytes = int(stream.split()[3])
        rx_packets = int(stream.split()[1])
        rate.close()

        rate_tx = os.popen(
            f"ethtool -S {args.interface} | grep -E 'tx_packets:|tx_bytes:'"
        )
        stream_tx = rate_tx.read()
        tx_bytes = int(stream_tx.split()[3])
        tx_packets = int(stream_tx.split()[1])
        rate_tx.close()

        measurement_time = 1

        prevtime = newtime
        newtime = datetime.now()
        newtime_ts = newtime.timestamp()
        prevtime_ts = prevtime.timestamp()
        timediff = newtime - prevtime
        timediff_ts = newtime_ts - prevtime_ts

        print(f"{newtime}     timediff_ts = {timediff_ts} s")

        rx_rate = (rx_bytes - prev_rx_bytes) * 8 / timediff_ts
        tx_rate = (tx_bytes - prev_tx_bytes) * 8 / timediff_ts

        print(f"\n\n")
        print(f"          Interface {args.interface}")
        print(f"|----------------------------------------")
        print(f"| Total rx_packets : {rx_packets}")
        print(f"| Total rx_bytes   : {rx_bytes}")
        print(f"|----------------------------------------")
        print(f"| rx_rate          : {rx_rate/1E9:.6} Gbps")
        print(f"|----------------------------------------")
        print(f"| Total tx_packets : {tx_packets}")
        print(f"| Total tx_bytes   : {tx_bytes}")
        print(f"|----------------------------------------")
        print(f"| tx_rate          : {tx_rate/1E9:.6} Gbps")
        print(f"|----------------------------------------")

        time.sleep(1)
        prev_rx_bytes = rx_bytes
        prev_rx_packets = rx_packets
        prev_tx_bytes = tx_bytes
        prev_tx_packets = tx_packets


if __name__ == "__main__":
    main()
