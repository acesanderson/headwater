from __future__ import annotations

import importlib.metadata
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI
    from headwater_server.server.routing_config import RouterConfig


def register_metrics(app: FastAPI, server_name: str) -> None:
    """Register OTel metrics for a subserver (bywater/deepwater).

    Mounts /metrics on app, activates HTTP auto-instrumentation,
    and registers GPU + Ollama observable gauges.
    Idempotent: returns early if an SDK MeterProvider is already active.
    """
    from opentelemetry import metrics as otel_metrics
    from opentelemetry.sdk.metrics import MeterProvider as SdkMeterProvider

    if isinstance(otel_metrics.get_meter_provider(), SdkMeterProvider):
        return

    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from prometheus_client import make_asgi_app

    resource = Resource.create({
        SERVICE_NAME: server_name,
        "host.name": os.uname().nodename,
        "service.version": importlib.metadata.version("headwater_server"),
    })
    reader = PrometheusMetricReader()
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    otel_metrics.set_meter_provider(provider)

    app.mount("/metrics", make_asgi_app())
    FastAPIInstrumentor().instrument_app(app)

    meter = otel_metrics.get_meter("headwater")
    _register_gpu_metrics(meter)
    _register_ollama_metrics(meter)


def register_router_metrics(
    app: FastAPI,
    server_name: str,
    router_config: RouterConfig,
) -> None:
    """Register OTel metrics for the router.

    Mounts /metrics on app, activates HTTP auto-instrumentation,
    and registers backend health gauges.
    Idempotent: returns early if an SDK MeterProvider is already active.
    """
    from opentelemetry import metrics as otel_metrics
    from opentelemetry.sdk.metrics import MeterProvider as SdkMeterProvider

    if isinstance(otel_metrics.get_meter_provider(), SdkMeterProvider):
        return

    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.resources import Resource, SERVICE_NAME
    from opentelemetry.exporter.prometheus import PrometheusMetricReader
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from prometheus_client import make_asgi_app

    resource = Resource.create({
        SERVICE_NAME: server_name,
        "host.name": os.uname().nodename,
        "service.version": importlib.metadata.version("headwater_server"),
    })
    reader = PrometheusMetricReader()
    provider = MeterProvider(resource=resource, metric_readers=[reader])
    otel_metrics.set_meter_provider(provider)

    _add_metrics_route(app)
    FastAPIInstrumentor().instrument_app(app)

    meter = otel_metrics.get_meter("headwater")
    _register_backend_metrics(meter, router_config)


def _add_metrics_route(app: FastAPI) -> None:
    """Register GET /metrics as a FastAPI APIRoute, inserted before the catch-all.

    Using app.mount() for the Prometheus ASGI app conflicts with the router's
    catch-all ``/{path:path}`` APIRoute — Starlette mounts do not take
    priority over FastAPI APIRoutes.  Using @app.get() appends to the end of
    the route list, also losing to the catch-all.

    The fix: build the APIRoute directly and insert it before the catch-all.

    Uses CONTENT_TYPE_PLAIN_0_0_4 to match the content type that make_asgi_app()
    produces by default (text/plain; version=0.0.4).
    """
    from fastapi import Response as FastAPIResponse
    from fastapi.routing import APIRoute
    from prometheus_client import generate_latest
    from prometheus_client.exposition import CONTENT_TYPE_PLAIN_0_0_4

    def metrics_endpoint() -> FastAPIResponse:
        return FastAPIResponse(
            content=generate_latest(),
            media_type=CONTENT_TYPE_PLAIN_0_0_4,
        )

    route = APIRoute(
        path="/metrics",
        endpoint=metrics_endpoint,
        methods=["GET"],
        include_in_schema=False,
        name="metrics_endpoint",
    )

    routes = app.router.routes
    insert_at = len(routes)
    for i, r in enumerate(routes):
        if getattr(r, "path", "") == "/{path:path}":
            insert_at = i
            break

    routes.insert(insert_at, route)


