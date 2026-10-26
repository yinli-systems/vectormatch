"""Independent read-yield phase/credit contract; accepts legacy closed traces without widening them."""
import bisect
import collections


def validate(configuration, registration, summary, metadata, phases, arrivals):
    selected = configuration.get('readBankDispatchSelection')
    if selected is None:
        assert 'readBankDispatchSelection' not in registration
        assert 'readBankDispatchSelection' not in summary
        policy = 'CLOSED'
    else:
        assert selected == registration['readBankDispatchSelection'] == summary['readBankDispatchSelection']
        assert set(selected) == {'policy', 'maximumBusinessCommandsPerTurn', 'singleCallerTurn'}
        assert selected['policy'] in ('CLOSED', 'BOUNDED_TURN')
        assert type(selected['maximumBusinessCommandsPerTurn']) is int and selected['maximumBusinessCommandsPerTurn'] == 127
        assert selected['singleCallerTurn'] is True
        policy = selected['policy']
    enabled = policy == 'BOUNDED_TURN'
    assert metadata.get('interBankBusinessPolicy', 'CLOSED') == policy
    if selected is not None:
        assert type(metadata['maximumReadYieldCommands']) is int and metadata['maximumReadYieldCommands'] == 127
    if enabled:
        assert configuration['fileWorkDispatchPolicy'] == 'CONTINUE'
        assert type(configuration['maximumReadYieldTurns']) is int and configuration['maximumReadYieldTurns'] > 0
    times = [ns for ns, _ in phases]
    counts = collections.Counter()
    for row in arrivals:
        if not row['submit_offset_ns']:
            continue
        ns = configuration['scheduledOriginMonotonicNs'] + int(row['submit_offset_ns'])
        index = bisect.bisect_right(times, ns) - 1
        if index >= 0 and phases[index][1]['to'] == 'READ_YIELD':
            assert enabled
            counts[times[index]] += 1
    resume = None
    yield_started = None
    drains = {}
    turns = 0
    for ns, row in phases:
        origin, target = row['from'], row['to']
        if origin in ('READ_YIELD', 'READ_DRAIN') or target in ('READ_YIELD', 'READ_DRAIN'):
            assert enabled, 'new read phases require explicit bound selection'
        if target == 'READ_YIELD':
            assert resume is None and origin in ('ARCHIVE_READ', 'EVENT_READ')
            assert row['readBankOpen'] is False and type(row['pendingLogicalCommands']) is int and row['pendingLogicalCommands'] == 0
            assert type(row['readYieldCommands']) is int and row['readYieldCommands'] == 0 and row['resumeRead'] == origin
            resume, yield_started = origin, ns
            turns += 1
        elif origin == 'READ_YIELD':
            assert target == 'READ_DRAIN' and resume is not None
            assert row['readBankOpen'] is False and row['resumeRead'] == resume
            assert type(row['readYieldCommands']) is int and 0 <= row['readYieldCommands'] <= 127
            assert counts[yield_started] == row['readYieldCommands'], 'raw admissions differ from bounded turn'
            drains[ns] = yield_started
        elif origin == 'READ_DRAIN':
            assert target == resume and type(row['pendingLogicalCommands']) is int and row['pendingLogicalCommands'] == 0
            assert row['readBankOpen'] is False and row['resumeRead'] == 'NONE'
            resume, yield_started = None, None
        else:
            assert resume is None and target != 'READ_DRAIN'
    assert resume is None
    if enabled:
        assert turns <= configuration['maximumReadYieldTurns']
    return enabled, drains
