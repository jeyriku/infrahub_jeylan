#!/usr/bin/env python3
"""
Script pour configurer SNMP sur les devices Juniper JunOS.
Ajoute l'IP 192.168.0.237 (jeysrv10) à la client-list SNMP.
"""

import os
import sys
from netmiko import ConnectHandler
from concurrent.futures import ThreadPoolExecutor, as_completed

# Credentials depuis variables d'environnement
USERNAME = os.getenv('NETWORK_USER', 'jeyriku')
PASSWORD = os.getenv('NETWORK_PASSWORD')

if not PASSWORD:
    print("❌ NETWORK_PASSWORD not set in environment")
    sys.exit(1)

# IP à ajouter à SNMP
INFRAHUB_IP = "192.168.0.237"
SNMP_COMMUNITY = "jeyricorp"

# Liste des devices Juniper
JUNIPER_DEVICES = [
    # Routeurs SRX PE
    ("10.0.0.1", "jey-srx3x-pe-01"),
    ("10.0.0.2", "jey-srx3x-pe-02"),
    ("10.0.0.3", "jey-srx3x-pe-03"),
    ("10.0.0.4", "jey-srx3x-pe-04"),
    ("10.0.0.5", "jey-srx3x-pe-05"),
    # Route Reflectors SRX
    ("10.0.0.11", "jey-srx3x-rr-01"),
    ("10.0.0.12", "jey-srx3x-rr-02"),
    # Routeur CE SRX
    ("10.0.1.1", "jey-srx3x-ce-01"),
    # Switch Juniper EX
    ("192.168.0.254", "jey-ex23k-sw-01"),
]


def configure_junos_snmp(device_ip, device_name, username, password):
    """Configure SNMP on Juniper device"""
    try:
        device = {
            'device_type': 'juniper_junos',
            'ip': device_ip,
            'username': username,
            'password': password,
            'timeout': 15,
            'session_log': f'/tmp/junos_snmp_{device_ip}.log'
        }

        print(f"🔄 Connexion à {device_name} ({device_ip})...")
        connection = ConnectHandler(**device)

        # Check current SNMP configuration
        output = connection.send_command("show configuration snmp", read_timeout=10)

        if INFRAHUB_IP in output:
            print(f"   ✅ {device_name} - SNMP déjà configuré")
            connection.disconnect()
            return True, device_name, "Already configured"

        # Enter configuration mode
        print(f"   🔧 Configuration de {device_name}...")
        connection.config_mode()

        # Configure SNMP avec la syntaxe JunOS
        cmd = f'set snmp community {SNMP_COMMUNITY} clients {INFRAHUB_IP}/32'
        connection.send_config_set([cmd])

        # Commit
        print(f"   💾 Commit en cours...")
        output = connection.commit()

        # Exit configuration mode
        connection.exit_config_mode()

        # Verify configuration
        verify = connection.send_command("show configuration snmp", read_timeout=10)

        connection.disconnect()

        if INFRAHUB_IP in verify:
            print(f"   ✅ {device_name} - Configuration réussie et commitée")
            return True, device_name, "Success"
        else:
            print(f"   ❌ {device_name} - Vérification échouée")
            return False, device_name, "Verification failed"

    except Exception as e:
        print(f"   ❌ {device_name} ({device_ip}) - Erreur: {str(e)[:100]}")
        return False, device_name, str(e)


def main():
    print("=" * 70)
    print("Configuration SNMP sur devices Juniper Jeylan".center(70))
    print(f"Ajout de l'IP {INFRAHUB_IP} à la client-list SNMP".center(70))
    print("=" * 70)
    print()

    results = {
        'success': [],
        'already_configured': [],
        'failed': []
    }

    print(f"📡 Configuration de {len(JUNIPER_DEVICES)} devices Juniper...\n")

    # Process devices with limited concurrency
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {}

        for device_ip, device_name in JUNIPER_DEVICES:
            future = executor.submit(
                configure_junos_snmp,
                device_ip,
                device_name,
                USERNAME,
                PASSWORD
            )
            futures[future] = (device_ip, device_name)

        for future in as_completed(futures):
            device_ip, device_name = futures[future]
            try:
                success, hostname, message = future.result()

                if success:
                    if "Already" in message:
                        results['already_configured'].append((hostname, device_ip))
                    else:
                        results['success'].append((hostname, device_ip))
                else:
                    results['failed'].append((device_name, device_ip, message))

            except Exception as e:
                results['failed'].append((device_name, device_ip, str(e)))

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
        for device_name, device_ip, reason in results['failed']:
            print(f"   • {device_name} ({device_ip}): {reason[:80]}")

    print("\n" + "=" * 70)
    total = len(results['success']) + len(results['already_configured'])
    print(f"✨ Total configuré: {total}/{len(JUNIPER_DEVICES)} devices")
    print("=" * 70)

    # Verification command
    print("\n📝 Test SNMP depuis jeysrv10:")
    print(f"   snmpwalk -v2c -c {SNMP_COMMUNITY} <DEVICE_IP> ifName")


if __name__ == "__main__":
    main()
