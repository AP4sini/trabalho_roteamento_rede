"""
Teste do DELAY-LS em simulação (sem Docker): 5 instâncias trocando mensagens em memória,
com os atrasos da topologia. Verifica: convergência, escolha do caminho por atraso (e não
por saltos), reação a queda de enlace, restauração e degradação de atraso.
Uso: python3 tests/test_delay_ls.py      (leva ~50 s, em tempo real)
"""
import logging, os, sys, threading, time
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "router"))
import topology as T
import delay_ls

logging.basicConfig(level=logging.WARNING)
NODES, CUT, EXTRA = {}, set(), {}          # CUT: enlaces derrubados; EXTRA: atraso extra (ms) por enlace
IP2NODE = {(n, l["peer_ip"]): l for n in T.ROUTERS for l in T.links_of(n)}


class SimNode(delay_ls.DelayLS):
    def __init__(self, me):
        super().__init__(me, logging.getLogger(me))
        self.routes = {}

    def ifname_of(self, local_ip): return "sim-" + local_ip
    def apply_route(self, net, nh, ifc): self.routes[net] = nh; return True
    def remove_route(self, net): self.routes.pop(net, None)

    def send(self, ip, msg):
        l = IP2NODE[(self.me, ip)]
        if l["id"] in CUT:
            return
        delay = (l["delay_ms"] + EXTRA.get(l["id"], 0)) / 1000.0
        dst, src_ip = NODES[l["peer"]], l["local_ip"]
        threading.Timer(delay, lambda: l["id"] in CUT or dst.handle(src_ip, __import__("json").dumps(msg))).start()


def path(src, dst_router):
    """Segue os próximos saltos instalados de src até o roteador dono da LAN."""
    net, hops, cur = T.lan_cidr(dst_router), [src], src
    while cur != dst_router and len(hops) < 10:
        nh_ip = NODES[cur].routes.get(net)
        if nh_ip is None:
            return None
        cur = next(l["peer"] for l in T.links_of(cur) if l["peer_ip"] == nh_ip)
        hops.append(cur)
    return hops


def wait(sec, msg):
    print(f"  ... {msg} (aguardando {sec}s)", flush=True); time.sleep(sec)


def check(cond, msg):
    print(("  OK   " if cond else "  FALHA"), msg, flush=True)
    return cond


ok = True
for r in T.ROUTERS:
    NODES[r] = SimNode(r)
for n in NODES.values():
    n.start_threads(with_rx=False)

print("1) Convergência inicial")
wait(8, "descoberta de vizinhos + inundação")
p = path("R1", "R4"); print("   R1->R4:", p)
ok &= check(p == ["R1", "R5", "R4"], "R1->R4 pelo caminho de menor atraso (R1-R5-R4, ~10 ms)")
p = path("R1", "R3"); print("   R1->R3:", p)
ok &= check(p == ["R1", "R2", "R3"], "R1->R3 evita a corda R1-R3 (1 salto, mas 40 ms) e usa R1-R2-R3 (~10 ms)")
ok &= check(all(path(a, b) for a in T.ROUTERS for b in T.ROUTERS if a != b), "todos alcançam todas as LANs")

print("2) Queda do enlace R4-R5")
CUT.add("L45"); wait(6, "detecção (DEAD=3s) + reconvergência")
p = path("R1", "R4"); print("   R1->R4:", p)
ok &= check(p is not None and not any(p[i:i+2] in (["R4","R5"],["R5","R4"]) for i in range(len(p)-1)), "R1->R4 não usa mais o enlace R4-R5")
ok &= check(all(path(a, b) for a in T.ROUTERS for b in T.ROUTERS if a != b), "rede continua totalmente conectada")

print("3) Restauração do enlace R4-R5")
CUT.discard("L45"); wait(6, "vizinho volta + sincronização do BD")
p = path("R1", "R4"); print("   R1->R4:", p)
ok &= check(p == ["R1", "R5", "R4"], "caminho original restaurado")

print("4) Degradação: atraso de R4-R5 sobe +95 ms (o link continua 'up' — OSPF/RIP não perceberiam)")
EXTRA["L45"] = 95; wait(12, "EWMA converge + histerese dispara novo LSA")
p = path("R1", "R4"); print("   R1->R4:", p)
ok &= check(p is not None and not any(p[i:i+2] in (["R4","R5"],["R5","R4"]) for i in range(len(p)-1)),
            "DELAY-LS desvia do enlace degradado")
print("\nRESULTADO:", "TODOS OS TESTES PASSARAM" if ok else "HÁ FALHAS")
sys.exit(0 if ok else 1)
