"""Register one bounded 350k checkpoint pilot, only after audited threading completion."""
import campaign as c


def main():
    prior = c.threading_prerequisites()
    identity = c.artifact_inputs(require_upload=True)
    root = c.EVIDENCE / 'window350k'
    for path in (root / 'pilot-plan.json', root / 'plan.json', root / 'pilot/campaign.json'):
        assert not path.exists(), 'Existing registration must be inspected, never overwritten: ' + str(path)
    assert not (root / 'pilot/runs/w-pilot-10000-w128').exists(), 'Pilot ID already exists; never replay'
    configuration = c.campaign_configuration(identity, prior, 128, pilot=True)
    plan = {'registeredAtUtc': c.now(), **identity, 'threadingPrerequisites': prior,
            'controllerSha256': {name: c.digest(c.BASE / name) for name in c.CONTROLLERS},
            'preparedSnapshotPolicy': 'Initially unknown. Pilot must prove exact fixture/canonical final state and full raw prepared-snapshot.bin hash; subsequent formal registration pins that hash.',
            'trials': [{'id': 'w-pilot-10000-w128', 'cohort': 'pilot', 'rate': 10000,
                        'arrivals': 350000, 'workers': 128,
                        'phase': 'window350k-full-checkpoint-pilot', 'repetition': 1}],
            'budget': c.budget(900), 'newResources': 0, 'localFreeBytesPerTrialMinimum': 1073741824,
            'loadWholeProcessTimeoutSeconds': 600, 'validationTimeoutSeconds': 600,
            'scope': 'Single 35-second arrival-window pilot. Full evidence, including invalid/failure CSVs, must be analyzed and archived losslessly. Do not silently raise the deadline for one side.'}
    manifest = c.read_json(root / 'node-deployment-manifest.json')
    c.exclusive_save(root / 'pilot/campaign.json', configuration)
    c.exclusive_save(root / 'pilot/deployment.json', identity['node'])
    c.exclusive_save(root / 'pilot/deployment-manifest.json', manifest)
    c.exclusive_save(root / 'pilot-plan.json', plan)
    print('WINDOW350K_PILOT_REGISTERED_NO_LOAD_SUBMITTED', flush=True)


if __name__ == '__main__':
    main()
