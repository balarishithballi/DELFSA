# DELFSA attacker node: minimal, purpose-built recon/attack toolkit
# for exercising the SIEM detection pipeline against controlled, in-lab
# targets only. Intended for use exclusively inside the isolated
# delfsa-attack-range Docker network.
FROM kalilinux/kali-rolling:latest

LABEL org.delfsa.component="attackers" org.delfsa.service="kali"

RUN apt-get update && apt-get install -y --no-install-recommends \
        nmap \
        hydra \
        curl \
        iproute2 \
        iputils-ping \
        python3 \
        python3-pip \
        openssh-client \
        netcat-traditional \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash attacker

COPY docker/services/attackers/kali/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

USER attacker
WORKDIR /home/attacker

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD pgrep -f entrypoint.sh || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
