#!/usr/bin/env python3
"""Read-only audit of unknown outcomes against a pinned canonical-core serializer.

This never resends commands, modifies CSV, or turns a post-load cache finding into
an original client confirmation. Run from the repository root; optional JSON is
a separate audit receipt. It does not validate a replicated core+outbox checkpoint.
"""
import argparse
import collections
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import struct

SERIALIZER_SHA = "b6e56f5884c7a2204726c4bca206f281558b4c967717cc3e46583d01db64db90"
MAX_BYTES = 256 * 1024 * 1024
HEADER = "index,worker,account_id,producer_id,request_seq,client_order_id,planned_offset_ns,enqueued_offset_ns,execute_started_offset_ns,initial_attempt_end_offset_ns,confirmed_offset_ns,ended_offset_ns,scheduler_lateness_ns,queue_delay_ns,initial_execute_rtt_ns,execute_through_resolution_ns,scheduled_to_confirmed_ns,missed_dispatch_deadline,outcome,attempts,unknown_at_initial_deadline,initial_leader,final_leader,result_code,result_reason,order_id,trade_count,replayed,result_command_seq,reply_command_seq,event_seq,market_seq,error".split(",")
CODES = ["ACCEPTED", "REJECTED", "INVALID_REQUEST", "IDEMPOTENCY_CONFLICT", "STALE_SEQUENCE"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def fingerprint(stream):
    digest, size = hashlib.sha256(), 0
    with stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
            size += len(block)
            require(size <= MAX_BYTES, "Decoded/file size exceeds audit bound")
    return {"bytes": size, "sha256": digest.hexdigest()}


class Reader:
    def __init__(self, data):
        self.stream = io.BytesIO(data)

    def number(self, kind):
        size = struct.calcsize(">" + kind)
        data = self.stream.read(size)
        require(len(data) == size, "Truncated canonical snapshot")
        return struct.unpack(">" + kind, data)[0]

    def text(self):
        count = self.number("i")
        if count == -1:
            return None
        require(0 <= count <= 65536, "Invalid UTF-16 string bound")
        data = self.stream.read(2 * count)
        require(len(data) == 2 * count, "Truncated UTF-16 string")
        return data.decode("utf-16-be", "surrogatepass")

    def count(self, maximum):
        count = self.number("i")
        require(0 <= count <= maximum, "Snapshot collection exceeds declared bound")
        return count

    def enum(self, values):
        value = self.number("b")
        require(0 <= value < len(values), "Invalid snapshot enum")
        return values[value]


def decode(path, config):
    require(path.stat().st_size <= MAX_BYTES, "Core snapshot exceeds 256 MiB")
    data = path.read_bytes()
    require(len(data) >= 32 and hashlib.sha256(data[:-32]).digest() == data[-32:], "Core checksum mismatch")
    r = Reader(data[:-32])
    require(r.number("i") == 0x564D4331 and r.number("i") == 2, "Unsupported canonical core schema")
    cache_per = r.number("i")
    limits = [r.number("i") for _ in range(4)]
    expected = config["expectedCoreLimits"]
    require(limits == [expected[k] for k in ("maxAccounts", "maxProducers", "maxRetainedOrders", "maxCachedResults")], "Core limits differ from declared profile")
    require(cache_per == config["expectedResultCachePerProducer"], "Per-producer cache differs")
    command_seq, event_seq, market_seq, next_order, total_base, total_quote = [r.number("q") for _ in range(6)]
    require(min(command_seq, event_seq, market_seq, total_base, total_quote) >= 0 and next_order > 0, "Invalid core counters")
    accounts, orders, cached, producers, cache_sequences = {}, {}, {}, [], set()
    for _ in range(r.count(limits[0])):
        account = r.number("q")
        balances = [r.number("q") for _ in range(4)]
        require(account > 0 and account not in accounts and min(balances) >= 0, "Invalid/duplicate account")
        accounts[account] = balances
    order_ids = set()
    for _ in range(r.count(limits[2])):
        order_id, account, client = r.number("q"), r.number("q"), r.text()
        side = r.enum(["BUY", "SELL"])
        price, original, remaining = [r.number("q") for _ in range(3)]
        tif = r.enum(["GTC", "IOC"])
        status = r.enum(["OPEN", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "EXPIRED"])
        accepted = r.number("q")
        require(order_id > 0 and order_id not in order_ids and account in accounts and (account, client) not in orders, "Invalid/duplicate order")
        require(price > 0 and original > 0 and 0 <= remaining <= original and 0 < accepted <= command_seq, "Invalid order fields")
        order_ids.add(order_id)
        orders[(account, client)] = dict(orderId=order_id, accountId=account, clientOrderId=client, side=side, priceTicks=price, originalQuantity=original, remainingQuantity=remaining, timeInForce=tif, status=status, acceptedCommandSeq=accepted)
    last_producer = None
    for _ in range(r.count(limits[1])):
        account, producer, high = r.number("q"), r.text(), r.number("q")
        require(account in accounts and producer and len(producer) <= 128 and high > 0, "Invalid producer")
        producer_key = (account, producer)
        require(last_producer is None or last_producer < producer_key, "Noncanonical/duplicate producer ordering")
        last_producer = producer_key
        count = r.count(cache_per)
        previous = 0
        for _ in range(count):
            kind, ca, cp, request = r.number("b"), r.number("q"), r.text(), r.number("q")
            require(ca == account and cp == producer and previous < request <= high, "Cached identity/order mismatch")
            previous = request
            command = dict(accountId=ca, producerId=cp, requestSeq=request)
            if kind == 0:
                command.update(type="Deposit", asset=r.enum(["BASE", "QUOTE"]), amount=r.number("q"))
            elif kind == 1:
                command.update(type="Place", clientOrderId=r.text(), side=r.enum(["BUY", "SELL"]), priceTicks=r.number("q"), quantityLots=r.number("q"), timeInForce=r.enum(["GTC", "IOC"]))
            elif kind == 2:
                command.update(type="Cancel", orderId=r.number("q"))
            else:
                raise ValueError("Invalid cached command type")
            result = dict(code=r.enum(CODES), reason=r.text(), commandSeq=r.number("q"), orderId=r.number("q"), remainingQuantity=r.number("q"), tradeCount=r.number("i"))
            require(0 < result["commandSeq"] <= command_seq and result["commandSeq"] not in cache_sequences, "Duplicate/invalid result sequence")
            require(result["orderId"] >= 0 and result["remainingQuantity"] >= 0 and result["tradeCount"] >= 0, "Invalid cached result fields")
            cache_sequences.add(result["commandSeq"])
            cached[(ca, cp, request)] = {"command": command, "result": result}
        require(count == 0 or previous == high, "Producer high-water mismatch")
        producers.append(dict(accountId=account, producerId=producer, highWater=high, cachedCount=count))
    require(r.stream.tell() == len(data) - 32, "Trailing/unparsed canonical bytes")
    require(len(cached) <= limits[3], "Global cache bound exceeded")
    require(sum(v[0] + v[1] for v in accounts.values()) == total_base, "Base asset total mismatch")
    require(sum(v[2] + v[3] for v in accounts.values()) == total_quote, "Quote asset total mismatch")
    require(not order_ids or max(order_ids) < next_order, "Next order ID mismatch")
    return dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), checksumVerified=True, commandSeq=command_seq, eventSeq=event_seq, marketSeq=market_seq, limits=limits, resultCachePerProducer=cache_per, accounts=accounts, orders=orders, cache=cached, producers=producers)


