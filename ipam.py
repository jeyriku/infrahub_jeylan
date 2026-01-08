#!/usr/bin/env python3
"""
IPAM Tool - Unified CLI for Infrahub IPAM Management
====================================================
Complete toolset for managing Infrahub IPAM with hierarchy support.

Commands:
  status       Show current IPAM status with statistics
  populate     Populate IPAM from inventory and network data
  hierarchy    Manage subnet parent-child relationships

Type 'ipam.py <command> --help' for detailed help on each command.
"""

import sys
import json
import requests
import ipaddress
import subprocess
import concurrent.futures
import socket
import re
import argparse
from collections import defaultdict
from typing import Dict, Set, List


# Configuration
INFRAHUB_URL = "http://127.0.0.1:8000"
API_TOKEN = "188600a3-6e17-9f97-339f-c516618aa3c0"
HEADERS = {
    "Content-Type": "application/json",
    "X-INFRAHUB-KEY": API_TOKEN
}

# Networks without subdivision (only use /24)
NETWORKS_WITHOUT_SUBDIVISION = [
    '192.168.0.0/24',
    '10.0.0.0/24',
    '10.0.1.0/24'
]


# ============================================================================
# GraphQL Helper Functions
# ============================================================================

def graphql_query(query, variables=None):
    """Execute a GraphQL query"""
    response = requests.post(
        f"{INFRAHUB_URL}/graphql/main",
        headers=HEADERS,
        json={"query": query, "variables": variables or {}}
    )
    response.raise_for_status()
    result = response.json()

    if "errors" in result:
        print("GraphQL Errors:")
        print(json.dumps(result["errors"], indent=2))
        raise Exception(f"GraphQL errors: {result['errors']}")

    return result.get("data", {})


# ============================================================================
# COMMAND: status
# ============================================================================

def get_subnet_stats():
    """Get subnet statistics including parent/child breakdown"""
    query = """
    {
      JeylanIPAMSubnet {
        edges {
          node {
            id
            subnet { value }
            subnet_type { value }
            parent_subnet {
              node {
                subnet { value }
              }
            }
            child_subnets {
              edges {
                node {
                  subnet { value }
                }
              }
            }
          }
        }
      }
    }
    """

    data = graphql_query(query)
    subnets = data.get("JeylanIPAMSubnet", {}).get("edges", [])

    total = len(subnets)
    by_type = {"parent": 0, "child": 0, "other": 0}
    parents_with_children = 0
    children_with_parent = 0

    for edge in subnets:
        node = edge["node"]
        subnet_type = node.get("subnet_type", {}).get("value")

        if subnet_type in by_type:
            by_type[subnet_type] += 1
        else:
            by_type["other"] += 1

        has_children = len(node.get("child_subnets", {}).get("edges", [])) > 0
        has_parent = node.get("parent_subnet", {}).get("node") is not None

        if has_children:
            parents_with_children += 1
        if has_parent:
            children_with_parent += 1

    return {
        "total": total,
        "parents": by_type["parent"],
        "children": by_type["child"],
        "other": by_type["other"],
        "parents_with_children": parents_with_children,
        "children_with_parent": children_with_parent
    }


def get_ip_stats():
    """Get IP address statistics"""
    query = """
    {
      JeylanIPAMIPAddress {
        count
        edges {
          node {
            subnet {
              node {
                id
              }
            }
          }
        }
      }
    }
    """

    data = graphql_query(query)
    total = data.get("JeylanIPAMIPAddress", {}).get("count", 0)
    edges = data.get("JeylanIPAMIPAddress", {}).get("edges", [])

    linked = sum(1 for edge in edges if edge["node"].get("subnet", {}).get("node"))
    unlinked = total - linked

    return {
        "total": total,
        "linked": linked,
        "unlinked": unlinked
    }


def cmd_status(args):
    """Display current IPAM status"""
    print("=" * 70)
    print("INFRAHUB IPAM STATUS".center(70))
    print("=" * 70)

    # Get statistics
    subnet_stats = get_subnet_stats()
    ip_stats = get_ip_stats()

    # Display subnets
    print(f"\n📊 Subnets: {subnet_stats['total']} total")
    print(f"   • Parents (/24, /16, /8): {subnet_stats['parents']}")
    print(f"   • Children (/30, /29): {subnet_stats['children']}")
    if subnet_stats['other'] > 0:
        print(f"   • Other: {subnet_stats['other']}")

    # Display hierarchy
    print(f"\n🔗 Hierarchy:")
    print(f"   • Parents with children: {subnet_stats['parents_with_children']}")
    print(f"   • Children with parent: {subnet_stats['children_with_parent']}")

    # Display IPs
    print(f"\n📍 IP Addresses: {ip_stats['total']} total")
    print(f"   • Linked to subnet: {ip_stats['linked']}")
    if ip_stats['unlinked'] > 0:
        print(f"   • Unlinked: {ip_stats['unlinked']}")

    print("\n" + "=" * 70)


