import argparse, glob, json, os, statistics as st
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

NOMES = {"ospf": "OSPF", "rip": "RIP", "custom": "DELAY-LS (próprio)"}
CORES = {"ospf": "#2b6cb0", "rip": "#dd6b20", "custom": "#2f855a"}


def carregar(d):
    runs = {}
    for f in sorted(glob.glob(os.path.join(d, "*_*.json"))):
        r = json.load(open(f))
        runs.setdefault(r["protocolo"], []).append(r)
    return runs


def dig(r, path):
    for p in path.split("."):
        r = r[p]
    return r


def agg(runs, path, fn=lambda x: x):
    """média e desvio-padrão do valor `path` sobre as rodadas de cada protocolo"""
    out = {}
    for p, rs in runs.items():
        vals = [fn(dig(r, path)) for r in rs if dig(r, path) is not None]
        if vals:
            out[p] = (st.mean(vals), st.pstdev(vals) if len(vals) > 1 else 0.0)
    return out


def barras(ax, dados, titulo, ylabel):
    ps = [p for p in ("ospf", "rip", "custom") if p in dados]
    xs = range(len(ps))
    ax.bar(xs, [dados[p][0] for p in ps], yerr=[dados[p][1] for p in ps], capsize=4,
           color=[CORES[p] for p in ps])
    ax.set_xticks(list(xs)); ax.set_xticklabels([NOMES[p] for p in ps])
    ax.set_title(titulo); ax.set_ylabel(ylabel)
    for x, p in zip(xs, ps):
        ax.text(x, dados[p][0], f"{dados[p][0]:.1f}", ha="center", va="bottom", fontsize=9)


def salvar(fig, out, nome):
    fig.tight_layout(); fig.savefig(os.path.join(out, nome), dpi=150); plt.close(fig)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--dir", default="results")
    a = ap.parse_args()
    runs = carregar(a.dir)
    if not runs:
        raise SystemExit("nenhum results/*.json encontrado; rode scripts/experiment.py antes")
    out = os.path.join(a.dir, "graficos"); os.makedirs(out, exist_ok=True)
    W = next(iter(runs.values()))[0]["janela_s"]

    graficos = [
        ("01_tabela_roteamento.png", agg(runs, "tabelas", lambda t: sum(v["total"] for v in t.values()) / len(t)),
         "Tamanho médio da tabela de roteamento", "rotas por roteador"),
        ("02_pacotes_controle.png", agg(runs, "regime.pacotes_controle"),
         f"Pacotes de controle enviados (rede toda, {W} s)", "pacotes"),
        ("03_taxa_controle.png", agg(runs, "regime.taxa_bps"),
         "Taxa de transmissão de controle (rede toda)", "bits/s"),
        ("04_convergencia_inicial.png", agg(runs, "conv_inicial_s"),
         "Convergência inicial (protocolo iniciado -> H1 alcança H4)", "segundos"),
        ("05_recuperacao_falha.png", agg(runs, "falha.recuperacao_s"),
         "Tempo sem conectividade após falha de enlace", "segundos"),
        ("06_recuperacao_restauracao.png", agg(runs, "restauracao.recuperacao_s"),
         "Tempo sem conectividade após restauração do enlace", "segundos"),
        ("07_overhead_falha.png", agg(runs, "falha.pacotes_controle"),
         "Pacotes de controle durante a falha (janela de 40 s)", "pacotes"),
    ]
    for nome, dados, t, y in graficos:
        fig, ax = plt.subplots(figsize=(6, 4)); barras(ax, dados, t, y); salvar(fig, out, nome)

    # RTT em três momentos
    fig, ax = plt.subplots(figsize=(8, 4.5))
    momentos = [("rtt_ms_base", "regime permanente"), ("rtt_ms_pos_falha", "após falha"),
                ("rtt_ms_pos_degradacao", f"após degradação do enlace (+atraso)")]
    ps = [p for p in ("ospf", "rip", "custom") if p in runs]
    w = 0.8 / len(ps)
    for i, p in enumerate(ps):
        vals = [agg({p: runs[p]}, m).get(p, (0, 0))[0] for m, _ in momentos]
        xs = [j + i * w for j in range(len(momentos))]
        ax.bar(xs, vals, w, label=NOMES[p], color=CORES[p])
        for x, v in zip(xs, vals):
            ax.text(x, v, f"{v:.0f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks([j + w * (len(ps) - 1) / 2 for j in range(len(momentos))])
    ax.set_xticklabels([n for _, n in momentos]); ax.set_ylabel("RTT H1 -> H4 (ms)")
    ax.set_title("Atraso fim a fim (RTT) em cada cenário"); ax.legend()
    salvar(fig, out, "08_rtt_cenarios.png")

    # tabela-resumo
    linhas = ["| Métrica | " + " | ".join(NOMES[p] for p in ps) + " |", "|---|" + "---|" * len(ps)]
    def linha(rot, path, fn=lambda x: x, fmt="{:.1f}"):
        d = agg(runs, path, fn)
        linhas.append(f"| {rot} | " + " | ".join(fmt.format(d[p][0]) if p in d else "-" for p in ps) + " |")
    linha("Tabela de roteamento (rotas/roteador)", "tabelas", lambda t: sum(v["total"] for v in t.values()) / len(t))
    linha("Rotas dinâmicas (média/roteador)", "tabelas", lambda t: sum(v["dinamicas"] for v in t.values()) / len(t))
    linha(f"Pacotes de controle em {W} s (rede)", "regime.pacotes_controle", fmt="{:.0f}")
    linha("Bytes de controle em janela (rede)", "regime.bytes_controle", fmt="{:.0f}")
    linha("Taxa de controle (bit/s)", "regime.taxa_bps")
    linha("Convergência inicial (s)", "conv_inicial_s", fmt="{:.2f}")
    linha("Recuperação após falha (s)", "falha.recuperacao_s", fmt="{:.2f}")
    linha("Recuperação após restauração (s)", "restauracao.recuperacao_s", fmt="{:.2f}")
    linha("RTT regime (ms)", "rtt_ms_base")
    linha("RTT após falha (ms)", "rtt_ms_pos_falha")
    linha("RTT após degradação (ms)", "rtt_ms_pos_degradacao")
    def moda_caminho(p, campo):
        """Caminho mais frequente entre as rodadas (em caso de empate, o da 1ª rodada)."""
        cams = [">".join(r[campo]) for r in runs[p]]
        return max(set(cams), key=lambda c: (cams.count(c), -cams.index(c)))

    linhas.append("| Caminho H1->H4 (regime) | " + " | ".join(moda_caminho(p, "caminho_base") for p in ps) + " |")
    linhas.append("| Caminho após falha | " + " | ".join(moda_caminho(p, "caminho_pos_falha") for p in ps) + " |")
    linhas.append("| Caminho após degradação | " + " | ".join(moda_caminho(p, "caminho_pos_degradacao") for p in ps) + " |")
    linhas.append("| Desviou da degradação? (rodadas) | " +
                  " | ".join(f"{sum(1 for r in runs[p] if r['desviou_da_degradacao'])}/{len(runs[p])}" for p in ps) + " |")
    open(os.path.join(a.dir, "resumo.md"), "w").write("\n".join(linhas) + "\n")
    print("\n".join(linhas)); print(f"\nGráficos em {out}/")