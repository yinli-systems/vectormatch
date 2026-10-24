import base64,hashlib,json,os,pathlib,stat,platform
SOURCE='d92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8'
CODE='87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa'
RELEASE='0ebad5d1ae1bd7900fc6dad7d78994d11ec3281f4077cfb7eba9b1bb3f506d59'
CONTROLLER='eb84eed09cad46c5097c32d980a1629f7c7c7fec3759e904544f7ef9e91e3100'
PREP='/opt/vectormatch-cpu/preparation/cpu-event-fetch-cloud-abab-r1'
REPOSITORY='yinli-systems/vectormatch'
PAGE_ORDER=(16, 32, 16, 32)
def need(ok, message):
    if not ok:
        raise AssertionError(message)

def digest(data):
    return hashlib.sha256(data).hexdigest()

def hexsha(value, length=64):
    return isinstance(value, str) and len(value) == length and all(c in '0123456789abcdef' for c in value)

def page(arm):
    need(type(arm) is int and arm in (1, 2, 3), 'Only preceding arms1..3 produce next-arm prerequisites')
    return PAGE_ORDER[arm - 1]

def validate_pair(gate, push, arm, push_sha):
    selected = page(arm)
    need(gate['schemaVersion'] == 2 and gate['scope'] == 'ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_ARM_COLLECTION'
         and gate['collectionComplete'] is True and gate['arm'] == arm and gate['eventFetchCount'] == selected
         and gate['sourceCommit'] == SOURCE and gate['codeFingerprint'] == CODE
         and gate['frozenReleaseSha256'] == RELEASE and gate['controllerSha256'] == CONTROLLER
         and gate['ownerPollMaximumParkNs'] == 1000000 and gate['serverDriverMaximumParkNs'] == 100000,
         'Exact new Event Fetch prior gate identity')
    for key in ('localFullMemberShaBytesModesOwnersEmptyDirsVerified', 'allRawInputsAndFailuresRetained',
                'strictSchedulerTimingAdmission', 'sameNewArtifactFunctionalQualified',
                'allOriginalRawCanonicalAndThreeSnapshotsVerified'):
        need(gate[key] is True, 'Actual gate predicate: ' + key)
    for key in ('independentLocalCollectionReceiptSha256', 'closedArchiveSha256', 'closedNativeInventorySha256',
                'privatePushReceiptSha256', 'rootIndependentReviewSha256', 'rawAuditSha256'):
        need(hexsha(gate[key]), 'Original gate evidence SHA: ' + key)
    need(gate['privatePushReceiptSha256'] == push_sha, 'Exact private-push original bytes')
    need(push['schemaVersion'] == 1 and push['scope'] == 'ROOT_VERIFIED_PRIVATE_EVIDENCE_PUSH'
         and push['repository'] == REPOSITORY and push['visibility'] == 'private'
         and push['pushCompleted'] is True and push['remoteCommitVerified'] is True
         and push['fullOriginalEvidencePushed'] is True and hexsha(push['commit'], 40)
         and push['actualLsRemote'].split() == [push['commit'], 'refs/heads/main'], 'Actual private remote commit receipt')
    need(push['evidencePath'] == 'evidence/2026-10-24/runpod-cpu/retention-event-fetch-v3/cloud-arm-%d-r1' % arm,
         'Exact arm full-evidence path')
    for key in ('evidenceManifestSha256', 'evidenceClosedSha256', 'repositoryMetadataReceiptSha256'):
        need(hexsha(push[key]), 'Private full-evidence SHA')
    for key in ('closedArchiveSha256', 'closedNativeInventorySha256', 'rootIndependentReviewSha256'):
        need(push[key] == gate[key], 'Gate/private-push actual evidence binding: ' + key)
    return True

