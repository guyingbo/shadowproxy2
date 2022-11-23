FROM python:3.10-slim

WORKDIR /app

RUN apt-get update

RUN apt-get install -y gcc htop procps strace iproute2 curl openssl libssl-dev

RUN apt-get clean

RUN python -m pip install -U pip setuptools

RUN python -m pip install py-spy poetry

ADD . .

RUN poetry build

RUN python -m pip install dist/shadowproxy2-*.tar.gz

# RUN rm -rf /app

WORKDIR /root

ENTRYPOINT ["/usr/local/bin/shadowproxy"]

CMD ["--help"]
