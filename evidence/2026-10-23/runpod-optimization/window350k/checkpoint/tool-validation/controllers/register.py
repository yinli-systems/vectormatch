"""Register the separate pilot checkpoint job; never starts a JVM or takes a snapshot."""
import common as p


def main():
    assert not (p.OUT / 'plan.json').exists(), 'Checkpoint registered already; inspect exact ID'
    assert not (p.OUT / 'runs' / p.JOB_ID).exists(), 'Checkpoint attempted already; never automatically reissue'
    c, identity = p.campaign()
    prior = p.prerequisites()
    budget = c.budget(900)
    p.save(p.OUT / 'plan.json', {'jobId': p.JOB_ID, 'registeredAtUtc': c.now(), 'identity': identity,
           'prerequisites': prior, 'sourceSha256': p.digest(p.SOURCE), 'classSha256': p.digest(p.CLASS),
           'controllerSha256': {name: p.digest(p.BASE / name) for name in ('common.py', 'register.py', 'run.py')},
           'expectedCoreSha256': p.CORE_SHA, 'expectedCoreBytes': 57682277,
           'expectedCommandSeq': 350167, 'expectedEventSeq': 700267, 'expectedMarketSeq': 700201,
           'expectedExportedSeq': 0, 'expectedPending': 700267,
           'wholeJobBudgetSeconds': 900, 'snapshotCommandTimeoutSeconds': 180,
           'snapshotRecoveryWaitSeconds': 180, 'fullPostProbeTimeoutSeconds': 600,
           'budget': budget, 'newResources': 0, 'requireAllKnownTestProcessesStopped': True,
           'independentlyEnumeratedOutboxPayload': False,
           'scope': 'Separate capacity-350k-v1 pilot state on unchanged52fb artifacts. Precheck replicated hash/sequences/watermark; official full core+outbox snapshot; three WRITTEN logs and new RecordingLog metadata; stop exact owned JVMs; cold-restart same directories/artifact; three RESTORED logs and full canonical core read. No business command, ACK, Pod stop, native/PG backup or archive payload export. Original pilot evidence unchanged. Cold JVM recovery is not a power-loss durability test.'})
    print('PILOT_CHECKPOINT_REGISTERED_NO_CLOUD_ACTION', p.JOB_ID, flush=True)


if __name__ == '__main__':
    main()
