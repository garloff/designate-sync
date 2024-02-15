#!/usr/bin/env python3

"""
dnssync.py is a utility to copy/sync designate managed DNS zones
from one OpenStack Cloud to another.

Usage: dnssync.py --from-cloud=CLOUD1 --to-cloud=CLOUD2 [options] --all|ZONE1 [ZONE2 ...]
Options: --remove|-r    remove records in target not found in source
         --mail|-m MAIL override email address in SOA records

dnssync.py looks at all records from ZONE1 (and ZONE2 if specified oor all
zones with --all) in CLOUD1 and analyzes all records. It then looks at the
records in the same zone in CLOUD2, creating the zone if needed. All records
are copied over.
NS and SOA records are treated specially. For the NS records of the zone
itself, it ignores them. (These records are created during zone creation and
should point to the nameservers of the zone. The NS records however are
remembered, as we'll need them later.
The SOA record of the source cloud zone is also analyzed and used for zone
creation in the target cloud. If the TTL or EMail there are different than a
preexisting setting in the target cloud, the latter is overwritten. (The
program also handles the quirk in OTC's SOA record formatting.) The SOA's mail
setting may be overwritten by --mail MAIL.

NS records for further zones (subdomains) are analyzed -- if they point to
a third party DNS, they are copied over. If they point to the DNS NS of either
source or target cloud, they are ignored.

(c) Kurt Garloff <scs@garloff.de>, 2/2024
SPDX-License-Identifier: CC-BY-SA-4.0
"""

# import os
import sys
import argparse
import openstack


def usage():
    "Help function"
    print(__doc__, file=sys.stderr)
    sys.exit(1)


def setup_parser():
    "Setup argument parser"
    parser = argparse.ArgumentParser(prog='dnssync.py',
                                     description='sync designate zones')
    parser.add_argument('-r', '--remove', action='store_true',
                        help='remove extra records on target cloud')
    parser.add_argument('-m', '--mail',
                        help='override email address in SOA records')
    parser.add_argument('-f', '--from-cloud', required=True,
                        help='source cloud')
    parser.add_argument('-t', '--to-cloud', required=True,
                        help='target cloud')
    parser.add_argument('-a', '--all', action='store_true',
                        help='process all found zones')
    parser.add_argument('zones', nargs="*",
                        help='zone(s) to process (space-separated), mand. if --all is not used')
    return parser


def get_zones(dnsconn):
    "Get list of DNS zones from dnsconn cloud DNS service"
    zones = []
    for zone in dnsconn.zones():
        zones.append(zone.name)
    return zones


def sync_zone(dns1, dns2, zone, mail, remove):
    """sync zone from dns1 to dns2,
       cleaning extra records in dns2 is remove is True
       overwriting mail in SOA if passed.
    """
    # Append trailing '.' if not passed
    if zone[-1] != '.':
        zone += '.'
    print(f"Sync zone {zone}: not yet implemented")


def main(argv):
    "Main entry point"
    if not argv[1:]:
        usage()
    parser = setup_parser()
    args = parser.parse_args()
    if not args.zones and not args.all:
        print('ERROR: Must specify zones or --all', file=sys.stderr)
        usage()
    if args.zones and args.all:
        print('ERROR: Specify either zones or --all', file=sys.stderr)
        usage()

    cloud1 = openstack.connect(args.from_cloud)
    cloud2 = openstack.connect(args.to_cloud)

    cloud1.authorize()
    cloud2.authorize()

    if args.all:
        zones = get_zones(cloud1.dns)
    else:
        zones = args.zones

    for zone in zones:
        sync_zone(cloud1.dns, cloud2.dns, zone, args.mail, args.remove)


# Call main if used alone
if __name__ == "__main__":
    main(sys.argv)