def validate_payload(payload, arm):
    page(arm)
    expected = {'release/arm-%d-collection-gate.json' % arm, 'release/arm-%d-private-push.json' % arm}
    need(set(payload) == expected, 'Exactly two arm-specific prior JSON names, no alternate destination')
    decoded = {}
    for name, row in payload.items():
        need(set(row) == {'data', 'sha256', 'bytes', 'mode'} and row['mode'] == 0o600
             and type(row['bytes']) is int and 0 < row['bytes'] <= 65536 and hexsha(row['sha256']), 'Bounded exact prior JSON row')
        data = base64.b64decode(row['data'], validate=True)
        need(len(data) == row['bytes'] and digest(data) == row['sha256'], 'Original prior JSON bytes')
        decoded[name] = data
    gate_name = 'release/arm-%d-collection-gate.json' % arm
    push_name = 'release/arm-%d-private-push.json' % arm
    validate_pair(json.loads(decoded[gate_name]), json.loads(decoded[push_name]), arm, digest(decoded[push_name]))
    return decoded

def exclusive_write_pair(prep, payload, arm):
    """Same function executes on remote; local guards use isolated temporary directories only."""
    decoded = validate_payload(payload, arm)
    prep = pathlib.Path(prep)
    for path in (prep, *prep.parents, prep / 'release'):
        need(not path.is_symlink(), 'No linked destination ancestor')
    need(prep.is_dir() and (prep / 'release').is_dir(), 'Existing canonical release directory only')
    # Validate BOTH absences before the first write. Partial syscall failures are preserved, never deleted/retried.
    for name in decoded:
        need(not os.path.lexists(prep / name), 'Exclusive prior file already exists')
    directory = os.open(prep / 'release', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name, data in sorted(decoded.items()):
            leaf = pathlib.PurePosixPath(name).name
            fd = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'wb') as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            check = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
            with os.fdopen(check, 'rb') as source:
                actual = source.read(65537)
                s = os.fstat(source.fileno())
            need(actual == data and stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and stat.S_IMODE(s.st_mode) == 0o600,
                 'Exact exclusive uploaded SHA/mode/link readback')
        os.fsync(directory)
    finally:
        os.close(directory)
    return {'passed': True, 'arm': arm, 'eventFetchCount': page(arm),
            'uploaded': {name: digest(data) for name, data in decoded.items()},
            'businessStarted': False, 'noOverwrite': True, 'noDeletionOrRetry': True}

