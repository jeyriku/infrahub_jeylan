#!/usr/bin/env python3
"""
Script de test pour configurer l'ACL SNMP sur UN device.
"""

import os
import sys
from netmiko import ConnectHandler

USERNAME = os.getenv('NETWORK_USER', 'jeyriku')
PASSWORD = os.getenv('NETWORK_PASSWORD')
INFRAHUB_IP = "192.168.0.237"

if not PASSWORD:
    print("❌ NETWORK_PASSWORD not set")
    sys.exit(1)

# Test avec un seul device
TEST_DEVICE = "10.0.0.1"  # jey-srx3x-pe-01

def test_cisco():
    try:
        device = {
            'device_type': 'cisco_ios',
            'ip': TEST_DEVICE,
            'username': USERNAME,
            'password': PASSWORD,
            'timeout': 10,
        }

        print(f"🔄 Test connexion à {TEST_DEVICE}...")
        connection = ConnectHandler(**device)

        hostname = connection.find_prompt().strip('#>')
        print(f"   ✅ Connecté à {hostname}")

        # Check current ACL
        print(f"\n📋 ACL 18 actuelle:")
        output = connection.send_command("show access-lists 18")
        print(output)

        if INFRAHUB_IP in output:
            print(f"\n   ✅ {INFRAHUB_IP} déjà dans l'ACL")
        else:
            print(f"\n   ⚠️  {INFRAHUB_IP} pas dans l'ACL")

            response = input("\n❓ Voulez-vous ajouter l'IP ? (y/n): ")
            if response.lower() == 'y':
                print("\n🔧 Configuration en cours...")
                commands = [
                    'configure terminal',
                    f'access-list 18 permit {INFRAHUB_IP}',
                    'end'
                ]
                output = connection.send_config_set(commands)
                print(output)

                print("\n📋 Vérification:")
                verify = connection.send_command("show access-lists 18")
                print(verify)

                if INFRAHUB_IP in verify:
                    print("\n✅ Configuration réussie!")

                    response = input("\n❓ Sauvegarder (write memory) ? (y/n): ")
                    if response.lower() == 'y':
                        connection.send_command("write memory")
                        print("✅ Configuration sauvegardée")
                else:
                    print("\n❌ Configuration échouée")

        connection.disconnect()

    except Exception as e:
        print(f"❌ Erreur: {e}")
        sys.exit(1)

if __name__ == "__main__":
    print("=" * 70)
    print(f"Test SNMP ACL - Device: {TEST_DEVICE}".center(70))
    print("=" * 70)
    test_cisco()
