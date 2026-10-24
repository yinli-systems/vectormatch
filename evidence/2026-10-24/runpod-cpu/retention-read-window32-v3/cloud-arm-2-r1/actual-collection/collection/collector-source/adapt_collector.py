"""One-time source fork only. New controller/close exact pins are bound separately after their real freezes."""
from pathlib import Path
import ast

HERE = Path(__file__).resolve().parent
OLD_PARSER = '468db7bdb5b2fcf29dd2fab975cef9b3dbe7ce8f9ed73d326d65a5cd74488d8b'
PARSER = '766ef61f32b8c0dfe8010749795637969b319ddcd19e05d8351830d0e02836ad'
names = ['common.py', 'owner_bundle.py', 'audit_native_artifacts.py', 'audit_raw.py', 'build_config.py',
         'collect_and_audit.py', 'collect_closed_round.py', 'finalize_local_collection.py']
for name in names:
    path = HERE / name
    text = path.read_text().replace('cpu_event_fetch_abab', 'cpu_read_window32_abab')
    text = text.replace('cpu-event-fetch-cloud-abab-r1', 'cpu-read-window32-cloud-abab-r1')
    text = text.replace('retention-event-fetch-long-v1', 'retention-read-window32-long-v1')
    text = text.replace('ROOT_VERIFIED_CLOSED_CPU_EVENT_FETCH_', 'ROOT_VERIFIED_CLOSED_CPU_READ_WINDOW32_')
    path.write_text(text)

p = HERE / 'common.py'
t = p.read_text().replace('WINDOWS=(8,)', 'SUPPORTED_WINDOWS=(8,32)')
t = t.replace("c['schemaVersion']==5", "c['schemaVersion']==6").replace('event-fetch long arm/schema5', 'fixed-page32 read-window arm/schema6')
t = t.replace("and c['eventFetchCount']==controller.selected_event_page()", "and c['eventFetchCount']==controller.selected_event_page()==32\n        and type(c['readWindow'])is int and c['readWindow']==controller.selected_read_window()")
t = t.replace("'eventFetchCount':c['eventFetchCount']}", "'eventFetchCount':c['eventFetchCount'],'readWindow':c['readWindow']}")
t = t.replace("require(len(expected)==39,'Exact39 explicit stage files required')", "require(1<=len(expected)<=64,'Bounded explicit staged file set; exact names checked against actual sourcefreeze/release below')")
t = t.replace('10a3f6e9144e1b6a54fef342e037d2de0987aee9dfddc6c7c5573f3e83ea56f6', '__CONTROLLER_PREPARATION_SHA__')
t = t.replace('Exact39', 'Exact frozen').replace('Frozen event-controller', 'Frozen read-window32 controller')
t = t.replace(OLD_PARSER, PARSER)
p.write_text(t)

p = HERE / 'frozen_parser.py'
t = p.read_text().replace(OLD_PARSER, PARSER).replace("'event_fetch_contract'", "'read_window32_contract'")
t = t.replace("'_qualified_long_'", "'_qualified_read_window32_'")
p.write_text(t)

p = HERE / 'build_config.py'
t = p.read_text().replace('selected_event_page, configure_arm', 'selected_event_page, selected_read_window, configure_arm')
t = t.replace("'schemaVersion': 5", "'schemaVersion': 6")
t = t.replace("'eventFetchCount':selected_event_page(),", "'eventFetchCount':selected_event_page(), 'readWindow':selected_read_window(),")
p.write_text(t)

p = HERE / 'owner_bundle.py'
t = p.read_text().replace("and c['eventFetchCount']==controller.selected_event_page()", "and c['eventFetchCount']==controller.selected_event_page()==32 and c['readWindow']==controller.selected_read_window()")
t = t.replace('validate_selected_page_observations', 'validate_selected_window_observations')
t = t.replace("identities['window-8-node-'+str(n)]", "identities['window-%d-node-%d'%(c['readWindow'],n)]")
t = t.replace('controller.node_argv(release,8,n,reg)', "controller.node_argv(release,c['readWindow'],n,reg)")
p.write_text(t)

