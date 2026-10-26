# Conserved multi-market escrow, version 1

Implemented in `MarketEscrow`; not connected to Aeron groups or deployed yet.
This is a bounded static-funded risk ledger and independent matching books. It
adds no production authentication, dynamic withdrawals, cross-book atomic trades,
or portfolio-margin guarantee. No 6/12/24-machine result follows from these tests.

An issuer owns each account/asset balance. A transfer identity binds account,
market, asset, amount and destination replication-group ID. The issuer subtracts
available funds before returning an HMAC-SHA256 grant. Same identity/payload
returns the original grant; a different payload conflicts. Rejected transfers
also have permanent bounded outcomes. The destination verifies issuer, market,
group, asset and signature, then credits its normal integer matching engine once.
Its permanent receipt registry is separate from the engine's evictable request
cache. Out-of-order grants use independent reserved producer identities. Business
commands cannot call Deposit or use that namespace.

A receipt binds the exact grant and committed destination command sequence. Lost
receipt or ACK leaves the parent transfer PENDING: it does not return available
funds. Delivering the grant again returns the same receipt. There is deliberately
no timeout refund or automatic reallocation API. Exhausted registries, account /
producer limits or destination supply bounds fail before destination mutation;
the parent credit remains reserved pending explicit operational resolution.
HMAC assumes a trusted issuer and trusted destination holding their scoped key;
it is not Byzantine proof or a client authorization mechanism.

Conservation counts parent available funds, every destination's available and
reserved assets, and grants not yet applied at a destination. PENDING at the
parent is not necessarily in transit: an ACK may have been lost after application.
Counting all PENDING grants as extra assets would double count those funds. Each
book retains the existing signed-long aggregate supply bound; BigInteger is used
only when auditing sums across independent books and parent balances.

Issuer and book snapshots have version, exact profile / market / issuer / key
fingerprint checks, permanent request/receipt registries, pending state, and a
SHA-256 checksum. Restore validates invariants and canonical bytes. Keys are
injected and defensively copied, never serialized. The checksum detects damage;
it does not authenticate a malicious snapshot. A real deployment still needs
replicated issuer state, durable grant delivery, managed key provisioning,
authenticated account access and recovery / reconciliation tooling.

Local Java21 `:core:test --offline` passed 57 tests with zero failures or skips,
including 15 escrow tests. They cover two books executing actual synthetic trades,
shared-USD overspending, conflicting retries, lost ACK, both sides restoring,
reordered grants, wrong scope / signatures, bounded registries, nonmutating supply
overflow, thread ownership and 600 seeded randomized loss / restart steps. These
are local functional tests, not independent physical-machine fault evidence.
