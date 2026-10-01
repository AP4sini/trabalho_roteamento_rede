"""
DELAY-LS -> algoritmo próprio de roteamento (estado de enlace com custo medido).

Ideia: cada roteador MEDE o atraso real dos seus enlaces, inunda essa
informação pela rede e todos rodam Dijkstra sobre o atraso medido, em vez de usar
contagem de saltos (RIP) ou um custo configurado à mão (OSPF).

Comunicação: UDP porta 5555, mensagens JSON (simples de depurar; o overhead é medido no relatório).
"""
import heapq
import json
import logging
import os
import socket
import sys
import threading
import time
from collections import deque

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import topology as T
from common import ROUTER, sh, iface_by_ip

PORT = 5555
HELLO = 1.0          # s entre sondagens
DEAD = 3.0           # s sem resposta => vizinho caiu (mesmo valor do OSPF configurado)
REFRESH = 10.0       # s entre re-anúncios periódicos do próprio LSA
MAX_AGE = 35.0       # s sem refresh => LSA descartado
ALPHA = 0.3          # peso da amostra nova na EWMA
HOP_PENALTY = 1.0    # ms de penalidade por salto (evita caminhos longos com ganho ínfimo)
LOSS_PENALTY = 100.0 # ms somados por 100% de perda nas últimas 10 sondas
HYST_ABS = 2.0       # ms
HYST_REL = 0.20      # 20 %
SPF_HOLD = 0.05      # s de espera para agrupar eventos antes de recalcular
KRT_PROTO = 250


