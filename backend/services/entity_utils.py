import asyncio
import threading
from typing import Any, Coroutine


_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_lock = threading.Lock()


def _get_persistent_loop() -> asyncio.AbstractEventLoop:
  """Obtiene el loop compartido donde viven los clientes async reutilizables."""
  global _loop, _loop_thread

  with _loop_lock:
    if (
      _loop is not None
      and not _loop.is_closed()
      and _loop_thread is not None
      and _loop_thread.is_alive()
    ):
      return _loop

    ready = threading.Event()
    loop = asyncio.new_event_loop()

    def _run_loop() -> None:
      asyncio.set_event_loop(loop)
      ready.set()
      loop.run_forever()

    thread = threading.Thread(
      target=_run_loop,
      name="backend-async-loop",
      daemon=True,
    )
    thread.start()
    ready.wait()
    _loop = loop
    _loop_thread = thread
    return loop


def run_async(coro: Coroutine[Any, Any, Any]) -> Any:
  """
  Ejecuta una coroutine desde código síncrono en un loop persistente.

  Los clientes HTTP asíncronos, como Google GenAI, quedan ligados al event
  loop de su primera llamada. Reutilizar siempre el mismo loop evita cerrar
  conexiones internas entre la extracción y una validación posterior.
  """
  loop = _get_persistent_loop()
  future = asyncio.run_coroutine_threadsafe(coro, loop)
  return future.result()
