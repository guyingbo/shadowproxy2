import asyncio

from aioquic.asyncio import QuicConnectionProtocol
from aioquic.quic.events import ConnectionTerminated, StreamDataReceived

from .. import app


class QuicInbound(QuicConnectionProtocol):
    def __init__(self, quic, ctx, stream_handler):
        super().__init__(quic, None)
        self._streams = {}
        self.ctx = ctx

    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived):
            stream = self._streams.get(event.stream_id)
            if stream is None:
                stream = QuicInboundStream(self, event.stream_id)
                self._streams[event.stream_id] = stream
            stream.data_received(event.data)
            if event.end_stream:
                stream.task.cancel()
                del self._streams[event.stream_id]
        elif isinstance(event, ConnectionTerminated):
            self._streams.clear()
            if event.error_code != 0 and app.settings.verbose > 0:
                print("quic server connection terminated:", event.reason_phrase)
        # super().quic_event_received(event)


class QuicStream:
    quic: QuicConnectionProtocol

    def write(self, data):
        self.quic._quic.send_stream_data(self.stream_id, data, False)
        self.quic._transmit_soon()

    def write_eof(self):
        self.quic._quic.send_stream_data(self.stream_id, b"", end_stream=True)
        self.quic._transmit_soon()

    def data_received(self, data):
        self.parser.data_received(data)

    def eof_received(self):
        self.parser.eof_received()

    def close(self):
        self.write_eof()


class QuicInboundStream(QuicStream):
    def __init__(self, quic_inbound: QuicInbound, stream_id: int):
        self.quic = quic_inbound
        self.stream_id = stream_id
        self.ctx = quic_inbound.ctx
        self.parser = self.ctx.create_server_parser()
        self.parser.set_transport(self)
        self.task = asyncio.create_task(self.ctx.run_proxy(self))
        self.task.add_done_callback(self.ctx.get_task_callback("quic inbound"))
        self.source_addr = ("", 0)


class QuicOutbound(QuicConnectionProtocol):
    def __init__(self, quic, ctx, stream_handler):
        super().__init__(quic, None)
        self._streams = {}
        self.ctx = ctx
        self._terminated_event = asyncio.Event()
        self.task = asyncio.create_task(self.keep_alive())

    async def keep_alive(self, ping_interval=10):
        while True:
            try:
                await asyncio.wait_for(self._terminated_event.wait(), ping_interval)
                return
            except asyncio.TimeoutError:
                await self.ping()

    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived):
            stream = self._streams.get(event.stream_id)
            if stream is None:
                print("non-exist stream id received")
                return
            stream.data_received(event.data)
            if event.end_stream:
                del self._streams[event.stream_id]
        elif isinstance(event, ConnectionTerminated):
            self._terminated_event.set()
            self._streams.clear()
            self.ctx.quic_outbound = None
            if event.error_code != 0 and app.settings.verbose > 0:
                print("quic client connection terminated:", event.reason_phrase)
        # super().quic_event_received(event)

    def create_stream(self, target_addr):
        stream_id = self._quic.get_next_available_stream_id()
        self._quic._get_or_create_stream_for_send(stream_id)
        stream = QuicOutboundStream(self, stream_id, target_addr)
        self._streams[stream_id] = stream
        return stream


class QuicOutboundStream(QuicStream):
    def __init__(self, quic_outbound: QuicOutbound, stream_id: int, target_addr):
        self.quic = quic_outbound
        self.stream_id = stream_id
        self.ctx = quic_outbound.ctx
        self.parser = self.ctx.create_client_parser(target_addr)
        self.parser.set_transport(self)
        self.parser.data_received(b"")
