"""Actual generated client scripts against synthetic loopback contract servers."""
import io
import json
import os
import secrets
import subprocess
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from app import exports


def package(owner,project,tmp_path):
    base='/v1/projects/'+project['id']+'/exports'
    response=owner.post(base,json={});assert response.status_code==202
    assert exports.run_once()
    raw=owner.get(base+'/'+response.json()['id']+'/download').content
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:archive.extractall(tmp_path)
    return tmp_path


def test_generated_client_reads_configured_ipv4_port_and_refuses_redirects(owner,project,tmp_path):
    directory=package(owner,project,tmp_path)
    calls=[];raw=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path,self.headers.get('Authorization')))
            if self.path=='/v1/pilot-evidence':
                self.send_response(302);self.send_header('Location',f'http://127.0.0.1:{self.server.server_port}/must-not-follow');self.end_headers()
            else:
                data=json.dumps({'synthetic_contract_only':True}).encode();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    (directory/'.env').write_text('API_PORT='+str(server.server_port)+'\n',encoding='utf-8')
    (directory/'.standalone-key').write_text(raw,encoding='utf-8')
    env={k:v for k,v in os.environ.items() if k!='STANDALONE_URL'};env['NO_PROXY']='127.0.0.1,localhost'
    try:
        client=subprocess.run([sys.executable,'scripts/manage.py','status'],cwd=directory,env=env,capture_output=True,text=True,timeout=30)
        assert client.returncode==0,client.stderr
        assert calls==[('/v1/status','Bearer '+raw)]
        proof=subprocess.run([sys.executable,'scripts/pilot-evidence.py','--output','proof.json'],cwd=directory,env=env,capture_output=True,text=True,timeout=30)
        assert proof.returncode!=0 and 'Refusing redirects' in proof.stderr+proof.stdout
        assert not (directory/'proof.json').exists()
        assert not any(path=='/must-not-follow' for path,_ in calls)
        assert raw not in client.stdout+client.stderr+proof.stdout+proof.stderr
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)
