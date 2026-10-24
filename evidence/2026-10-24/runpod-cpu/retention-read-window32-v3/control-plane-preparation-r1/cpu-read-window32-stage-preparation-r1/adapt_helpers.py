from pathlib import Path
S=Path(__file__).resolve().parent
t=(S/'baseline/stage_event_fetch.py').read_text()
replacements={
'Exclusive event-page source staging,19+42 Linux guards':'Exclusive fixed-page32 read-window8/32 source staging,27+51 Linux guards',
'cpu-event-fetch-cloud-abab-r1':'cpu-read-window32-cloud-abab-r1',
'd92301d3058acc83cb85d5bc5b4fd2e3f0ed4df8':'605eb43fcafd8fa0a6287304387c93c4d1bbddf6',
'87a7ccd092f4d3c890bf8cc8bd7c6ffcd18900838699cd2b873fd1931cddb6aa':'d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea',
'10a3f6e9144e1b6a54fef342e037d2de0987aee9dfddc6c7c5573f3e83ea56f6':'3c08ef18ecb9599ccce4a7e6d03c8afeea760cdf66297f422520e5708ec1a9f0',
'eb84eed09cad46c5097c32d980a1629f7c7c7fec3759e904544f7ef9e91e3100':'d0dbd4c5051ab328e94102e151382d358aa1c5dee115fbc991ad2e0d41fe8c04',
'468db7bdb5b2fcf29dd2fab975cef9b3dbe7ce8f9ed73d326d65a5cd74488d8b':'766ef61f32b8c0dfe8010749795637969b319ddcd19e05d8351830d0e02836ad',
'eventFetchRawParserFreeze':'readWindow32RawParserFreeze',
'test_event_delta':'test_read_window32_delta',
"'tests':19":"'tests':27",
"'tests':42":"'tests':51",
'19controller +42new selected-page LONG':'27controller/helper +51fixed-page32 read-window LONG',
'cpu_event_fetch_abab.py':'cpu_read_window32_abab.py',
"gate['schemaVersion']==2":"gate['schemaVersion']==3",
'ROOT_VERIFIED_EVENT_FETCH_CPU_RELEASE':'ROOT_VERIFIED_READ_WINDOW32_CPU_RELEASE',
"len(frozen['files'])==27":"len(frozen['files'])==43",
'Exact immutable27file owner preparation':'Exact immutable43file read-window32 preparation',
'Actual frozen33source R2 owner parser receipt differs':'Actual fixed-page32 read-window32 parser source freeze differs',
'frozen_owner_poll_controller':'frozen_read_window32_controller',
"'test_event_fetch'":"'test_read_window32'",
'Exact selected-page42 guard group required':'Exact fixed-page32/window8|32 51 guard group required',
"identity['pid']==67629 and identity['startTicks']==4772830":"identity['pid']==69431 and identity['startTicks']==5325814",
"free>=1024**3+reserved_bytes":"free>=2116076873+reserved_bytes",
"free>=1024**3+sum(row['bytes'] for row in rows.values())":"free>=2116076873+sum(row['bytes'] for row in rows.values())",
}
for old,new in replacements.items():
 assert old in t,old;t=t.replace(old,new)
old="require(parser['schemaVersion']==1 and parser['scope']=='EVENT_FETCH_LONG_RAW_AUDIT_SOURCE_CLOSURE'\n         and parser['sourceCommit']==SOURCE_COMMIT and parser['actualLocalMetadataCodeFingerprint']==CODE_SHA\n         and parser['actualPureGuardMethods']==42 and parser['selectedPageHasNoDefault'] is True\n         and parser['defaultCpuSchedulerStrict'] is True,'Exact new explicit selected-page parser source proof required')"
new="require(parser['schemaVersion']==1 and parser['scope']=='SOURCE_ONLY_FIXED_PAGE32_LONG_READ_WINDOW8_32_PARSER'\n         and parser['sourceCommit']==SOURCE_COMMIT and parser['actualLocalMetadataCodeFingerprint']==CODE_SHA\n         and parser['pureGuardMethods']==51 and parser['noImplicitSelectedPage'] is True\n         and parser['selectedReadWindows']==[8,32] and parser['explicitFixedEventFetchCount']==32\n         and parser['actualRawAuditOrJavaNativeSshGitBusinessExecuted'] is False\n         and parser['defaultCpuSchedulerStrict'] is True,'Exact fixed-page32/window8|32 parser source proof required')"
assert old in t;t=t.replace(old,new)
line="OWNER_VALIDATOR_SHA='868b1f426906e16602e2ad9a0e7c7bba33bb5e80ea950af171a9903ac5dc4fdd'"
t=t.replace(line,line+"\nIDLE_VALIDATOR_SHA='74a666f0087e92de6ce1da311bd73e4941db7cc2b264a472cc84b0512d40032a'")
line=" require(sha(files['owner_poll_attestation.py'])==OWNER_VALIDATOR_SHA and ready['ownerPollValidatorSha256']==OWNER_VALIDATOR_SHA,'Unique shared owner source/selection gate differs')"
assert line in t;t=t.replace(line,line+"\n require(sha(files['idle_attestation.py'])==IDLE_VALIDATOR_SHA,'Exact dynamic selected-window idle-role validator required')")
t=t.replace("require(12<=len(rows)<=MAX_FILES and sum(row['bytes'] for row in rows.values())<=LIMIT", "require(len(rows)==55 and len(rows)<=MAX_FILES and sum(row['bytes'] for row in rows.values())<=LIMIT")
with(S/'stage_read_window32.py').open('x')as f:f.write(t)
t=(S/'baseline/launch_event_fetch.py').read_text().replace('import stage_event_fetch as stage','import stage_read_window32 as stage').replace('cpu_event_fetch_abab.py','cpu_read_window32_abab.py')
with(S/'launch_read_window32.py').open('x')as f:f.write(t)
