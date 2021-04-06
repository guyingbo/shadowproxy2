FROM python:3.9-slim

WORKDIR /app/ShadowProxy

ADD . .

RUN apt-get update

RUN apt-get install -y gcc

RUN apt-get clean

RUN python -m pip install -U pip

RUN python -m pip install mypy

RUN python setup.py install

RUN rm -rf /app/ShadowProxy

WORKDIR /root

ENTRYPOINT ["/usr/local/bin/shadowproxy"]
