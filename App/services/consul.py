"""Registro opcional del servicio en el agente local de Consul."""

import logging
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI

from App.config.settings import Settings

logger = logging.getLogger(__name__)


def _consul_target(consul_http_addr: str) -> tuple[str, int]:
    address = consul_http_addr.strip()
    parsed = urlsplit(address if "://" in address else f"http://{address}")
    if not parsed.hostname:
        raise ValueError("Invalid Consul HTTP address")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    return parsed.hostname, port


def _get_instance_address(consul_http_addr: str) -> str:
    """Return the local IP selected by the route to the Consul agent."""
    host, port = _consul_target(consul_http_addr)
    for family, socktype, proto, _, sockaddr in socket.getaddrinfo(
        host, port, type=socket.SOCK_DGRAM
    ):
        try:
            with socket.socket(family, socktype, proto) as connection:
                connection.connect(sockaddr)
                return connection.getsockname()[0]
        except OSError:
            continue
    raise OSError("Unable to determine the service instance address")


def _url_host(address: str) -> str:
    if ":" in address and not address.startswith("["):
        return f"[{address}]"
    return address


class ConsulRegistrar:
    def __init__(self, config: Settings) -> None:
        self.config = config
        self.service_id: str | None = None
        self.consul_http_addr = (config.consul_http_addr or "").strip().rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.consul_http_addr)

    def _service_payload(self) -> dict:
        service_name = self.config.consul_service_name or self.config.app_name
        service_address = self.config.consul_service_address or _get_instance_address(
            self.consul_http_addr
        )
        hostname = socket.gethostname()
        self.service_id = f"{service_name}-{hostname}"
        check_url = (
            f"http://{_url_host(service_address)}:"
            f"{self.config.consul_service_port}/health"
        )
        return {
            "ID": self.service_id,
            "Name": service_name,
            "Address": service_address,
            "Port": self.config.consul_service_port,
            "Tags": [
                tag.strip()
                for tag in self.config.consul_service_tags.split(",")
                if tag.strip()
            ],
            "Check": {
                "HTTP": check_url,
                "Interval": "10s",
                "Timeout": "2s",
                "DeregisterCriticalServiceAfter": "1m",
            },
        }

    def _headers(self) -> dict[str, str]:
        headers = {}
        token = (self.config.consul_http_token or "").strip()
        if token:
            headers["X-Consul-Token"] = token
        return headers

    async def register(self) -> None:
        if not self.enabled:
            return
        try:
            payload = self._service_payload()
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.put(
                    f"{self.consul_http_addr}/v1/agent/service/register",
                    json=payload,
                    headers=self._headers(),
                )
                response.raise_for_status()
        except Exception:
            raise RuntimeError("Consul service registration failed") from None

    async def deregister(self) -> None:
        if not self.enabled or self.service_id is None:
            return
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.put(
                    f"{self.consul_http_addr}/v1/agent/service/deregister/{self.service_id}",
                    headers=self._headers(),
                )
                response.raise_for_status()
        except Exception:
            logger.warning("Consul service deregistration failed")


def consul_lifespan(config: Settings):
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        registrar = ConsulRegistrar(config)
        await registrar.register()
        try:
            yield
        finally:
            await registrar.deregister()

    return lifespan
