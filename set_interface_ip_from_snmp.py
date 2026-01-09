#!/usr/bin/env python3
import ipam
import time
import re


def main(community=None, verbose=True):
    community = community or ipam.SNMP_COMMUNITY

    # Get devices with mgmt_ip
    q = '''
    {
      JeylanDevice {
        edges {
          node {
            id
            name { value }
            mgmt_ip { value }
          }
        }
      }
    }
    '''
    data = ipam.graphql_query(q)
    devices = []
    for edge in data.get('JeylanDevice', {}).get('edges', []):
        node = edge['node']
        mgmt = node.get('mgmt_ip', {}).get('value')
        if mgmt:
            devices.append({'id': node['id'], 'name': node['name']['value'], 'mgmt_ip': mgmt})

    updated = 0
    for dev in devices:
        name = dev['name']
        ip = dev['mgmt_ip']
        if verbose:
            print(f"Querying SNMP on {name} ({ip})")

        snmp_ifaces = ipam.get_snmp_interfaces(ip, community)
        if not snmp_ifaces:
            if verbose:
                print(f"  No SNMP data for {name}")
            continue

        # Get current Infrahub interfaces for device
        q_dev_if = '''
        query GetDeviceInterfaces($device_name: String!) {
            JeylanDevice(name__value: $device_name) {
                edges { node { interfaces { edges { node { id name { value } ip_address { value } } } } } }
            }
        }
        '''
        res = ipam.graphql_query(q_dev_if, {'device_name': name})
        edges = res.get('JeylanDevice', {}).get('edges', [])
        if not edges:
            if verbose:
                print(f"  No device record for {name}")
            continue
        inf_interfaces = edges[0]['node'].get('interfaces', {}).get('edges', [])
        # Map by interface name -> id
        iface_map = {iface['node']['name']['value']: iface['node']['id'] for iface in inf_interfaces}
        # Also build a normalized name map to improve matching across vendors

        def normalize_name(n: str) -> str:
            s = n.lower()
            # common canonical replacements
            reps = {
                'gigabitethernet': 'gi',
                'ten': '10',
                'fastethernet': 'fa',
                'ethernet': 'eth',
                'vlan': 'vl',
                'loopback': 'lo',
                'management': 'mgmt',
                'port-channel': 'po',
                'ae': 'ae',
                'ge-': 'ge',
            }
            for k, v in reps.items():
                s = s.replace(k, v)
            # remove non-alphanumeric
            s = re.sub(r'[^0-9a-z]', '', s)
            return s

        normalized_map = {}
        for name, iid in iface_map.items():
            normalized_map[normalize_name(name)] = iid
        # For each SNMP interface, set ip_address on matching Infrahub interface
        for ifindex, snmp_data in snmp_ifaces.items():
            ifname = snmp_data['name']
            for ip_addr in snmp_data['ips']:
                # try exact match
                iface_id = iface_map.get(ifname)
                if not iface_id:
                    # try normalized matching
                    nid = normalize_name(ifname)
                    iface_id = normalized_map.get(nid)
                if not iface_id:
                    # try short variants (last part) and normalized short
                    short = ifname.split('/')[-1]
                    iface_id = iface_map.get(short) or normalized_map.get(normalize_name(short))

                if not iface_id:
                    if verbose:
                        print(f"  Interface {ifname} not found in Infrahub for {name}")
                    continue

                # Update mutation
                mut = '''
                mutation UpdateInterface($id: String!, $ip: String!) {
                  JeylanInterfacesUpdate(
                    data: {
                      id: $id
                      ip_address: {value: $ip}
                    }
                  ) { ok }
                }
                '''
                vars = {'id': iface_id, 'ip': ip_addr}
                try:
                    r = ipam.graphql_query(mut, vars)
                    ok = r.get('JeylanInterfacesUpdate', {}).get('ok', False)
                    if ok:
                        updated += 1
                        if verbose:
                            print(f"  Set {ip_addr} on {name} / {ifname}")
                    else:
                        if verbose:
                            print(f"  Failed to set {ip_addr} on {name} / {ifname}")
                except Exception as e:
                    if verbose:
                        print(f"  Error updating interface: {e}")

        # be gentle
        time.sleep(0.2)

    print(f"Done. Interfaces updated: {updated}")


if __name__ == '__main__':
    main()
