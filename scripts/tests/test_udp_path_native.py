import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location('udp_path_native_audit',ROOT/'scripts/analyze_udp_path.py')
audit=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(audit)

class NativeUdpProtocolTest(unittest.TestCase):
    def test_two_idle_caps_preserve_real_datagram_identity_and_all_arrivals(self):
        java=shutil.which('java');javac=shutil.which('javac')
        if not java or not javac:self.fail('Java 21 tools required for the actual UDP protocol test')
        with tempfile.TemporaryDirectory()as directory:
            p=Path(directory);subprocess.run([javac,'-Xlint:all','-Werror','-d',str(p),str(ROOT/'tools/udp-path/UdpPathBench.java')],check=True,capture_output=True,timeout=20)
            for index,cap in enumerate([1000000,100000]):
                with socket.socket(socket.AF_INET,socket.SOCK_DGRAM)as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
                server=p/('server'+str(index));client=p/('client'+str(index));run='660000000000000'+str(index)
                process=subprocess.Popen([java,'-cp',str(p),'UdpPathBench','server',str(server),str(port),str(cap),'5',run],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
                try:
                    end=time.monotonic()+5
                    while not (server/'ready.json').exists()and time.monotonic()<end:
                        self.assertIsNone(process.poll(),'owned UDP server exited before readiness');time.sleep(.01)
                    self.assertTrue((server/'ready.json').exists())
                    subprocess.run([java,'-cp',str(p),'UdpPathBench','client',str(client),'127.0.0.1',str(port),'200','1',str(cap),run,'131072'],check=True,capture_output=True,timeout=8)
                    out,err=process.communicate(timeout=7);self.assertEqual(0,process.returncode,out+err)
                    result=audit.audit(client);summary=json.loads((server/'summary.json').read_text())
                    self.assertTrue(result['allPlannedReplied']);self.assertEqual(200,result['replied']);self.assertEqual(200,summary['replied']);self.assertEqual(0,summary['invalid'])
                finally:
                    if process.poll()is None:process.terminate();process.communicate(timeout=3)

if __name__=='__main__':unittest.main()
