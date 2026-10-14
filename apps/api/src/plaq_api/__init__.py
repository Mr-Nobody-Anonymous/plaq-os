try:
    import starlette.routing
    _orig = starlette.routing.Router.__init__
    if not getattr(_orig, "_plaq_patched", False):
        def _shim(self, *args, on_startup=None, on_shutdown=None, **kwargs):
            _orig(self, *args, **kwargs)
            self.on_startup = on_startup or []
            self.on_shutdown = on_shutdown or []
        _shim._plaq_patched = True  # type: ignore
        starlette.routing.Router.__init__ = _shim
    import fastapi
    if not hasattr(fastapi.FastAPI, "max_body_size"):
        setattr(fastapi.FastAPI, "max_body_size", None)
except Exception:
    pass

from plaq_api.app import app, create_app
from plaq_api.events import EventBroadcaster, broadcaster

__all__ = ["app", "create_app", "EventBroadcaster", "broadcaster"]
