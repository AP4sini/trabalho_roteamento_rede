import ipaddress

ROUTERS = ["R1", "R2", "R3", "R4", "R5"]

LINKS_DEF = [
    ("R1", "R2", 5, 100),
    ("R2", "R3", 5, 100),
    ("R3", "R4", 5, 100),
    ("R4", "R5", 5, 100),
    ("R5", "R1", 5, 100),
    ("R1", "R3", 40, 10),   # atalho de 1 salto, porém lento
    ("R2", "R5", 10, 100),  # corda
]

LAN_HOST_SUFFIX = 10  # host de cada LAN = 192.168.N.10


def rnum(r):
    return int(r[1:])


def _build_links():
    out = []
    for a, b, delay, rate in LINKS_DEF:
        lo, hi = sorted((rnum(a), rnum(b)))
        net = ipaddress.ip_network(f"10.0.{lo}{hi}.0/29")
        hosts = list(net.hosts())
        out.append({
            "id": f"L{lo}{hi}",
            "a": a, "b": b,
            "subnet": str(net),
            "gw": str(hosts[-1]),                 # gateway "fantasma" do docker (.6)
            "ip": {a: str(hosts[0]), b: str(hosts[1])},   # .1 e .2
            "delay_ms": delay,
            "rate_mbit": rate,
        })
    return out


LINKS = _build_links()


def lan_cidr(r):
    return f"192.168.{rnum(r)}.0/24"


def lan_router_ip(r):
    return f"192.168.{rnum(r)}.1"


def lan_gw(r):
    return f"192.168.{rnum(r)}.254"      # gateway "fantasma" do docker


def host_name(r):
    return f"H{rnum(r)}"


def host_ip(r):
    return f"192.168.{rnum(r)}.{LAN_HOST_SUFFIX}"


def router_id(r):
    return f"10.255.0.{rnum(r)}"


def links_of(r):
    """Enlaces ponto a ponto de um roteador, com IP local e IP do vizinho."""
    res = []
    for l in LINKS:
        if r in (l["a"], l["b"]):
            peer = l["b"] if r == l["a"] else l["a"]
            res.append({
                "id": l["id"], "peer": peer,
                "local_ip": l["ip"][r], "peer_ip": l["ip"][peer],
                "delay_ms": l["delay_ms"], "rate_mbit": l["rate_mbit"],
                "ospf_cost": ospf_cost(l),
            })
    return res


def link_between(x, y):
    for l in LINKS:
        if {l["a"], l["b"]} == {x, y}:
            return l
    raise KeyError(f"não existe enlace {x}-{y}")


def ospf_cost(l):
    """Custo OSPF 'de administrador': inversamente proporcional à banda nominal."""
    return max(1, 1000 // l["rate_mbit"])


def ip_to_node():
    """Mapa IP -> nome (para traduzir traceroute em caminho de roteadores)."""
    m = {}
    for l in LINKS:
        for r, ip in l["ip"].items():
            m[ip] = r
    for r in ROUTERS:
        m[lan_router_ip(r)] = r
        m[host_ip(r)] = host_name(r)
    return m
