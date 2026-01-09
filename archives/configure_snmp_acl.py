#!/usr/bin/env python3
"""
Script pour configurer l'ACL SNMP sur tous les devices Cisco et Junos.
Ajoute l'IP 192.168.0.237 (jeysrv10) à l'ACL 18 existante.
"""

import os
import sys
from netmiko import ConnectHandler
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Credentials depuis variables d'environnement
USERNAME = os.getenv('NETWORK_USER', 'jeyriku')
PASSWORD = os.getenv('NETWORK_PASSWORD')

if not PASSWORD:
    print("❌ NETWORK_PASSWORD not set in environment")
    sys.exit(1)

# IP à ajouter à l'ACL
INFRAHUB_IP = "192.168.0.237"

# Liste des devices Cisco
CISCO_DEVICES = [
    # Routeurs PE
    "10.0.0.1",   # jey-srx3x-pe-01
    "10.0.0.2",   # jey-srx3x-pe-02
    "10.0.0.3",   # jey-srx3x-pe-03
    "10.0.0.4",   # jey-srx3x-pe-04
    "10.0.0.5",   # jey-srx3x-pe-05
    "10.0.0.21",  # jey-isr1k-pe-01
    "10.0.0.22",  # jey-isr1k-pe-02
    "10.0.0.31",  # jey-isr8x-pe-01
    "10.0.0.41",  # jey-isr4k-pe-01
    # Route Reflectors
    "10.0.0.11",  # jey-srx3x-rr-01
    "10.0.0.12",  # jey-srx3x-rr-02
    # Routeurs CE
    "10.0.1.1",   # jey-srx3x-ce-01
    "10.0.1.11",  # jey-isr1k-ce-01
    "10.0.1.12",  # jey-isr1k-ce-02
    "10.0.1.13",  # jey-isr1k-ce-03
]

# Switches (certains peuvent être Cisco, d'autres non)
SWITCH_DEVICES = [
    "192.168.0.64",   # jey-c1000-sw-01
    "192.168.0.60",   # jey-c2960-sw-01
    "192.168.0.61",   # jey-c2960-sw-02
    "192.168.0.62",   # jey-c2960-sw-03
    "192.168.0.63",   # jey-c2960-sw-04
    "192.168.10.6",   # jey-c2960-sw-05
    "192.168.0.67",   # jey-cbs220-sw-01
    "192.168.0.66",   # jey-c1200-sw-01
    "192.168.0.68",   # jey-c1200-sw-02
    "192.168.0.254",  # jey-ex23k-sw-01 (Juniper)
]

def configure_cisco_snmp(device_ip, username, password):
    """Configure SNMP ACL on Cisco device"""
    try:
        device = {
            'device_type': 'cisco_ios',
            'ip': device_ip,
            'username': username,
            'password': password,
            'timeout': 10,
            'session_log': f'/tmp/cisco_snmp_{device_ip}.log'
        }

        print(f"🔄 Connexion à {device_ip}...")
        connection = ConnectHandler(**device)

        # Get hostname
        hostname = connection.find_prompt().strip('#>')

        # Check current ACL 18
        output = connection.send_command("show access-lists 18")

        if INFRAHUB_IP in output:
            print(f"   ✅ {hostname} ({device_ip}) - ACL déjà configurée")
            connection.disconnect()
            return True, hostname, "Already configured"

        # Configure ACL
        commands = [
            'configure terminal',
            f'access-list 18 permit {INFRAHUB_IP}',
            'end',
            'write memory'
        ]

        output = connection.send_config_set(commands)

        # Verify
        verify = connection.send_command("show access-lists 18")

        connection.disconnect()

        if INFRAHUB_IP in verify:
            print(f"   ✅ {hostname} ({device_ip}) - Configuration réussie")
            return True, hostname, "Success"
        else:
            print(f"   ❌ {hostname} ({device_ip}) - Vérification échouée")
            return False, hostname, "Verification failed"

    except Exception as e:
        print(f"   ❌ {device_ip} - Erreur: {str(e)}")
        return False, device_ip, str(e)