def cmd_status_detailed(args):
    """Display detailed IPAM inventory"""
    print("=" * 70)
    print("IPAM INVENTORY SUMMARY".center(70))
    print("=" * 70)

    # Get prefixes
    query = """
    {
      JeylanIPAMPrefix {
        count
        edges {
          node {
            id
            prefix { value }
            description { value }
          }
        }
      }
    }
    """

    data = graphql_query(query)
    print(f"\n📊 PREFIXES: {data['JeylanIPAMPrefix']['count']}")
    print("-" * 70)
    for edge in data['JeylanIPAMPrefix']['edges']:
        node = edge['node']
        print(f"  • {node['prefix']['value']:20s} {node['description']['value']}")

    # Get subnets by prefix
    query = """
    {
      JeylanIPAMSubnet {
        count
        edges {
          node {
            subnet { value }
            name { value }
            status { value }
            prefix {
              node {
                prefix { value }
              }
            }
          }
        }
      }
    }
    """

    data = graphql_query(query)

    # Group subnets by prefix
    subnets_by_prefix = defaultdict(list)
    for edge in data['JeylanIPAMSubnet']['edges']:
        node = edge['node']
        prefix_node = node.get('prefix', {}).get('node')
        if prefix_node:
            prefix = prefix_node['prefix']['value']
            subnets_by_prefix[prefix].append({
                'subnet': node['subnet']['value'],
                'name': node['name']['value'],
                'status': node['status']['value']
            })

    print(f"\n🌐 SUBNETS: {data['JeylanIPAMSubnet']['count']}")
    print("-" * 70)
    for prefix, subnets in sorted(subnets_by_prefix.items()):
        print(f"\n  Under {prefix}:")
        for subnet in sorted(subnets, key=lambda x: x['subnet'])[:10]:
            status_icon = "✓" if subnet['status'] == 'active' else "✗"
            print(f"    {status_icon} {subnet['subnet']:20s} ({subnet['name']})")
        if len(subnets) > 10:
            print(f"    ... and {len(subnets) - 10} more")

    # Get IP addresses
    query = """
    {
      JeylanIPAMIPAddress {
        count
        edges {
          node {
            address { value }
            status { value }
          }
        }
      }
    }
    """

    data = graphql_query(query)
    print(f"\n🔢 IP ADDRESSES: {data['JeylanIPAMIPAddress']['count']}")
    print("-" * 70)

    # Group by status
    by_status = defaultdict(int)
    ips = []
    for edge in data['JeylanIPAMIPAddress']['edges']:
        node = edge['node']
        status = node['status']['value']
        by_status[status] += 1
        ips.append(node['address']['value'])

    print(f"  Status breakdown:")
    for status, count in sorted(by_status.items()):
        print(f"    • {status}: {count}")

    print(f"\n  Sample IPs:")
    for ip in sorted(ips)[:10]:
        print(f"    • {ip}")
    if len(ips) > 10:
        print(f"    ... and {len(ips) - 10} more")

    print("\n" + "=" * 70)


# ============================================================================
# COMMAND: populate
# ============================================================================