def _register_gpu_metrics(meter) -> None:
    from opentelemetry.metrics import Observation

    def _observe_gpu_available(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            yield Observation(1, {})
        except Exception:
            yield Observation(0, {})

    def _observe_gpu_memory_used(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                info = pynvml.nvmlDeviceGetMemoryInfo(h)
                name = pynvml.nvmlDeviceGetName(h)
                yield Observation(info.used, {"gpu_index": str(i), "gpu_name": name})
        except Exception:
            return

    def _observe_gpu_memory_free(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                info = pynvml.nvmlDeviceGetMemoryInfo(h)
                name = pynvml.nvmlDeviceGetName(h)
                yield Observation(info.free, {"gpu_index": str(i), "gpu_name": name})
        except Exception:
            return

    def _observe_gpu_memory_total(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                info = pynvml.nvmlDeviceGetMemoryInfo(h)
                name = pynvml.nvmlDeviceGetName(h)
                yield Observation(info.total, {"gpu_index": str(i), "gpu_name": name})
        except Exception:
            return

    def _observe_gpu_utilization(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                util = pynvml.nvmlDeviceGetUtilizationRates(h)
                name = pynvml.nvmlDeviceGetName(h)
                yield Observation(util.gpu / 100.0, {"gpu_index": str(i), "gpu_name": name})
        except Exception:
            return

    def _observe_gpu_temperature(options):
        try:
            import pynvml
            pynvml.nvmlInit()
            for i in range(pynvml.nvmlDeviceGetCount()):
                h = pynvml.nvmlDeviceGetHandleByIndex(i)
                temp = pynvml.nvmlDeviceGetTemperature(h, pynvml.NVML_TEMPERATURE_GPU)
                name = pynvml.nvmlDeviceGetName(h)
                yield Observation(temp, {"gpu_index": str(i), "gpu_name": name})
        except Exception:
            return

    meter.create_observable_gauge("headwater.gpu.available", callbacks=[_observe_gpu_available],
                                  description="1 if GPU is accessible via pynvml, 0 otherwise")
    meter.create_observable_gauge("headwater.gpu.memory.used", callbacks=[_observe_gpu_memory_used],
                                  unit="By", description="Used GPU VRAM in bytes")
    meter.create_observable_gauge("headwater.gpu.memory.free", callbacks=[_observe_gpu_memory_free],
                                  unit="By", description="Free GPU VRAM in bytes")
    meter.create_observable_gauge("headwater.gpu.memory.total", callbacks=[_observe_gpu_memory_total],
                                  unit="By", description="Total GPU VRAM in bytes")
    meter.create_observable_gauge("headwater.gpu.utilization.ratio", callbacks=[_observe_gpu_utilization],
                                  description="GPU compute utilization as a ratio 0.0-1.0")
    meter.create_observable_gauge("headwater.gpu.temperature.celsius", callbacks=[_observe_gpu_temperature],
                                  description="GPU temperature in degrees Celsius")


def _register_ollama_metrics(meter) -> None:
    from opentelemetry.metrics import Observation

    def _observe_ollama_loaded(options):
        try:
            import httpx
            resp = httpx.get("http://localhost:11434/api/ps", timeout=2.0)
            resp.raise_for_status()
            for model in resp.json().get("models", []):
                yield Observation(1, {"model_name": model["name"]})
        except Exception:
            return

    def _observe_ollama_vram(options):
        try:
            import httpx
            resp = httpx.get("http://localhost:11434/api/ps", timeout=2.0)
            resp.raise_for_status()
            for model in resp.json().get("models", []):
                yield Observation(model.get("size_vram", 0), {"model_name": model["name"]})
        except Exception:
            return

    def _observe_ollama_cpu_offload(options):
        try:
            import httpx
            resp = httpx.get("http://localhost:11434/api/ps", timeout=2.0)
            resp.raise_for_status()
            for model in resp.json().get("models", []):
                total = model.get("size", 0)
                vram = model.get("size_vram", 0)
                ratio = max(0.0, (total - vram) / total) if total > 0 else 0.0
                yield Observation(ratio, {"model_name": model["name"]})
        except Exception:
            return

    meter.create_observable_gauge("headwater.ollama.model.loaded", callbacks=[_observe_ollama_loaded],
                                  description="1 if Ollama model is currently loaded")
    meter.create_observable_gauge("headwater.ollama.model.vram", callbacks=[_observe_ollama_vram],
                                  unit="By", description="VRAM used by loaded Ollama model")
    meter.create_observable_gauge("headwater.ollama.model.cpu.offload.ratio",
                                  callbacks=[_observe_ollama_cpu_offload],
                                  description="Fraction of model layers on CPU (0.0=all GPU, 1.0=all CPU)")


def _register_backend_metrics(meter, router_config) -> None:
    from opentelemetry.metrics import Observation
    import httpx

    config = router_config  # live reference; reads .backends at observation time

    def _observe_backend_up(options):
        for name, url in config.backends.items():
            try:
                resp = httpx.get(f"{url}/ping", timeout=2.0)
                up = 1 if resp.status_code == 200 else 0
            except Exception:
                up = 0
            yield Observation(up, {"backend_name": name, "backend_url": url})

    meter.create_observable_gauge("headwater.backend.up", callbacks=[_observe_backend_up],
                                  description="1 if backend responds to /ping within 2s, 0 otherwise")