p = HERE / 'audit_native_artifacts.py'
t = p.read_text().replace('from common import WINDOWS,require', 'from common import require')
t = t.replace("    controller.configure_arm(c['arm'])", "    controller.configure_arm(c['arm'])\n    WINDOWS=(c['readWindow'],)")
t = t.replace("completion['eventFetchCount']==c['eventFetchCount'] and", "completion['eventFetchCount']==c['eventFetchCount']==32 and completion['readWindow']==c['readWindow'] and")
t = t.replace('controller.validate_registration(release,8,reg)', 'controller.validate_registration(release,chunk,reg)')
t = t.replace("v['role']=='window-8-node-'+str(n)", "v['role']=='window-%d-node-%d'%(c['readWindow'],n)")
t = t.replace("'eventFetchCount':c['eventFetchCount'],", "'eventFetchCount':c['eventFetchCount'],'readWindow':c['readWindow'],")
p.write_text(t)

p = HERE / 'audit_raw.py'
t = p.read_text().replace('def strict_arm(parser,workload,arm,*,event_fetch_count):', 'def strict_arm(parser,workload,arm,*,selected_window,event_fetch_count):')
t = t.replace("event_fetch_count in(16,32),'Explicit selected event page16|32 required'", "event_fetch_count==32 and type(selected_window)is int and selected_window in(8,32),'Explicit fixedpage32 and selected read8|32 required'")
t = t.replace('return parser.audit_arm(8,arm,workload=workload,event_fetch_count=event_fetch_count)', 'return parser.audit_read_window32_arm(selected_window,arm,workload=workload,event_fetch_count=event_fetch_count)')
t = t.replace('def qualify_new_artifact(report,terminal,final,event_fetch_count):', 'def qualify_new_artifact(report,terminal,final,event_fetch_count,selected_window):')
t = t.replace("report['commonEventFetchEnvelope'] is True\n        and report['readWindow']==8", "report['commonReadWindow32Envelope'] is True and report.get('commonEventFetchEnvelope',False)is False\n        and report['readWindow']==selected_window")
t = t.replace("parser.audit_arm.__kwdefaults__", "parser.audit_read_window32_arm.__kwdefaults__")
old = """    contract.validate_actual_plan_observation(parser.js(a.collection/'raw-files/source/release/proofs/linuxMetadataObservation.json'),
        parser.js(arm/'load/admission-plan.json'),release['codeFingerprint'],event_fetch_count=c['eventFetchCount'])"""
new = """    validate_actual_plan_sources(
        parser.js(a.collection/'raw-files/source/release/proofs/linuxMetadataObservation.json'),
        parser.js(a.collection/'raw-files/source/fixtures/actual-local-distribution-observation.json'),
        parser.js(arm/'load/admission-plan.json'),release['codeFingerprint'],selected_window=c['readWindow'],
        event_fetch_count=c['eventFetchCount'],contract=contract)"""
assert old in t
t = t.replace(old, new)
t = t.replace('parser.terminal_inventory(8,arm', "parser.terminal_inventory(c['readWindow'],arm")
t = t.replace("json.dump({'8':terminal}", "json.dump({str(c['readWindow']):terminal}")
t = t.replace("strict_arm(parser,contract.LONG,arm,event_fetch_count=c['eventFetchCount'])", "strict_arm(parser,contract.LONG,arm,selected_window=c['readWindow'],event_fetch_count=c['eventFetchCount'])")
t = t.replace("identities['window-8-node-'+str(n)]", "identities['window-%d-node-%d'%(c['readWindow'],n)]")
t = t.replace("qualify_new_artifact(report,terminal,final,c['eventFetchCount'])", "qualify_new_artifact(report,terminal,final,c['eventFetchCount'],c['readWindow'])")
t = t.replace("'eventFetchCount':c['eventFetchCount'],", "'eventFetchCount':c['eventFetchCount'],'readWindow':c['readWindow'],")
addition = '''
def validate_actual_plan_sources(linux,local,registered_plan,actual_code,*,selected_window,event_fetch_count,contract):
    require(type(selected_window)is int and selected_window in(8,32) and event_fetch_count==32,
        'Explicit selected window and fixed32 required')
    require(set(linux['plans'])=={'8','32'},'Actual Linux schema must contain exactly two observed plans; never synthesize four Linux plans')
    require(set(local['plans'])=={'page16-window8','page16-window32','page32-window8','page32-window32'},'Actual local metadata four-choice schema required')
    for key in ('sourceCommit','sourceBaseCommit','actualCodeFingerprint','profileSha256'):
        require(linux[key]==local[key], 'Actual local/Linux metadata identity differs: '+key)
    require(linux['sourceCommit']=='605eb43fcafd8fa0a6287304387c93c4d1bbddf6'
        and linux['actualCodeFingerprint']==actual_code=='d0fbef05df5a23d7b8e27d2673005908a18373c3d0c1921a8c4e4465111591ea'
        and linux['fixedEventFetchCount']==32 and linux['actualMetadataPlatform']['osName']=='Linux',
        'Actual new Linux metadata identity/platform required')
    for window in(8,32):
        name='page32-window%d'%window
        require(linux['plans'][str(window)]==local['plans'][name], 'Actual Linux selected Plan and configuration must exactly equal real local page32 body')
    # The qualified parser requires real local4 metadata; passing or inventing Linux4 is forbidden.
    return contract.validate_actual_plan_observation(local,registered_plan,actual_code,
        selected_window=selected_window,event_fetch_count=event_fetch_count)

'''
t = t.replace('\ndef audit(a,c,release):', '\n'+addition+'\ndef audit(a,c,release):')
p.write_text(t)

