"""Run only the exact registered pilot; existing IDs are never resubmitted."""
import campaign as c


def main():
    root = c.EVIDENCE / 'window350k'
    plan = c.read_json(root / 'pilot-plan.json')
    identity = c.validate_identity(plan)
    assert len(plan['trials']) == 1
    task = plan['trials'][0]
    assert task == {'id': 'w-pilot-10000-w128', 'cohort': 'pilot', 'rate': 10000,
                    'arrivals': 350000, 'workers': 128,
                    'phase': 'window350k-full-checkpoint-pilot', 'repetition': 1}
    assert plan['loadWholeProcessTimeoutSeconds'] == 600 and plan['validationTimeoutSeconds'] == 600
    c.configure(identity)
    row = c.run_task(root, task, plan, identity)
    c.OUT = root
    c.record('window350k-pilot-completed', trial=row, budget=c.budget(0))
    print('WINDOW350K_PILOT_COMPLETE_INSPECT_BEFORE_FORMAL_REGISTRATION', flush=True)


if __name__ == '__main__':
    main()
