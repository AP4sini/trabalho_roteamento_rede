"""Inicialização do roteador: aplica atraso e taxa (tc netem) em cada enlace e fica vivo."""
import time
import topology as T
from common import ROUTER, sh, iface_by_ip

for l in T.links_of(ROUTER):
    ifc = iface_by_ip(l["local_ip"])
    r = sh(f"tc qdisc replace dev {ifc} root netem delay {l['delay_ms']}ms rate {l['rate_mbit']}mbit")
    print(f"[{ROUTER}] {ifc} ({l['id']}->{l['peer']}): delay={l['delay_ms']}ms rate={l['rate_mbit']}Mbit",
          "OK" if r.returncode == 0 else f"ERRO: {r.stderr.strip()}", flush=True)
print(f"[{ROUTER}] pronto", flush=True)
while True:
    time.sleep(3600)
