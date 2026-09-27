#!/usr/bin/env bash
# Utilitário do laboratório. Uso: scripts/lab.sh <comando> [args]
set -euo pipefail
cd "$(dirname "$0")/.."
R="R1 R2 R3 R4 R5"
lk() { docker exec "$1" python3 /opt/ga/router/linkctl.py "${@:2}"; }

case "${1:-help}" in
  up)      python3 scripts/gen_compose.py && docker compose up -d --build
           echo "Laboratório no ar. Próximo passo: scripts/lab.sh start ospf|rip|custom" ;;
  down)    docker compose down ;;
  start)   for r in $R; do docker exec "$r" python3 /opt/ga/router/proto.py start "$2" & done; wait
           echo "Protocolo '$2' iniciado em todos os roteadores" ;;
  stop)    for r in $R; do docker exec "$r" python3 /opt/ga/router/proto.py stop & done; wait ;;
  routes)  for r in $R; do echo "== $r"; docker exec "$r" ip -4 route | sort; done ;;
  ping)    docker exec "${2:-H1}" ping -c "${4:-4}" "${3:-192.168.4.10}" ;;
  trace)   docker exec "${2:-H1}" traceroute -n "${3:-192.168.4.10}" ;;
  fail)    lk "$2" down "$3"; lk "$3" down "$2"; echo "Enlace $2-$3 em falha silenciosa (100% de perda)" ;;
  ifdown)  lk "$2" ifdown "$3"; lk "$3" ifdown "$2"; echo "Interfaces do enlace $2-$3 derrubadas" ;;
  restore) lk "$2" up "$3"; lk "$3" up "$2"; echo "Enlace $2-$3 restaurado" ;;
  degrade) lk "$2" delay "$3" "$4"; lk "$3" delay "$2" "$4"; echo "Enlace $2-$3 com atraso de $4 ms" ;;
  reset)   for l in "R1 R2" "R2 R3" "R3 R4" "R4 R5" "R5 R1" "R1 R3" "R2 R5"; do
             set -- x $l; lk "$2" reset "$3"; lk "$3" reset "$2"; done; echo "Enlaces nominais" ;;
  logs)    docker exec "$2" sh -c 'tail -n 40 /var/log/delay_ls.log 2>/dev/null; tail -n 40 /var/log/bird.log 2>/dev/null' ;;
  birdc)   docker exec -it "$2" birdc -s /run/bird/bird.ctl "${@:3}" ;;
  *) cat <<USO
Comandos:
  up | down                     sobe/derruba os 10 contêineres (5 roteadores + 5 hosts)
  start ospf|rip|custom         inicia UM protocolo em todos os roteadores (para o anterior)
  stop                          para qualquer protocolo
  routes                        tabelas de roteamento de R1..R5
  ping [H1] [IP] [n]            ping entre hosts (padrão H1 -> 192.168.4.10)
  trace [H1] [IP]               traceroute (mostra o caminho)
  fail A B | restore A B        falha silenciosa (100% perda, interface "up") / restaura o enlace A-B
  ifdown A B                    derruba as interfaces de verdade (o kernel avisa os protocolos na hora)
  degrade A B MS                aumenta o atraso do enlace A-B para MS (o enlace segue "up")
  reset                         volta todos os enlaces ao atraso/taxa nominais
  logs Rn                       últimas linhas de log do protocolo em Rn
  birdc Rn show route           console do BIRD (ex.: birdc R1 show ospf neighbors)
USO
  ;;
esac
