FROM python:3.9-slim

WORKDIR /app

ADD . .

RUN apt-get update

RUN apt-get install -y gcc htop procps strace iproute2 curl

RUN apt-get clean

RUN python -m pip install -U pip

RUN python -m pip install py-spy

RUN python setup.py install

RUN rm -rf /app

WORKDIR /root

EXPOSE 8527

ENTRYPOINT ["/usr/local/bin/shadowproxy"]
