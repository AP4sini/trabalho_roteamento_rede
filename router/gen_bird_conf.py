"""Gera o /etc/bird/bird.conf do roteador atual para OSPF ou RIP (BIRD 2.x).

As interfaces são descobertas pelo IP (o docker não garante a ordem eth0/eth1..).
A interface da LAN é configurada como "stub"/"passive": a rede é anunciada,
mas não se gastam mensagens de controle onde só existe um host.
"""
import topology as T
from common import ROUTER, iface_by_ip

# Temporizadores reduzidos e equivalentes entre os protocolos (para experimentar em segundos)
OSPF_HELLO, OSPF_DEAD = 1, 3
RIP_UPDATE, RIP_TIMEOUT, RIP_GARBAGE = 5, 20, 20

KERNEL = """
protocol device { scan time 10; }

protocol kernel {
    ipv4 {
        import none;
        export filter {
            if source ~ [RTS_OSPF, RTS_OSPF_IA, RTS_OSPF_EXT1, RTS_OSPF_EXT2, RTS_RIP] then accept;
            reject;
        };
    };
    scan time 10;
}
"""


def make_conf(proto):
    lan_if = iface_by_ip(T.lan_router_ip(ROUTER))
    links = [(iface_by_ip(l["local_ip"]), l) for l in T.links_of(ROUTER)]
    c = [f"router id {T.router_id(ROUTER)};",
         'log "/var/log/bird.log" { warning, error, fatal, bug };', KERNEL]

    if proto == "ospf":
        c.append("protocol ospf v2 {\n    ipv4 { import all; export none; };\n    area 0 {")
        c.append(f'        interface "{lan_if}" {{ stub yes; }};')
        for ifc, l in links:
            c.append(f'        interface "{ifc}" {{ type ptp; cost {l["ospf_cost"]}; '
                     f'hello {OSPF_HELLO}; dead {OSPF_DEAD}; }};')
        c.append("    };\n}")
    elif proto == "rip":
        c.append('protocol direct { ipv4; interface "eth*"; }')
        c.append("protocol rip {\n    ipv4 { import all; export all; };")
        c.append(f'    interface "{lan_if}" {{ passive yes; metric 1; }};')
        for ifc, l in links:
            c.append(f'    interface "{ifc}" {{ metric 1; version 2; update time {RIP_UPDATE}; '
                     f'timeout time {RIP_TIMEOUT}; garbage time {RIP_GARBAGE}; }};')
        c.append("}")
    else:
        raise ValueError(proto)
    return "\n".join(c) + "\n"


if __name__ == "__main__":
    import sys
    print(make_conf(sys.argv[1]))