p = HERE / 'finalize_local_collection.py'
t = p.read_text().replace('*,event_fetch_count):', '*,event_fetch_count,selected_window):')
t = t.replace('event_fetch_count in(16,32)', 'event_fetch_count==32 and type(selected_window)is int and selected_window in(8,32)')
t = t.replace("and native['eventFetchCount']==raw['eventFetchCount']==event_fetch_count", "and native['eventFetchCount']==raw['eventFetchCount']==event_fetch_count\n        and native['readWindow']==raw['readWindow']==selected_window")
t = t.replace("event_fetch_count=c['eventFetchCount'])", "event_fetch_count=c['eventFetchCount'],selected_window=c['readWindow'])")
t = t.replace("'eventFetchCount':c['eventFetchCount'],", "'eventFetchCount':c['eventFetchCount'],'readWindow':c['readWindow'],")
t = t.replace('event-fetch arm collection', 'fixed-page32 read-window arm collection')
p.write_text(t)

p = HERE / 'collect_and_audit.py'
t = p.read_text().replace("CLOSE_SOURCE_SHA = '67fcfe5bd15efb8bdc488d25b156534b34878ce6584e5cb2ec3cf95ebeb2b5f2'", "CLOSE_SOURCE_SHA = '__NEW_CLOSE_SOURCE_SHA__'")
t = t.replace("x['schemaVersion'] == 2", "x['schemaVersion'] == 3")
t = t.replace("and x['eventFetchCount'] == c['eventFetchCount']", "and x['eventFetchCount'] == c['eventFetchCount']==32\n              and x['readWindow'] == c['readWindow']")
t = t.replace("'eventFetchCount':c['eventFetchCount'],", "'eventFetchCount':c['eventFetchCount'],'readWindow':c['readWindow'],")
p.write_text(t)

p = HERE / 'collect_closed_round.py'
t = p.read_text().replace("+'\\nEVENT_PAGE='+repr(c['eventFetchCount'])", "+'\\nEVENT_PAGE='+repr(c['eventFetchCount'])+'\\nREAD_WINDOW='+repr(c['readWindow'])")
t = t.replace("completion['eventFetchCount']==EVENT_PAGE and", "completion['eventFetchCount']==EVENT_PAGE==32 and completion['readWindow']==READ_WINDOW and")
t = t.replace("'eventFetchCount':c['eventFetchCount'],", "'eventFetchCount':c['eventFetchCount'],'readWindow':c['readWindow'],")
p.write_text(t)

p = HERE / 'telemetry_audit.py'
t = p.read_text().replace('raw,js,JOB,WINDOWS=parser.raw,parser.js,job,(8,)', "raw,js,JOB,WINDOWS=parser.raw,parser.js,job,tuple(a['readWindow']for a in arms)")
p.write_text(t)
p = HERE / 'run_guards.py'
t = p.read_text().replace("'test_event_collection'", "'test_read_window32_collection'")
p.write_text(t)
for path in HERE.glob('*.py'):
    ast.parse(path.read_text())
print('Source-only adaptation complete; real controller and close freeze pins deliberately unbound until their closure')
