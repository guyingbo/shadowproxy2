import asyncio
import traceback
from functools import cache

import click
from aioquic.asyncio import QuicConnectionProtocol
from aioquic.quic.events import ConnectionTerminated, StreamDataReceived

from .. import app


class QuicInbound(QuicConnectionProtocol):
    def __init__(self, quic, ctx, stream_handler):
        super().__init__(quic, None)
        self._bound_streams = {}
        self.ctx = ctx

    def quic_event_received(self, event):
        if isinstance(event, StreamDataReceived):
            stream = self._bound_streams.get(event.stream_id)
            if stream is None:
                stream = QuicInboundStream(self, event.stream_id)
                self._bound_streams[event.stream_id] = stream
            if event.data:
                stream.data_received(event.data)
            if event.end_stream:
                s = self._bound_streams.pop(event.stream_id, None)
                if s is not None:
                    s.eof_received()
        elif isinstance(event, ConnectionTerminated):
            self._bound_streams.clear()
            if event.error_code != 0 and app.settings.verbose > 0:
                click.secho(
                    f"quic server connection terminated: {event.reason_phrase}",
                    fg="yellow",
                )
        # super().quic_event_received(event)


class QuicStream:
    quic: QuicConnectionProtocol
    stream_id: int

    @property
    def transport(self):
        return self.quic._transport

    def write(self, data):
        self.quic._quic.send_stream_data(self.stream_id, data, False)
        self.quic._transmit_soon()

    def write_eof(self):
        self.quic._quic.send_stream_data(self.stream_id, b"", end_stream=True)
        self.quic._transmit_soon()

    def data_received(self, data):
        try:
            self.parser.push(data)
        except Exception as e:
            click.secho(f"{self}: {e}", fg="red")

    def eof_received(self):
        try:
            self.parser.push_eof()
            # self.parser.close()
        except Exception as e:
            click.secho(f"{self}: {e}", fg="red")

    def can_write_eof(self):
        return True

    def close(self):
        pass
        # self.write_eof()


class QuicInboundStream(QuicStream):
    def __init__(self, quic_inbound: QuicInbound, stream_id: int):
        self.quic = quic_inbound
        self.stream_id = stream_id
        self.ctx = quic_inbound.ctx
        self.parser = self.ctx.create_server_parser()
        self.parser.set_transport(self)
        self.task = asyncio.create_task(self.ctx.run_proxy(self))
        self.task.add_done_callback(self.ctx.get_task_callback(repr(self)))
        self.source_addr = ("", 0)

    @cache
    def __repr__(self):
        sockname = self.transport.get_extra_info("sockname")
        sock = f"{sockname[0]}:{sockname[1]}"
        return f"{self.__class__.__name__}:{self.stream_id}({sock})"

    def __del__(self):
        self.task.cancel()


class QuicOutbound(QuicConnectionProtocol):
    def __init__(self, quic, ctx, stream_handler):
        super().__init__(quic, None)
        self._bound_streams = {}
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
            stream = self._bound_streams.get(event.stream_id)
            if stream is None:
                click.secho(
                    f"non-exist stream {event.stream_id} receive: {event.data}",
                    fg="red",
                )
                return
            if event.data:
                stream.data_received(event.data)
            if event.end_stream:
                s = self._bound_streams.pop(event.stream_id, None)
                if s is not None:
                    s.eof_received()
        elif isinstance(event, ConnectionTerminated):
            self._terminated_event.set()
            self._bound_streams.clear()
            self.ctx.quic_outbound = None
            if event.error_code != 0 and app.settings.verbose > 0:
                click.secho(
                    f"quic client connection terminated: {event.reason_phrase}",
                    fg="red",
                )
        # super().quic_event_received(event)

    def create_stream(self, target_addr):
        stream_id = self._quic.get_next_available_stream_id()
        self._quic._get_or_create_stream_for_send(stream_id)
        stream = QuicOutboundStream(self, stream_id, target_addr)
        self._bound_streams[stream_id] = stream
        return stream


class QuicOutboundStream(QuicStream):
    def __init__(self, quic_outbound: QuicOutbound, stream_id: int, target_addr):
        self.quic = quic_outbound
        self.stream_id = stream_id
        self.target_addr = target_addr
        self.ctx = quic_outbound.ctx
        self.parser = self.ctx.create_client_parser()
        self.parser.set_transport(self)

    @cache
    def __repr__(self):
        sockname = self.transport.get_extra_info("sockname")
        sock = f"{sockname[0]}:{sockname[1]}"
        target = f"{self.target_addr[0]}:{self.target_addr[1]}"
        return f"{self.__class__.__name__}:{self.stream_id}({sock} -> {target})"
