# Preserved first observer failure

Actual JMH A1 Java run completed successfully, but the owned-process observer saw0/45forks, so the experiment gate failed and no B1/A2/B2 stage launched. All raw scores/logs,original worker/registration and failure/cleanup receipts remain unchanged. This A1 is not reused as a control in a later corrected experiment. A new Linux probe separately checks non-main-thread child semantics. No core business mismatch was found; no code speedup is claimed.
