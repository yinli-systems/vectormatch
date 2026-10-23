"""Register W128/W256/W128/W256 only after the complete 350k pilot passes audit."""
import campaign as c


def main():
    prior = c.threading_prerequisites()
    identity = c.artifact_inputs(require_upload=True)
    pilot = c.pilot_prerequisites(identity)
    prepared = pilot['preparedSnapshotSha256']
    root = c.EVIDENCE / 'window350k'
    assert not (root / 'plan.json').exists(), 'Formal plan exists; inspect/resume exact IDs'
    for cohort in ('w128', 'w256'):
        assert not (root / cohort / 'campaign.json').exists(), 'Partial formal registration exists; never overwrite'
    trials = [{'id': f'w-window-26000-w{workers}-r{repetition}', 'cohort': f'w{workers}',
               'rate': 26000, 'arrivals': 350000, 'workers': workers,
               'phase': 'window350k-concurrency-configuration-control', 'repetition': repetition}
              for repetition in (1, 2) for workers in (128, 256)]
    for task in trials:
        assert not (root / task['cohort'] / 'runs' / task['id']).exists(), 'Existing trial ID; never replay'
    budget = c.budget(3000)
    manifest = c.read_json(root / 'node-deployment-manifest.json')
    for workers in (128, 256):
        cohort = root / f'w{workers}'
        c.exclusive_save(cohort / 'campaign.json', c.campaign_configuration(identity, prior, workers, prepared_sha=prepared))
        c.exclusive_save(cohort / 'deployment.json', identity['node'])
        c.exclusive_save(cohort / 'deployment-manifest.json', manifest)
    c.exclusive_save(root / 'plan.json', {'registeredAtUtc': c.now(), **identity,
                     'threadingPrerequisites': prior, 'pilotPrerequisites': pilot,
                     'controllerSha256': {name: c.digest(c.BASE / name) for name in c.CONTROLLERS},
                     'preparedSnapshotSha256': prepared, 'trials': trials, 'budget': budget,
                     'newResources': 0, 'localFreeBytesPerTrialMinimum': 1073741824,
                     'loadWholeProcessTimeoutSeconds': 600, 'validationTimeoutSeconds': 600,
                     'scope': 'Whole concurrency configuration comparison, including total FIFO capacity. Same artifact/maxSessions256/fixture/heap/sync2/receive131072/SHARED on both sides. Preserve all overloaded, invalid and failed evidence; never reissue an existing ID.'})
    print('WINDOW350K_FORMAL_REGISTERED_NO_LOAD_SUBMITTED', len(trials), flush=True)


if __name__ == '__main__':
    main()
