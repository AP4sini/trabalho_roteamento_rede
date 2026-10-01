"""
Experimento automatizado: para cada protocolo (ospf, rip, custom) executa a mesma sequência
de cenários sobre a mesma topologia e grava as métricas em results/<protocolo>_<rodada>.json.

Cenários (H1 -> H4 é o fluxo de teste):
  1. Convergência inicial      : tempo até H1 alcançar H4 depois de iniciar o protocolo
  2. Regime permanente         : tamanho das tabelas, pacotes/bytes de controle em JANELA s,
                                 RTT (delay) e caminho
  3. Falha de enlace           : falha SILENCIOSA (100% de perda, interface continua "up") do último
                                 enlace do caminho em uso: cada protocolo detecta pelo próprio mecanismo; mede perdas
                                 (=> tempo de recuperação), overhead durante a reconvergência
  4. Restauração do enlace     : idem
  5. Degradação (enlace "up")  : eleva o atraso do enlace em uso para 100 ms e vê se o
                                 protocolo desvia (só quem mede atraso percebe)

Requisitos: laboratório no ar (scripts/lab.sh up), docker acessível sem sudo.
Uso: python3 scripts/experiment.py [--protocols ospf rip custom] [--runs 1]
"""
import argparse, json, os, re, struct, subprocess, sys, threading, time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
import topology as T

ROUTERS = T.ROUTERS
DST = T.host_ip("R4")
IP2NODE = T.ip_to_node()
WINDOW = 30          # s de captura em regime permanente
SETTLE = 30          # s de espera após a convergência inicial
PING_INT = 0.1       # s entre pings nos testes de perda (resolução do tempo de recuperação)
DEGRADE_MS = 100
FILTER = "ip proto 89 or udp port 520 or udp port 5555"   # OSPF | RIP | DELAY-LS


# ------------------------------------------------------------------ docker ---
def dx(container, cmd, timeout=None):
    return subprocess.run(["docker", "exec", container, "sh", "-c", cmd],
                          capture_output=True, text=True, timeout=timeout)


def par(fn, items):
    ts = [threading.Thread(target=fn, args=(i,)) for i in items]
    [t.start() for t in ts]
    [t.join() for t in ts]


def lk(router, *args):
    r = dx(router, "python3 /opt/ga/router/linkctl.py " + " ".join(map(str, args)))
    if r.returncode:
        raise RuntimeError(f"linkctl {router} {args}: {r.stderr}")


def fail(a, b):      lk(a, "down", b);  lk(b, "down", a)
def restore(a, b):   lk(a, "up", b);    lk(b, "up", a)
def degrade(a, b, ms): lk(a, "delay", b, ms); lk(b, "delay", a, ms)


def reset_links():
    for l in T.LINKS:
        lk(l["a"], "reset", l["b"]); lk(l["b"], "reset", l["a"])


def proto(name):
    def one(r):
        out = dx(r, f"python3 /opt/ga/router/proto.py {'stop' if name == 'stop' else 'start ' + name}")
        if out.returncode:
            raise RuntimeError(f"{r}: {out.stderr}{out.stdout}")
    par(one, ROUTERS)


# ---------------------------------------------------------------- métricas ---
def parse_pcap(data):
    """Conta pacotes e bytes (nível IP) de um pcap gerado pelo tcpdump (-i any)."""
    if len(data) < 24:
        return 0, 0
    endian = "<" if struct.unpack("<I", data[:4])[0] in (0xa1b2c3d4, 0xa1b23c4d) else ">"
    link = struct.unpack(endian + "I", data[20:24])[0]
    l2 = {113: 16, 276: 20, 1: 14, 101: 0, 12: 0}.get(link, 16)   # SLL, SLL2, Ethernet, raw
    off, n, total = 24, 0, 0
    while off + 16 <= len(data):
        incl = struct.unpack(endian + "I", data[off + 8:off + 12])[0]
        pkt = data[off + 16:off + 16 + incl]
        off += 16 + incl
        ip = pkt[l2:]
        if len(ip) >= 4 and ip[0] >> 4 == 4:
            n += 1
            total += struct.unpack(">H", ip[2:4])[0]
    return n, total


def start_capture(seconds):
    """tcpdump em cada roteador, só tráfego de controle ENVIADO (-Q out): a soma = total da rede."""
    cmd = (f"rm -f /tmp/cap.pcap; timeout -s INT {seconds} "
           f"tcpdump -i any -Q out -nn -U -Z root -s 128 -w /tmp/cap.pcap '{FILTER}' 2>/dev/null")
    return {r: subprocess.Popen(["docker", "exec", r, "sh", "-c", cmd],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) for r in ROUTERS}


def finish_capture(procs):
    per = {}
    for r, p in procs.items():
        p.wait()
        raw = subprocess.run(["docker", "exec", r, "cat", "/tmp/cap.pcap"], capture_output=True).stdout
        per[r] = parse_pcap(raw)
    return {"pacotes": sum(v[0] for v in per.values()),
            "bytes": sum(v[1] for v in per.values()),
            "por_roteador": {r: {"pacotes": v[0], "bytes": v[1]} for r, v in per.items()}}


def route_tables():
    res = {}
    for r in ROUTERS:
        total = int(dx(r, "ip -4 route show | wc -l").stdout.strip())
        dyn = int(dx(r, "(ip -4 route show proto 12; ip -4 route show proto 250) | wc -l").stdout.strip())
        res[r] = {"total": total, "dinamicas": dyn}
    return res


