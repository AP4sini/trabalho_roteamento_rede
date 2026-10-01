"""Gera o docker-compose.yml a partir de topology.py (sem depender de PyYAML)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import topology as T

out = []
w = out.append
w("# ARQUIVO GERADO por scripts/gen_compose.py -- não edite à mão.")
w("name: ga-routing")
w("x-base: &base")
w("  image: ga-router:latest")
w("  build: .")
w("  volumes:")
w("    - ./:/opt/ga:ro")
w("  cap_add: [NET_ADMIN]")
w("  init: true")
w("  sysctls:")
w("    net.ipv4.ip_forward: 1")
w("    net.ipv4.conf.all.rp_filter: 0")
w("    net.ipv4.conf.default.rp_filter: 0")
w("")
w("services:")
for r in T.ROUTERS:
    w(f"  {r}:")
    w("    <<: *base")
    w(f"    container_name: {r}")
    w(f"    hostname: {r}")
    w(f"    environment: [ROUTER={r}]")
    w("    command: python3 /opt/ga/router/init.py")
    w("    networks:")
    for l in T.links_of(r):
        w(f"      net_{l['id']}: {{ipv4_address: {l['local_ip']}}}")
    w(f"      lan_{r}: {{ipv4_address: {T.lan_router_ip(r)}}}")
for r in T.ROUTERS:
    h = T.host_name(r)
    w(f"  {h}:")
    w("    <<: *base")
    w(f"    container_name: {h}")
    w(f"    hostname: {h}")
    w(f"    command: sh -c \"ip route replace default via {T.lan_router_ip(r)} && exec sleep infinity\"")
    w("    networks:")
    w(f"      lan_{r}: {{ipv4_address: {T.host_ip(r)}}}")
w("")
w("networks:")
for l in T.LINKS:
    w(f"  net_{l['id']}:")
    w("    internal: true")
    w("    ipam:")
    w(f"      config: [{{subnet: {l['subnet']}, gateway: {l['gw']}}}]")
for r in T.ROUTERS:
    w(f"  lan_{r}:")
    w("    internal: true")
    w("    ipam:")
    w(f"      config: [{{subnet: {T.lan_cidr(r)}, gateway: {T.lan_gw(r)}}}]")

path = os.path.join(os.path.dirname(__file__), "..", "docker-compose.yml")
open(path, "w").write("\n".join(out) + "\n")
print("docker-compose.yml gerado")
