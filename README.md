# BHTTP — Binary HTTP Protocol (Server Track)

A binary, length-prefixed HTTP-style protocol over a single persistent TCP connection.  
This submission implements **Track 1: The Server (`bserve`)**.

---

## What it does

The `bserve` server:

- **Listens on TCP** (default port `9000` or specified port) and accepts persistent connections.
- **Parses Binary Frames**: Decodes 8-byte frame headers (Length, Type, Flags, Request ID) and handles `REQUEST` frames with HPACK-style header compression (static table indexing + literal fallback).
- **Safe Path Mapping**: Resolves paths to files under the web root with directory traversal protection (`..` prevention) and automatic directory index resolution (`/` → `/index.html`).
- **Binary Responses**: Emits `RESPONSE` frames (status code, headers such as `server`, `content-type`, `content-length`) followed by `DATA` frames chunked up to 64 KiB, signaling completion via the `END_STREAM` flag (`0x01`).
- **Robust Error Handling**:
  - `404 Not Found` for nonexistent paths or directory traversal attempts.
  - `400 Bad Request` for malformed payloads or unsupported methods, keeping the TCP connection open for subsequent requests.
  - `400 Bad Request` + close for oversize frames exceeding maximum allowed size.
  - **Extensibility**: Unknown frame types are cleanly skipped by reading `Length` payload bytes, ensuring forward compatibility.
- **Persistent Keep-Alive**: Multiple sequential requests are handled over a single TCP connection without closing until client disconnects.

---

## Quick Start

### 1. Start the Server
Serve files from `./www` on port `9000`:

```bash
./bserve ./www 9000
# or on Windows: python bserve.py ./www 9000
```

### 2. Test with Client
A companion client (`bcurl`) is provided to query and test the server:

```bash
./bcurl localhost:9000/index.html
# or on Windows: python bcurl.py localhost:9000/index.html
```

Output:
```html
<html><body><h1>Hello from BHTTP!</h1></body></html>
```

### 3. Verbose Frame Hexdump
Use the `-v` flag to inspect binary frames sent and received:

```bash
./bcurl -v localhost:9000/index.html
# or on Windows: python bcurl.py -v localhost:9000/index.html
```

Sample output:
```text
> REQUEST id=1 len=48
> 00000000  00 00 30 01 00 00 00 01 01 00 0b 2f 69 6e 64 65  |..0......../inde|
> 00000010  78 2e 68 74 6d 6c 03 81 00 0e 6c 6f 63 61 6c 68  |x.html....localh|
> 00000020  6f 73 74 3a 39 30 30 30 82 00 07 62 63 75 72 6c  |ost:9000...bcurl|
> 00000030  2f 31 83 00 03 2a 2f 2a                          |/1...*/*|
< RESPONSE id=1 flags=0x00 len=31
< 00000000  00 00 1f 02 00 00 00 01 00 c8 03 86 00 08 62 73  |..............bs|
< 00000010  65 72 76 65 2f 31 85 00 09 74 65 78 74 2f 68 74  |erve/1...text/ht|
< 00000020  6d 6c 84 00 02 35 33                             |ml...53|
< DATA id=1 flags=0x01 len=53
< 00000000  00 00 35 03 01 00 00 01 3c 68 74 6d 6c 3e 3c 62  |..5.....<html><b|
< 00000010  6f 64 79 3e 3c 68 31 3e 48 65 6c 6c 6f 20 66 72  |ody><h1>Hello fr|
< 00000020  6f 6d 20 42 48 54 54 50 21 3c 2f 68 31 3e 3c 2f  |om BHTTP!</h1></|
< 00000030  62 6f 64 79 3e 3c 2f 68 74 6d 6c 3e 0a           |body></html>.|
<html><body><h1>Hello from BHTTP!</h1></body></html>
```

---

## Testing

Run the automated test suite covering all server behaviors:

```bash
python test_bhttp.py
# or: python -m unittest -v
```

Output:
```text
test_200 (test_bhttp.BHTTPTest.test_200) ... ok
test_404 (test_bhttp.BHTTPTest.test_404) ... ok
test_bad_method_400 (test_bhttp.BHTTPTest.test_bad_method_400) ... ok
test_bcurl_cli_exit_codes_and_verbose (test_bhttp.BHTTPTest.test_bcurl_cli_exit_codes_and_verbose) ... ok
test_bcurl_function_single_connection (test_bhttp.BHTTPTest.test_bcurl_function_single_connection) ... ok
test_keep_alive_multiple_requests (test_bhttp.BHTTPTest.test_keep_alive_multiple_requests) ... ok
test_large_file_multi_frame (test_bhttp.BHTTPTest.test_large_file_multi_frame) ... ok
test_malformed_payload_400_and_stays_open (test_bhttp.BHTTPTest.test_malformed_payload_400_and_stays_open) ... ok
test_oversize_frame_400_then_close (test_bhttp.BHTTPTest.test_oversize_frame_400_then_close) ... ok
test_root_and_dir_index (test_bhttp.BHTTPTest.test_root_and_dir_index) ... ok
test_traversal_is_404 (test_bhttp.BHTTPTest.test_traversal_is_404) ... ok
test_unknown_frame_type_skipped (test_bhttp.BHTTPTest.test_unknown_frame_type_skipped) ... ok
test_unknown_header_literal_roundtrip (test_bhttp.BHTTPTest.test_unknown_header_literal_roundtrip) ... ok

----------------------------------------------------------------------
Ran 13 tests in 0.095s

OK
```

---

## Protocol Specification

See [`SPEC.md`](SPEC.md) for the complete protocol specification:
- Fixed 8-byte frame header (Length, Type, Flags, Request ID)
- Frame types: `REQUEST` (`0x01`), `RESPONSE` (`0x02`), `DATA` (`0x03`)
- HPACK static table and literal header encodings
- Connection lifecycle, keep-alive, and error handling rules

For a byte-by-byte annotated walkthrough of an actual request/response exchange, see [`hexdump.md`](hexdump.md).

---

## Project Files

```
SPEC.md          Protocol specification
proto.py         Shared framing library (encode/decode frames, headers, hexdump)
bserve.py        Server implementation (Track 1)
bserve           Shell wrapper for ./bserve
bcurl.py         Test client (for demo/testing)
bcurl            Shell wrapper for ./bcurl
hexdump.md       Annotated hexdump with byte-by-byte explanations
test_bhttp.py    Automated unit test suite (13 tests)
www/             Sample web root (index.html)
.gitignore       Ignores Python cache and OS artifacts
```
# Binary_HTTP_Protocol
