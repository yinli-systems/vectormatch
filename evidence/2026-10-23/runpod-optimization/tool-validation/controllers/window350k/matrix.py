"""Run the exact registered whole-concurrency comparison with pinned immutable tools."""
import campaign as c


def main():
    root = c.EVIDENCE / 'window350k'
    plan = c.read_json(root / 'plan.json')
    identity = c.validate_identity(plan)
    assert c.pilot_prerequisites(identity) == plan['pilotPrerequisites'], 'Pilot evidence changed'
    expected = [(f'w-window-26000-w{workers}-r{repetition}', workers)
                for repetition in (1, 2) for workers in (128, 256)]
    assert [(task['id'], task['workers']) for task in plan['trials']] == expected
    assert plan['loadWholeProcessTimeoutSeconds'] == 600 and plan['validationTimeoutSeconds'] == 600
    prepared = plan['preparedSnapshotSha256']
    assert prepared == plan['pilotPrerequisites']['preparedSnapshotSha256']
    c.configure(identity)
    for task in plan['trials']:
        assert c.pilot_prerequisites(identity) == plan['pilotPrerequisites'], 'Pilot evidence changed'
        assert (task['rate'], task['arrivals']) == (26000, 350000)
        assert task['cohort'] == 'w' + str(task['workers'])
        assert task['phase'] == 'window350k-concurrency-configuration-control'
        c.run_task(root, task, plan, identity, prepared)
    c.OUT = root
    c.record('window350k-concurrency-matrix-completed', budget=c.budget(0))
    print('WINDOW350K_MATRIX_COMPLETE_INSPECT_BEFORE_NEXT_FACTOR', flush=True)


if __name__ == '__main__':
    main()
