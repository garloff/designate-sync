#!/usr/bin/env python3

"""
dnssync.py is a utility to copy/sync designate managed DNS zones
from one OpenStack Cloud to another.

Usage: dnssync.py --from-cloud=CLOUD1 --to-cloud=CLOUD2 [options] --all|ZONE1 [ZONE2 ...]
Options: --remove|-r    remove records in target not found in source
         --mail|-m MAIL override email address in SOA records
         --quiet|-q     don't output statistics
         --verbose|-v   progress output

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


# Globals
nodom = 0
nodomcreate = 0
noreccreate = 0
norecskip   = 0
norecchange = 0
norecnochg  = 0
norecdelete = 0


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
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='suppress statistics')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='output progress')
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


def extract_soamail(rec):
    "Transform mail in SOA rec into proper email address"
    if rec[-1] == '.':
        rec = rec[0:-1]
    return rec.replace('.', '@', 1)


def find_record(dns, zone, rec):
    "Find matching record"
    rset = dns.recordsets(zone, name=rec.name, type=rec.type)
    if rset:
        rset = list(rset)
        if len(rset) == 0:
            return None
        if len(rset) != 1:
            print(f"ERROR: recordset({rec.name}, {rec.type} not unique: {rset}",
                  file=sys.stderr)
        assert len(rset) == 1
        return rset[0]
    return None


def set_equal(set1, set2):
    "Compare unordered set for equality"
    for el1 in set1:
        if el1 not in set2:
            return False
    for el2 in set2:
        if el2 not in set1:
            return False
    return True


def sync_zone(dns1, dns2, zone, mail, remove, verbose):
    """sync zone from dns1 to dns2,
       cleaning extra records in dns2 is remove is True
       overwriting mail in SOA if passed.
    """
    global nodomcreate, noreccreate, norecchange, norecnochg, norecdelete, norecskip
    # Append trailing '.' if not passed
    if zone[-1] != '.':
        zone += '.'
    if verbose:
        print(f"Sync zone {zone}")
    szone = dns1.find_zone(zone)
    if not szone:
        print(f'ERROR: zone {zone} does not exist in src cloud', file=sys.stderr)
        return 1
    ssets = dns1.recordsets(szone)
    zonens = dns1.recordsets(szone, name=zone, type='NS')
    if not zonens:
        print(f'ERROR: zone {zone} has no NS records', file=sys.stderr)
        return 1
    zonesoa = dns1.recordsets(szone, name=zone, type='SOA')
    if not zonesoa:
        print(f'EROOR: zone {zone} has no SOA record', file=sys.stderr)
        return 1
    srcns = list(zonens)[0].records
    srcsoa = list(zonesoa)[0].records[0].split(" ")
    if mail:
        soamail = mail
    else:
        # soamail = extract_soamail(srcsoa[1])
        soamail = szone.email

    errs = 0
    tzone = dns2.find_zone(zone)
    if not tzone:
        print(f"DNS create(name={zone}, ttl={srcsoa[4]}, mail={soamail})")
        try:
            tzone = dns2.create_zone(name=zone, ttl=srcsoa[4], email=soamail,
                                     description=szone.description)
            nodomcreate += 1
        except openstack.exceptions.SDKException as exc:
            print(exc, file=sys.stderr)
            return 1

    dstns = list(dns2.recordsets(tzone, name=zone, type='NS'))[0].records
    tsets = dns2.recordsets(tzone)
    # TODO: Check if it's more efficient to collect lists and then iterate over them ...
    # Forward copy
    for sset in ssets:
        # Do not copy NS records for sub domains pointing to one self
        if verbose:
            print(f"\rRecord {sset.name} type {sset.type}                    ", end="")
        if sset.type == 'NS':
            if set_equal(sset.records, srcns) or set_equal(sset.records, dstns):
                norecskip += 1
                continue
        # Never overwrite SOA (ignore TTL differences if any)
        if sset.type == 'SOA':
            norecskip += 1
            continue
        # Record already present?
        tset = find_record(dns2, tzone, sset)
        # FIXME: Do we need to copy over status field as well?
        if not tset:
            try:
                dns2.create_recordset(tzone, name=sset.name, type=sset.type, ttl=sset.ttl,
                                      records=sset.records, description=sset.description)
                noreccreate += 1
            except openstack.exceptions.SDKException as exc:
                print(exc, file=sys.stderr)
                errs += 1
        else:
            if tset.ttl != sset.ttl or tset.records != sset.records or tset.description != sset.description:
                try:
                    dns2.update_recordset(tset, name=sset.name, type=sset.type, ttl=sset.ttl,
                                          records=sset.records, description=sset.description)
                    norecchange += 1
                except openstack.exceptions.SDKException as exc:
                    print(exc, file=sys.stderr)
                    errs += 1
            else:
                norecnochg += 1
    # Backward cleanup
    if remove:
        for tset in tsets:
            if verbose:
                print(f"\rRecord {tset.name} type {tset.type}                    ", end="")
            sset = find_record(dns1, szone, tset)
            if not sset:
                try:
                    dns2.delete_recordset(tset)
                    norecdelete += 1
                except openstack.exceptions.SDKException as exc:
                    print(exc, file=sys.stderr)
                    errs += 1
    if verbose:
        print("\r   \r", end="")
    return errs


def main(argv):
    "Main entry point"
    global nodom
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

    errs = 0
    for zone in zones:
        errs += sync_zone(cloud1.dns, cloud2.dns, zone, args.mail, args.remove, args.verbose)
        nodom += 1

    if not args.quiet:
        print(f"Statistics: {nodom} domains processed, {nodomcreate} domains created")
        print(f"            {noreccreate} records created, {norecdelete} records deleted")
        print(f"            {norecchange} records changed, {norecnochg} records unchanged, {norecskip} records skipped")
        print(f"{errs} errors")

    return errs


# Call main if used alone
if __name__ == "__main__":
    main(sys.argv)
