"""Register one exact same-key recovery job. No process is started by registration."""
import hashlib
import json
import common as u


def main():
    assert not (u.OUT / 'plan.json').exists(), 'Recovery already registered; inspect exact job, never overwrite'
    assert not (u.OUT / 'runs' / u.JOB_ID).exists(), 'Recovery already attempted; never reissue'
    c, identity = u.campaign()
    observed = u.inputs()
    budget = c.budget(900)
    classes = {name: u.digest(u.CLASS.parent / name)
               for name in ('UnknownRecoveryProbe.class', 'UnknownRecoveryProbe$Saved.class')}
    bundle_sha = hashlib.sha256(json.dumps(classes, sort_keys=True).encode()).hexdigest()
    commands = observed.pop('commands').encode()
    with (u.OUT / 'commands.tsv').open('xb') as stream:
        stream.write(commands)
    known_states = {observed['state']}
    for cohort in ('pilot', 'w128', 'w256'):
        directory = u.WINDOW / cohort / 'runs'
        if directory.exists():
            for trial in directory.glob('*/trial.json'):
                value = u.read(trial)
                assert value['release'] == identity['node']['root']
                known_states.add(value['state'])
    u.save(u.OUT / 'plan.json', {'jobId': u.JOB_ID, 'registeredAtUtc': c.now(), 'identity': identity,
           'state': observed['state'], 'knownTestStates': sorted(known_states),
           'inputSha256': observed['proofs'], 'preCoreSha256': observed['preCoreSha256'],
           'commandsSha256': hashlib.sha256(commands).hexdigest(),
           'sourceSha256': u.digest(u.SOURCE), 'classSha256': u.digest(u.CLASS),
           'classFiles': classes, 'classBundleSha256': bundle_sha,
           'controllerSha256': {name: u.digest(u.BASE / name) for name in ('common.py', 'register.py', 'run.py')},
           'expectedExportedSeq': 0, 'expectedPending': 7385, 'expectedCached': 252, 'expectedFrozenAbsent': 4,
           'expectedPostCoreSha256': 'a29e6d2b4135f5a779f980bb40eac6752cda8e9790f1dd5aa1d4d5fee243dff9',
           'wholeRecoveryBudgetSeconds': 900, 'probeDeadlineSeconds': 600, 'budget': budget,
           'originalCapacityRoundRemainsInvalid': True, 'newResources': 0,
           'scope': 'One fresh client resolves exact 256 original saved keys against immutable52fb failed-W256 state. Exclusive local directory and remote start marker forbid resubmission after ambiguous failure. Frozen absence is not proof of historical nonexecution. Original CSV/results/latency/status are never modified; no ACK, Pod stop or node artifact replacement.'})
    print('UNKNOWN_RECOVERY_REGISTERED_NO_COMMAND_SENT', u.JOB_ID, flush=True)


if __name__ == '__main__':
    main()
