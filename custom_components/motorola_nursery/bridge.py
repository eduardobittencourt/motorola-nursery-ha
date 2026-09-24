"""Loopback-only RTSP bridge for Motorola Nursery cameras."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib

from .protocol import Credentials, MagicP2PTunnel


class RtspBridge:
    """Expose MagicP2P as conventional RTSP on a loopback socket."""

    def __init__(
        self,
        camera_host: str,
        credentials: Credentials,
        on_connection_error: Callable[[Exception], None],
    ) -> None:
        self._camera_host = camera_host
        self._credentials = credentials
        self._on_connection_error = on_connection_error
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._slots = asyncio.Semaphore(4)

    @property
    def port(self) -> int:
        """Return the selected loopback port."""
        if self._server is None or not self._server.sockets:
            raise RuntimeError("RTSP bridge has not been started")
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        """Start the listener on an ephemeral loopback port."""
        if self._server is not None:
            return
        self._server = await asyncio.start_server(
            self._accept, "127.0.0.1", 0, limit=256 * 1024
        )

    async def stop(self) -> None:
        """Stop accepting clients and close active tunnels."""
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        tasks = tuple(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        assert task is not None
        self._tasks.add(task)
        try:
            async with self._slots:
                await self._forward(reader, writer)
        finally:
            self._tasks.discard(task)

    async def _forward(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        tunnel: MagicP2PTunnel | None = None
        try:
            tunnel = await MagicP2PTunnel.connect(
                self._camera_host, self._credentials
            )

            async def client_to_camera() -> None:
                while data := await reader.read(65536):
                    await tunnel.send(data)

            async def camera_to_client() -> None:
                while data := await tunnel.receive():
                    writer.write(data)
                    await writer.drain()

            directions = {
                asyncio.create_task(client_to_camera()),
                asyncio.create_task(camera_to_client()),
            }
            done, pending = await asyncio.wait(
                directions, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
        except asyncio.CancelledError:
            raise
        except (ConnectionError, EOFError, OSError, TimeoutError) as err:
            self._on_connection_error(err)
        finally:
            writer.close()
            with contextlib.suppress(ConnectionError, OSError):
                await writer.wait_closed()
            if tunnel is not None:
                with contextlib.suppress(ConnectionError, OSError):
                    await tunnel.close()
