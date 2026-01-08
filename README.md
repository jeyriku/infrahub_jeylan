# Infrahub Jeylan - Configuration IPAM

Projet de gestion IPAM avec hiérarchie parent-enfant des subnets dans Infrahub.

## 📁 Structure du projet

### Fichiers essentiels

- **ipam_schema.yml** - Schéma complet Jeylan incluant tous les nœuds (Device, Model, Interfaces, Manufacturer, OSVersion, IPAM, Location, Routing, DeviceType, DeviceRole) avec les extensions de hiérarchie IPAM (subnet_type, parent_subnet, child_subnets)
- **ipam.py** - Outil unifié de gestion IPAM (40K, voir section Commandes)
- **reset_infrahub.sh** - Réinitialise l'instance Infrahub
- **README.md** - Cette documentation complète

## 🎯 État actuel de l'IPAM

Déploiement réussi avec hiérarchie complète :

- **Prefixes** : 4 supernets (10.0.0.0/8, 172.18.0.0/16, 172.19.0.0/16, 192.168.0.0/16)
- **Subnets** : 55 total (30 parents, 25 enfants avec relations parent-enfant)
- **IP Addresses** : 124 toutes liées à leur subnet le plus spécifique
- **Hierarchy** : 34 relations parent-enfant actives
- **Classification** : Tous les subnets tagués parent/child pour filtrage GUI

### Réseaux principaux

**192.168.12.0/24 - Backbone MPLS** (14 enfants /30)
- Interconnexion des routeurs PE/CE/RR
- 28 IPs actives avec résolution DNS complète

**192.168.0.0/24 - Management** 
- 41 IPs (switches, serveurs, NAS, WiFi APs, imprimantes)
- Réseau flat sans subdivision

**10.0.0.0/24 - Loopback Network 1**
- 11 IPs (loopbacks des PE/CE/RR routers)

**Autres réseaux avec subdivisions :**
- 192.168.10.0/24 → 3 enfants (/29, /30, /30)
- 192.168.11.0/24 → 1 enfant (/30)
- 192.168.13.0/24 → 2 enfants (/30, /30)
- 192.168.14-17.0/24 → 1 enfant chacun (/30)
- 192.168.100.0/24 → 1 enfant (/29)

## 🛠️ Outil CLI : ipam.py

### Commandes principales

```bash
# Afficher le statut
./ipam.py status               # Statut rapide
./ipam.py status --detailed    # Inventaire détaillé

# Peupler l'IPAM
./ipam.py populate             # Depuis inventaire uniquement
./ipam.py populate --scan      # Avec scan réseau (ping)
./ipam.py populate --scan --workers 100  # Plus de threads
./ipam.py populate --routing-tables routing_*.txt  # Avec tables de routage
./ipam.py populate --scan --routing-tables routing_*.txt  # Tout combiné

# Gérer la hiérarchie
./ipam.py hierarchy status     # Afficher état hiérarchie
./ipam.py hierarchy setup      # Configuration complète (types + relations + IPs)
./ipam.py hierarchy types      # Définir types parent/child
./ipam.py hierarchy subnets    # Créer relations parent-enfant
./ipam.py hierarchy ips        # Lier IPs aux subnets
./ipam.py hierarchy reset      # Supprimer toutes les relations
```

### Aide en ligne

```bash
./ipam.py --help                    # Aide générale
./ipam.py status --help             # Aide commande status
./ipam.py populate --help           # Aide commande populate
./ipam.py hierarchy --help          # Aide commande hierarchy
```

## 📚 Architecture IPAM

### Hiérarchie des nœuds

```
Supernets (JeylanIPAMPrefix)
├── 10.0.0.0/8
│   ├── 10.0.0.0/24 (loopback network 1)
│   ├── 10.0.1.0/24 (loopback network 2)
│   └── 10.0.5.0/24
└── 192.168.0.0/16
    ├── 192.168.0.0/24 (jeylan1 - management)
    ├── 192.168.10.0/24 (jeylan10)
    │   ├── 192.168.10.0/29 (subdivision)
    │   ├── 192.168.10.8/30 (subdivision)
    │   └── 192.168.10.12/30 (subdivision)
    ├── 192.168.12.0/24 (backbone MPLS)
    │   ├── 192.168.12.0/30
    │   ├── 192.168.12.4/30
    │   └── ... (14 subnets /30 au total)
    ├── 192.168.13.0/24 (jeylan13)
    │   ├── 192.168.13.0/30 (subdivision)
    │   └── 192.168.13.8/30 (subdivision)
    └── ... (autres subnets)
```

### Nœuds IPAM

**1. JeylanIPAMPrefix** (Supernets)
- Attributs : `prefix` (CIDR), `description`, `status`
- Relations : `subnets` (many) → JeylanIPAMSubnet

**2. JeylanIPAMSubnet** (Subnets avec hiérarchie)
- Attributs : 
  - `subnet` (CIDR), `name`, `description`, `vlan_id`, `status`, `utilization` (%)
  - `subnet_type` (Dropdown: parent/child) - Pour filtrage GUI
