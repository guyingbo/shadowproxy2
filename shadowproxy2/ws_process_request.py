import asyncio
import socket
import traceback
import uuid
from http import HTTPStatus
from urllib.parse import urlparse, parse_qs

import objgraph
from prometheus_client import generate_latest, Gauge
from pympler import summary, muppy

from . import app

concurrent_requests = Gauge(
    "concurrent_requests",
    "concurrent requests",
    labelnames=["instance_id", "hostname"],
).labels(uuid.getnode(), socket.gethostname())
task_number = Gauge(
    "task_number",
    "task number",
    labelnames=["instance_id", "hostname"],
).labels(uuid.getnode(), socket.gethostname())
task_number.set_function(lambda: len(asyncio.all_tasks()))
obj_count = Gauge(
    "obj_count",
    "obj count by type",
    labelnames=["type"],
)


async def ws_process_request(path, request_headers):
    if path == "/metrics":
        for label, value in objgraph.most_common_types():
            obj_count.labels(label).set(value)
        return HTTPStatus.OK, [], generate_latest()
    elif path == "/summary":
        s = summary.summarize(muppy.get_objects())
        return HTTPStatus.OK, [], ("\n".join(summary.format_(s))).encode()
    elif path == "/headers":
        return (
            HTTPStatus.OK,
            [],
            ("\n".join(f"{k}: {v}" for k, v in request_headers.items())).encode(),
        )
    elif path.startswith("/health_check") and app.settings.enable_health_check:
        pr = urlparse(path)
        query_dict = parse_qs(pr.query)
        uri = query_dict.get("uri")
        if not uri:
            return HTTPStatus.BAD_REQUEST, [], b"no uri"
        from .client import Client

        try:
            client = Client(uri[0])
            await client.make_httpbin_request()
        except Exception as e:
            if app.settings.verbose > 1:
                traceback.print_exc()
            return HTTPStatus.SERVICE_UNAVAILABLE, [], str(e).encode()
        return HTTPStatus.OK, [], b"ok"