payload={'release/arm-2-collection-gate.json': {'data': 'ewogICJhbGxPcmlnaW5hbFJhd0Nhbm9uaWNhbEFuZFRocmVlU25hcHNob3RzVmVyaWZpZWQiOiB0cnVlLAogICJhbGxSYXdJbnB1dHNBbmRGYWlsdXJlc1JldGFpbmVkIjogdHJ1ZSwKICAiYXJjaGl2ZVJvb3RSZXZpZXdTaGEyNTYiOiAiYWE0NWFhNmYzNGZmN2UyMGUxYzBkMjE1YTUyYzk5ZmVmNTQ0NjE1ZTNiMmNiNGVkNWExNTJlYWJhNmZiNDIyYiIsCiAgImFybSI6IDIsCiAgImF0VXRjIjogIjIwMjYtMTAtMjRUMTE6NTY6MzQuNTg1Nzc1KzAwOjAwIiwKICAiY2xvc2VkQXJjaGl2ZVNoYTI1NiI6ICI4Yzg1NWI2NTg3ZmIwOWUwZWMzM2E5Yjc2NDMzMjZhOTE2NTdkYWQzMmVhMzVkNTNkYjE1ZDYyN2VlZGY0MDFmIiwKICAiY2xvc2VkTmF0aXZlSW52ZW50b3J5U2hhMjU2IjogIjM2NzJlMjM3ZTVlYjAyNGI3MGYyMDljNTI3Mzc0MTRkZGQ0Yjc0NjUyZDJjYWVkN2U2ZjFmZmJjNWEyZWJlNjIiLAogICJjb2RlRmluZ2VycHJpbnQiOiAiODdhN2NjZDA5MmY0ZDNjODkwYmY4Y2M4YmQ3YzZmZmNkMTg5MDA4Mzg2OTljZDJiODczZmQxOTMxY2RkYjZhYSIsCiAgImNvbGxlY3Rpb25Db21wbGV0ZSI6IHRydWUsCiAgImNvbnRyb2xsZXJTaGEyNTYiOiAiZWI4NGVlZDA5Y2FkNDZjNTA5N2MzMmQ5ODBhMTYyOWY3YzdjN2ZlYzM3NTllOTA0NTQ0ZjdlZjllOTFlMzEwMCIsCiAgImV2ZW50RmV0Y2hDb3VudCI6IDMyLAogICJmcm96ZW5SZWxlYXNlU2hhMjU2IjogIjBlYmFkNWQxYWUxYmQ3OTAwZmM2ZGFkN2Q3ODk5NGQxMWVjMzI4MWY0MDc3Y2ZiN2ViYTliMWJiM2Y1MDZkNTkiLAogICJpbmRlcGVuZGVudExvY2FsQ29sbGVjdGlvblJlY2VpcHRTaGEyNTYiOiAiYTVkOTI4OThiNWQyYzE2ODcxNDJjY2FiMjZjNzk4N2EyNjJhMWViMjc3M2RlMDU5NGQ0ZjEwMGEyYWE0MmVhYyIsCiAgImxvY2FsRnVsbE1lbWJlclNoYUJ5dGVzTW9kZXNPd25lcnNFbXB0eURpcnNWZXJpZmllZCI6IHRydWUsCiAgIm93bmVyUG9sbE1heGltdW1QYXJrTnMiOiAxMDAwMDAwLAogICJwcml2YXRlUHVzaFJlY2VpcHRTaGEyNTYiOiAiMDY0MzJjZDcyYjFhZjIxOWJjMDE2NmE2MTJiN2EyMGJlNGE0ZjczODZmODQyY2YzOWM5YzA4MmZmYzc3Yzk1NiIsCiAgInJhd0F1ZGl0U2hhMjU2IjogIjMxYTM4MWY4NTVhYWVhOTMzYzM3NWZlNTUyY2MwZDM5ZmNlMjgyMTMxNjI5OThkNmY3NTM5YzZhMTBkODMwMTkiLAogICJyb290SW5kZXBlbmRlbnRSZXZpZXdTaGEyNTYiOiAiZWQ4YTllZTY5MTU5OTdiNzRhNTcxMGY1Zjk0YjI0ODlhM2UwYTM0ZDZiNjZjNjhiZDMzNTAwZGNmZmVjYmM2NiIsCiAgInNhbWVOZXdBcnRpZmFjdEZ1bmN0aW9uYWxRdWFsaWZpZWQiOiB0cnVlLAogICJzY2hlbWFWZXJzaW9uIjogMiwKICAic2NvcGUiOiAiUk9PVF9WRVJJRklFRF9DTE9TRURfQ1BVX0VWRU5UX0ZFVENIX0FSTV9DT0xMRUNUSU9OIiwKICAic2VydmVyRHJpdmVyTWF4aW11bVBhcmtOcyI6IDEwMDAwMCwKICAic291cmNlQ29tbWl0IjogImQ5MjMwMWQzMDU4YWNjODNjYjg1ZDViYzViNGZkMmUzZjBlZDRkZjgiLAogICJzb3VyY2VTaGEyNTYiOiAiNTM0ODFiYTlmOTU3NDM4ODA4MjNmNzdkOGIyZDJkMjYyYWM1NTZmMDNjZmQzOTUwMmJjODYwY2E3OWI1OGY2YiIsCiAgInN0cmljdFNjaGVkdWxlclRpbWluZ0FkbWlzc2lvbiI6IHRydWUKfQo=', 'sha256': '98abf3db23497ce2137e977fe5ef63f9cef9cb4738485cee3a0aad37d5616445', 'bytes': 1646, 'mode': 384}, 'release/arm-2-private-push.json': {'data': 'ewogICJhY3R1YWxMc1JlbW90ZSI6ICI5ZThjZjY2OTQ5Y2E2MGMwZmUwNzFmMTY5MWNiMzE0Njc3Yjk3NzMyXHRyZWZzL2hlYWRzL21haW4iLAogICJhcmNoaXZlUm9vdFJldmlld1NoYTI1NiI6ICJhYTQ1YWE2ZjM0ZmY3ZTIwZTFjMGQyMTVhNTJjOTlmZWY1NDQ2MTVlM2IyY2I0ZWQ1YTE1MmVhYmE2ZmI0MjJiIiwKICAiYXRVdGMiOiAiMjAyNi0xMC0yNFQxMTo1NjozNC41ODU3NzUrMDA6MDAiLAogICJjbG9zZWRBcmNoaXZlU2hhMjU2IjogIjhjODU1YjY1ODdmYjA5ZTBlYzMzYTliNzY0MzMyNmE5MTY1N2RhZDMyZWEzNWQ1M2RiMTVkNjI3ZWVkZjQwMWYiLAogICJjbG9zZWROYXRpdmVJbnZlbnRvcnlTaGEyNTYiOiAiMzY3MmUyMzdlNWViMDI0YjcwZjIwOWM1MjczNzQxNGRkZDRiNzQ2NTJkMmNhZWQ3ZTZmMWZmYmM1YTJlYmU2MiIsCiAgImNvbW1pdCI6ICI5ZThjZjY2OTQ5Y2E2MGMwZmUwNzFmMTY5MWNiMzE0Njc3Yjk3NzMyIiwKICAiZXZpZGVuY2VDbG9zZWRTaGEyNTYiOiAiMjVlZTliN2UzOWY2NTVjZjg5OWJlZTIxODQwNjAwYzMyYzdkMzA5OWM4NDUyOTU0ZDJiYzQ3MmNiYTM3NTY1NiIsCiAgImV2aWRlbmNlTWFuaWZlc3RTaGEyNTYiOiAiYTA1OWY2YTAwZWM4NWNkNTNmNTQ2NGRhZDcyMzc5YTczNzc2Mjk1ZWM1MjAwNTE2NjUyNGQxNWMzMDMxOGEwMCIsCiAgImV2aWRlbmNlUGF0aCI6ICJldmlkZW5jZS8yMDI2LTEwLTI0L3J1bnBvZC1jcHUvcmV0ZW50aW9uLWV2ZW50LWZldGNoLXYzL2Nsb3VkLWFybS0yLXIxIiwKICAiZnVsbE9yaWdpbmFsRXZpZGVuY2VQdXNoZWQiOiB0cnVlLAogICJwdXNoQ29tcGxldGVkIjogdHJ1ZSwKICAicmVtb3RlQ29tbWl0VmVyaWZpZWQiOiB0cnVlLAogICJyZXBvc2l0b3J5IjogInlpbmxpLXN5c3RlbXMvdmVjdG9ybWF0Y2giLAogICJyZXBvc2l0b3J5TWV0YWRhdGFSZWNlaXB0U2hhMjU2IjogIjNjN2E2NGU1MjFhODEzM2M0OTBmNzBmZDg2MDJhNDU4ZmU4MjA4ZjQ2MGY1OWI5NTU0YWM4ZWMzZTNmNGI4NzMiLAogICJyb290SW5kZXBlbmRlbnRSZXZpZXdTaGEyNTYiOiAiZWQ4YTllZTY5MTU5OTdiNzRhNTcxMGY1Zjk0YjI0ODlhM2UwYTM0ZDZiNjZjNjhiZDMzNTAwZGNmZmVjYmM2NiIsCiAgInNjaGVtYVZlcnNpb24iOiAxLAogICJzY29wZSI6ICJST09UX1ZFUklGSUVEX1BSSVZBVEVfRVZJREVOQ0VfUFVTSCIsCiAgInZpc2liaWxpdHkiOiAicHJpdmF0ZSIKfQo=', 'sha256': '06432cd72b1af219bc0166a612b7a20be4a4f7386f842cf39c9c082ffc77c956', 'bytes': 1205, 'mode': 384}}
arm=2

need(platform.system()=='Linux' and platform.machine()=='x86_64' and platform.node()=='ed6c0673f5cb' and os.geteuid()==0,'Exact existing CPU host/root')
prep=pathlib.Path(PREP)
for path in (prep,*prep.parents,prep/'release',prep/'release/release.json',prep/'cpu_event_fetch_abab.py'):
 need(not path.is_symlink(),'No linked canonical deployment')
need(digest((prep/'release/release.json').read_bytes())==RELEASE,'Same actual ready release')
need(digest((prep/'cpu_event_fetch_abab.py').read_bytes())==CONTROLLER,'Same frozen controller')
print(json.dumps(exclusive_write_pair(prep,payload,arm)),flush=True)
