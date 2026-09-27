# Comparação: OSPF × RIP × DELAY-LS

## 1. Comparação conceitual (critérios pedidos no enunciado)

| Critério | OSPFv2 (BIRD) | RIPv2 (BIRD) | DELAY-LS (próprio) |
|---|---|---|---|
| **Princípio de funcionamento** | Estado de enlace: inunda LSAs (com confirmação), todos têm o mesmo BD e rodam Dijkstra | Vetor de distância (Bellman‑Ford): cada roteador anuncia sua tabela aos vizinhos | Estado de enlace com custo **medido**: sondas de atraso, LSAs, Dijkstra |
| **Seleção de rotas** | Menor soma de custos **configurados** (aqui: 1000/banda em Mbit) | Menor número de saltos (máx. 15) | Menor soma de **atraso medido** (+ perda + 1 ms/salto) |
| **Mudança de topologia** | Detecta por hello/dead (aqui 1 s/3 s), inunda LSA, recalcula. Rápido | Detecta pela ausência de atualizações (timeout, aqui 20 s) + atualizações disparadas. Lento; risco de *count‑to‑infinity* (mitigado por split horizon) | Detecta por sondas (dead 3 s), inunda LSA, recalcula. **Também reage a degradação sem queda de enlace** |
| **Overhead de controle** | Baixo em regime (só hellos); LSAs só nas mudanças | Baixo/moderado: tabela completa periodicamente (cresce com nº de rotas) | Maior: sondas + respostas em todo enlace o tempo todo, JSON verboso |
| **Escalabilidade** | Boa (áreas, DR/BDR em redes broadcast); custo: memória do BD e CPU do SPF | Ruim (limite de 15 saltos, convergência lenta, tabela inteira a cada update) | Limitada (inundação global, sem áreas; sondagem por vizinho) |
| **Complexidade** | Config. moderada; protocolo complexo, mas maduro | Config. trivial | Implementação própria (~300 linhas); config. zero, mas requer manutenção/testes |
| **Adequação** | Redes corporativas/campus/ISP internas | Redes pequenas/simples, laboratório, legado | Redes pequenas onde a qualidade dos enlaces varia (radioenlaces, WAN com VPN); protótipo/pesquisa |

## 2. Hipóteses (para conferir com as medições — não são resultados)

Cálculo teórico do tráfego de controle em regime, com os temporizadores do laboratório (14 pontas de enlace = 7 enlaces × 2):

* **OSPF**: 1 hello/s por ponta ⇒ ≈ 14 pacotes/s ⇒ ≈ 420 pacotes em 30 s (LANs são *stub*, sem hellos).
* **RIP**: 1 atualização a cada 5 s por ponta (≈ 12 rotas cabem em 1 pacote) ⇒ ≈ 2,8 pacotes/s ⇒ ≈ 84 em 30 s.
* **DELAY-LS**: 1 sonda + 1 resposta/s por ponta ⇒ ≈ 28 pacotes/s ⇒ ≈ 840 em 30 s, mais os LSAs periódicos.
* **Falha silenciosa**: OSPF ≈ dead (3 s); DELAY-LS ≈ dead (3 s); RIP ≈ timeout (20 s).
* **Degradação** do enlace em uso (continua “up”): só o DELAY-LS deve desviar; OSPF e RIP mantêm o caminho.
* **Caminho em regime**: RIP empata R1‑R5‑R4 e R1‑R3‑R4 (2 saltos) e pode escolher o segundo, que passa pela corda
  lenta ⇒ RTT bem maior. OSPF e DELAY-LS devem escolher R1‑R5‑R4.

Se as medições divergirem, **isso é resultado**: discuta a causa (temporizadores do BIRD, `tcpdump` perdendo pacotes,
tráfego adicional etc.).

## 3. Como cada métrica é medida (`scripts/experiment.py`)

| Métrica | Como |
|---|---|
| Tamanho da tabela | `ip -4 route show \| wc -l` em cada roteador (total) e só rotas do protocolo (`proto 12` BIRD / `proto 250` DELAY-LS) |
| Pacotes / bytes / taxa de controle | `tcpdump -i any -Q out` em todos os roteadores com filtro `ip proto 89 or udp port 520 or udp port 5555`; soma dos **enviados** = total da rede; bytes contam o cabeçalho IP; taxa = bytes×8 / janela (30 s) |
| Convergência inicial | tempo entre iniciar o protocolo nos 5 roteadores e o primeiro ping H1→H4 com sucesso |
| Tempo de recuperação (falha/restauração) | `ping -i 0.1` H1→H4 durante 40 s; pacotes perdidos × 0,1 s (resolução: 0,1 s) |
| Delay | RTT médio de 20 pings H1→H4 (regime, após falha, após degradação) |
| Caminho | `traceroute -n` H1→H4 traduzido para nomes de roteadores |
| Overhead na reconvergência | mesma captura, durante a janela da falha/restauração |

Cuidados: rode `--runs 3` ou mais e reporte média ± desvio (o `plot.py` faz isso); feche outros programas pesados;
o cenário de falha derruba o **último enlace do caminho em uso por cada protocolo** (registrado em `enlace_testado`),
portanto o enlace pode diferir entre protocolos se eles escolherem caminhos diferentes.

## 4. Resultados medidos (preencher após rodar)

Cole aqui `results/resumo.md` e insira os gráficos de `results/graficos/`:

```
![Tabela de roteamento](../results/graficos/01_tabela_roteamento.png)
![Pacotes de controle](../results/graficos/02_pacotes_controle.png)
![Taxa de controle](../results/graficos/03_taxa_controle.png)
![Convergência inicial](../results/graficos/04_convergencia_inicial.png)
![Recuperação após falha](../results/graficos/05_recuperacao_falha.png)
![RTT por cenário](../results/graficos/08_rtt_cenarios.png)
```

### Discussão (roteiro para escrever)
1. Qual protocolo converge mais rápido e por quê (temporizadores × mecanismo de detecção)?
2. O overhead do DELAY-LS compensa? Quanto a mais em pacotes e em bit/s? Isso escala?
3. O que acontece com RIP/OSPF na degradação sem queda? O DELAY-LS desviou? A histerese evitou oscilação?
4. Onde cada solução é adequada? (ver tabela da seção 1)