def configure_junos_snmp(device_ip, username, password):
    """Configure SNMP on Juniper device"""
    try:
        device = {
            'device_type': 'juniper_junos',
            'ip': device_ip,
            'username': username,
            'password': password,
            'timeout': 10,
        }

        print(f"🔄 Connexion à {device_ip} (Juniper)...")
        connection = ConnectHandler(**device)

        # Get hostname
        hostname = connection.find_prompt().strip('#>')

        # Check current SNMP configuration
        output = connection.send_command("show configuration snmp")

        if INFRAHUB_IP in output:
            print(f"   ✅ {hostname} ({device_ip}) - SNMP déjà configuré")
            connection.disconnect()
            return True, hostname, "Already configured"

        # Configure SNMP client-list
        commands = [
            'configure',
            f'set snmp client-list jeyricorp {INFRAHUB_IP}/32',
            'commit',
            'exit'
        ]

        for cmd in commands:
            connection.send_command(cmd, expect_string=r'[#>]')

        connection.disconnect()

        print(f"   ✅ {hostname} ({device_ip}) - Configuration Juniper réussie")
        return True, hostname, "Success"

    except Exception as e:
        print(f"   ⚠️  {device_ip} - Peut-être pas un Juniper: {str(e)}")
        return False, device_ip, str(e)

def main():
    print("=" * 70)
    print("Configuration SNMP ACL sur devices Jeylan".center(70))
    print(f"Ajout de l'IP {INFRAHUB_IP} à l'ACL 18".center(70))
    print("=" * 70)
    print()

    results = {
        'success': [],
        'already_configured': [],
        'failed': []
    }

    all_devices = CISCO_DEVICES + SWITCH_DEVICES

    print(f"📡 Configuration de {len(all_devices)} devices...\n")

    # Process devices with limited concurrency to avoid overwhelming network
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}

        for device_ip in all_devices:
            # Try Cisco first for all devices
            future = executor.submit(configure_cisco_snmp, device_ip, USERNAME, PASSWORD)
            futures[future] = (device_ip, 'cisco')

        for future in as_completed(futures):
            device_ip, device_type = futures[future]
            try:
                success, hostname, message = future.result()

                if success:
                    if "Already" in message:
                        results['already_configured'].append((hostname, device_ip))
                    else:
                        results['success'].append((hostname, device_ip))
                else:
                    # If Cisco failed and device is in SWITCH_DEVICES, try Juniper
                    if device_ip in SWITCH_DEVICES and "254" in device_ip:
                        print(f"   🔄 Tentative Juniper pour {device_ip}...")
                        success_j, hostname_j, message_j = configure_junos_snmp(device_ip, USERNAME, PASSWORD)
                        if success_j:
                            if "Already" in message_j:
                                results['already_configured'].append((hostname_j, device_ip))
                            else:
                                results['success'].append((hostname_j, device_ip))
                        else:
                            results['failed'].append((device_ip, message_j))
                    else:
                        results['failed'].append((device_ip, message))

            except Exception as e:
                results['failed'].append((device_ip, str(e)))

    # Summary
    print("\n" + "=" * 70)
    print("📊 RAPPORT FINAL")
    print("=" * 70)

    if results['success']:
        print(f"\n✅ Configurés avec succès ({len(results['success'])}):")
        for hostname, ip in results['success']:
            print(f"   • {hostname} ({ip})")

    if results['already_configured']:
        print(f"\n⏭️  Déjà configurés ({len(results['already_configured'])}):")
        for hostname, ip in results['already_configured']:
            print(f"   • {hostname} ({ip})")

    if results['failed']:
        print(f"\n❌ Échecs ({len(results['failed'])}):")
        for device, reason in results['failed']:
            print(f"   • {device}: {reason}")

    print("\n" + "=" * 70)
    total = len(results['success']) + len(results['already_configured'])
    print(f"✨ Total configuré: {total}/{len(all_devices)} devices")
    print("=" * 70)

if __name__ == "__main__":
    main()
