FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
        bird2 iproute2 iputils-ping traceroute tcpdump python3 procps \
    && rm -rf /var/lib/apt/lists/*
ENV PYTHONPATH=/opt/ga:/opt/ga/router
WORKDIR /opt/ga
