"""Register only after audited network completion; never starts a remote process."""
import argparse
import pathlib
import campaign as c


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receive-bytes', type=int, choices=(131072, 1048576), required=True)
    options = parser.parse_args()
    prior = c.network_prerequisites()
    identity = c.artifact_inputs(require_upload=True)
    root = c.EVIDENCE / 'threading'
    assert not (root / 'plan.json').exists(), 'Already registered; inspect/resume exact existing trial IDs'
    source_cohort = 'receive128k' if options.receive_bytes == 131072 else 'receive1m'
    source = c.read_json(c.EVIDENCE / 'network' / source_cohort / 'campaign.json')
    for name in ('shared', 'dedicated'):
        assert not (root / name / 'campaign.json').exists(), 'Partial registration exists; inspect instead of overwriting'
    trials = []
    for repetition in (1, 2):
        for name, mode in (('shared', 'SHARED'), ('dedicated', 'DEDICATED')):
            trials.append({'id': f't-{name}-15000-w128-r{repetition}', 'cohort': name,
                           'driverThreading': mode, 'receiveBytes': options.receive_bytes,
                           'rate': 15000, 'arrivals': 190000, 'workers': 128,
                           'phase': 'node-driver-threading-control', 'repetition': repetition})
    controller = {name: c.digest(c.BASE / name) for name in ('campaign.py', 'register.py', 'matrix.py', 'deploy-node.py')}
    # Validate every prerequisite and reserve before creating any campaign record.
    budget = c.budget(3600)
    node_manifest = c.read_json(root / 'node-deployment-manifest.json')
    for name, mode in (('shared', 'SHARED'), ('dedicated', 'DEDICATED')):
        fixed = {**source['fixed'], 'driverThreadingArgument': mode, 'driverThreading': mode,
                 'driverIdleMaxSpins': 10, 'driverIdleMaxYields': 5,
                 'driverIdleMinParkNs': 1000, 'driverIdleMaxParkNs': 1000000,
                 'idleStrategy': 'BackoffIdleStrategy(10,5,1000,1000000), independent per driver role',
                 'socketReceiveBufferArgumentBytes': options.receive_bytes,
                 'socketReceiveBufferBytes': options.receive_bytes}
        configuration = {**source, 'registeredAtUtc': c.now(), 'fixed': fixed,
                         'clientDriverMode': 'shared', 'preparedSnapshotSha256': c.PREPARED_SHA,
                         'sourceCampaign': str(c.EVIDENCE / 'network' / source_cohort / 'campaign.json'),
                         'screeningRates': [15000], 'screeningWorkers': 128,
                         'reason': 'Only node MediaDriver scheduling mode changes. Same new node artifact in both groups; archive SHARED, sync2, receive buffer, client driver and all worker/request identities preserved.',
                         'scope': 'SHARED/DEDICATED/SHARED/DEDICATED at15k,190k,W128. Five driver idle instances use identical explicit10/5/1000/1000000 parameters. Dedicated mode has four driver runners; native-resource role is included. Finite-window path comparison, not an engine ceiling or long-run capacity proof.'}
        c.exclusive_save(root / name / 'campaign.json', configuration)
        c.exclusive_save(root / name / 'deployment.json', identity['node'])
        c.exclusive_save(root / name / 'deployment-manifest.json', node_manifest)
    c.exclusive_save(root / 'plan.json', {'registeredAtUtc': c.now(), **identity,
                     'receiveBytes': options.receive_bytes, 'preparedSnapshotSha256': c.PREPARED_SHA,
                     'networkPrerequisites': prior, 'controllerSha256': controller, 'trials': trials,
                     'budget': budget, 'newResources': 0,
                     'scope': 'Registration after complete valid network matrix; no load is submitted by registration. Preserve all valid overloaded results and all invalid/pending evidence; never reissue an existing ID.'})
    print('THREADING_REGISTERED', len(trials), 'receiveBytes', options.receive_bytes, flush=True)


if __name__ == '__main__':
    main()
