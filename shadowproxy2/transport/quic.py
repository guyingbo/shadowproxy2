import asyncio

from aioquic.asyncio import QuicConnectionProtocol
from aioquic.quic.events import (
    ConnectionTerminated,
    StreamDataReceived,
    HandshakeCompleted,
)


class QuicIngress(QuicConnectionProtocol):
    def __init__(self, quic, ctx, stream_handler=None):
        super().__init__(quic, None)
        self._streams = {}
        self.ctx = ctx

    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived):
            stream = self._streams.get(event.stream_id)
            if stream is None:
                stream = QuicIngressStream(self, event.stream_id)
                self._streams[event.stream_id] = stream
            stream.data_received(event.data)
            if event.end_stream:
                stream.eof_received()
                del self._streams[event.stream_id]
        elif isinstance(event, ConnectionTerminated):
            print(event)
            pass


class QuicIngressStream:
    def __init__(self, quic_ingress, stream_id):
        self.quic_ingress = quic_ingress
        self.stream_id = stream_id
        self.ctx = quic_ingress.ctx
        self.parser = self.ctx.create_server_parser()
        self.parser.set_transport(self)
        self.task = asyncio.create_task(self.ctx.run_proxy(self))

        def myprint(task):
            exc = task.exception()
            if exc:
                print(exc)

        self.task.add_done_callback(myprint)

    def send(self, data):
        self.quic_ingress._quic.send_stream_data(self.stream_id, data, False)
        self.quic_ingress._transmit_soon()

    write = send

    def write_eof(self):
        self.quic_ingress._quic.send_stream_data(self.stream_id, b"", end_stream=True)
        self.quic_ingress._transmit_soon()

    def data_received(self, data):
        self.parser.send(data)

    def eof_received(self):
        self.task.cancel()

    close = eof_received


class QuicEgress(QuicConnectionProtocol):
    def __init__(self, quic, ctx, stream_handler=None):
        super().__init__(quic, None)
        self._streams = {}
        self.ctx = ctx
        self._hanshake_event = asyncio.Future()

    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived):
            stream = self._streams.get(event.stream_id)
            if stream is None:
                print("non-exist stream id received")
                return
            stream.data_received(event.data)
            if event.end_stream:
                stream.eof_received()
                del self._streams[event.stream_id]
        elif isinstance(event, HandshakeCompleted):
            self._hanshake_event.set_result(None)
        elif isinstance(event, ConnectionTerminated):
            print(event)
            self._streams.clear()

    async def wait_handshake(self):
        await self._hanshake_event

    def create_stream(self, target_addr):
        stream_id = self._quic.get_next_available_stream_id()
        stream = QuicEgressStream(self, stream_id, target_addr)
        self._streams[stream_id] = stream
        return stream


class QuicEgressStream:
    def __init__(self, quic_egress, stream_id, target_addr):
        self.quic_egress = quic_egress
        self.stream_id = stream_id
        self.ctx = quic_egress.ctx
        self.parser = self.ctx.create_client_parser(target_addr)
        self.parser.set_transport(self)
        self.parser.send(b"")

    def send(self, data):
        self.quic_egress._quic.send_stream_data(self.stream_id, data, False)
        self.quic_egress._transmit_soon()

    write = send

    def data_received(self, data):
        self.parser.send(data)

    def eof_received(self):
        ...
