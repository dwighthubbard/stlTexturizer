"""BeeWare desktop wrapper for the BumpMesh PyScript app."""

from __future__ import annotations

import functools
import pathlib
import socket
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import toga


class QuietStaticHandler(SimpleHTTPRequestHandler):
    """Static file handler that keeps BeeWare console output readable."""

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        return


class LocalStaticServer:
    """Serve bundled web assets on localhost for Toga WebView."""

    def __init__(self, root: pathlib.Path):
        self.root = root
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> str:
        handler = functools.partial(QuietStaticHandler, directory=str(self.root))
        self.httpd = ThreadingHTTPServer(("127.0.0.1", _free_port()), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, name="bumpmesh-static-server", daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address
        return f"http://{host}:{port}/"

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        if self.thread:
            self.thread.join(timeout=2)
            self.thread = None


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def find_web_root() -> pathlib.Path:
    """Find the bundled app root in dev and packaged Briefcase layouts."""
    here = pathlib.Path(__file__).resolve()
    candidates = [
        here.parent / "webroot",
        here.parent,
        here.parent.parent,
        here.parent.parent.parent,
        pathlib.Path.cwd(),
    ]
    for candidate in candidates:
        if (candidate / "index.html").exists() and (candidate / "pyscript.json").exists():
            return candidate
    raise RuntimeError("Could not find bundled BumpMesh web assets.")


class BumpMeshNative(toga.App):
    def startup(self):
        self.server = LocalStaticServer(find_web_root())
        url = self.server.start()

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.webview = toga.WebView(url=url)
        self.main_window.content = self.webview
        self.main_window.show()

    def on_exit(self):
        self.server.stop()
        return True


def main():
    return BumpMeshNative("BumpMesh", "com.cnckitchen.bumpmesh")
