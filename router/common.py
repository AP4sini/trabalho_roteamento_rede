"""Funções auxiliares usadas dentro dos contêineres dos roteadores."""
import os, re, subprocess

ROUTER = os.environ.get("ROUTER", "R1")


def sh(cmd, check=False):
    return subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)


def iface_by_ip(ip):
    """Descobre o nome da interface que possui o IP dado (docker não garante eth0/eth1...)."""
    out = sh("ip -o -4 addr show").stdout
    for line in out.splitlines():
        m = re.match(r"\d+:\s+(\S+)\s+inet\s+(\d+\.\d+\.\d+\.\d+)/", line)
        if m and m.group(2) == ip:
            return m.group(1)
    raise RuntimeError(f"nenhuma interface com IP {ip}")
