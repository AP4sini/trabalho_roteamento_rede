import sys
import topology as T
from common import ROUTER, sh, iface_by_ip


def link_to(peer):
    for l in T.links_of(ROUTER):
        if l["peer"] == peer:
            return l
    sys.exit(f"{ROUTER} não tem enlace com {peer}")


def netem(ifc, delay, rate, loss=0):
    extra = f" loss {loss}%" if loss else ""
    sh(f"tc qdisc replace dev {ifc} root netem delay {delay}ms rate {rate}mbit{extra}", check=True)


if __name__ == "__main__":
    cmd, peer = sys.argv[1], sys.argv[2]
    l = link_to(peer)
    ifc = iface_by_ip(l["local_ip"])
    if cmd == "down":
        netem(ifc, l["delay_ms"], l["rate_mbit"], loss=100)
    elif cmd in ("up", "reset"):
        sh(f"ip link set dev {ifc} up")
        netem(ifc, l["delay_ms"], l["rate_mbit"])
    elif cmd in ("ifdown", "ifup"):
        sh(f"ip link set dev {ifc} {cmd[2:]}", check=True)
    elif cmd == "delay":
        netem(ifc, int(sys.argv[3]), l["rate_mbit"])
    else:
        sys.exit("comando inválido")
