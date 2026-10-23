# Controlled 64/128-client comparison

The node JVMs continue to use the exact 8b4bea3 release and configuration from the extended campaign: leader 0, sync=2, 1 GiB heaps, 262144 outbox, MTU1248, maxsessions128. Only the separately identified load-generator release changes. Both W64 and W128 controls use that same new release/profile.

The prepared state remains byte-identical (64 buyer accounts; distinct producers share accounts by worker modulo64). At most eight client constructors run concurrently before the timed window. There is a 12-second quiet interval after setup closes and before final validation connects, outside measurement, to permit session cleanup under the default 10-second session timeout. All measurement workers remain connected and participate concurrently. Raw wait timing is retained.

Compare 8000/s W64 against W128, then 9000/s W128 if the scheduler and state checks remain valid. Refine/repeat any observed transition. CPU, quota, scheduling and memory evidence must distinguish generator saturation from a server limit. The 90k bound still permits >=10-second windows only up to9000/s; this bound must never be presented as the server ceiling.
