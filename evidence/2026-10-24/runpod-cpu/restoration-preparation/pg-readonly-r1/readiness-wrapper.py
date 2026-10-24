from pathlib import Path
import time,json,socket
j=Path('/opt/vectormatch-cpu/preparation/pg-readonly-recovery-r1')
end=time.monotonic()+20
while time.monotonic()<end:
 log=(j/'postgres.log').read_text(errors='replace') if (j/'postgres.log').exists() else ''
 if (j/'start-ready.json').exists() and 'database system is ready to accept connections' in log:
  with socket.create_connection(('127.0.0.1',15432),timeout=2):pass
  print(json.dumps({'ready':True,'startReady':json.loads((j/'start-ready.json').read_text()),'log':log}));break
 if (j/'start-failure.json').exists() or (j/'outer-result.json').exists():
  print(json.dumps({'ready':False,'phaseFiles':[x.name for x in j.iterdir()],'log':log}));break
 time.sleep(.25)
else: print(json.dumps({'ready':False,'reason':'20secondreadinessobservationexpired','log':log}))
