"""Only diagnostic directories and declared JAVA_TOOL_OPTIONS differ from reviewed execute lifecycle. No matching code or durability changes."""
def execute(base, release, release_path):
    before = preflight(base, release)
    base.enable_pidfd()
    JOB.mkdir(mode=0o700)
    (JOB/'recordings').mkdir(mode=0o700)
    (JOB/'jfr-repository').mkdir(mode=0o700)
    base.save(JOB / 'before.json', before)
    for source, name in [(Path(__file__), 'controller-source.py'), (HERE / 'owned_linux_base_8eeb.py', 'owned_linux_base_8eeb.py'),
                         (release_path, 'release.json')]:
        shutil.copy2(source, JOB / name)
    initial = allocated_scan(base, JOB)['allocatedBytes']
    registry = Registry(base, release, JOB)
    args = parent_argv(release)
    errors, parent, cleaning = [], None, False
    samples = []
    previous = {}
    def interrupted(signum, frame):
        if not cleaning:
            raise InterruptedError('Controller signal ' + str(signum))
    for signum in [signal.SIGTERM, signal.SIGINT, signal.SIGHUP]:
        previous[signum] = signal.signal(signum, interrupted)
    started = time.monotonic()
    telemetry = Telemetry(base, JOB, started)
    try:
        with (JOB / 'parent.log').open('xb') as log:
            parent = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                cwd=str(JOB), env={'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'TZ': 'UTC',
                'VECTOR_AERON_MTU_LENGTH': '1248', 'JAVA_TOOL_OPTIONS': release['diagnosticJavaToolOptions']}, start_new_session=True)
        # Direct child is retained before any fallible read/write/identity check.
        base.save(JOB / 'parent-launch-handle.json', {'pid': parent.pid, 'expectedArguments': args,
            'expectedCommandSha256': base.argv_digest(args), 'observedExecIdentityVerified': False})
        actual = base.process_identity(parent.pid)
        require(actual is not None, 'Parent exited before kernel identity capture')
        registry.record(actual, 'pilot-parent', 'independent-direct-child-proc')
        require(actual['arguments'] == args and actual['commandSha256'] == base.argv_digest(args), 'Parent kernel argv differs')
        while True:
            observation = monitor(base, registry, release, initial)
            telemetry.sample(registry)
            if len(samples) < 360:
                samples.append(dict(observation, elapsedSeconds=time.monotonic() - started,
                                    freeBytes=shutil.disk_usage(ROOT).free))
            if parent.poll() is not None:
                break
            require(time.monotonic() - started < EXECUTE_SECONDS, 'Execution deadline 240s; reserve 120s clean closure in overall 360s')
            time.sleep(0.5)
        require(parent.returncode == 0, 'Pilot parent failed; retain partial raw attempt')

    except BaseException as error:
        errors.append({'phase': 'execution', 'error': repr(error)})
    finally:
        cleaning = True
        try:
            closure = clean_all(base, registry, parent, args, started + TOTAL_SECONDS) if parent is not None else {
                'allOwnedStopped': True, 'reports': [], 'errors': [], 'noParentLaunched': True, 'forcedKill': False}
        except BaseException as error:
            closure = {'allOwnedStopped': False, 'errors': [{'error': repr(error)}], 'forcedKill': False}
        try:
            telemetry.sample(registry, phase='after-clean-stop-observation', force=True)
            base.save(JOB / 'telemetry-receipt.json', telemetry.close(closure['allOwnedStopped']))
        except BaseException as error:
            errors.append({'phase': 'telemetry-close', 'error': repr(error)})
            if not telemetry.stream.closed:
                telemetry.stream.close()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    base.save(JOB / 'monitor-samples.json', {'samples': samples, 'sampleCap': 360, 'pollSeconds': 0.5,
        'preservedOnExecutionFailure': True})
    base.save(JOB / 'python-owned-stop.json', closure)
    if not closure['allOwnedStopped']:
        base.save(JOB / 'BENCHMARK_BLOCKED.json', {'atUtc': base.now(), 'errors': errors + closure['errors'],
            'reason': 'Owned clean stop unconfirmed; no forced kill, no active-native hashing/archive, no next run'})
        raise RuntimeError('BENCHMARK_BLOCKED: strict owned clean shutdown unconfirmed')
    after_protected = protected_state(base, release)
    result = None
    try:
        if not errors:
            result = validate_result(base, registry, release)
    except BaseException as error:
        errors.append({'phase': 'proof-validation', 'error': repr(error)})
    archived = collect_stopped(base, release) if PAIR.exists() else {'noArmCreated': True}
    base.save(JOB / 'after-clean-stop.json', {'archive': archived, 'protectedOriginal': after_protected})
    base.save(JOB / 'completion.json', {'passed': not errors and result is not None, 'result': result, 'errors': errors,
        'allOwnedStopped': True, 'functionalPilotOnly': True, 'capacityOrEnduranceProven': False,
        'arm': ARM, 'serverDriverMaximumParkNs': selected_park_ns(), 'ownerPollMaximumParkNs': selected_owner_park_ns(), 'eventFetchCount':selected_event_page(),'readWindow':selected_read_window(),'commonReadWindow32Envelope':True,'commonEventFetchEnvelope':False, 'frozenReleaseSha256': FROZEN_RELEASE_SHA, 'noNewResources': True, 'hardKernelDeadlineGuaranteed': False, 'atUtc': base.now()})
    require(not errors and result is not None, 'Functional pilot failed; complete stopped raw attempt retained; no rerun')
    return {'passed': True, 'job': str(JOB), 'arm': ARM, 'serverDriverMaximumParkNs': selected_park_ns(), 'ownerPollMaximumParkNs': selected_owner_park_ns(), 'eventFetchCount':selected_event_page(),'readWindow':selected_read_window(),'commonReadWindow32Envelope':True,'commonEventFetchEnvelope':False, 'functionalPilotOnly': True, 'authoritativeRawQualificationStillRequired': True}
