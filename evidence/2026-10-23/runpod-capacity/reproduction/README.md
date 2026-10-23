# Orchestration capture

These are the exact orchestration sources used for this campaign, captured before the screening sweep. No SSH private key is included. `connections.json` contains only the previously authorized lab network/price metadata.

To reproduce the live lab layout, place `campaign.py`, `screen.py`, and `install-tools.py` in ignored `runtime/cloud/capacity-20261023/`, put `remote.py` and a local `resources.json` (from connections.json with your own servers) in ignored `runtime/cloud/runpod-20261023/`, and supply your SSH key and known_hosts at the paths declared by remote.py. Build a committed release with the repository Gradle installDist tasks, transfer the libraries plus deploy scripts, and create current-release.json with revision/root/bundleSha256. The pinned original release is only the retained demonstration platform; substitute a real original release when testing another lab.

`prepare` pauses the retained original application after Linux tool checks. `trial ID RATE ARRIVALS WORKERS PHASE REP` uses isolated state and never overwrites evidence. `finish ID` resumes only export/stop after an interrupted local exporter; it does not resend load. `restore` resumes the retained original application. Follow docs/CAPACITY_CAMPAIGN.md.

The Java CLI can also be invoked independently against three prestarted members; its configuration.json records every load parameter. Raw evidence is synthetic, and all SHA manifests can be recomputed locally.
