from pathlib import Path
import re

P=Path(__file__).resolve().parent
def change(name,old,new,count=1):
 p=P/'source'/name;text=p.read_text();assert text.count(old)==count,(name,old,text.count(old));p.write_text(text.replace(old,new))
for name in ['audit_raw.py','read_phase_audit.py','workload_contract.py']:
 change(name,'from event_fetch_contract import','from read_window32_contract import')
(P/'source/event_fetch_contract.py').unlink()
change('common.py','WINDOWS=(1,8)','WINDOWS=(8,32)')
p=P/'source/common.py';text=p.read_text();start=text.index('def load_config(');end=text.index('\ndef audit_arguments(',start)
text=text[:start]+'''def load_config(path):
    raise AssertionError('Source-only read32 parser: a new independently reviewed controller/common schema and new605/d0 Linux/native qualification are required; old config/release gates are forbidden')
'''+text[end:];p.write_text(text)
change('read_phase_audit.py','selected_page,validate_fetch_pair','selected_page,selected_read_window,validate_fetch_pair')
change('read_phase_audit.py','def audit_rpc_phases(','def audit_read_window32_phases(')
change('read_phase_audit.py',"require(type(selected_window) is int and selected_window in (1,8), 'Selected read window must be1 or8')","selected_read_window(selected_window)")
change('audit_raw.py','from read_phase_audit import audit_rpc_phases,correlation_map','from read_phase_audit import audit_read_window32_phases,correlation_map')
change('audit_raw.py','selected_page,validate_fetch_pair','selected_page,selected_read_window,validate_fetch_pair')
change('audit_raw.py','def audit_arm(','def audit_read_window32_arm(')
change('audit_raw.py',"require(type(selected_window)is int and selected_window==8,'New event-page LONG audit requires fixed read window8')",'selected_read_window(selected_window)')
change('audit_raw.py',"cfg.get('commonEventFetchEnvelope') is True","cfg.get('commonReadWindow32Envelope') is True and cfg.get('commonEventFetchEnvelope',False) is False")
change('audit_raw.py','validate_selected_configuration(cfg,summary,plan,event_fetch_count=event_fetch_count)','validate_selected_configuration(cfg,summary,plan,selected_window=selected_window,event_fetch_count=event_fetch_count)')
change('audit_raw.py','validate_plan(plan,workload)','validate_plan(plan,workload,selected_window=selected_window)')
change('audit_raw.py',"plan['maxReadOnlyInFlight']==8","plan['maxReadOnlyInFlight']==32 and plan['commonReadWindow32Envelope'] is True")
change('audit_raw.py','phase_report=audit_rpc_phases(','phase_report=audit_read_window32_phases(')
change('audit_raw.py','origin,phase_report,event_fetch_count=event_fetch_count,workload=workload)','origin,phase_report,selected_window=selected_window,event_fetch_count=event_fetch_count,workload=workload)')
change('audit_raw.py',"owner['readOnlyHardCapacity']==8","owner['readOnlyHardCapacity']==32")
change('audit_raw.py',"'commonEventFetchEnvelope':True,'readWindow':selected_window","'commonReadWindow32Envelope':True,'commonEventFetchEnvelope':False,'readWindow':selected_window")
change('audit_raw.py','origin,phase_report,*,event_fetch_count,workload=LONG):','origin,phase_report,*,selected_window,event_fetch_count,workload=LONG):')
change('audit_raw.py','validate_cycle_selection(row,phase_report,chunk,event_fetch_count=event_fetch_count)','validate_cycle_selection(row,phase_report,chunk,selected_window=selected_window,event_fetch_count=event_fetch_count)')
p=P/'source/audit_raw.py';text=p.read_text();start=text.index('\ndef main():');text=text[:start]+'''
if __name__=='__main__':
    raise SystemExit('Source-only read32 library: explicit fixed page32 and selected read8|32; a new frozen controller/schema/Linux/native gate must be independently supplied')
''';p.write_text(text)
change('workload_contract.py','from read_window32_contract import selected_page','from read_window32_contract import selected_page,selected_read_window,SOURCE_COMMIT,CODE_FINGERPRINT,PROFILE_FINGERPRINT')
change('workload_contract.py','def validate_plan(plan,workload):','def validate_plan(plan,workload,*,selected_window):')
change('workload_contract.py','w=contract(workload)\n    require(plan','w=contract(workload);selected_read_window(selected_window)\n    require(plan')
change('workload_contract.py',"plan['requestedReadWindow']==8","plan['requestedReadWindow']==selected_window and plan['maxReadOnlyInFlight']==32 and plan['commonReadWindow32Envelope']is True")
p=P/'source/workload_contract.py';text=p.read_text();start=text.index('def validate_actual_plan_observation(');end=text.index('\ndef scheduler_gate(',start)
text=text[:start]+'''def validate_actual_plan_observation(observation,registered_plan,actual_code,*,selected_window,event_fetch_count):
    selected_page(event_fetch_count);selected_read_window(selected_window)
    require(actual_code==CODE_FINGERPRINT and observation['actualCodeFingerprint']==CODE_FINGERPRINT
        and observation['sourceCommit']==SOURCE_COMMIT and observation['profileSha256']==PROFILE_FINGERPRINT,
        'Captured actual-JAR new605/d0 source/code/profile differs; old87a cannot qualify')
    require(set(observation['plans'])=={'page16-window8','page16-window32','page32-window8','page32-window32'},
        'Captured actual-JAR explicit page/window choices differ')
    for page in(16,32):
        pair=[]
        for window in(8,32):
            row=observation['plans']['page%d-window%d'%(page,window)];plan=row['plan'];cfg=row['configuration']
            require(cfg['eventFetchCount']==plan['eventFetchCount']==page and cfg['readWindow']==plan['requestedReadWindow']==window
                and cfg['commonReadWindow32Envelope']is True and plan['commonReadWindow32Envelope']is True
                and cfg['commonEventFetchEnvelope']is False and plan.get('commonEventFetchEnvelope',False)is False
                and plan['maxReadOnlyInFlight']==32,'Captured actual-JAR page/common32 envelope differs')
            pair.append({k:v for k,v in plan.items()if k!='requestedReadWindow'})
        require(pair[0]==pair[1],'Captured actual-JAR selected windows differ beyond requested read size')
    require(observation['plans']['page32-window%d'%selected_window]['plan']==registered_plan,
        'Captured actual-JAR full selected fixed-page32 plan differs')
    return {'passed':True,'selectedReadWindow':selected_window,'fixedEventFetchCount':32,
        'metadataPlanSemanticsOnly':True,'linuxOrNativeQualificationClaimed':False}

'''+text[end:];p.write_text(text)
