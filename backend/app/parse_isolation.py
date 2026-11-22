import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

from .config import settings
from .ingestion import ExtractionError


def execute_parser(content: bytes,kind:str,probe=None,outside=None):
    s=settings()
    if len(content)>s.max_upload_mb*1024**2:raise ExtractionError('Source exceeds the upload size limit')
    if kind not in ('pdf','docx','txt','md','csv'):raise ExtractionError('Unsupported parser format')
    with tempfile.TemporaryDirectory(prefix='ragforge-parse-') as temporary:
        work=Path(temporary);(work/('source.'+kind)).write_bytes(content)
        environment={k:v for k,v in os.environ.items() if k.upper() in ('SYSTEMROOT','WINDIR','PATH','PATHEXT','TEMP','TMP')}
        environment.update(PYTHONIOENCODING='utf-8',PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1')
        request={'kind':kind,'max_chars':s.max_extracted_chars,'memory_mb':s.parser_memory_mb,'cpu_seconds':s.parser_cpu_seconds,'output_mb':s.parser_output_mb,'strict':s.parser_require_sandbox or s.deployment_mode=='private_alpha','probe':probe,'outside':outside}
        child=Path(__file__).with_name('parser_child.py')
        proc=subprocess.Popen([sys.executable,'-I',str(child)],cwd=work,env=environment,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=os.name=='posix',creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name=='nt' else 0)
        job=None
        try:
            if os.name=='nt':
                from .parser_sandbox import WindowsJob
                job=WindowsJob(proc,s.parser_memory_mb,s.parser_cpu_seconds)
            proc.communicate(json.dumps(request).encode(),timeout=s.parser_wall_seconds)
            output=work/'output.json'
            if not output.is_file() or output.stat().st_size>s.parser_output_mb*1024**2:raise ExtractionError('Document parser exceeded CPU, memory or output limits')
            result=json.loads(output.read_text(encoding='utf-8'))
            if proc.returncode or 'error' in result:raise ExtractionError(result.get('error','Document parser exceeded a resource limit'))
            return result
        except subprocess.TimeoutExpired:
            raise ExtractionError('Document parser exceeded the execution-time limit') from None
        except ExtractionError:
            raise
        except (OSError,ValueError) as exc:
            raise ExtractionError('Document parser could not run safely (OS code '+str(getattr(exc,'errno',None))+')') from None
        finally:
            if proc.poll() is None:
                if os.name=='posix':os.killpg(proc.pid,signal.SIGKILL)
                else:proc.kill()
            proc.wait()
            if job:job.close()


def parse_document(path:Path,kind:str):
    with path.open('rb') as source:content=source.read(settings().max_upload_mb*1024**2+1)
    result=execute_parser(content,kind)
    return [(text,location) for text,location in result['sections']],result['metadata']
