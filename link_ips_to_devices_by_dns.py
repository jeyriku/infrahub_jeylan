#!/usr/bin/env python3
import requests
import socket
import json

INFRAHUB_URL = "http://127.0.0.1:8000"
API_TOKEN = "188600a3-6e17-9f97-339f-c516618aa3c0"
HEADERS = {
    "Content-Type": "application/json",
    "X-INFRAHUB-KEY": API_TOKEN
}


def graphql(query, variables=None):
    r = requests.post(f"{INFRAHUB_URL}/graphql/main", headers=HEADERS, json={"query": query, "variables": variables or {}})
    r.raise_for_status()
    data = r.json()
    if 'errors' in data:
        raise Exception(data['errors'])
    return data.get('data', {})


def reverse_dns(ip):
    try:
        name, _, _ = socket.gethostbyaddr(ip)
        return name
    except Exception:
        return None


def main():
    # Build device map: full name and short name -> id
    q_devices = '''
    {
      JeylanDevice {
        edges {
          node {
            id
            name { value }
          }
        }
      }
    }
    '''
    data = graphql(q_devices)
    devices = {}
    for edge in data.get('JeylanDevice', {}).get('edges', []):
        node = edge['node']
        name = node['name']['value']
        dev_id = node['id']
        devices[name] = dev_id
        short = name.split('.')[0]
        devices[short] = dev_id

    # Fetch IPs
    q_ips = '''
    {
      JeylanIPAMIPAddress {
        edges {
          node {
            id
            address { value }
            hostname { value }
            device { node { id name { value } } }
          }
        }
      }
    }
    '''

    data = graphql(q_ips)
    edges = data.get('JeylanIPAMIPAddress', {}).get('edges', [])

    updated = 0
    for edge in edges:
        node = edge['node']
        ip_id = node['id']
        ip = node['address']['value']
        hostname = node.get('hostname', {}).get('value') if node.get('hostname') else None
        device_node = node.get('device', {}).get('node') if node.get('device') else None

        if device_node:
            continue  # already linked

        candidates = []
        # try hostname first
        if hostname:
            candidates.append(hostname)
            candidates.append(hostname.split('.')[0])

        # try reverse DNS
        if not candidates:
            rd = reverse_dns(ip)
            if rd:
                candidates.append(rd)
                candidates.append(rd.split('.')[0])

        found_dev = None
        for cand in candidates:
            if cand in devices:
                found_dev = devices[cand]
                break

        if found_dev:
            mut = '''
            mutation UpdateIPDevice($id: String!, $device_id: String!) {
              JeylanIPAMIPAddressUpdate(
                data: {
                  id: $id
                  device: {id: $device_id}
                }
              ) { ok }
            }
            '''
            vars = {"id": ip_id, "device_id": found_dev}
            try:
                res = graphql(mut, vars)
                ok = res.get('JeylanIPAMIPAddressUpdate', {}).get('ok', False)
                if ok:
                    print(f"Linked {ip} -> device id {found_dev}")
                    updated += 1
            except Exception as e:
                print(f"Failed to link {ip}: {e}")

    print(f"Done. Updated: {updated}")


if __name__ == '__main__':
    main()
