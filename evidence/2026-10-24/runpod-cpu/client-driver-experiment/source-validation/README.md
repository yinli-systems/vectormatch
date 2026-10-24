# Experimental client shared-driver max park

Candidate ebede54 on codex/client-driver-park is not deployed or promoted. Node and owner/synchronous idle remain unchanged;opt-in property changes only the client sharedMediaDriver maximum park. Same candidateJAR must be used for both futureA1ms/B100us arms.

Full Gradlecheck+installDist succeeded:134passed,0failed,11PostgreSQL integration tests explicitly skipped because VM_TEST_PG_URL is absent. The six new policy tests include actual embedded drivers,property entry validation,and clean close;37load/mux tests also passed. Initial full-check.json's strict report gate expectedzero skipped and is retained;full-check-reviewed.json identifies the exact11skips and narrows acceptance to the configured non-Postgres scope. No PG or performance claim is inferred.

The actual measured mux driver produces one immutable startup observation in configuration/load-result/result; unavailable evidence stays explicitly unavailable. Source files and build log hashes are retained. Cloud source433capacity trials continue separately.
