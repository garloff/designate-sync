# designate-sync
Copy over designate-managed DNS zones over from one OpenStack cloud to another

## Usage
`dnssync.py` is a utility to copy/sync designate managed DNS zones
from one OpenStack Cloud to another.

Usage: `dnssync.py --from-cloud=`CLOUD1` --to-cloud=`CLOUD2 [options]` --all`|ZONE1 [ZONE2 ...]<br/>
Options: `--remove`|`-r`    remove records in target not found in source<br/>
         `--mail`|`-m `MAIL override email address in SOA records<br/>
         `--quiet`|`-q`     don't output statistics<br/>
         `--verbose`|`-v`   progress output<br/>

`dnssync.py` looks at all records from ZONE1 (and ZONE2 if specified or all
zones with `--all`) in CLOUD1 and analyzes all records. It then looks at the
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
setting may be overwritten by `--mail` MAIL.

NS records for further zones (subdomains) are analyzed -- if they point to
a third party DNS, they are copied over. If they point to the DNS NS of either
source or target cloud, they are ignored.

(c) Kurt Garloff <scs@garloff.de>, 2/2024<br/>
SPDX-License-Identifier: CC-BY-SA-4.0

