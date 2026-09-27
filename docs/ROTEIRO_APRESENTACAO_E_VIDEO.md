# Roteiro – apresentação (10 min, 01/10/2026) e vídeo

## Apresentação (10 min – o tempo vale nota!)
| Tempo | Conteúdo |
|---|---|
| 0:00–1:00 | Objetivo e topologia (diagrama do README: anel + 2 cordas, corda R1‑R3 lenta) |
| 1:00–2:00 | Plataforma: BIRD 2 em Docker, `tc netem` para atraso/banda, um protocolo por vez |
| 2:00–4:00 | OSPF × RIP em 30 s cada; algoritmo DELAY‑LS: sondas → custo → LSA → Dijkstra (`docs/ALGORITMO.md`) |
| 4:00–7:00 | Demonstração ao vivo curta (ou trecho do vídeo): trace, falha silenciosa, degradação |
| 7:00–9:00 | Gráficos e discussão (`results/graficos`) |
| 9:00–10:00 | Conclusões, limitações, quando usar cada um |

Dica: ensaie com cronômetro; deixe o laboratório **já no ar** (`scripts/lab.sh up`) antes de começar.

## Roteiro do vídeo (5–8 min, gravar a tela do terminal + narração)
```bash
scripts/lab.sh up
# 1) OSPF
scripts/lab.sh start ospf ; sleep 15
scripts/lab.sh routes | head -30 ; scripts/lab.sh trace          # caminho H1->H4
scripts/lab.sh birdc R1 show ospf neighbors
scripts/lab.sh ping H1 192.168.4.10 100 &                        # ping contínuo
scripts/lab.sh fail R5 R4 ; sleep 8 ; scripts/lab.sh trace       # reconvergência
scripts/lab.sh restore R5 R4
# 2) RIP
scripts/lab.sh start rip ; sleep 30 ; scripts/lab.sh trace       # atenção: pode escolher a corda lenta
scripts/lab.sh birdc R1 show route protocol rip1 2>/dev/null || scripts/lab.sh birdc R1 show route
# 3) DELAY-LS
scripts/lab.sh start custom ; sleep 10 ; scripts/lab.sh logs R1 ; scripts/lab.sh trace
scripts/lab.sh degrade R5 R4 100 ; sleep 15 ; scripts/lab.sh trace   # desvia! (OSPF/RIP não desviariam)
scripts/lab.sh reset ; scripts/lab.sh down
```
Mostre também: o experimento automatizado rodando (trechos do log) e os gráficos gerados.

## Checklist da avaliação
| # | Item | Onde está |
|---|---|---|
| 1 | Organização da apresentação | este roteiro |
| 2 | Instalar/configurar plataforma | `Dockerfile`, `router/gen_bird_conf.py`, `router/proto.py` |
| 3 | Topologias física e lógica | `topology.py`, `docker-compose.yml`, diagrama no README |
| 4 | Algoritmo próprio (lógica e critérios) | `docs/ALGORITMO.md` |
| 5 | Dois protocolos + algoritmo implementado | OSPF/RIP em `gen_bird_conf.py`; `router/delay_ls.py` |
| 6 | Coleta de métricas | `scripts/experiment.py` |
| 7 | Comparação com gráficos | `scripts/plot.py`, `docs/COMPARACAO.md` |
| 8 | Vídeo | gravar e adicionar ao GitHub (link no README) |
| 9 | Apresentação/demonstração | dia 01/10 |
| 10 | Tempo | ensaiar |

**Entrega:** submeter no Moodle até **19h de 01/10/2026** (link do GitHub) e ter o vídeo no repositório.
