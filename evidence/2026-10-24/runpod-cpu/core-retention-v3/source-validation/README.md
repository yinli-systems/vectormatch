# Core bounded-retention V3 candidate

Candidate109ae1800f0b76620af344a3dd7543849ffffd69 on private branch codex/core-retention-v3 is a separate opt-in core prototype; it is not deployed to the CPU capacity cluster. All frozen source/fixture file SHA values in its validation manifest match the copied files. Root independently ran full Gradlecheck+clusterDist:140configured tests pass,0failures,11PostgreSQL integration tests skipped because noDBfixture is configured. The dedicated core run contains29JUnit methods,including14V3 tests and one legacygolden method that checks92full snapshot prefixes and their restored suffixes.92prefixes are not92JUnit methods.

The new facade keeps permanent producer high-water and bounded retries,records full command/result/events and newly terminal identities,requires exact prefix archive ACK before compaction,and restores a separate bounded64MiB canonical snapshot. Actual local traces include100fresh accepted orders beyond a hot cap4,and independent flat-reference trace/restore/ACK comparisons. They do not prove million/hundred-million execution,cluster/wire integration,external archive durability,UNKNOWN recovery or any new performance number.

The unimplemented Cluster/export/harness work is recorded separately in the project endurance design. Existing capacity evidence stays tied to originalsource433and clientcandidateebede54.
