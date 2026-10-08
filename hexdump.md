# BHTTP Request/Response Hexdump

This file contains an annotated hexdump captured from running `bcurl` against `bserve`.

## Test command

```bash
./bcurl -v localhost:9000/index.html
```

## Raw Output

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

## Annotated Breakdown

### 1. REQUEST Frame (Client to Server)

- **Header (8 bytes):**
  - `00 00 30`: Payload Length = 48 bytes
  - `01`: Frame Type = REQUEST (0x01)
  - `00`: Flags = 0x00
  - `00 00 01`: Request ID = 1

- **Payload (48 bytes):**
  - `01`: Method = GET (0x01)
  - `00 0b`: Path Length = 11 bytes
  - `2f 69 6e 64 65 78 2e 68 74 6d 6c`: `/index.html`

  - **Headers (3 headers):**
    - `03`: Header count = 3
    - `81 00 0e 6c 6f 63 61 6c 68 6f 73 74 3a 39 30 30 30`:
      - `81`: Indexed header #1 (`host`)
      - `00 0e`: Value length = 14
      - Value: `localhost:9000`
    - `82 00 07 62 63 75 72 6c 2f 31`:
      - `82`: Indexed header #2 (`user-agent`)
      - `00 07`: Value length = 7
      - Value: `bcurl/1`
    - `83 00 03 2a 2f 2a`:
      - `83`: Indexed header #3 (`accept`)
      - `00 03`: Value length = 3
      - Value: `*/*`

---

### 2. RESPONSE Frame (Server to Client)

- **Header (8 bytes):**
  - `00 00 1f`: Payload Length = 31 bytes
  - `02`: Frame Type = RESPONSE (0x02)
  - `00`: Flags = 0x00
  - `00 00 01`: Request ID = 1

- **Payload (31 bytes):**
  - `00 c8`: Status Code = 200 OK

  - **Headers (3 headers):**
    - `03`: Header count = 3
    - `86 00 08 62 73 65 72 76 65 2f 31`:
      - `86`: Indexed header #6 (`server`)
      - `00 08`: Value length = 8
      - Value: `bserve/1`
    - `85 00 09 74 65 78 74 2f 68 74 6d 6c`:
      - `85`: Indexed header #5 (`content-type`)
      - `00 09`: Value length = 9
      - Value: `text/html`
    - `84 00 02 35 33`:
      - `84`: Indexed header #4 (`content-length`)
      - `00 02`: Value length = 2
      - Value: `53`

---

### 3. DATA Frame (Server to Client)

- **Header (8 bytes):**
  - `00 00 35`: Payload Length = 53 bytes
  - `03`: Frame Type = DATA (0x03)
  - `01`: Flags = END_STREAM (0x01)
  - `00 00 01`: Request ID = 1

- **Payload (53 bytes):**
  - `3c 68 74 6d 6c 3e 3c 62 6f 64 79 3e 3c 68 31 3e 48 65 6c 6c 6f 20 66 72 6f 6d 20 42 48 54 54 50 21 3c 2f 68 31 3e 3c 2f 62 6f 64 79 3e 3c 2f 68 74 6d 6c 3e 0a`
  - Text: `<html><body><h1>Hello from BHTTP!</h1></body></html>\n`