def load_inventory():
    """Load network inventory from JSON file"""
    try:
        with open('inventaire_librenms.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("⚠️  Warning: inventaire_librenms.json not found")
        return {'devices': []}


def ping_ip(ip):
    """Ping an IP address"""
    try:
        result = subprocess.run(
            ['ping', '-c', '1', '-W', '1', ip],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=2
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


def reverse_dns_lookup(ip):
    """Perform reverse DNS lookup"""
    try:
        hostname, _, _ = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror):
        return None


def scan_network(network_str, workers=50):
    """Scan a network for active hosts"""
    network = ipaddress.ip_network(network_str)
    print(f"  🔍 Scanning {network_str}...")

    active_ips = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_ip = {
            executor.submit(ping_ip, str(ip)): str(ip)
            for ip in network.hosts()
        }

        for future in concurrent.futures.as_completed(future_to_ip):
            ip = future_to_ip[future]
            try:
                if future.result():
                    hostname = reverse_dns_lookup(ip)
                    active_ips.append({
                        'address': ip,
                        'device_name': hostname or f'device-{ip}',
                        'discovered': True
                    })
            except Exception:
                pass

    print(f"     ✓ Found {len(active_ips)} active hosts")
    return active_ips


def parse_cisco_routing_table(text):
    """Parse Cisco IOS routing table output"""
    subnets = set()

    patterns = [
        r'(\d+\.\d+\.\d+\.\d+/\d+)\s+is\s+(?:variably\s+)?subnetted',
        r'^[A-Z*+%#@]\s+(\d+\.\d+\.\d+\.\d+/\d+)',
        r'^\s+(\d+\.\d+\.\d+\.\d+/\d+)\s+is\s+',
    ]

    for line in text.split('\n'):
        for pattern in patterns:
            match = re.search(pattern, line, re.MULTILINE)
            if match:
                subnet_str = match.group(1)
                try:
                    network = ipaddress.ip_network(subnet_str, strict=False)
                    if not str(network.network_address).startswith('127.'):
                        subnets.add(str(network))
                except ValueError:
                    pass

    return subnets


def parse_juniper_routing_table(text):
    """Parse Juniper JunOS routing table output"""
    subnets = set()
    pattern = r'^(\d+\.\d+\.\d+\.\d+/\d+)\s+'

    for line in text.split('\n'):
        match = re.match(pattern, line.strip())
        if match:
            subnet_str = match.group(1)
            try:
                network = ipaddress.ip_network(subnet_str, strict=False)
                if not str(network.network_address).startswith('127.'):
                    subnets.add(str(network))
            except ValueError:
                pass

    return subnets


def load_routing_tables(routing_files):
    """Load and parse routing tables from files"""
    if not routing_files:
        return {'subnets': set(), 'host_ips': set()}

    all_subnets = set()
    all_host_ips = set()

    for filename in routing_files:
        try:
            with open(filename, 'r') as f:
                content = f.read()

            # Detect vendor
            if 'show ip route' in content.lower():
                subnets = parse_cisco_routing_table(content)
                vendor = "Cisco"
            elif 'show route' in content.lower():
                subnets = parse_juniper_routing_table(content)
                vendor = "Juniper"
            else:
                subnets = parse_cisco_routing_table(content) | parse_juniper_routing_table(content)
                vendor = "Generic"

            # Separate /32 (host IPs) from subnets
            for subnet_str in subnets:
                network = ipaddress.ip_network(subnet_str)
                if network.prefixlen == 32:
                    all_host_ips.add(str(network.network_address))
                else:
                    all_subnets.add(subnet_str)

            subnet_count = len([s for s in subnets if ipaddress.ip_network(s).prefixlen != 32])
            host_count = len([s for s in subnets if ipaddress.ip_network(s).prefixlen == 32])
            print(f"  ✓ {vendor} {filename}: {subnet_count} subnets, {host_count} IPs")

        except FileNotFoundError:
            print(f"  ⚠️  File not found: {filename}")
        except Exception as e:
            print(f"  ⚠️  Error parsing {filename}: {e}")

    return {'subnets': all_subnets, 'host_ips': all_host_ips}


def detect_smaller_subnets(ip_list, parent_network):
    """Detect smaller subnets within a parent network based on IP usage"""
    if not ip_list:
        return [str(parent_network)]

    sorted_ips = sorted([ipaddress.ip_address(ip) for ip in ip_list])

    if len(sorted_ips) <= 2:
        return [str(parent_network)]

    ip_to_best_subnet = {}

    # Check only /30 and /29
    for subnet_size in [30, 29]:
        subnet_groups = {}
        for ip in sorted_ips:
            if ip in ip_to_best_subnet:
                continue

            subnet = ipaddress.ip_network(f"{ip}/{subnet_size}", strict=False)
            if subnet.subnet_of(parent_network):
                subnet_str = str(subnet)
                if subnet_str not in subnet_groups:
                    subnet_groups[subnet_str] = []
                subnet_groups[subnet_str].append(ip)

        for subnet_str, ips_in_subnet in subnet_groups.items():
            if len(ips_in_subnet) >= 2:
                for ip in ips_in_subnet:
                    if ip not in ip_to_best_subnet:
                        ip_to_best_subnet[ip] = subnet_str

    detected_subnets = set(ip_to_best_subnet.values())

    if detected_subnets:
        return sorted(detected_subnets)
    else:
        return [str(parent_network)]


def analyze_network_structure(inventory, enable_scan=False, routing_tables=None, workers=50):
    """Analyze inventory to determine prefixes and subnets"""
    ip_addresses = []

    # From LibreNMS inventory
    for device in inventory.get('devices', []):
        if device.get('ip_address'):
            try:
                ipaddress.ip_address(device['ip_address'])
                ip_addresses.append({
                    'address': device['ip_address'],
                    'device_name': device.get('hostname', device.get('name', 'unknown')),
                    'interface': None,
                    'discovered': False
                })
            except ValueError:
                continue

    # Group IPs by /24
    ips_by_network = {}
    for ip_data in ip_addresses:
        try:
            ip = ipaddress.ip_address(ip_data['address'])
            if ip.version == 4 and not str(ip).startswith('127.'):
                network_24 = ipaddress.ip_network(f"{ip}/24", strict=False)
                network_str = str(network_24)
                if network_str not in ips_by_network:
                    ips_by_network[network_str] = []
                ips_by_network[network_str].append(ip_data['address'])
        except ValueError:
            continue

    # Integrate routing tables first to get additional networks to scan
    routing_data = {'subnets': set(), 'host_ips': set()}
    if routing_tables:
        print("\n📋 Integrating routing table information...")
        routing_data = load_routing_tables(routing_tables)

        # Add /24 networks from routing tables to scan list
        if enable_scan:
            for subnet_str in routing_data['subnets']:
                try:
                    network = ipaddress.ip_network(subnet_str)
                    if network.prefixlen == 24 and not str(network.network_address).startswith('127.'):
                        network_str = str(network)
                        if network_str not in ips_by_network:
                            ips_by_network[network_str] = []
                            print(f"  ✓ Added {network_str} to scan list from routing table")
                except ValueError:
                    continue

    # Network scan if enabled
    if enable_scan:
        print(f"\n🔍 Network Discovery Mode: Scanning {len(ips_by_network)} networks...\n")

        for network_str in sorted(ips_by_network.keys()):
            discovered_hosts = scan_network(network_str, workers)

            existing_ips = {ip_data['address'] for ip_data in ip_addresses}
            for discovered in discovered_hosts:
                if discovered['address'] not in existing_ips:
                    ip_addresses.append(discovered)
                    ips_by_network[network_str].append(discovered['address'])

        print(f"\n✓ Total IPs after discovery: {len(ip_addresses)}\n")

    # Continue with routing table integration
    if routing_tables:
        print(f"  ✓ Subnets: {len(routing_data['subnets'])}, Host IPs: {len(routing_data['host_ips'])}")

        # Add /32 host IPs with DNS lookup
        if routing_data['host_ips']:
            print("  🔍 Resolving hostnames via DNS...")
            for ip_str in routing_data['host_ips']:
                if ip_str not in {ip_data['address'] for ip_data in ip_addresses}:
                    hostname = reverse_dns_lookup(ip_str)
                    device_name = hostname if hostname else f'host-{ip_str}'

                    ip_addresses.append({
                        'address': ip_str,
                        'device_name': device_name,
                        'interface': None,
                        'discovered': True,
                        'source': 'routing_table'
                    })
            print(f"  ✓ Resolved {len(routing_data['host_ips'])} IPs\n")

    # Detect subnets
    subnets = set()
    for network_str, ips in ips_by_network.items():
        parent_network = ipaddress.ip_network(network_str)

        if network_str in NETWORKS_WITHOUT_SUBDIVISION:
            subnets.add(network_str)
            continue

        detected = detect_smaller_subnets(ips, parent_network)
        subnets.add(network_str)
        for subnet in detected:
            if subnet != network_str:
                subnets.add(subnet)

    # Add routing table subnets (with rules)
    for subnet_str in routing_data['subnets']:
        try:
            network = ipaddress.ip_network(subnet_str)

            # Skip loopback
            if str(network.network_address).startswith('127.'):
                continue

            # Skip forbidden prefix lengths
            if network.prefixlen in [25, 26, 27, 28]:
                continue

            # Skip subdivisions of special networks
            skip = False
            for no_sub_net in NETWORKS_WITHOUT_SUBDIVISION:
                parent = ipaddress.ip_network(no_sub_net)
                if network.subnet_of(parent) and network != parent:
                    skip = True
                    break

            if not skip:
                subnets.add(subnet_str)
        except ValueError:
            pass

    # Determine prefixes
    prefixes = set()
    for subnet in subnets:
        network = ipaddress.ip_network(subnet)
        if str(network.network_address).startswith('127.'):
            continue

        if network.network_address.packed[0] == 10:
            prefix = ipaddress.ip_network(f"{network.network_address}/8", strict=False)
        elif network.network_address.packed[0] == 192 and network.network_address.packed[1] == 168:
            prefix = ipaddress.ip_network(f"{network.network_address}/16", strict=False)
        else:
            prefix = ipaddress.ip_network(f"{network.network_address}/16", strict=False)

        prefixes.add(str(prefix))

    return {
        'prefixes': sorted(prefixes),
        'subnets': sorted(subnets),
        'ip_addresses': ip_addresses
    }


def get_or_create_prefix(prefix_str):
    """Get or create an IPAM prefix"""
    query = """
    query GetPrefix($prefix: String!) {
        JeylanIPAMPrefix(prefix__value: $prefix) {
            edges {
                node {
                    id
                }
            }
        }
    }
    """

    result = graphql_query(query, {"prefix": prefix_str})
    edges = result.get("JeylanIPAMPrefix", {}).get("edges", [])

    if edges:
        return edges[0]["node"]["id"]

    desc = f"Prefix {prefix_str}"
    mutation = """
    mutation CreatePrefix($prefix: String!, $description: String!) {
        JeylanIPAMPrefixCreate(
            data: {
                prefix: {value: $prefix}
                description: {value: $description}
                status: {value: "active"}
            }
        ) {
            ok
            object {
                id
            }
        }
    }
    """

    result = graphql_query(mutation, {"prefix": prefix_str, "description": desc})
    if result.get("JeylanIPAMPrefixCreate", {}).get("ok"):
        prefix_id = result["JeylanIPAMPrefixCreate"]["object"]["id"]
        print(f"  ✓ Created prefix {prefix_str}")
        return prefix_id
    else:
        raise Exception(f"Failed to create prefix {prefix_str}")


def get_or_create_subnet(subnet_str, prefix_id):
    """Get or create an IPAM subnet"""
    query = """
    query GetSubnet($subnet: String!) {
        JeylanIPAMSubnet(subnet__value: $subnet) {
            edges {
                node {
                    id
                }
            }
        }
    }
    """

    result = graphql_query(query, {"subnet": subnet_str})
    edges = result.get("JeylanIPAMSubnet", {}).get("edges", [])

    if edges:
        return edges[0]["node"]["id"]

    # Generate name
    network = ipaddress.ip_network(subnet_str)
    octets = str(network.network_address).split('.')

    if network.network_address.packed[0] == 192:
        name = f"jeylan{octets[2]}"
    elif network.network_address.packed[0] == 10:
        name = f"subnet-10.{octets[1]}.{octets[2]}"
    else:
        name = f"subnet-{network.network_address}"

    mutation = """
    mutation CreateSubnet($subnet: String!, $name: String!, $prefix_id: String!) {
        JeylanIPAMSubnetCreate(
            data: {
                subnet: {value: $subnet}
                name: {value: $name}
                status: {value: "active"}
                prefix: {id: $prefix_id}
            }
        ) {
            ok
            object {
                id
            }
        }
    }
    """

    result = graphql_query(mutation, {
        "subnet": subnet_str,
        "name": name,
        "prefix_id": prefix_id
    })

    if result.get("JeylanIPAMSubnetCreate", {}).get("ok"):
        subnet_id = result["JeylanIPAMSubnetCreate"]["object"]["id"]
        print(f"  ✓ Created subnet {subnet_str} ({name})")
        return subnet_id
    else:
        raise Exception(f"Failed to create subnet {subnet_str}")


def find_subnet_for_ip(ip_str, subnet_map):
    """Find the most specific subnet that contains an IP"""
    try:
        ip = ipaddress.ip_address(ip_str)
        candidates = []
        for subnet_str, subnet_id in subnet_map.items():
            network = ipaddress.ip_network(subnet_str)
            if ip in network:
                candidates.append((network, subnet_id))

        if candidates:
            candidates.sort(key=lambda x: x[0].prefixlen, reverse=True)
            return candidates[0][1]
        return None
    except ValueError:
        return None


def create_ip_address(ip_str, device_name, subnet_id, device_id=None):
    """Create an IP address in IPAM"""
    query = """
    query GetIP($address: String!) {
        JeylanIPAMIPAddress(address__value: $address) {
            edges {
                node {
                    id
                }
            }
        }
    }
    """

    result = graphql_query(query, {"address": ip_str})
    edges = result.get("JeylanIPAMIPAddress", {}).get("edges", [])

    if edges:
        print(f"    ℹ IP {ip_str} already exists")
        return False

    desc = f"{device_name} - Management IP"

    if device_id:
        mutation = """
        mutation CreateIPAddress($address: String!, $description: String!, $subnet_id: String!, $device_id: String!) {
            JeylanIPAMIPAddressCreate(
                data: {
                    address: {value: $address}
                    description: {value: $description}
                    status: {value: "active"}
                    subnet: {id: $subnet_id}
                    device: {id: $device_id}
                }
            ) {
                ok
                object {
                    id
                }
            }
        }
        """
        variables = {
            "address": ip_str,
            "description": desc,
            "subnet_id": subnet_id,
            "device_id": device_id
        }
    else:
        mutation = """
        mutation CreateIPAddress($address: String!, $description: String!, $subnet_id: String!) {
            JeylanIPAMIPAddressCreate(
                data: {
                    address: {value: $address}
                    description: {value: $description}
                    status: {value: "active"}
                    subnet: {id: $subnet_id}
                }
            ) {
                ok
                object {
                    id
                }
            }
        }
        """
        variables = {
            "address": ip_str,
            "description": desc,
            "subnet_id": subnet_id
        }

    result = graphql_query(mutation, variables)

    if result.get("JeylanIPAMIPAddressCreate", {}).get("ok"):
        print(f"  ✓ Created IP {ip_str} for {device_name}")
        return True
    else:
        print(f"  ✗ Failed to create IP {ip_str}")
        return False


def cmd_populate(args):
    """Populate IPAM from network data"""
    print("=" * 70)
    print("IPAM POPULATION".center(70))
    if args.scan and args.routing_tables:
        print("Mode: Inventory + Scan + Routing Tables".center(70))
    elif args.scan:
        print("Mode: Inventory + Network Scan".center(70))
    elif args.routing_tables:
        print("Mode: Inventory + Routing Tables".center(70))
    else:
        print("Mode: Inventory only".center(70))
    print("=" * 70)

    # Load inventory
    print("\n1️⃣  Loading LibreNMS inventory...")
    inventory = load_inventory()
    print(f"   ✓ {len(inventory.get('devices', []))} devices")

    # Analyze structure
    print("\n2️⃣  Analyzing network structure...")
    structure = analyze_network_structure(
        inventory,
        args.scan,
        args.routing_tables,
        args.workers
    )

    print(f"\n📊 Results:")
    print(f"   • Prefixes: {len(structure['prefixes'])}")
    print(f"   • Subnets: {len(structure['subnets'])}")
    print(f"   • IP Addresses: {len(structure['ip_addresses'])}")

    # Show subnet breakdown
    subnet_sizes = {}
    for subnet in structure['subnets']:
        size = subnet.split('/')[1]
        subnet_sizes[size] = subnet_sizes.get(size, 0) + 1

    print(f"\n   Subnet breakdown:")
    for size in sorted(subnet_sizes.keys(), key=lambda x: int(x)):
        print(f"     /{size}: {subnet_sizes[size]} subnets")

    # Create prefixes
    print(f"\n3️⃣  Creating/updating prefixes...")
    prefix_map = {}
    for prefix_str in structure['prefixes']:
        prefix_id = get_or_create_prefix(prefix_str)
        prefix_map[prefix_str] = prefix_id

    # Create subnets
    print(f"\n4️⃣  Creating/updating subnets...")
    subnet_map = {}

    for subnet_str in structure['subnets']:
        network = ipaddress.ip_network(subnet_str)

        # Find parent prefix
        prefix_id = None
        for prefix_str, pid in prefix_map.items():
            prefix_net = ipaddress.ip_network(prefix_str)
            if network.subnet_of(prefix_net):
                prefix_id = pid
                break

        if prefix_id:
            subnet_id = get_or_create_subnet(subnet_str, prefix_id)
            subnet_map[subnet_str] = subnet_id

    # Create IPs
    print(f"\n5️⃣  Creating/updating IP addresses...")
    created_count = 0
    existing_count = 0
    skipped_count = 0

    for ip_data in structure['ip_addresses']:
        ip_str = ip_data['address']
        device_name = ip_data['device_name']

        subnet_id = find_subnet_for_ip(ip_str, subnet_map)

        if not subnet_id:
            print(f"  ⚠ No subnet found for IP {ip_str}")
            skipped_count += 1
            continue

        created = create_ip_address(ip_str, device_name, subnet_id)
        if created:
            created_count += 1
        else:
            existing_count += 1

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY".center(70))
    print("=" * 70)
    print(f"  Prefixes: {len(structure['prefixes'])}")
    print(f"  Subnets: {len(structure['subnets'])}")
    print(f"  IP Addresses:")
    print(f"    - Created: {created_count}")
    print(f"    - Already existing: {existing_count}")
    print(f"    - Skipped (no subnet): {skipped_count}")
    print("=" * 70)


# ============================================================================
# COMMAND: hierarchy
# ============================================================================

def get_all_subnets():
    """Fetch all subnets from Infrahub"""
    query = """
    {
      JeylanIPAMSubnet {
        edges {
          node {
            id
            subnet { value }
            subnet_type { value }
          }
        }
      }
    }
    """

    data = graphql_query(query)
    subnets = []

    for edge in data.get("JeylanIPAMSubnet", {}).get("edges", []):
        node = edge["node"]
        subnets.append({
            "id": node["id"],
            "subnet": node["subnet"]["value"],
            "subnet_type": node.get("subnet_type", {}).get("value", "parent")
        })

    return subnets


def set_subnet_type(subnet_id, subnet_type):
    """Set the subnet_type attribute"""
    mutation = """
    mutation UpdateSubnetType($id: String!, $type: String!) {
      JeylanIPAMSubnetUpdate(
        data: {
          id: $id
          subnet_type: {value: $type}
        }
      ) {
        ok
      }
    }
    """

    result = graphql_query(mutation, {"id": subnet_id, "type": subnet_type})
    return result.get("JeylanIPAMSubnetUpdate", {}).get("ok", False)


def set_child_subnets(parent_id, child_ids):
    """Set child subnets from parent side"""
    mutation = """
    mutation SetChildSubnets($parent_id: String!, $child_ids: [String!]!) {
      JeylanIPAMSubnetUpdate(
        data: {
          id: $parent_id
          child_subnets: $child_ids
        }
      ) {
        ok
      }
    }
    """

    result = graphql_query(mutation, {
        "parent_id": parent_id,
        "child_ids": [{"id": cid} for cid in child_ids]
    })
    return result.get("JeylanIPAMSubnetUpdate", {}).get("ok", False)


def clear_parent_subnet(subnet_id):
    """Clear the parent_subnet relationship"""
    mutation = """
    mutation ClearParent($id: String!) {
      JeylanIPAMSubnetUpdate(
        data: {
          id: $id
          parent_subnet: null
        }
      ) {
        ok
      }
    }
    """

    result = graphql_query(mutation, {"id": subnet_id})
    return result.get("JeylanIPAMSubnetUpdate", {}).get("ok", False)


def get_all_ips():
    """Fetch all IP addresses"""
    query = """
    {
      JeylanIPAMIPAddress {
        edges {
          node {
            id
            address { value }
            subnet {
              node {
                id
                subnet { value }
              }
            }
          }
        }
      }
    }
    """

    data = graphql_query(query)
    ips = []

    for edge in data.get("JeylanIPAMIPAddress", {}).get("edges", []):
        node = edge["node"]
        current_subnet = node.get("subnet", {}).get("node")

        ips.append({
            "id": node["id"],
            "address": node["address"]["value"],
            "current_subnet_id": current_subnet["id"] if current_subnet else None,
            "current_subnet": current_subnet["subnet"]["value"] if current_subnet else None
        })

    return ips


def update_ip_subnet(ip_id, subnet_id):
    """Update IP address subnet relationship"""
    mutation = """
    mutation UpdateIPSubnet($ip_id: String!, $subnet_id: String!) {
      JeylanIPAMIPAddressUpdate(
        data: {
          id: $ip_id
          subnet: {id: $subnet_id}
        }
      ) {
        ok
      }
    }
    """

    result = graphql_query(mutation, {"ip_id": ip_id, "subnet_id": subnet_id})
    return result.get("JeylanIPAMIPAddressUpdate", {}).get("ok", False)


def cmd_hierarchy_types(args):
    """Set subnet types (parent/child)"""
    print("\n🏷️  Setting subnet types...")

    subnets = get_all_subnets()
    parents = 0
    children = 0

    for subnet_data in subnets:
        subnet_str = subnet_data["subnet"]
        network = ipaddress.ip_network(subnet_str)

        # Determine type based on prefix length
        if network.prefixlen in [29, 30]:
            subnet_type = "child"
            children += 1
        else:
            subnet_type = "parent"
            parents += 1

        # Update if different
        if subnet_data.get("subnet_type") != subnet_type:
            set_subnet_type(subnet_data["id"], subnet_type)
            print(f"  ✓ {subnet_str} → {subnet_type}")

    print(f"\n✓ Set {parents} parents and {children} children")


def cmd_hierarchy_subnets(args):
    """Apply subnet parent-child relationships"""
    print("\n🔗 Applying subnet hierarchy...")

    subnets = get_all_subnets()
    subnet_map = {s["subnet"]: s for s in subnets}

    # Build parent-children mapping
    parent_children = {}

    for child_data in subnets:
        child_network = ipaddress.ip_network(child_data["subnet"])

        # Skip if not a child type
        if child_network.prefixlen not in [29, 30]:
            continue

        # Find parent /24
        for parent_data in subnets:
            parent_network = ipaddress.ip_network(parent_data["subnet"])

            # Must be different subnet and child must be subset of parent
            if (parent_data["subnet"] != child_data["subnet"] and
                child_network.subnet_of(parent_network)):

                parent_subnet = parent_data["subnet"]
                if parent_subnet not in parent_children:
                    parent_children[parent_subnet] = []
                parent_children[parent_subnet].append(child_data["id"])
                break

    # Apply relationships from parent side
    created = 0
    for parent_subnet, child_ids in parent_children.items():
        parent_data = subnet_map[parent_subnet]

        if set_child_subnets(parent_data["id"], child_ids):
            print(f"  ✓ {parent_subnet} → {len(child_ids)} children")
            created += 1

    print(f"\n✓ Created {created} parent-child relationships")


def cmd_hierarchy_ips(args):
    """Link IP addresses to most specific subnets"""
    print("\n📍 Linking IP addresses to subnets...")

    subnets = get_all_subnets()
    ips = get_all_ips()

    updated = 0
    already_correct = 0

    for ip_data in ips:
        ip_addr = ipaddress.ip_address(ip_data["address"])

        # Find most specific subnet
        candidates = []
        for subnet_data in subnets:
            subnet_network = ipaddress.ip_network(subnet_data["subnet"])
            if ip_addr in subnet_network:
                candidates.append((subnet_network, subnet_data))

        if not candidates:
            print(f"  ⚠ No subnet found for {ip_data['address']}")
            continue

        # Sort by prefix length (most specific first)
        candidates.sort(key=lambda x: x[0].prefixlen, reverse=True)
        most_specific_subnet = candidates[0][1]

        # Update if different
        if ip_data["current_subnet_id"] != most_specific_subnet["id"]:
            if update_ip_subnet(ip_data["id"], most_specific_subnet["id"]):
                old = ip_data["current_subnet"] or "none"
                new = most_specific_subnet["subnet"]
                print(f"  ✓ {ip_data['address']}: {old} → {new}")
                updated += 1
        else:
            already_correct += 1

    print(f"\n✓ Updated {updated} IPs, {already_correct} already correct")


def cmd_hierarchy_reset(args):
    """Clear all parent subnet relationships"""
    print("\n🔄 Resetting subnet hierarchy...")

    subnets = get_all_subnets()
    cleared = 0

    for subnet_data in subnets:
        if clear_parent_subnet(subnet_data["id"]):
            cleared += 1

    print(f"✓ Cleared {cleared} parent relationships")


def cmd_hierarchy_setup(args):
    """Complete hierarchy setup (types + subnets + ips)"""
    print("=" * 70)
    print("HIERARCHY SETUP".center(70))
    print("=" * 70)

    cmd_hierarchy_types(args)
    cmd_hierarchy_subnets(args)
    cmd_hierarchy_ips(args)

    print("\n" + "=" * 70)
    print("✓ Hierarchy setup complete")
    print("=" * 70)


def cmd_hierarchy(args):
    """Handle hierarchy subcommands"""
    if args.hierarchy_command == 'status':
        cmd_status(args)
    elif args.hierarchy_command == 'setup':
        cmd_hierarchy_setup(args)
    elif args.hierarchy_command == 'types':
        cmd_hierarchy_types(args)
    elif args.hierarchy_command == 'subnets':
        cmd_hierarchy_subnets(args)
    elif args.hierarchy_command == 'ips':
        cmd_hierarchy_ips(args)
    elif args.hierarchy_command == 'reset':
        cmd_hierarchy_reset(args)
    else:
        print("Unknown hierarchy command. Use: status, setup, types, subnets, ips, or reset")
        sys.exit(1)


# ============================================================================
# Main CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Status command
    status_parser = subparsers.add_parser('status', help='Show IPAM status')
    status_parser.add_argument('--detailed', action='store_true',
                              help='Show detailed inventory')

    # Populate command
    populate_parser = subparsers.add_parser('populate', help='Populate IPAM from network data')
    populate_parser.add_argument('--scan', action='store_true',
                                help='Enable network scan (ping)')
    populate_parser.add_argument('--workers', type=int, default=50,
                                help='Number of workers for scanning (default: 50)')
    populate_parser.add_argument('--routing-tables', nargs='*',
                                help='Routing table files to parse')

    # Hierarchy command
    hierarchy_parser = subparsers.add_parser('hierarchy', help='Manage subnet hierarchy')
    hierarchy_subparsers = hierarchy_parser.add_subparsers(
        dest='hierarchy_command',
        help='Hierarchy operations'
    )
    hierarchy_subparsers.add_parser('status', help='Show hierarchy status')
    hierarchy_subparsers.add_parser('setup', help='Complete hierarchy setup')
    hierarchy_subparsers.add_parser('types', help='Set subnet types')
    hierarchy_subparsers.add_parser('subnets', help='Apply parent-child relationships')
    hierarchy_subparsers.add_parser('ips', help='Link IPs to subnets')
    hierarchy_subparsers.add_parser('reset', help='Clear all parent relationships')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        if args.command == 'status':
            if args.detailed:
                cmd_status_detailed(args)
            else:
                cmd_status(args)
        elif args.command == 'populate':
            cmd_populate(args)
        elif args.command == 'hierarchy':
            cmd_hierarchy(args)
        else:
            parser.print_help()
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
