"""Liga/desliga o protocolo de roteamento deste contêiner.

Uso: proto.py start ospf|rip|custom   |   proto.py stop
Apenas UM protocolo roda por vez (exigência do trabalho): 'start' sempre para
o anterior e limpa as rotas que ele instalou no kernel.
"""
import os, subprocess, sys, time
from common import sh

KRT_BIRD = 12     # proto id que o BIRD usa nas rotas que instala
KRT_CUSTOM = 250  # proto id que o nosso algoritmo usa


def stop():
    sh("pkill -x bird; pkill -f delay_ls.py")
    time.sleep(0.5)
    sh(f"ip route flush proto {KRT_BIRD}")
    sh(f"ip route flush proto {KRT_CUSTOM}")


def start(name):
    stop()
    if name in ("ospf", "rip"):
        from gen_bird_conf import make_conf
        os.makedirs("/etc/bird", exist_ok=True)
        os.makedirs("/run/bird", exist_ok=True)
        open("/etc/bird/bird.conf", "w").write(make_conf(name))
        chk = sh("bird -p -c /etc/bird/bird.conf")       # só valida a sintaxe
        if chk.returncode:
            sys.exit(f"config do BIRD inválida:\n{chk.stderr}{chk.stdout}")
        r = sh("bird -c /etc/bird/bird.conf -s /run/bird/bird.ctl")
        if r.returncode:
            sys.exit(f"erro ao iniciar o BIRD: {r.stderr}{r.stdout}")
    elif name == "custom":
        log = open("/var/log/delay_ls.log", "w")
        subprocess.Popen([sys.executable, "/opt/ga/router/delay_ls.py"], stdout=log,
                         stderr=subprocess.STDOUT, start_new_session=True)
    else:
        sys.exit("protocolo inválido")


if __name__ == "__main__":
    if sys.argv[1] == "stop":
        stop()
    else:
        start(sys.argv[2])
