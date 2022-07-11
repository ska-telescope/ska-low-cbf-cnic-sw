# CNIC Control Software

# Installation

## End User
Releases are [published via the SKA Central Artefact Repository](https://artefact.skao.int).

```commandline
pip install ska-low-cbf-sw-cnic \
  --extra-index-url https://artefact.skao.int/repository/pypi-internal/simple
```

More up-to-date development packages are available in
[this project's package registry](https://gitlab.com/ska-telescope/low-cbf/ska-low-cbf-sw-cnic/-/packages).
Note that a GitLab API token will be required for access.

## Developer

This repository uses [Poetry](https://python-poetry.org/), a python package
and dependency manager, and [pre-commit](https://pre-commit.com/), a framework
for managing git-commit hooks used here to check that committed code follows
the project style guide.

1. [Install Poetry](https://python-poetry.org/docs/#installation). Be sure to
use "install\_poetry.py", not "get\_poetry.py" (the superseded installer).
2. Run `poetry install` to install the project & its dependencies. Poetry
uses the `pyproject.toml` file which lists required python tools and versions.
3. [Install pre-commit](https://pre-commit.com/), which is a framework for
managing actions invoked when `git commit` is run.
4. Run `pre-commit install` to ensure your code will be correctly formatted
when committing changes. Pre-commit sets up actions based on the
`.pre-commit-config.yaml` file in the repository.
5. A git hook is provided that may help comply with SKA commit message rules.
You can install the hook with `cp -s "$(pwd)/resources/git-hooks"/* .git/hooks`.
Once installed, the hook will insert commit messages to match the JIRA ticket
from the branch name.
e.g. On branch `perentie-1350-new-base-classes`:
```console
ska-low-cbf$ git commit -m "Add git hook note to README"
Branch perentie-1350-new-base-classes
Inserting PERENTIE-1350 prefix
[perentie-1350-new-base-classes 3886657] PERENTIE-1350 Add git hook note to README
 1 file changed, 7 insertions(+)
```
You can see the modified message above, and confirming via the git log:
```console
ska-low-cbf$ git log -n 1 --oneline
3886657 (HEAD -> perentie-1350-new-base-classes) PERENTIE-1350 Add git hook note to README

# Usage

You'll need to source the XRT setup script before using these utilities.
```commandline
source /opt/xilinx/xrt/setup.sh
```

The following utilities are provided, each can be launched directly from the
command line.

Use the `--help` flag to get more detailed (and up-to-date) usage instructions.

## change\_port
Change the port number in a pcap file.

**Warning** the input file is loaded into memory in full.

```commandline
change_port [-h] [--port PORT] [--output OUTPUT] input
```

## compare\_pcap
Find differences between two pcap files, checking only packets with a specified
destination port.

**Warning** both files are loaded into memory in full.

```commandline
compare_pcap [-h] [--packets PACKETS] [--dport DPORT] [--report REPORT] input input
```

## eth\_interface\_rate

Monitor the transmit & recieve rates on an ethernet interface.

**Warnings**
* uses the sudo command
* activates promiscuous mode on the interface
* requires ethtool

```commandline
eth_interface_rate [-h] interface
```

## pcap\_to\_hbm

Transmit a pcap file via the Alveo's 100G Ethernet port.

```commandline
usage: pcap_to_hbm [-h] [-f KERNEL] [-d CARD] [-m MEMORY] [--burst-size BURST_SIZE] [--burst-gap BURST_GAP]
                   [--total-time TOTAL_TIME] [--numpackets NUMPACKETS] [--loop] [--debugpkts DEBUGPKTS]
                   [--ptp-domain PTP_DOMAIN] [--start-time START_TIME] [-v]
                   [pcap]
```
``` e.g.
  pcap_to_hbm --card 0 -f cnic.xclbin test/codif_sample.pcapng --start-time "2022-03-30 13:14:15.75"
```
# Road Map

Some ideas for future work... consider all details suggestions subject to change,
they're not set in stone!

* Split the load/monitoring parts of pcap\_to\_hbm into different programs.
The user may want to start sending packets forever without blocking their terminal.
  * `cnic_send` to perform the "load to HBM" and "begin transmit" functions
  * `cnic_monitor` to launch the monitoring UI
* HBM Packet Controller setup functions could be moved to HbmPacketController,
rather than driving all registers individually/directly in the main program.
* Controlling multiple FPGA cards with one instance of the program would be
viable after doing some more refactoring. Could either use a loop over a list
of `CnicFpga` objects or invent some FPGA group object to handle it.
* pcap/pcapng detection is a bit crude, there may be a way to detect based on content
rather than file extension?
* There really should be a lot more tests!
  * We might need ArgsSimulator to simulate HBM in order to test without an FPGA
  * Adding tests that exercise a real FPGA may be easier, and a good idea in any case...
* A program to control capturing of packets (when FPGA images supports same)
* Configuration of inter-packet gaps (i.e. jitter, maybe a Poisson distribution)
* Record statistics over time, so they can be graphed
  * Sampling statistics in the FPGA would be more accurate, we could download
when ready, in batches, whatever
* A software utility could be provided to download the latest xclbin file,
after that has been published somewhere... (or it could perhaps be bundled up
with the python package?)

# Changelog
### 0.2.5
- Add option to disable PTP
- Move to SKA repo