def audit(directory, source):
    require(hashlib.sha256(source.read_bytes()).hexdigest() == SERIALIZER_SHA, "Serializer source differs from reviewed 52fb byte family")
    c = json.loads((directory / "configuration.json").read_text())
    manifest = json.loads((directory / "arrivals-archive.json").read_text())
    compressed = fingerprint((directory / "arrivals.csv.gz").open("rb"))
    decoded = fingerprint(gzip.open(directory / "arrivals.csv.gz", "rb"))
    raw = fingerprint((directory / "arrivals.csv").open("rb"))
    require(compressed == {"bytes": manifest["compressedBytes"], "sha256": manifest["compressedSha256"]}, "Compressed archive differs")
    require(decoded == raw == {"bytes": manifest["rawBytes"], "sha256": manifest["rawSha256"]}, "Decoded/raw archive differs")
    summary = json.loads((directory.parent.parent / "analysis/summary.json").read_text())
    trial = next(t for t in summary["trials"] if t["id"] == directory.name)
    require(trial["inputSha256"]["arrivals.csv"] == decoded["sha256"], "Analyzer input SHA differs")
    prepared = decode(directory / "prepared-snapshot.bin", c)
    final = decode(directory / "final-snapshot.bin", c)
    require(prepared["sha256"] == c["preparedSnapshotSha256"], "Prepared snapshot digest differs")
    # This failed trial is small enough that every executed request must still be cached.
    require(final["commandSeq"] < final["limits"][3] and all(p["highWater"] < final["resultCachePerProducer"] for p in final["producers"]), "Cache completeness cannot be inferred for this trial")
    require({v["result"]["commandSeq"] for v in final["cache"].values()} == set(range(1, final["commandSeq"] + 1)), "Snapshot cache does not cover every applied command")
    require(all(final["cache"].get(k) == v for k, v in prepared["cache"].items()), "Prepared request cache changed")
    outcomes, identities, known, unresolved, offered_by_identity = collections.Counter(), set(), [], [], {}
    initial_unknown = resolved = within = 0
    window_ns = c["scheduledArrivals"] * 10**9 // c["ratePerSecond"]
    with gzip.open(directory / "arrivals.csv.gz", "rt", newline="") as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == HEADER, "Original 33-column header differs")
        for index, row in enumerate(reader):
            require(None not in row and all(v is not None for v in row.values()), "Missing or extra CSV column")
            worker = index % c["workers"]
            key = (int(row["account_id"]), row["producer_id"], int(row["request_seq"]))
            require(int(row["index"]) == index and int(row["worker"]) == worker, "Index/worker mismatch")
            require(key == (1000100 + worker % 64, c["producerPrefix"] + "-w" + str(worker), index // c["workers"] + 1), "Original business identity differs")
            require(key not in identities and row["client_order_id"] == "ioc-" + c["producerPrefix"] + "-" + str(index), "Duplicate/changed command")
            require(int(row["planned_offset_ns"]) == index * 10**9 // c["ratePerSecond"], "Planned arrival differs")
            identities.add(key)
            offered_by_identity[key] = row
            outcomes[row["outcome"]] += 1
            unknown = row["unknown_at_initial_deadline"] == "true"
            initial_unknown += unknown
            if row["outcome"] == "CONFIRMED_ACCEPTED":
                require(key in final["cache"], "Known response absent from complete snapshot cache")
                cached = final["cache"][key]
                result = cached["result"]
                expected = dict(code=row["result_code"], reason=row["result_reason"], commandSeq=int(row["result_command_seq"]), orderId=int(row["order_id"]), remainingQuantity=0, tradeCount=int(row["trade_count"]))
                require(result == expected, "Known business response differs from canonical cached result")
                known.append((key, row))
                within += int(row["confirmed_offset_ns"]) <= window_ns
                resolved += unknown
            elif row["outcome"] == "UNKNOWN_UNRESOLVED":
                require(unknown and int(row["attempts"]) > 0 and row["confirmed_offset_ns"] == "", "Invalid unresolved row")
                unresolved.append((key, row))
            else:
                require(row["outcome"] in ("CLIENT_QUEUE_FULL_NOT_SENT", "WORKER_BLOCKED_UNKNOWN_NOT_SENT") and row["attempts"] == "0" and row["execute_started_offset_ns"] == row["confirmed_offset_ns"] == "", "Invalid not-sent outcome")
                require(key not in final["cache"], "Explicitly not-sent identity exists in complete snapshot")
    require(len(identities) == c["scheduledArrivals"], "Not every planned arrival is present")
    require(initial_unknown == resolved + len(unresolved), "Unknown accounting mismatch")
    new_cache = {k: v for k, v in final["cache"].items() if v["result"]["commandSeq"] > prepared["commandSeq"]}
    require(len(new_cache) == final["commandSeq"] - prepared["commandSeq"], "Applied command coverage mismatch")
    bought = collections.Counter()
    for key, cached in new_cache.items():
        require(key in offered_by_identity, "Applied measured identity absent from raw offered CSV")
        row, command, result = offered_by_identity[key], cached["command"], cached["result"]
        expected_command = dict(type="Place", accountId=key[0], producerId=key[1], requestSeq=key[2], clientOrderId=row["client_order_id"], side="BUY", priceTicks=c["priceTicks"], quantityLots=1, timeInForce="IOC")
        require(command == expected_command and result["code"] == "ACCEPTED" and result["tradeCount"] == 1 and result["remainingQuantity"] == 0, "Executed cached command/business effect differs")
        order = final["orders"][(key[0], command["clientOrderId"])]
        require(order["orderId"] == result["orderId"] and order["acceptedCommandSeq"] == result["commandSeq"] and order["remainingQuantity"] == 0 and order["status"] == "FILLED", "Executed order differs from cached result")
        bought[key[0]] += 1
    count, price, warmup = len(new_cache), c["priceTicks"], c["warmupCommands"]
    require(final["eventSeq"] - prepared["eventSeq"] == final["marketSeq"] - prepared["marketSeq"] == 2 * count, "Executed event deltas differ")
    require(len(final["orders"]) == len(prepared["orders"]) + count, "Retained order delta differs")
    require(final["accounts"][1000001] == [0, c["seededMakerQuantity"] - warmup - count, (warmup + count) * price, 0], "Seller assets differ")
    require(final["accounts"][1000002] == [warmup, 0, 0, 0], "Warmup buyer assets differ")
    for account in range(1000100, 1000100 + c["seededBuyerAccounts"]):
        require(final["accounts"][account] == [bought[account], 0, c["seededQuotePerBuyer"] - bought[account] * price, 0], "Measured buyer assets differ")
    details = []
    for key, row in unresolved:
        cached = final["cache"].get(key)
        details.append(dict(arrivalIndex=int(row["index"]), worker=int(row["worker"]), accountId=key[0], producerId=key[1], requestSeq=key[2], clientOrderId=row["client_order_id"], command=dict(type="Place", accountId=key[0], producerId=key[1], requestSeq=key[2], clientOrderId=row["client_order_id"], side="BUY", priceTicks=price, quantityLots=1, timeInForce="IOC"), originalOutcome=row["outcome"], originalAttempts=int(row["attempts"]), originalInitialUnknown=True, originalError=row["error"], snapshotObservation="CACHED_ACCEPTED" if cached else "ABSENT_FROM_THIS_FROZEN_SNAPSHOT", cachedResult=cached["result"] if cached else None))
    known_sequences = {int(row["result_command_seq"]) for _, row in known}
    missing = sorted({v["result"]["commandSeq"] for v in new_cache.values()} - known_sequences)
    first_gap = missing[0] if missing else None
    first_after = min((row for _, row in known if int(row["result_command_seq"]) > first_gap), key=lambda row: int(row["result_command_seq"])) if first_gap else None
    return dict(schemaVersion=1, test="read-only-canonical-core-unknown-audit", sourceSerializer=dict(path=str(source), sha256=SERIALIZER_SHA, magic="0x564D4331", version=2, UTF16CodeUnits=True), sourceLoadRevision="52fbf7fa46ed274891a2bbf0d9fba9d87456d1f5", run=str(directory), archive=dict(compressed=compressed, decoded=decoded, retainedRaw=raw, analyzerInputSha256=trial["inputSha256"]["arrivals.csv"], fullRows=len(identities), fullColumns=len(HEADER)), originalOutcomes=dict(outcomes), originalInitialUnknown=initial_unknown, originalResolvedAfterInitialUnknown=resolved, originalWithinWindow=within, originalArrivalWindowGoodput=within * 1e9 / window_ns, originalClassification=trial["classification"], preparedSnapshot=dict(bytes=prepared["bytes"], sha256=prepared["sha256"], commandSeq=prepared["commandSeq"]), finalSnapshot=dict(bytes=final["bytes"], sha256=final["sha256"], checksumVerified=True, commandSeq=final["commandSeq"], eventSeq=final["eventSeq"], marketSeq=final["marketSeq"], retainedOrders=len(final["orders"]), cachedResults=len(final["cache"]), producers=len(final["producers"]), actualMeasuredCommands=count, limits=final["limits"], resultCachePerProducer=final["resultCachePerProducer"]), allKnownRepliesMatchCanonicalCachedResults=True, allExecutedMeasuredCommandsMatchOriginalPayloads=True, independentAccountConservationVerified=True, independentRetainedOrderAndEventDeltaVerified=True, cacheCompleteForThisFrozenSnapshot=True, unresolvedCount=len(details), unresolvedCachedAccepted=sum(x["cachedResult"] is not None for x in details), unresolvedAbsentFromFrozenSnapshot=sum(x["cachedResult"] is None for x in details), firstMissingKnownCommandSeq=first_gap, firstMissingIdentity=next((dict(accountId=k[0], producerId=k[1], requestSeq=k[2], clientOrderId=v["command"].get("clientOrderId")) for k, v in new_cache.items() if v["result"]["commandSeq"] == first_gap), None), firstKnownReplyAfterGap=first_after, unresolved=details, scope="Post-load observation of a checksum-protected canonical core, with serializer source pinned and independent byte parsing. Does not change original UNKNOWN outcomes, response times, validity or goodput; cached acceptance is not an original client confirmation. Absence is only at this frozen snapshot, not proof of permanent nonexecution. Outbox checkpoint/recovery is not parsed or proven; no request is sent.", validatorFinding="Confirmed-only replay omitted executed unresolved identities before comparing later result sequence/order IDs. This explains the reported first business mismatch without establishing a matching-engine/reply defect. Original benchmark remains invalid/incomplete.", passed=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--serializer-source", type=Path, default=Path("core/src/main/java/io/vectormatch/core/MatchingEngine.java"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.directory, args.serializer_source)
    result["auditToolSha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        require(not args.output.exists(), "Refusing to overwrite an existing audit receipt")
        args.output.write_text(text)
        print(json.dumps({"passed": True, "output": str(args.output), "unresolved": result["unresolvedCount"], "cachedAccepted": result["unresolvedCachedAccepted"], "absentAtSnapshot": result["unresolvedAbsentFromFrozenSnapshot"]}))
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
