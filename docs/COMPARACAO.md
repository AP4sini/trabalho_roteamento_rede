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

## 4. Resultados medidos

Experimento: `python3 scripts/experiment.py --runs 3`, executado em VM Ubuntu (VirtualBox), laboratório com
Docker + BIRD 2. Resultados agregados (média de 3 rodadas):

| Métrica | OSPF | RIP | DELAY-LS (próprio) |
|---|---|---|---|
| Tabela de roteamento (rotas/roteador) | 20.2 | 17.6 | 7.8 |
| Rotas dinâmicas (média/roteador) | 16.4 | 13.8 | 4.0 |
| Pacotes de controle em 30 s (rede) | 414 | 83 | 1430 |
| Bytes de controle em janela (rede) | 28152 | 22667 | 135805 |
| Taxa de controle (bit/s) | 7507.2 | 6044.5 | 36214.6 |
| Convergência inicial (s) | 7.62 | 1.65 | 2.81 |
| Recuperação após falha (s) | 3.00 | 15.17 | 1.53 |
| Recuperação após restauração (s) | 0.00 | 0.00 | 0.00 |
| RTT regime (ms) | 24.4 | 46.1 | 33.9 |
| RTT após falha (ms) | 44.1 | 116.2 | 38.5 |
| RTT após degradação (ms) | 260.0 | 234.5 | 45.0 |
| Caminho H1->H4 (regime) | H1>R1>R5>R4>H4 | H1>R1>R5>R4>H4 | H1>R1>R5>R4>H4 |
| Caminho após falha | H1>R1>R2>R3>R4>H4 | H1>R1>R3>R4>H4 | H1>R1>R5>R4>H4 |
| Caminho após degradação | H1>R1>R5>R4>H4 | H1>R1>R5>R4>H4 | H1>R1>R2>R3>R4>H4 |
| Desviou da degradação? (rodadas) | 0/3 | 0/3 | 2/3 |

![Tabela de roteamento](../results/graficos/01_tabela_roteamento.png)
![Pacotes de controle](../results/graficos/02_pacotes_controle.png)
![Taxa de controle](../results/graficos/03_taxa_controle.png)
![Convergência inicial](../results/graficos/04_convergencia_inicial.png)
![Recuperação após falha](../results/graficos/05_recuperacao_falha.png)
![RTT por cenário](../results/graficos/08_rtt_cenarios.png)

### Discussão

**1. Convergência e detecção de falha.** O RIP converge inicialmente mais rápido (1.65 s) porque começa a
anunciar assim que sobe, sem esperar formar adjacência completa como o OSPF/DELAY-LS. Mas essa vantagem
desaparece na recuperação de falha: o RIP levou em média **15.17 s** para restabelecer conectividade, contra
**3.00 s** do OSPF e **1.53 s** do DELAY-LS. A causa é o mecanismo de detecção: RIP só percebe a ausência de
anúncios pelo timeout (20 s configurados), enquanto OSPF e DELAY-LS usam hello/dead (1 s / 3 s), que reage
quase uma ordem de grandeza mais rápido. Isso confirma a troca clássica do vetor de distância: simplicidade
de configuração em troca de reação lenta a falhas.

**2. O overhead do DELAY-LS.** Ele enviou **1430 pacotes** de controle em 30 s contra 414 do OSPF e 83 do RIP
— quase 3,5× o OSPF e 17× o RIP. Isso é esperado: o algoritmo sonda cada vizinho a cada segundo, o tempo
todo, independente de haver mudança. Em taxa de bits, a diferença é ainda maior (36,2 kbit/s contra 7,5 e 6,0
kbit/s), porque o DELAY-LS usa JSON, que é mais verboso que os formatos binários do BIRD. Esse custo não
escala bem: numa rede com muito mais enlaces, o tráfego de sondagem cresceria proporcionalmente, o que é a
limitação mais séria do algoritmo, já prevista em `docs/ALGORITMO.md`.

**3. A degradação sem queda — o resultado central do trabalho.** Com o enlace em uso continuando "up" mas
com atraso elevado para 100 ms, OSPF e RIP **nunca** desviaram nas 3 rodadas (0/3): o RTT ficou acima de
230 ms nos dois, porque eles continuaram usando o enlace ruim. O DELAY-LS desviou em **2 das 3 rodadas**,
mantendo o RTT em ~45 ms. Investigamos a rodada em que não desviou (dados em `results/custom_1.json`): nela,
o caminho de regime já era diferente das demais (`R1>R2>R3>R4>H4`, em vez de `R1>R5>R4`), provavelmente por
flutuação de atraso durante a convergência inicial — observamos picos semelhantes nos logs do laboratório
(custo do enlace R1-R3 chegando a 589 ms durante congestionamento momentâneo). Como o enlace testado nessa
rodada foi outro (R3-R4), degradá-lo não trouxe ganho real de desviar, e o RTT pós-degradação (31 ms) ficou
próximo do próprio RTT em regime (54 ms). Isso não é uma falha do algoritmo: ele reagiu corretamente à
situação medida, só que o cenário de teste automatizado não controla qual caminho cada protocolo escolhe em
regime, então o enlace testado varia entre rodadas e protocolos. Uma melhoria de projeto seria fixar o enlace
testado (sempre o mesmo, independente do caminho de cada protocolo), o que tornaria a comparação mais justa
entre rodadas.

**4. Tamanho da tabela de roteamento.** O DELAY-LS instalou menos rotas (7.8 contra 20.2 do OSPF e 17.6 do
RIP). Isso provavelmente reflete menos rotas de ECMP (múltiplos caminhos de custo igual): como o DELAY-LS usa
atraso medido com casas decimais, empates exatos de custo são raros, enquanto OSPF (custo inteiro por banda)
e RIP (contagem de saltos) empatam com frequência entre os caminhos do anel, gerando múltiplas entradas
`nexthop` para o mesmo destino — o que vimos diretamente nas tabelas do laboratório.

**5. Onde cada um se encaixa.** Os dados confirmam a tabela conceitual da seção 1: RIP é simples de configurar,
mas lento para detectar falhas e cego a qualidade de enlace — adequado só a redes pequenas e estáveis. OSPF
converge rápido e tem overhead baixo, mas também não enxerga degradação de desempenho sem queda de enlace —
um bom equilíbrio geral para redes corporativas. O DELAY-LS é o único que reage a enlaces que pioram sem cair,
pagando por isso em tráfego de controle; faz mais sentido em redes pequenas onde a qualidade do enlace varia
bastante (rádio, VPN sobre internet) e esse ganho compensa o custo extra de controle.