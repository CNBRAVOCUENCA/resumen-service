import json

import httpx
import pytest
import respx
from App.config.settings import Settings
from App.services import consul
from App.services.consul import ConsulRegistrar, consul_lifespan
from fastapi import FastAPI
from fastapi.testclient import TestClient

CONSUL_URL = "http://consul.test:8500"


@pytest.mark.asyncio
@respx.mock
async def test_registers_payload_and_deregisters_with_token(monkeypatch):
    monkeypatch.setattr(consul, "_get_instance_address", lambda _: "10.1.2.3")
    register = respx.put(f"{CONSUL_URL}/v1/agent/service/register").mock(
        return_value=httpx.Response(200)
    )
    config = Settings(
        _env_file=None,
        consul_http_addr=CONSUL_URL,
        consul_http_token="private-token",
        consul_service_tags="traefik.enable=true, traefik.http.routers.summary.rule=Path(`/`)",
    )
    registrar = ConsulRegistrar(config)

    await registrar.register()
    deregister = respx.put(
        f"{CONSUL_URL}/v1/agent/service/deregister/{registrar.service_id}"
    ).mock(return_value=httpx.Response(200))
    await registrar.deregister()

    request = register.calls.last.request
    payload = json.loads(request.content)
    assert request.headers["X-Consul-Token"] == "private-token"
    assert payload == {
        "ID": f"resumen-service-{consul.socket.gethostname()}",
        "Name": "resumen-service",
        "Address": "10.1.2.3",
        "Port": 8000,
        "Tags": [
            "traefik.enable=true",
            "traefik.http.routers.summary.rule=Path(`/`)",
        ],
        "Check": {
            "HTTP": "http://10.1.2.3:8000/health",
            "Interval": "10s",
            "Timeout": "2s",
            "DeregisterCriticalServiceAfter": "1m",
        },
    }
    assert deregister.called
    assert deregister.calls.last.request.headers["X-Consul-Token"] == "private-token"


def test_registration_lifecycle_runs_on_startup_and_shutdown(monkeypatch):
    monkeypatch.setattr(consul, "_get_instance_address", lambda _: "10.1.2.3")
    app = FastAPI(
        lifespan=consul_lifespan(
            Settings(_env_file=None, consul_http_addr=CONSUL_URL)
        )
    )

    with respx.mock:
        register = respx.put(f"{CONSUL_URL}/v1/agent/service/register").mock(
            return_value=httpx.Response(200)
        )
        deregister = respx.put(
            url__regex=rf"{CONSUL_URL}/v1/agent/service/deregister/.*"
        ).mock(return_value=httpx.Response(200))
        with TestClient(app):
            assert register.called
            assert not deregister.called
        assert deregister.called


@pytest.mark.asyncio
async def test_empty_consul_address_disables_registration(monkeypatch):
    def unexpected_address_lookup(_):
        raise AssertionError("disabled registration must not resolve an address")

    monkeypatch.setattr(consul, "_get_instance_address", unexpected_address_lookup)
    registrar = ConsulRegistrar(Settings(_env_file=None, consul_http_addr=""))

    await registrar.register()
    await registrar.deregister()

    assert registrar.service_id is None


@pytest.mark.asyncio
@respx.mock
async def test_registration_failure_fails_startup_without_exposing_token():
    respx.put(f"{CONSUL_URL}/v1/agent/service/register").mock(
        return_value=httpx.Response(500)
    )
    registrar = ConsulRegistrar(
        Settings(
            _env_file=None,
            consul_http_addr=CONSUL_URL,
            consul_http_token="private-token",
            consul_service_address="10.1.2.3",
        )
    )

    with pytest.raises(RuntimeError, match="Consul service registration failed") as error:
        await registrar.register()

    assert "private-token" not in str(error.value)


def test_registration_failure_prevents_application_startup():
    app = FastAPI(
        lifespan=consul_lifespan(
            Settings(
                _env_file=None,
                consul_http_addr=CONSUL_URL,
                consul_service_address="10.1.2.3",
            )
        )
    )

    with respx.mock:
        respx.put(f"{CONSUL_URL}/v1/agent/service/register").mock(
            return_value=httpx.Response(500)
        )
        with pytest.raises(RuntimeError, match="Consul service registration failed"), TestClient(app):
            pytest.fail("the application must not start after failed registration")


@pytest.mark.asyncio
@respx.mock
async def test_shutdown_failure_logs_without_exposing_token(caplog):
    respx.put(f"{CONSUL_URL}/v1/agent/service/register").mock(
        return_value=httpx.Response(200)
    )
    respx.put(url__regex=rf"{CONSUL_URL}/v1/agent/service/deregister/.*").mock(
        return_value=httpx.Response(500)
    )
    registrar = ConsulRegistrar(
        Settings(
            _env_file=None,
            consul_http_addr=CONSUL_URL,
            consul_http_token="private-token",
            consul_service_address="10.1.2.3",
        )
    )
    await registrar.register()

    await registrar.deregister()

    assert "Consul service deregistration failed" in caplog.text
    assert "private-token" not in caplog.text
