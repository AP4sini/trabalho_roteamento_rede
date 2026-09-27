# DELAY-LS – algoritmo próprio de roteamento

## Motivação
Nos protocolos clássicos a métrica **não enxerga a qualidade real do enlace**:
RIP conta saltos (um enlace lento de 1 salto “ganha” de dois enlaces rápidos) e o custo do OSPF é um número
**configurado** (baseado na banda nominal): se um enlace continua “up” mas passa a ter atraso alto ou perdas,
o OSPF continua usando-o. O DELAY-LS parte da pergunta: *e se o roteador medisse o atraso de cada enlace e
roteasse pelo caminho de menor atraso medido?*

## Visão geral
Protocolo de **estado de enlace** (como OSPF), porém com **custo dinâmico medido**:

1. **Sondagem.** A cada 1 s cada roteador envia `PROBE` (UDP 5555) a cada vizinho; o vizinho devolve `REPLY`.
   Atraso unidirecional ≈ RTT/2, suavizado por **EWMA** (α = 0,3). Sem resposta por 3 s → vizinho **caído**.
2. **Custo do enlace** = `EWMA(atraso, ms) + 1 (penalidade por salto) + 100 × taxa_de_perda (últimas 10 sondas)`.
3. **Histerese.** O custo só é re-anunciado se mudar mais que `max(2 ms, 20 %)`. Evita inundar a rede e
   trocar de rota por ruído de medição (*route flapping*).
4. **Inundação de LSAs.** `LSA = {roteador, nº de sequência, custos dos vizinhos ativos, LAN}`. Um roteador só
   aceita/reencaminha LSA com sequência maior (não há laços de inundação), reencaminha para todos os vizinhos
   **menos** o de origem, renova o próprio LSA a cada 10 s e descarta LSAs não renovados em 35 s. Quando um
   vizinho sobe, o BD inteiro é enviado a ele (sincronização).
5. **Cálculo de rotas.** Dijkstra sobre o grafo do BD com **verificação de duas vias** (só usa o enlace A→B se B
   também anuncia B→A). Desempate determinístico por `(custo, nº de saltos, nome do 1º salto)`.
6. **Instalação.** `ip route replace <LAN> via <vizinho> dev <if> proto 250`, apenas o que mudou; rotas obsoletas são removidas.
   Recalcula em até 50 ms após um evento (agrupa rajadas).

## Critérios de seleção de rota
Menor soma de custos medidos; empate → menos saltos → menor nome. Como cada nó tem o mesmo BD, todos calculam
árvores consistentes (sem laços em regime permanente).

## Decisões de projeto e justificativas
| Decisão | Justificativa |
|---|---|
| Estado de enlace, não vetor de distância | Convergência rápida e sem *count‑to‑infinity*; visão global permite verificação de duas vias |
| Medir atraso ativamente (sondas) | Única forma de perceber degradação sem que a interface caia |
| EWMA + histerese | Suaviza jitter; evita oscilação; controla a quantidade de mensagens de controle |
| Penalidade por perda | Enlace com perda tem “atraso efetivo” maior (retransmissões); um enlace com 100 % de perda vira inutilizável |
| Penalidade por salto (1 ms) | Desempate natural a favor de caminhos curtos quando o atraso é praticamente igual |
| UDP + JSON | Simples de implementar/depurar; overhead de bytes **é medido** e discutido no relatório |
| Sequência baseada em `time()` em ms | Após reinício do daemon, LSAs novos continuam “mais novos” que os antigos na rede |
| Inundação não confiável + refresh periódico | Evita implementar ACKs; a perda ocasional é corrigida pelo refresh de 10 s |

## Limitações (a discutir na apresentação)
* Overhead maior que o OSPF (sondas em todo enlace o tempo todo; JSON verboso).
* Só roteia por atraso/perda; não considera banda disponível/congestionamento nem múltiplos caminhos (ECMP).
* Atraso unidirecional estimado como RTT/2 (assume enlace simétrico).
* Sem autenticação: qualquer nó que fale UDP 5555 com um vizinho poderia injetar LSAs. Em produção: HMAC.
* Escalabilidade limitada: inundação global, sem áreas hierárquicas.

## Como observar
`scripts/lab.sh start custom` · `scripts/lab.sh logs R1` (linhas `vizinho … UP/DOWN`, `LSA própria`, `ROTA …`) ·
`scripts/lab.sh degrade R5 R4 100` e ver o caminho mudar com `scripts/lab.sh trace`.
