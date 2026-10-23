# Private UDP preflight

`udp-preflight.py` uses Python 3's standard library. It binds an explicit RFC1918
or CGNAT IPv4 address, accepts one configured peer IP, and echoes only requests
authenticated with a 32-byte shared HMAC key and this run's random ID. It never
opens a wildcard/public listener. `--allow-loopback` exists for local tests only.
Both roles stop after the configured lifetime, at most 60 seconds. The server
also exits once it has received every expected sequence. Replies are the same
size as requests.

This is a low-rate reachability and latency probe. It is not a capacity benchmark,
proof of physical host separation, or evidence of production availability. A
successful request/echo includes traffic in both directions; run it again with
roles reversed to check each node's listener and source-address behavior.

## Copy over SSH

Use the already authorized lab SSH key and known host fingerprints. Keep the
private SSH key local. Transfer the probe and its separate shared test key over
SSH/SCP, never through command-line plaintext, public HTTP, or a committed file.

```sh
python3 scripts/udp-preflight.py init-key reports/local/udp-preflight.key
# The command prints a key-file path and a suggested nonsecret run ID, not the key.
```

Copy `scripts/udp-preflight.py` and `reports/local/udp-preflight.key` to the same
private lab directory on each node with `scp -i LOCAL_SSH_KEY -P SSH_PORT ...`.
Set that directory to mode `700` and the copied key to mode `600`. The key command
refuses to overwrite a pre-existing key file. Delete the probe key from both
nodes after collecting evidence. The program does not need sudo, packages,
Docker, public UDP exposure, or changes to provider firewall rules.

## Run each direction

Use the actual interface private IPs, not a public NAT address or HTTP proxy. Set
`RUN_ID` below to the same freshly generated 32-character hexadecimal string on
both nodes. A new ID is required for the reverse run. The following example uses
the first two authorized Runpod lab IPs; these are not a reusable provider range
or permanent inventory.

On node A, start the listener:

```sh
python3 udp-preflight.py server \
  --bind 10.0.212.169 --peer 10.1.60.60 --port 19080 --peer-port 19081 \
  --key-file udp-preflight.key --run-id RUN_ID \
  --sizes 96,512,1248 --dont-fragment --count 100 --duration 15 \
  --output a-server.json
```

After node A prints `READY`, run on node B:

```sh
python3 udp-preflight.py client \
  --bind 10.1.60.60 --peer 10.0.212.169 --port 19081 --peer-port 19080 \
  --key-file udp-preflight.key --run-id RUN_ID \
  --sizes 96,512,1248 --dont-fragment --count 100 --rate 100 \
  --drain 2 --duration 15 --output b-client.json
```

Then use a new run ID, run the server on B and client on A, and swap the two IP
arguments. Preserve all four JSON files and their program exit statuses. After
adding the third node, probe all three pairs in both initiating directions.

## MTU and verdict

- `--sizes` describes **UDP payload bytes**, including this probe's authenticated
  protocol. IPv4 and UDP headers add 28 bytes. At an interface MTU of 1300,
  `1248` becomes a 1276-byte IPv4 datagram and leaves some room. This also matches
  a proposed Aeron MTU aligned to 32 bytes; configure Aeron separately.
- `--dont-fragment` requires Linux and sets `IP_MTU_DISCOVER=IP_PMTUDISC_DO` on
  both sockets. An oversized send may fail with `EMSGSIZE`; the client writes the
  size, errno and error to failed evidence. The program does not silently retry
  using smaller packets or disable DF.
- `--sizes 1408` is available as a separate diagnostic. With DF it may fail when
  MTU is 1300. Without DF, successful delivery may involve fragmentation and
  **must not be described as a PMTU pass**. Keep it separate from the 1248-byte
  pass/fail report.
- Default client `PASS` requires all planned requests sent, at least one returned
  echo at every configured size, zero loss at every size, zero duplicate/reordered
  echoes, and no authenticated reply mismatching this client's request. Optional
  `--max-loss` changes the explicit per-size loss threshold and is recorded.
- Server `PASS` means all expected authenticated sequences were received and
  echoed without a local send error, duplicate or reordering. Only the paired
  client can confirm return delivery and RTT; require both reports for a clean
  pair. Invalid unrelated packets are counted and ignored, never echoed.
- RTT uses one process's monotonic clock. No synchronized clock or one-way delay
  is implied. JSON includes every valid RTT sample, nearest-rank p50/p95/p99,
  loss, duplicate/reordering counts, actual peer source IP/port, hostname,
  interface MTUs and container-visible CPU/memory information.
- Source IP/port in each report must match the other node's bound endpoint.
  Record provider `machineId` externally for each node. Different hostnames or
  boot IDs alone do not establish the provider's placement guarantee; the probe
  deliberately leaves `providerMachineId` null.

Exit code `0` means `PASS`, `1` means failed probe with JSON evidence, and `2`
means invalid CLI arguments. A network/path failure is evidence, not a reason to
publish an artificial zero-latency result.

## Verify locally

```sh
python3 -B -m unittest discover -s scripts/tests -p test_udp_preflight.py -v
```

Tests exercise real bounded loopback UDP sockets, authentication and run-ID
rejection, source checking, deadline failure evidence, key permissions, and
separate duplicate/reordering/loss accounting. Loopback does not validate cloud
networking.
