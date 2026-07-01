from __future__ import annotations

import ctypes
from dataclasses import dataclass
from typing import Protocol

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9


class Kernel32Like(Protocol):
    def CreateJobObjectW(self, security_attributes: int, name: str | None) -> int: ...

    def SetInformationJobObject(self, handle: int, info_class: int, info, info_size: int) -> int: ...

    def AssignProcessToJobObject(self, handle: int, process_handle: int) -> int: ...

    def TerminateJobObject(self, handle: int, exit_code: int) -> int: ...

    def CloseHandle(self, handle: int) -> int: ...


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


@dataclass(frozen=True, slots=True)
class WindowsJobObject:
    kernel32: Kernel32Like | None = None

    def create(self) -> int:
        kernel32 = self._kernel32()
        handle = kernel32.CreateJobObjectW(0, None)
        if handle == 0:
            raise OSError("CreateJobObjectW failed")
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        ok = kernel32.SetInformationJobObject(
            handle,
            JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if ok == 0:
            kernel32.CloseHandle(handle)
            raise OSError("SetInformationJobObject failed")
        return handle

    def assign_process(self, handle: int, *, process_handle: int) -> None:
        if self._kernel32().AssignProcessToJobObject(handle, process_handle) == 0:
            raise OSError("AssignProcessToJobObject failed")

    def terminate(self, handle: int, *, exit_code: int) -> None:
        if self._kernel32().TerminateJobObject(handle, exit_code) == 0:
            raise OSError("TerminateJobObject failed")

    def close(self, handle: int) -> None:
        if self._kernel32().CloseHandle(handle) == 0:
            raise OSError("CloseHandle failed")

    def _kernel32(self) -> Kernel32Like:
        if self.kernel32 is not None:
            return self.kernel32
        return ctypes.windll.kernel32
