#!/usr/bin/env python3
"""Test SNMP configuration on a single Juniper device"""

import os
import sys
from netmiko import ConnectHandler

USERNAME = os.getenv('NETWORK_USER', 'jeyriku')
PASSWORD = os.getenv('NETWORK_PASSWORD')

if not PASSWORD:
    print("❌ NETWORK_PASSWORD not set")
    sys.exit(1)

DEVICE_IP = "10.0.0.2"
INFRAHUB_IP = "192.168.0.237"
SNMP_COMMUNITY = "jeyricorp"

try:
    device = {
        'device_type': 'juniper_junos',
        'ip': DEVICE_IP,
        'username': USERNAME,
        'password': PASSWORD,
        'timeout': 30,
        'global_delay_factor': 2,
    }

    print(f"🔄 Connexion à {DEVICE_IP}...")
    connection = ConnectHandler(**device)
    print(f"✅ Connecté!")

    # Check current config
    print("📋 Configuration SNMP actuelle:")
    current = connection.send_command("show configuration snmp", read_timeout=15)
    print(current[:300])

    if INFRAHUB_IP in current:
        print(f"\n✅ IP {INFRAHUB_IP} déjà présente!")
    else:
        print(f"\n🔧 Configuration en cours...")

        # Enter config mode
        connection.config_mode()

        # Send command
        cmd = f'set snmp community {SNMP_COMMUNITY} clients {INFRAHUB_IP}/32'
        print(f"📝 Commande: {cmd}")
        output = connection.send_config_set([cmd])
        print(f"Output: {output[:200]}")

        # Commit
        print("💾 Commit...")
        commit_output = connection.commit()
        print(f"Commit output: {commit_output[:200]}")

        # Exit config mode
        connection.exit_config_mode()

        # Verify
        print("\n🔍 Vérification:")
        verify = connection.send_command("show configuration snmp", read_timeout=15)
        if INFRAHUB_IP in verify:
            print(f"✅ Configuration réussie!")
            print(verify[:500])
        else:
            print(f"❌ Vérification échouée")
            print(verify)

    connection.disconnect()
    print("\n✅ Test terminé avec succès!")

except Exception as e:
    print(f"\n❌ Erreur: {str(e)}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
