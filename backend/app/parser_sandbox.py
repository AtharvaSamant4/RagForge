"""Small auditable OS boundary. No uploaded text is interpreted as code."""
import ctypes
import errno
import os
import platform
import sys
from pathlib import Path


def linux_sandbox(work: Path) -> dict:
    """Landlock deny-by-default filesystem + seccomp syscall restrictions."""
    libc=ctypes.CDLL(None,use_errno=True)
    libc.syscall.restype=ctypes.c_long
    def call(number,*args):
        result=libc.syscall(ctypes.c_long(number),*args)
        if result<0:raise OSError(ctypes.get_errno(),"OS parser restriction failed")
        return result
    # Landlock syscall numbers are identical on supported x86_64/aarch64 Linux.
    if platform.machine() not in ('x86_64','aarch64'):raise OSError("Unsupported sandbox architecture")
    abi=call(444,ctypes.c_void_p(),ctypes.c_size_t(0),ctypes.c_uint(1))
    class Ruleset(ctypes.Structure):_fields_=[('handled_access_fs',ctypes.c_uint64)]
    class Beneath(ctypes.Structure):
        _pack_=1
        _fields_=[('allowed_access',ctypes.c_uint64),('parent_fd',ctypes.c_int32)]
    rights=(1<<13)-1
    if abi>=2:rights|=1<<13
    if abi>=3:rights|=1<<14
    rules=Ruleset(rights)
    fd=call(444,ctypes.byref(rules),ctypes.c_size_t(ctypes.sizeof(rules)),ctypes.c_uint(0))
    try:
        # After imports, only Python dependency data and this disposable job are readable.
        paths={work.resolve():rights,Path(sys.base_prefix).resolve():((1<<2)|(1<<3)),Path(sys.prefix).resolve():((1<<2)|(1<<3))}
        for path,allowed in paths.items():
            parent=os.open(path,getattr(os,'O_PATH',0x200000)|os.O_CLOEXEC)
            try:
                rule=Beneath(allowed,parent)
                call(445,ctypes.c_int(fd),ctypes.c_uint(1),ctypes.byref(rule),ctypes.c_uint(0))
            finally:os.close(parent)
        if libc.prctl(38,1,0,0,0)!=0:raise OSError("Cannot set no_new_privs")
        call(446,ctypes.c_int(fd),ctypes.c_uint(0))
    finally:os.close(fd)
    # Reject networking, new processes, ptrace, namespaces and kernel escape surfaces.
    if platform.machine()=='x86_64':
        arch=0xc000003e;denied=[41,42,43,49,50,53,56,57,58,59,76,77,90,91,92,93,94,101,132,165,166,235,260,268,272,280,308,310,311,322,323,425,426,427,435,452]
    else:
        arch=0xc00000b7;denied=[198,199,200,201,202,203,220,221,117,40,39,45,46,52,53,54,55,88,97,268,270,271,281,282,425,426,427,435,452]
    class Filter(ctypes.Structure):_fields_=[('code',ctypes.c_ushort),('jt',ctypes.c_ubyte),('jf',ctypes.c_ubyte),('k',ctypes.c_uint)]
    class Program(ctypes.Structure):_fields_=[('len',ctypes.c_ushort),('filter',ctypes.POINTER(Filter))]
    instructions=[(0x20,0,0,4),(0x15,1,0,arch),(0x06,0,0,0x80000000),(0x20,0,0,0)]
    # x32 syscall numbers must not bypass the x86_64 deny list.
    if platform.machine()=='x86_64':instructions += [(0x35,0,1,0x40000000),(0x06,0,0,0x00050000|errno.EPERM)]
    for number in denied:instructions += [(0x15,0,1,number),(0x06,0,0,0x00050000|errno.EPERM)]
    instructions += [(0x06,0,0,0x7fff0000)]
    array=(Filter*len(instructions))(*(Filter(*i) for i in instructions))
    program=Program(len(instructions),array)
    if libc.prctl(22,2,ctypes.byref(program),0,0)!=0:raise OSError("Cannot install seccomp restrictions")
    return {'landlock_abi':abi,'filesystem':'landlock','network_process':'seccomp'}


class WindowsJob:
    def __init__(self,process,memory_mb,cpu_seconds):
        from ctypes import wintypes as w
        class Basic(ctypes.Structure):_fields_=[('ProcessTime',ctypes.c_int64),('JobTime',ctypes.c_int64),('Flags',w.DWORD),('MinWorking',ctypes.c_size_t),('MaxWorking',ctypes.c_size_t),('Active',w.DWORD),('Affinity',ctypes.c_size_t),('Priority',w.DWORD),('Scheduling',w.DWORD)]
        class IO(ctypes.Structure):_fields_=[('x'+str(i),ctypes.c_uint64) for i in range(6)]
        class Extended(ctypes.Structure):_fields_=[('Basic',Basic),('IO',IO),('ProcessMemory',ctypes.c_size_t),('JobMemory',ctypes.c_size_t),('PeakProcess',ctypes.c_size_t),('PeakJob',ctypes.c_size_t)]
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.kernel.CreateJobObjectW.restype=w.HANDLE
        self.kernel.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD]
        self.kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE]
        self.kernel.CloseHandle.argtypes=[w.HANDLE]
        self.handle=self.kernel.CreateJobObjectW(None,None)
        # Windows venv python.exe is a launcher plus the real interpreter.
        # Bound the whole job, allowing exactly that two-process bootstrap.
        limits=Extended();limits.Basic.Flags=0x4|0x8|0x200|0x2000
        limits.Basic.JobTime=int(cpu_seconds)*10_000_000;limits.Basic.Active=2;limits.JobMemory=int(memory_mb)*1024**2
        if not self.handle or not self.kernel.SetInformationJobObject(self.handle,9,ctypes.byref(limits),ctypes.sizeof(limits)) or not self.kernel.AssignProcessToJobObject(self.handle,w.HANDLE(int(process._handle))):
            error=ctypes.get_last_error();self.close();raise OSError(error,"Cannot apply Windows parser job limits")
    def close(self):
        if getattr(self,'handle',None):self.kernel.CloseHandle(self.handle);self.handle=None