class DelayLS:
    def __init__(self, me=ROUTER, log=None):
        self.me = me
        self.log = log or logging.getLogger("delay_ls")
        self.lan = T.lan_cidr(me)
        self.lock = threading.RLock()
        self.seq = int(time.time() * 1000)
        self.lsdb = {}                  # origem -> {"seq", "links", "nets", "ts"}
        self.installed = {}             # prefixo -> (nexthop, ifname)
        self.spf_evt = threading.Event()
        self.sock = None
        self.nbrs = {}                  # ip do vizinho -> estado
        for l in T.links_of(me):
            self.nbrs[l["peer_ip"]] = {
                "id": l["peer"], "local_ip": l["local_ip"], "up": False,
                "ewma": None, "last_rx": 0.0, "got_reply": False,
                "hist": deque(maxlen=10), "adv": None, "ifname": None,
            }

    
    def ifname_of(self, local_ip):
        return iface_by_ip(local_ip)

    def apply_route(self, net, nh, ifc):
        r = sh(f"ip route replace {net} via {nh} dev {ifc} proto {KRT_PROTO}")
        if r.returncode:
            self.log.error("falha ao instalar %s: %s", net, r.stderr.strip())
        return r.returncode == 0

    def remove_route(self, net):
        sh(f"ip route del {net} proto {KRT_PROTO}")

    def send(self, ip, msg):
        try:
            self.sock.sendto(json.dumps(msg, separators=(",", ":")).encode(), (ip, PORT))
        except OSError:
            pass  
        
    def flood(self, msg, skip_ip=None):
        with self.lock:
            targets = [ip for ip, n in self.nbrs.items() if n["up"] and ip != skip_ip]
        for ip in targets:
            self.send(ip, msg)

    def cost_of(self, n):
        loss = 1.0 - (sum(n["hist"]) / len(n["hist"])) if n["hist"] else 0.0
        return round(n["ewma"] + HOP_PENALTY + LOSS_PENALTY * loss, 1)

    def on_probe(self, ip, m):
        self.send(ip, {"t": "R", "id": self.me, "ts": m["ts"]})

    def on_reply(self, ip, m):
        n = self.nbrs.get(ip)
        if not n:
            return
        now = time.monotonic()
        owd = (now - m["ts"]) * 1000.0 / 2.0
        with self.lock:
            n["last_rx"] = now
            n["got_reply"] = True
            n["ewma"] = owd if n["ewma"] is None else ALPHA * owd + (1 - ALPHA) * n["ewma"]
            if not n["up"]:
                n["up"] = True
                n["hist"].clear()
                n["ifname"] = self.ifname_of(n["local_ip"])
                self.log.info("vizinho %s UP (atraso %.1f ms)", n["id"], owd)
                self.originate()
                for lsa in list(self.lsdb.values()):      # sincroniza o BD com o novo vizinho
                    self.send(ip, self.lsa_msg(lsa))
                self.spf_evt.set()

    def tick(self):
        """Roda a cada HELLO: avalia a sonda anterior, detecta queda/mudança de custo e sonda de novo."""
        now = time.monotonic()
        changed = False
        with self.lock:
            for ip, n in self.nbrs.items():
                if n["up"]:
                    n["hist"].append(1 if n["got_reply"] else 0)
                    if now - n["last_rx"] > DEAD:
                        n["up"], n["ewma"] = False, None
                        self.log.info("vizinho %s DOWN (sem resposta há %.1fs)", n["id"], DEAD)
                        changed = True
                    else:
                        c = self.cost_of(n)
                        if n["adv"] is None or abs(c - n["adv"]) > max(HYST_ABS, HYST_REL * n["adv"]):
                            changed = True
                n["got_reply"] = False
            if changed:
                self.originate()
                self.spf_evt.set()
        for ip in list(self.nbrs):
            self.send(ip, {"t": "P", "id": self.me, "ts": time.monotonic()})

    def lsa_msg(self, lsa, origin=None):
        return {"t": "L", "o": origin or lsa["o"], "seq": lsa["seq"],
                "links": lsa["links"], "nets": lsa["nets"]}

    def originate(self):
        with self.lock:
            self.seq += 1
            links = {}
            for n in self.nbrs.values():
                if n["up"]:
                    n["adv"] = self.cost_of(n)
                    links[n["id"]] = n["adv"]
            lsa = {"o": self.me, "seq": self.seq, "links": links, "nets": [self.lan], "ts": time.monotonic()}
            self.lsdb[self.me] = lsa
            self.log.info("LSA própria seq=%d links=%s", self.seq, links)
        self.flood(self.lsa_msg(lsa))

    def on_lsa(self, ip, m):
        o = m["o"]
        if o == self.me:
            return
        with self.lock:
            cur = self.lsdb.get(o)
            if cur and m["seq"] <= cur["seq"]:
                return
            self.lsdb[o] = {"o": o, "seq": m["seq"], "links": m["links"], "nets": m["nets"],
                            "ts": time.monotonic()}
        self.flood(m, skip_ip=ip)
        self.spf_evt.set()

    def age_out(self):
        now = time.monotonic()
        with self.lock:
            dead = [o for o, l in self.lsdb.items() if o != self.me and now - l["ts"] > MAX_AGE]
            for o in dead:
                del self.lsdb[o]
                self.log.info("LSA de %s expirou", o)
        if dead:
            self.spf_evt.set()

    def compute_routes(self):
        """Dijkstra. Retorna {prefixo_LAN: (proximo_salto_roteador, custo, saltos)}."""
        with self.lock:
            edges = {}
            for o, lsa in self.lsdb.items():
                for v, c in lsa["links"].items():
                    if o in self.lsdb.get(v, {}).get("links", {}):     # verificação de duas vias
                        edges.setdefault(o, {})[v] = c
            best = {self.me: (0.0, 0, "")}
            pq = [(0.0, 0, "", self.me)]
            while pq:
                c, h, fh, u = heapq.heappop(pq)
                if best.get(u) != (c, h, fh):
                    continue
                for v, w in edges.get(u, {}).items():
                    cand = (round(c + w, 3), h + 1, v if u == self.me else fh)
                    if v not in best or cand < best[v]:
                        best[v] = cand
                        heapq.heappush(pq, cand + (v,))
            routes = {}
            for r, (c, h, fh) in best.items():
                if r == self.me or r not in self.lsdb:
                    continue
                for net in self.lsdb[r]["nets"]:
                    routes[net] = (fh, c, h)
            return routes

    def install(self, routes):
        with self.lock:
            byname = {n["id"]: (ip, n) for ip, n in self.nbrs.items()}
            desired = {}
            for net, (fh, c, h) in routes.items():
                if fh in byname and byname[fh][1]["up"]:
                    desired[net] = (byname[fh][0], byname[fh][1]["ifname"])
        for net, (nh, ifc) in desired.items():
            if self.installed.get(net) != (nh, ifc):
                if not self.apply_route(net, nh, ifc):
                    continue
                self.installed[net] = (nh, ifc)
                self.log.info("ROTA %s via %s dev %s (custo %.1f)", net, nh, ifc, routes[net][1])
        for net in [n for n in self.installed if n not in desired]:
            self.remove_route(net)
            del self.installed[net]
            self.log.info("ROTA %s removida", net)

    def handle(self, ip, data):
        if ip not in self.nbrs:
            return
        try:
            m = json.loads(data)
            {"P": self.on_probe, "R": self.on_reply, "L": self.on_lsa}[m["t"]](ip, m)
        except Exception as e:                           # mensagem malformada não derruba o daemon
            self.log.warning("mensagem inválida de %s: %s", ip, e)

    def rx_loop(self):
        while True:
            data, (ip, _) = self.sock.recvfrom(65535)
            self.handle(ip, data)

    def hello_loop(self):
        last_refresh = time.monotonic()
        while True:
            time.sleep(HELLO)
            self.tick()
            self.age_out()
            if time.monotonic() - last_refresh >= REFRESH:
                last_refresh = time.monotonic()
                self.originate()

    def spf_loop(self):
        while True:
            self.spf_evt.wait()
            time.sleep(SPF_HOLD)         
            self.spf_evt.clear()
            self.install(self.compute_routes())

    def start_threads(self, with_rx=True):
        with self.lock:
            self.lsdb[self.me] = {"o": self.me, "seq": self.seq, "links": {}, "nets": [self.lan],
                                  "ts": time.monotonic()}
        for fn in ((self.rx_loop,) if with_rx else ()) + (self.hello_loop, self.spf_loop):
            threading.Thread(target=fn, daemon=True).start()
        self.log.info("DELAY-LS iniciado em %s (LAN %s)", self.me, self.lan)

    def run(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("0.0.0.0", PORT))
        self.start_threads()
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s.%(msecs)03d %(message)s", datefmt="%H:%M:%S")
    DelayLS().run()
