FROM python:3.9-slim

WORKDIR /app/ShadowProxy

ADD . .

RUN python setup.py install

RUN rm -rf /app/ShadowProxy

WORKDIR /root

ENTRYPOINT ["/usr/local/bin/shadowproxy"]