def rtt_ms(count=20):
    out = dx("H1", f"ping -c {count} -i 0.2 -q {DST}", timeout=60).stdout
    m = re.search(r"= [\d.]+/([\d.]+)/", out)
    return float(m.group(1)) if m else None


def trace_path():
    out = dx("H1", f"traceroute -n -q1 -w1 -m 10 {DST}", timeout=60).stdout
    hops = ["H1"]
    for line in out.splitlines()[1:]:
        m = re.match(r"\s*\d+\s+(\d+\.\d+\.\d+\.\d+)", line)
        hops.append(IP2NODE.get(m.group(1), m.group(1)) if m else "*")
    return hops


def wait_reachable(timeout=180):
    """Bloqueia até H1 alcançar H4; retorna o instante (epoch). Relógio compartilhado com o host."""
    cmd = (f"while ! ping -c1 -W0.3 -q {DST} >/dev/null 2>&1; do sleep 0.05; done; date +%s.%N")
    r = dx("H1", cmd, timeout=timeout)
    return float(r.stdout.strip())


def loss_test(action, total_s=40, at_s=5):
    """Ping contínuo H1->H4; executa `action` em at_s; devolve (pacotes perdidos, overhead de controle)."""
    n = int(total_s / PING_INT)
    caps = start_capture(total_s + 2)
    ping = subprocess.Popen(["docker", "exec", "H1", "ping", "-c", str(n), "-i", str(PING_INT),
                             "-W", "1", "-q", DST], stdout=subprocess.PIPE, text=True)
    time.sleep(at_s)
    action()
    out = ping.communicate(timeout=total_s + 30)[0]
    m = re.search(r"(\d+) packets transmitted, (\d+) received", out)
    lost = int(m.group(1)) - int(m.group(2)) if m else None
    return lost, finish_capture(caps)


def link_in_use(path):
    """Último enlace entre roteadores do caminho H1 -> ... -> H4 (ex.: R5-R4)."""
    routers = [h for h in path if h.startswith("R")]
    return (routers[-2], routers[-1]) if len(routers) >= 2 else None


# -------------------------------------------------------------- experimento --
def run(name, out_dir, k):
    log = lambda msg: print(f"[{name} #{k}] {msg}", flush=True)
    res = {"protocolo": name, "rodada": k, "janela_s": WINDOW}
    proto("stop"); reset_links(); time.sleep(2)

    log("1) convergência inicial")
    t0 = time.time(); proto(name)
    res["conv_inicial_s"] = round(wait_reachable() - t0, 2)
    log(f"   H1 alcançou H4 em {res['conv_inicial_s']} s; aguardando {SETTLE}s de estabilização")
    time.sleep(SETTLE)

    log(f"2) regime permanente ({WINDOW}s de captura)")
    caps = start_capture(WINDOW); time.sleep(WINDOW + 3)
    cap = finish_capture(caps)
    res["regime"] = {"pacotes_controle": cap["pacotes"], "bytes_controle": cap["bytes"],
                     "taxa_bps": round(cap["bytes"] * 8 / WINDOW, 1), "por_roteador": cap["por_roteador"]}
    res["tabelas"] = route_tables()
    res["rtt_ms_base"] = rtt_ms()
    res["caminho_base"] = trace_path()
    a, b = link_in_use(res["caminho_base"])
    res["enlace_testado"] = f"{a}-{b}"
    log(f"   caminho {'>'.join(res['caminho_base'])}, RTT {res['rtt_ms_base']} ms, enlace testado {a}-{b}")

    log(f"3) falha do enlace {a}-{b}")
    lost, cap = loss_test(lambda: fail(a, b))
    res["falha"] = {"pacotes_perdidos": lost, "recuperacao_s": None if lost is None else round(lost * PING_INT, 2),
                    "pacotes_controle": cap["pacotes"], "bytes_controle": cap["bytes"]}
    res["caminho_pos_falha"] = trace_path()
    res["rtt_ms_pos_falha"] = rtt_ms()
    log(f"   perdidos {lost} (~{res['falha']['recuperacao_s']} s); novo caminho {'>'.join(res['caminho_pos_falha'])}")

    log(f"4) restauração do enlace {a}-{b}")
    lost, cap = loss_test(lambda: restore(a, b))
    res["restauracao"] = {"pacotes_perdidos": lost, "recuperacao_s": None if lost is None else round(lost * PING_INT, 2),
                          "pacotes_controle": cap["pacotes"], "bytes_controle": cap["bytes"]}
    time.sleep(20)
    res["caminho_pos_restauracao"] = trace_path()

    log(f"5) degradação: atraso de {a}-{b} -> {DEGRADE_MS} ms (enlace continua 'up')")
    degrade(a, b, DEGRADE_MS); time.sleep(45)
    res["caminho_pos_degradacao"] = trace_path()
    res["rtt_ms_pos_degradacao"] = rtt_ms()
    res["desviou_da_degradacao"] = (res["caminho_pos_degradacao"] != res["caminho_pos_restauracao"])
    log(f"   caminho {'>'.join(res['caminho_pos_degradacao'])}, RTT {res['rtt_ms_pos_degradacao']} ms")

    proto("stop"); reset_links()
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{name}_{k}.json")
    json.dump(res, open(path, "w"), indent=2, ensure_ascii=False)
    log(f"resultado salvo em {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocols", nargs="+", default=["ospf", "rip", "custom"], choices=["ospf", "rip", "custom"])
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--out", default=os.path.join(ROOT, "results"))
    a = ap.parse_args()
    for k in range(1, a.runs + 1):
        for p in a.protocols:
            run(p, a.out, k)
    print("Concluído")
