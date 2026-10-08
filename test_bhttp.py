import io
import os
import socket
import subprocess
import sys
import tempfile
import unittest

import proto
from bserve import start_server
from bcurl import fetch

HERE = os.path.dirname(os.path.abspath(__file__))


def request(sock, req_id, path):
    sock.sendall(proto.encode_request(req_id, path, [("host", "t")]))
    return read_response(sock)


def read_response(sock):
    frame = proto.read_frame(sock)
    assert frame.type == proto.T_RESPONSE, proto.describe(frame)
    status, headers = proto.decode_response(frame.payload)
    body, frames = b"", 0
    while True:
        d = proto.read_frame(sock)
        assert d.type == proto.T_DATA
        body += d.payload
        frames += 1
        if d.flags & proto.F_END_STREAM:
            return status, dict(headers), body, frames


class BHTTPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = cls.tmp.name
        cls.root = os.path.join(base, "www")
        os.makedirs(os.path.join(cls.root, "sub"))
        with open(os.path.join(cls.root, "index.html"), "wb") as f:
            f.write(b"<h1>hello</h1>\n")
        with open(os.path.join(cls.root, "sub", "index.html"), "wb") as f:
            f.write(b"sub index")
        cls.big = os.urandom(300_000)
        with open(os.path.join(cls.root, "big.bin"), "wb") as f:
            f.write(cls.big)
        with open(os.path.join(base, "secret.txt"), "wb") as f:
            f.write(b"top secret")
        cls.listener, _ = start_server(cls.root)
        cls.port = cls.listener.getsockname()[1]

    @classmethod
    def tearDownClass(cls):
        cls.listener.close()
        cls.tmp.cleanup()

    def conn(self):
        s = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        self.addCleanup(s.close)
        return s

    def test_200(self):
        status, h, body, _ = request(self.conn(), 1, "/index.html")
        self.assertEqual((status, body), (200, b"<h1>hello</h1>\n"))
        self.assertEqual(h["content-type"], "text/html")
        self.assertEqual(h["content-length"], str(len(body)))

    def test_root_and_dir_index(self):
        s = self.conn()
        self.assertEqual(request(s, 1, "/")[2], b"<h1>hello</h1>\n")
        self.assertEqual(request(s, 2, "/sub/")[2], b"sub index")

    def test_404(self):
        status, _, body, _ = request(self.conn(), 1, "/nope.html")
        self.assertEqual((status, body), (404, b""))

    def test_traversal_is_404(self):
        s = self.conn()
        for p in ("/../secret.txt", "/sub/../../secret.txt", "/%2e%2e/secret.txt"):
            status, _, body, _ = request(s, 1, p)
            self.assertEqual((status, body), (404, b""), p)

    def test_keep_alive_multiple_requests(self):
        s = self.conn()
        for i in range(1, 6):
            self.assertEqual(request(s, i, "/index.html")[0], 200)

    def test_large_file_multi_frame(self):
        status, _, body, frames = request(self.conn(), 1, "/big.bin")
        self.assertEqual(status, 200)
        self.assertEqual(body, self.big)
        self.assertGreater(frames, 1)

    def test_malformed_payload_400_and_stays_open(self):
        s = self.conn()
        s.sendall(proto.encode_frame(proto.T_REQUEST, 0, 7, b"\x01\x00\x50abc"))  # truncated
        self.assertEqual(request_status(s), 400)
        self.assertEqual(request(s, 8, "/index.html")[0], 200)   # connection still usable

    def test_bad_method_400(self):
        s = self.conn()
        s.sendall(proto.encode_request(3, "/index.html", [], method=0x09))
        self.assertEqual(request_status(s), 400)

    def test_unknown_frame_type_skipped(self):
        s = self.conn()
        s.sendall(proto.encode_frame(0x7E, 0xFF, 5, b"future extension"))
        s.sendall(proto.encode_frame(0x00, 0, 5, b""))
        self.assertEqual(request(s, 6, "/index.html")[0], 200)

    def test_oversize_frame_400_then_close(self):
        s = self.conn()
        s.sendall((1_000_000).to_bytes(3, "big") + bytes([proto.T_REQUEST, 0]) + (9).to_bytes(3, "big"))
        self.assertEqual(request_status(s), 400)
        self.assertIsNone(proto.read_frame(s))   # server closed

    def test_unknown_header_literal_roundtrip(self):
        s = self.conn()
        s.sendall(proto.encode_request(1, "/index.html", [("x-custom", "v"), ("accept", "*/*")]))
        self.assertEqual(read_response(s)[0], 200)

    def test_bcurl_function_single_connection(self):
        out = io.BytesIO()
        status = fetch("127.0.0.1", self.port, "/index.html", out)
        self.assertEqual((status, out.getvalue()), (200, b"<h1>hello</h1>\n"))

    def test_bcurl_cli_exit_codes_and_verbose(self):
        cli = [sys.executable, os.path.join(HERE, "bcurl.py")]
        ok = subprocess.run(cli + ["-v", f"127.0.0.1:{self.port}/index.html"], capture_output=True)
        self.assertEqual(ok.returncode, 0)
        self.assertEqual(ok.stdout, b"<h1>hello</h1>\n")
        self.assertIn(b"REQUEST", ok.stderr)
        self.assertIn(b"|", ok.stderr)             # hexdump present
        bad = subprocess.run(cli + [f"127.0.0.1:{self.port}/missing"], capture_output=True)
        self.assertEqual(bad.returncode, 22)
        down = subprocess.run(cli + ["127.0.0.1:1/x"], capture_output=True)
        self.assertEqual(down.returncode, 1)


def request_status(sock):
    frame = proto.read_frame(sock)
    status, _ = proto.decode_response(frame.payload)
    d = proto.read_frame(sock)
    assert d.flags & proto.F_END_STREAM
    return status


if __name__ == "__main__":
    unittest.main()
