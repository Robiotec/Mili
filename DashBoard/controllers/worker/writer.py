#from queue import Queue
#from threading import Thread
#class AsyncWriter:
#    def __init__(self, maxsize=200):
#        self.q = Queue(maxsize=maxsize)
#        self.t = Thread(target=self._worker, daemon=True)
#        self.t.start()
#
#    def _worker(self):
#        while True:
#            path, img = self.q.get()
#            if path is None:
#                break
#            cv2.imwrite(path, img)
#            self.q.task_done()
#
#    def submit(self, path, img):
#        # si se llena la cola, en vez de congelar: se descarta
#        if not self.q.full():
#            self.q.put((path, img))
#
#    def close(self):
#        self.q.put((None, None))
# ========================================
# 2) I/O ASÍNCRONO (evita congelamiento por cv2.imwrite)
# ========================================
from queue import Queue
from threading import Thread

import cv2
import numpy as np
class AsyncWriter:
    def __init__(self, maxsize: int = 300):
        self.q: Queue[tuple[str, np.ndarray] | tuple[None, None]] = Queue(maxsize=maxsize)
        self.t = Thread(target=self._worker, daemon=True)
        self.t.start()

    def _worker(self):
        while True:
            item = self.q.get()
            try:
                path, img = item  # type: ignore[misc]
                if path is None:
                    break
                cv2.imwrite(path, img)
            finally:
                self.q.task_done()

    def submit(self, path: str, img: np.ndarray) -> None:
        # Si se llena la cola, NO bloqueamos el loop: descartamos el guardado.
        if not self.q.full():
            self.q.put((path, img))

    def close(self):
        # Señal de parada
        if not self.q.full():
            self.q.put((None, None))
        else:
            # si está llena, igual bloqueamos poquito para cerrar bien (preferible al final)
            self.q.put((None, None))
        self.q.join()
