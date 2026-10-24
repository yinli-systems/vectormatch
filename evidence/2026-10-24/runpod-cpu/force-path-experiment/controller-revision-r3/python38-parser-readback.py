import re,datetime as dt,sys,platform,json
assert platform.node()=='ed6c0673f5cb'
def require(ok,message):
 if not ok:raise ValueError(message)
def validate_utc_timestamp(value):
    # Java Instant emits up to9 fractional digits. Python3.8 fromisoformat
    # accepts only microsecond precision; validate the raw fraction separately.
    match=re.fullmatch(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?Z',value)
    require(match is not None,'Exact UTC Instant timestamp required')
    dt.datetime.strptime(match.group(1),'%Y-%m-%dT%H:%M:%S')
validate_utc_timestamp('2026-10-24T04:26:43.287007133Z')
print(json.dumps({'passed':True,'pythonVersion':sys.version,'nanosecondInstantValidated':True,'readOnly':True,'jvmLaunched':False}))
