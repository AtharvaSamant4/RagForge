"""Isolated executable; never imports application config, DB or server credentials."""
import importlib.util
import json
import os
from pathlib import Path
import sys


def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def main():
    request=json.loads(sys.stdin.buffer.read(16384))
    work=Path.cwd()
    if os.name=='posix':
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(request['memory_mb']*1024**2,)*2)
        resource.setrlimit(resource.RLIMIT_CPU,(request['cpu_seconds'],)*2)
        resource.setrlimit(resource.RLIMIT_FSIZE,(request['output_mb']*1024**2,)*2)
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    import logging
    logging.disable(logging.CRITICAL)
    core=load('parser_core')
    restrictions={'filesystem':'not_sandboxed','network_process':'not_sandboxed'}
    if sys.platform=='linux':
        try:restrictions=load('parser_sandbox').linux_sandbox(work)
        except OSError:
            if request['strict']:raise RuntimeError('Strict parser sandbox is unavailable')
    elif request['strict']:raise RuntimeError('Strict alpha parsing requires a supported Linux kernel')
    if request.get('probe'):
        import socket,subprocess,time
        operation=request['probe']
        if operation=='timeout':time.sleep(60)
        elif operation=='cpu':
            while True:pass
        elif operation=='memory':bytearray(request['memory_mb']*2*1024**2)
        elif operation=='boundaries':
            blocked={}
            for name,action in [('outside_file',lambda:Path(request['outside']).read_bytes()),('network',lambda:socket.socket()),('process',lambda:subprocess.run([sys.executable,'-c','pass']))]:
                try:action();blocked[name]=False
                except (OSError,PermissionError):blocked[name]=True
            result={'restrictions':restrictions,'blocked':blocked}
    else:
        sections,metadata=core.extract(work/('source.'+request['kind']),request['kind'],request['max_chars'])
        metadata['parser_containment']=restrictions
        result={'sections':sections,'metadata':metadata}
    (work/'output.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')


if __name__=='__main__':
    try:main()
    except Exception as exc:
        # Only controlled validation messages; third-party diagnostics never cross boundary.
        safe=str(exc) if type(exc).__name__=='ExtractionError' or str(exc)=='Strict parser sandbox is unavailable' or str(exc)=='Strict alpha parsing requires a supported Linux kernel' else 'Document parser failed or exceeded a resource limit'
        try:Path('output.json').write_text(json.dumps({'error':safe[:250]}),encoding='utf-8')
        except Exception:pass
        sys.exit(2)