- Relations :
  - `prefix` → JeylanIPAMPrefix (parent prefix)
  - `parent_subnet` → JeylanIPAMSubnet (relation hiérarchique)
  - `child_subnets` (many) → JeylanIPAMSubnet (relation hiérarchique)
  - `ip_addresses` (many) → JeylanIPAMIPAddress
  - `location` → JeylanLocation

**3. JeylanIPAMIPAddress** (Adresses IP)
- Attributs : `address` (IP), `description`, `status`
- Relations :
  - `subnet` → JeylanIPAMSubnet (subnet le plus spécifique)
  - `device` → JeylanDevice (pour IPs management)
  - `interface` → JeylanInterfaces (pour IPs d'interface)

### Algorithme Longest Prefix Match

Le système utilise le "longest prefix match" pour associer automatiquement les IPs au subnet le plus spécifique :

1. Requête tous les subnets déclarés dans Infrahub
2. Trouve tous les subnets qui contiennent l'IP
3. Sélectionne le subnet avec le **préfixe le plus long** (most specific)
4. Crée l'association IP → Subnet

**Exemples :**
- `192.168.13.1` → `192.168.13.0/30` (et non le /24)
- `192.168.13.9` → `192.168.13.8/30` (deuxième /30)
- `192.168.13.20` → `192.168.13.0/24` (pas dans les /30)
- `192.168.10.6` → `192.168.10.0/29` (subdivision)
- `192.168.0.64` → `192.168.0.0/24` (pas de subdivisions)

## 🚀 Guide d'utilisation

### 1. Charger le schéma

```bash
cd /opt/infrahub && source bin/activate
infrahubctl schema load --branch main /opt/infrahub_jeylan/ipam_schema.yml
```

### 2. Peupler l'IPAM

**Méthode 1 : Depuis inventaire LibreNMS**
```bash
cd /opt/infrahub_jeylan
./ipam.py populate
```

**Méthode 2 : Avec scan réseau (découverte active)**
```bash
./ipam.py populate --scan
```

**Méthode 3 : Avec tables de routage (Cisco/Juniper)**
```bash
./ipam.py populate --routing-tables routing_cisco.txt routing_juniper.txt
```

**Méthode 4 : Tout combiné (maximum de couverture)**
```bash
./ipam.py populate --scan --routing-tables routing_*.txt
```

### 3. Configurer la hiérarchie

```bash
# Configuration complète en une commande
./ipam.py hierarchy setup

# Ou étape par étape :
./ipam.py hierarchy types      # 1. Définir types parent/child
./ipam.py hierarchy subnets    # 2. Créer relations parent-enfant
./ipam.py hierarchy ips        # 3. Lier IPs aux subnets
```

### 4. Vérifier le statut

```bash
# Statut rapide
./ipam.py status

# Inventaire détaillé
./ipam.py status --detailed
```

### 5. Accéder à la GUI

**URL :** http://jeysrv10:8000/objects/JeylanIPAMSubnet

**Filtres utiles :**
- `subnet_type = parent` - Afficher uniquement les parents (/24, /16, /8)
- `subnet_type = child` - Afficher uniquement les enfants (/30, /29)

Dans la vue détaillée d'un subnet parent, onglet "Child Subnets" affiche tous les sous-réseaux hiérarchiques.

## 🔧 Fonctionnalités avancées

### Détection automatique de subnets

L'outil `populate` utilise un algorithme intelligent pour détecter les subdivisions :

1. Groupe toutes les IPs par leur réseau /24 parent
2. Pour chaque /24, analyse les IPs présentes
3. Teste les masques /30 et /29 (du plus spécifique au moins spécifique)
4. Assigne chaque IP au sous-réseau le plus petit qui la contient
5. Ne garde que les sous-réseaux avec 2+ IPs (évite les subdivisions inutiles)

**Exemple :** Si 10.0.0.1, 10.0.0.2, 10.0.0.11, 10.0.0.12 sont présents
- Détecte : `10.0.0.0/30` (pour .1 et .2) et `10.0.0.8/30` (pour .11 et .12)
- Ignore les masques plus grands car les /30 sont plus spécifiques

### Réseaux sans subdivision

Certains réseaux sont configurés pour ne **pas** être subdivisés :
- `192.168.0.0/24` (management)
- `10.0.0.0/24` (loopbacks)
- `10.0.1.0/24` (loopbacks secondaires)

Ces réseaux restent "flat" même s'ils contiennent plusieurs IPs.

### Scan réseau avec ping

L'option `--scan` permet de découvrir des hôtes actifs :
- Ping chaque IP du réseau (timeout 1s)
- Résolution DNS automatique (reverse lookup)
- Parallélisation avec threads (50 workers par défaut)
- Ajustable avec `--workers N`

### Parsing de tables de routage

L'outil supporte les formats Cisco IOS et Juniper JunOS :
- Détecte automatiquement le vendor (Cisco: `show ip route`, Juniper: `show route`)
- Extrait les réseaux et les IPs /32 (host routes)
- Sépare les subnets des host IPs
- Résolution DNS pour les host IPs

## 📊 Maintenance et dépannage

### Recalculer l'utilisation des subnets

L'utilisation est calculée automatiquement :
- **Formule** : `(nombre_ips_allouées / total_ips_utilisables) * 100`
- **IPs utilisables** :
  - /24 : 254 IPs (256 - réseau - broadcast)
  - /30 : 2 IPs (4 - réseau - broadcast)
  - /29 : 6 IPs (8 - réseau - broadcast)

Pour mettre à jour manuellement, relancer `./ipam.py hierarchy ips`.

### Réinitialiser la hiérarchie

```bash
# Supprimer toutes les relations parent-enfant
./ipam.py hierarchy reset

# Puis reconfigurer si nécessaire
./ipam.py hierarchy setup
```

### Réinitialiser complètement l'IPAM

```bash
# ⚠️ ATTENTION : Supprime TOUTES les données Infrahub
./reset_infrahub.sh

# Puis recharger le schéma et repeupler
cd /opt/infrahub && source bin/activate
infrahubctl schema load --branch main /opt/infrahub_jeylan/ipam_schema.yml
cd /opt/infrahub_jeylan
./ipam.py populate
./ipam.py hierarchy setup
```

### Erreurs courantes

**"No subnet found for IP x.x.x.x"**
- L'IP ne correspond à aucun subnet déclaré
- Solution : Ajouter le subnet parent via `populate` avec tables de routage ou manuellement

**"GraphQL errors"**
- Problème de connexion à Infrahub ou schéma non chargé
- Vérifier : `curl http://127.0.0.1:8000/graphql` et recharger le schéma si nécessaire

**Relations parent-enfant non créées**
- Vérifier que `subnet_type` est défini : `./ipam.py hierarchy types`
- Vérifier les logs GraphQL pour erreurs de cardinalité

## 🔍 Requêtes GraphQL utiles

### Lister tous les subnets avec leur hiérarchie

```graphql
{
  JeylanIPAMSubnet {
    edges {
      node {
        subnet { value }
        name { value }
        subnet_type { value }
        parent_subnet {
          node {
            subnet { value }
          }
        }
        child_subnets {
          count
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
```

### Trouver toutes les IPs d'un subnet spécifique

```graphql
{
  JeylanIPAMSubnet(subnet__value: "192.168.12.0/24") {
    edges {
      node {
        subnet { value }
        name { value }
        ip_addresses {
          count
          edges {
            node {
              address { value }
              description { value }
            }
          }
        }
      }
    }
  }
}
```

### Vérifier une IP spécifique et ses relations

```graphql
{
  JeylanIPAMIPAddress(address__value: "192.168.12.1") {
    edges {
      node {
        address { value }
        subnet {
          node {
            subnet { value }
            name { value }
          }
        }
        device {
          node {
            name { value }
          }
        }
      }
    }
  }
}
```

## 📝 Configuration

### Variables d'environnement

```bash
# URL de l'instance Infrahub
export INFRAHUB_URL="http://127.0.0.1:8000"

# Token API (défini dans ipam.py)
export INFRAHUB_API_TOKEN="188600a3-6e17-9f97-339f-c516618aa3c0"
```

### Fichiers requis

- `inventaire_librenms.json` - Export LibreNMS (optionnel pour populate)
- `ipam_schema.yml` - Schéma Infrahub (obligatoire)

## 🎓 Références et ressources

### Documentation Infrahub
- API GraphQL : http://jeysrv10:8000/graphql
- Documentation : https://docs.infrahub.app/
- SDK Python : https://github.com/opsmill/infrahub-sdk-python

### Structure du projet
- **Instance Infrahub** : `/opt/infrahub`
- **Schéma source** : `/opt/infrahub/models/base/jeylan_v0.4.yml` (maintenant fusionné dans ipam_schema.yml)
- **Projet IPAM** : `/opt/infrahub_jeylan`

## 📖 Historique

### Janvier 2026 - v1.0 (Actuel)
- ✅ Fusion complète : 3 scripts Python → 1 outil CLI unifié (`ipam.py`)
- ✅ Fusion schémas : jeylan_v0.4.yml + hiérarchie → `ipam_schema.yml` complet
- ✅ 55 subnets avec 34 relations parent-enfant actives
- ✅ 124 IPs toutes liées au subnet le plus spécifique
- ✅ Classification parent/child pour filtrage GUI
- ✅ Documentation consolidée en un seul README.md

### Décembre 2025 - v0.4
- Architecture IPAM hiérarchique (Prefix → Subnet → IPAddress)
- Ajout relations `parent_subnet` et `child_subnets`
- Attribut `subnet_type` (parent/child)
- Longest prefix match pour association automatique
- Support des subdivisions (/24 contenant /30, /29)

### Versions antérieures
- v0.3 : IPAM 3 niveaux sans hiérarchie
- v0.2 : Relations bidirectionnelles Device ↔ Interface
- v0.1 : Schéma initial Jeylan avec devices et interfaces
