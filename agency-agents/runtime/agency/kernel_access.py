"""
kernel_access.py - Kernel-level OS access module for JARVIS BRAINIAC.

Provides low-level Windows kernel integration via ctypes, including process
manipulation, memory access, DLL injection, driver communication, and privilege
escalation. Includes comprehensive mock fallbacks for non-Windows platforms or
when admin privileges are unavailable.

Author: JARVIS BRAINIAC Runtime Team
License: Proprietary
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import enum
import logging
import os
import platform
import struct
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Windows constants
# ---------------------------------------------------------------------------

TOKEN_ADJUST_PRIVILEGES = 0x0020
TOKEN_QUERY = 0x0008
SE_PRIVILEGE_ENABLED = 0x00000002
PROCESS_ALL_ACCESS = 0x001F0FFF
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_CREATE_THREAD = 0x0002
PROCESS_QUERY_INFORMATION = 0x0400
MEM_COMMIT = 0x00001000
MEM_RESERVE = 0x00002000
PAGE_READWRITE = 0x04
PAGE_EXECUTE_READWRITE = 0x40
MEM_RELEASE = 0x8000
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_SHOWWINDOW = 0x0040


class PrivilegeName(enum.Enum):
    """Common Windows privileges for token adjustment."""

    SE_DEBUG_NAME = "SeDebugPrivilege"
    SE_TCB_NAME = "SeTcbPrivilege"
    SE_ASSIGNPRIMARYTOKEN_NAME = "SeAssignPrimaryTokenPrivilege"
    SE_INCREASE_QUOTA_NAME = "SeIncreaseQuotaPrivilege"
    SE_LOAD_DRIVER_NAME = "SeLoadDriverPrivilege"
    SE_SYSTEM_PROFILE_NAME = "SeSystemProfilePrivilege"
    SE_PROF_SINGLE_PROCESS_NAME = "SeProfileSingleProcessPrivilege"
    SE_RESTORE_NAME = "SeRestorePrivilege"
    SE_SHUTDOWN_NAME = "SeShutdownPrivilege"
    SE_TAKE_OWNERSHIP_NAME = "SeTakeOwnershipPrivilege"
    SE_INC_BASE_PRIORITY_NAME = "SeIncreaseBasePriorityPrivilege"


# ---------------------------------------------------------------------------
# Windows structures via ctypes
# ---------------------------------------------------------------------------

class LUID(ctypes.Structure):
    _fields_ = [("LowPart", wt.DWORD), ("HighPart", wt.LONG)]


class LUID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Luid", LUID), ("Attributes", wt.DWORD)]


class TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [
        ("PrivilegeCount", wt.DWORD),
        ("Privileges", LUID_AND_ATTRIBUTES * 1),
    ]


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("th32ModuleID", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("GlblcntUsage", wt.DWORD),
        ("ProccntUsage", wt.DWORD),
        ("modBaseAddr", ctypes.POINTER(wt.BYTE)),
        ("modBaseSize", wt.DWORD),
        ("hModule", wt.HMODULE),
        ("szModule", wt.CHAR * 256),
        ("szExePath", wt.CHAR * 260),
    ]


class MEMORY_BASIC_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BaseAddress", wt.LPVOID),
        ("AllocationBase", wt.LPVOID),
        ("AllocationProtect", wt.DWORD),
        ("RegionSize", ctypes.c_size_t),
        ("State", wt.DWORD),
        ("Protect", wt.DWORD),
        ("Type", wt.DWORD),
    ]


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wt.DWORD),
        ("cntUsage", wt.DWORD),
        ("th32ProcessID", wt.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(wt.ULONG)),
        ("th32ModuleID", wt.DWORD),
        ("cntThreads", wt.DWORD),
        ("th32ParentProcessID", wt.DWORD),
        ("pcPriClassBase", wt.LONG),
        ("dwFlags", wt.DWORD),
        ("szExeFile", wt.CHAR * 260),
    ]


@dataclass
class ProcessInfo:
    """Information about a running process."""

    pid: int
    name: str
    parent_pid: int = 0
    thread_count: int = 0
    base_priority: int = 0
    is_elevated: bool = False
    memory_usage: int = 0
    cpu_percent: float = 0.0


@dataclass
class MemoryRegion:
    """Represents a contiguous memory region in a process."""

    base_address: int
    size: int
    state: str
    protection: str
    type: str


# ---------------------------------------------------------------------------
# Mock implementations for non-Windows or non-admin environments
# ---------------------------------------------------------------------------

class MockKernelAccess:
    """
    Mock kernel access provider for non-Windows platforms or when
    Windows APIs are unavailable. Simulates realistic behavior.
    """

    def __init__(self) -> None:
        self._mock_processes: Dict[int, ProcessInfo] = {}
        self._mock_memory: Dict[int, Dict[int, bytes]] = {}
        self._mock_drivers: Dict[str, Any] = {}
        self._mock_privileges: Dict[str, bool] = {}
        self._elevated = False
        self._next_pid = 1000
        self._call_log: List[Dict[str, Any]] = []
        self._initialize_mock_data()

    def _log(self, method: str, **kwargs: Any) -> None:
        """Log a mock method call for debugging."""
        entry = {"timestamp": time.time(), "method": method, "params": kwargs}
        self._call_log.append(entry)
        logger.debug("[MOCK] %s called with %s", method, kwargs)

    def _initialize_mock_data(self) -> None:
        """Populate mock process table with realistic entries."""
        mock_pids = [
            (4, "System", True),
            (100, "svchost.exe", False),
            (256, "explorer.exe", False),
            (512, "python.exe", False),
            (768, "chrome.exe", False),
            (1024, "code.exe", False),
        ]
        for pid, name, elevated in mock_pids:
            self._mock_processes[pid] = ProcessInfo(
                pid=pid,
                name=name,
                parent_pid=0 if pid == 4 else 256,
                thread_count=8,
                base_priority=8,
                is_elevated=elevated,
                memory_usage=pid * 1024 * 512,
                cpu_percent=0.5,
            )
            self._mock_memory[pid] = {}

    def elevate_privileges(self) -> bool:
        """Mock: Simulate privilege escalation."""
        self._log("elevate_privileges")
        if not self._elevated:
            self._elevated = True
            logger.info("[MOCK] Privileges elevated to admin")
        return True

    def is_admin(self) -> bool:
        """Mock: Check admin status."""
        self._log("is_admin")
        return self._elevated

    def create_process(self, command: str, elevated: bool = False) -> int:
        """Mock: Create a simulated process."""
        self._log("create_process", command=command, elevated=elevated)
        pid = self._next_pid
        self._next_pid += 1
        proc_name = command.split()[0] if command else "unknown.exe"
        self._mock_processes[pid] = ProcessInfo(
            pid=pid,
            name=proc_name,
            thread_count=1,
            base_priority=8,
            is_elevated=elevated,
            memory_usage=4096,
            cpu_percent=0.0,
        )
        self._mock_memory[pid] = {}
        logger.info("[MOCK] Created process %d: %s", pid, command)
        return pid

    def inject_dll(self, pid: int, dll_path: str) -> bool:
        """Mock: Simulate DLL injection."""
        self._log("inject_dll", pid=pid, dll_path=dll_path)
        if pid not in self._mock_processes:
            logger.warning("[MOCK] Cannot inject: PID %d not found", pid)
            return False
        logger.info("[MOCK] Injected %s into PID %d", dll_path, pid)
        return True

    def read_process_memory(self, pid: int, address: int, size: int) -> bytes:
        """Mock: Read simulated process memory."""
        self._log("read_process_memory", pid=pid, address=address, size=size)
        mem = self._mock_memory.get(pid, {})
        if address in mem:
            return mem[address][:size]
        return b"\x00" * size

    def write_process_memory(self, pid: int, address: int, data: bytes) -> bool:
        """Mock: Write simulated process memory."""
        self._log("write_process_memory", pid=pid, address=address, size=len(data))
        if pid not in self._mock_memory:
            self._mock_memory[pid] = {}
        self._mock_memory[pid][address] = data
        return True

    def set_privilege(self, privilege_name: str, enable: bool = True) -> bool:
        """Mock: Set a privilege flag."""
        self._log("set_privilege", privilege_name=privilege_name, enable=enable)
        self._mock_privileges[privilege_name] = enable
        return True

    def open_driver(self, driver_name: str) -> Optional[int]:
        """Mock: Open a simulated driver handle."""
        self._log("open_driver", driver_name=driver_name)
        handle = id(driver_name) & 0xFFFFFFFF
        self._mock_drivers[driver_name] = handle
        return handle

    def send_ioctl(
        self,
        handle: int,
        ioctl_code: int,
        in_buffer: Optional[bytes] = None,
        out_size: int = 0,
    ) -> Tuple[bool, bytes]:
        """Mock: Send IOCTL and return simulated response."""
        self._log(
            "send_ioctl", handle=handle, ioctl_code=ioctl_code, out_size=out_size
        )
        response = b"\x00" * out_size if out_size > 0 else b""
        return True, response

    def enumerate_processes(self) -> List[ProcessInfo]:
        """Mock: Return simulated process list."""
        self._log("enumerate_processes")
        return list(self._mock_processes.values())

    def get_process_info(self, pid: int) -> Optional[ProcessInfo]:
        """Mock: Return simulated process info."""
        self._log("get_process_info", pid=pid)
        return self._mock_processes.get(pid)

    def terminate_process(self, pid: int) -> bool:
        """Mock: Terminate a simulated process."""
        self._log("terminate_process", pid=pid)
        if pid in self._mock_processes:
            del self._mock_processes[pid]
            self._mock_memory.pop(pid, None)
            return True
        return False

    def allocate_memory(self, pid: int, size: int) -> int:
        """Mock: Allocate simulated memory region."""
        self._log("allocate_memory", pid=pid, size=size)
        addr = 0x7FFF00000000 + (pid * 0x100000)
        if pid not in self._mock_memory:
            self._mock_memory[pid] = {}
        self._mock_memory[pid][addr] = b"\x00" * size
        return addr

    def free_memory(self, pid: int, address: int) -> bool:
        """Mock: Free simulated memory region."""
        self._log("free_memory", pid=pid, address=address)
        if pid in self._mock_memory and address in self._mock_memory[pid]:
            del self._mock_memory[pid][address]
            return True
        return False

    def scan_memory_regions(self, pid: int) -> List[MemoryRegion]:
        """Mock: Return simulated memory layout."""
        self._log("scan_memory_regions", pid=pid)
        return [
            MemoryRegion(
                base_address=0x7FF700000000,
                size=0x100000,
                state="MEM_COMMIT",
                protection="PAGE_READWRITE",
                type="MEM_PRIVATE",
            ),
            MemoryRegion(
                base_address=0x7FF800000000,
                size=0x200000,
                state="MEM_COMMIT",
                protection="PAGE_EXECUTE_READ",
                type="MEM_IMAGE",
            ),
        ]

    def get_call_log(self) -> List[Dict[str, Any]]:
        """Return the log of all mock calls (useful for testing)."""
        return list(self._call_log)


# ---------------------------------------------------------------------------
# Real Windows implementation via ctypes
# ---------------------------------------------------------------------------

class WindowsKernelAccess:
    """
    Real Windows kernel-level access using ctypes and the Windows API.

    Requires administrator privileges for most operations. Uses ctypes.windll
    to call kernel32, advapi32, and user32 functions directly without external
    dependencies.
    """

    def __init__(self) -> None:
        self._kernel32 = ctypes.windll.kernel32
        self._advapi32 = ctypes.windll.advapi32
        self._user32 = ctypes.windll.user32
        self._ntdll = ctypes.windll.ntdll
        self._open_handles: List[int] = []
        self._initialize_ctypes_prototypes()

    def _initialize_ctypes_prototypes(self) -> None:
        """Set up proper argtypes/restypes for ctypes functions."""
        self._kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
        self._kernel32.OpenProcess.restype = wt.HANDLE

        self._kernel32.ReadProcessMemory.argtypes = [
            wt.HANDLE,
            wt.LPCVOID,
            wt.LPVOID,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self._kernel32.ReadProcessMemory.restype = wt.BOOL

        self._kernel32.WriteProcessMemory.argtypes = [
            wt.HANDLE,
            wt.LPVOID,
            wt.LPCVOID,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self._kernel32.WriteProcessMemory.restype = wt.BOOL

        self._kernel32.VirtualAllocEx.argtypes = [
            wt.HANDLE,
            wt.LPVOID,
            ctypes.c_size_t,
            wt.DWORD,
            wt.DWORD,
        ]
        self._kernel32.VirtualAllocEx.restype = wt.LPVOID

        self._kernel32.VirtualFreeEx.argtypes = [
            wt.HANDLE,
            wt.LPVOID,
            ctypes.c_size_t,
            wt.DWORD,
        ]
        self._kernel32.VirtualFreeEx.restype = wt.BOOL

        self._kernel32.CreateRemoteThread.argtypes = [
            wt.HANDLE,
            ctypes.c_void_p,
            ctypes.c_size_t,
            wt.LPTHREAD_START_ROUTINE,
            wt.LPVOID,
            wt.DWORD,
            wt.LPDWORD,
        ]
        self._kernel32.CreateRemoteThread.restype = wt.HANDLE

        self._kernel32.CloseHandle.argtypes = [wt.HANDLE]
        self._kernel32.CloseHandle.restype = wt.BOOL

        self._advapi32.OpenProcessToken.argtypes = [
            wt.HANDLE,
            wt.DWORD,
            ctypes.POINTER(wt.HANDLE),
        ]
        self._advapi32.OpenProcessToken.restype = wt.BOOL

        self._advapi32.LookupPrivilegeValueA.argtypes = [
            wt.LPCSTR,
            wt.LPCSTR,
            ctypes.POINTER(LUID),
        ]
        self._advapi32.LookupPrivilegeValueA.restype = wt.BOOL

        self._advapi32.AdjustTokenPrivileges.argtypes = [
            wt.HANDLE,
            wt.BOOL,
            ctypes.POINTER(TOKEN_PRIVILEGES),
            wt.DWORD,
            ctypes.c_void_p,
            wt.LPDWORD,
        ]
        self._advapi32.AdjustTokenPrivileges.restype = wt.BOOL

        self._kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
        self._kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE

        self._kernel32.Process32First.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
        self._kernel32.Process32First.restype = wt.BOOL

        self._kernel32.Process32Next.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
        self._kernel32.Process32Next.restype = wt.BOOL

        self._kernel32.VirtualQueryEx.argtypes = [
            wt.HANDLE,
            wt.LPCVOID,
            ctypes.POINTER(MEMORY_BASIC_INFORMATION),
            ctypes.c_size_t,
        ]
        self._kernel32.VirtualQueryEx.restype = ctypes.c_size_t

    def elevate_privileges(self) -> bool:
        """
        Request administrator elevation by re-launching with elevated privileges.

        Returns True if already admin, or if elevation dialog was shown.
        On failure, returns False.
        """
        if self.is_admin():
            return True
        try:
            import ctypes

            # Use ShellExecute to request elevation
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, " ".join(sys.argv), None, 1
            )
            return True
        except Exception as e:
            logger.error("Failed to elevate privileges: %s", e)
            return False

    def is_admin(self) -> bool:
        """
        Check whether the current process is running with administrator privileges.

        Uses the Windows CheckTokenMembership API to verify the administrator SID.
        """
        try:
            import ctypes

            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    def create_process(self, command: str, elevated: bool = False) -> int:
        """
        Create a new process with optional elevation.

        Args:
            command: Command line string to execute.
            elevated: If True, request UAC elevation for the new process.

        Returns:
            Process ID of the created process, or -1 on failure.
        """
        startup_info = wt.STARTUPINFO()
        startup_info.cb = ctypes.sizeof(wt.STARTUPINFO)
        process_info = wt.PROCESS_INFORMATION()

        creation_flags = 0
        if elevated:
            # Use ShellExecute for elevation - CreateProcess doesn't support UAC
            try:
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None, "runas", command.split()[0], " ".join(command.split()[1:]), None, 1
                )
                return int(ret) if ret > 32 else -1
            except Exception as e:
                logger.error("Failed to create elevated process: %s", e)
                return -1

        success = self._kernel32.CreateProcessA(
            None,
            command.encode("utf-8"),
            None,
            None,
            False,
            creation_flags,
            None,
            None,
            ctypes.byref(startup_info),
            ctypes.byref(process_info),
        )
        if not success:
            err = self._kernel32.GetLastError()
            logger.error("CreateProcess failed with error %d", err)
            return -1

        pid = process_info.dwProcessId
        self._kernel32.CloseHandle(process_info.hProcess)
        self._kernel32.CloseHandle(process_info.hThread)
        return pid

    def inject_dll(self, pid: int, dll_path: str) -> bool:
        """
        Inject a DLL into a remote process using CreateRemoteThread + LoadLibraryA.

        Requires administrator privileges (SeDebugPrivilege).

        Args:
            pid: Target process ID.
            dll_path: Absolute path to the DLL file.

        Returns:
            True if injection was successful.
        """
        if not self.is_admin():
            logger.warning("DLL injection requires admin privileges")
            return False

        dll_path_bytes = dll_path.encode("utf-8")
        dll_size = len(dll_path_bytes) + 1

        h_process = self._kernel32.OpenProcess(
            PROCESS_ALL_ACCESS, False, pid
        )
        if not h_process:
            logger.error("Failed to open process %d", pid)
            return False

        try:
            # Allocate memory in remote process
            remote_mem = self._kernel32.VirtualAllocEx(
                h_process, None, dll_size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
            )
            if not remote_mem:
                logger.error("VirtualAllocEx failed")
                return False

            # Write DLL path to remote process
            written = ctypes.c_size_t(0)
            success = self._kernel32.WriteProcessMemory(
                h_process, remote_mem, dll_path_bytes, dll_size, ctypes.byref(written)
            )
            if not success:
                logger.error("WriteProcessMemory failed")
                self._kernel32.VirtualFreeEx(h_process, remote_mem, 0, MEM_RELEASE)
                return False

            # Get LoadLibraryA address
            h_kernel = self._kernel32.GetModuleHandleA(b"kernel32.dll")
            load_library_addr = self._kernel32.GetProcAddress(h_kernel, b"LoadLibraryA")

            # Create remote thread to call LoadLibraryA
            thread_id = wt.DWORD(0)
            h_thread = self._kernel32.CreateRemoteThread(
                h_process,
                None,
                0,
                wt.LPTHREAD_START_ROUTINE(load_library_addr),
                remote_mem,
                0,
                ctypes.byref(thread_id),
            )
            if not h_thread:
                logger.error("CreateRemoteThread failed")
                self._kernel32.VirtualFreeEx(h_process, remote_mem, 0, MEM_RELEASE)
                return False

            self._kernel32.WaitForSingleObject(h_thread, 5000)
            self._kernel32.CloseHandle(h_thread)
            self._kernel32.VirtualFreeEx(h_process, remote_mem, 0, MEM_RELEASE)
            logger.info("DLL '%s' injected into PID %d", dll_path, pid)
            return True

        finally:
            self._kernel32.CloseHandle(h_process)

    def read_process_memory(self, pid: int, address: int, size: int) -> bytes:
        """
        Read memory from a remote process.

        Args:
            pid: Target process ID.
            address: Base address to read from.
            size: Number of bytes to read.

        Returns:
            Raw bytes read from the process memory.
        """
        h_process = self._kernel32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not h_process:
            logger.error("Failed to open process %d for reading", pid)
            return b""

        try:
            buffer = ctypes.create_string_buffer(size)
            bytes_read = ctypes.c_size_t(0)
            success = self._kernel32.ReadProcessMemory(
                h_process, ctypes.c_void_p(address), buffer, size, ctypes.byref(bytes_read)
            )
            if not success:
                err = self._kernel32.GetLastError()
                logger.error("ReadProcessMemory failed: error %d", err)
                return b""
            return buffer.raw[: bytes_read.value]
        finally:
            self._kernel32.CloseHandle(h_process)

    def write_process_memory(self, pid: int, address: int, data: bytes) -> bool:
        """
        Write data to a remote process's memory.

        Args:
            pid: Target process ID.
            address: Base address to write to.
            data: Bytes to write.

        Returns:
            True if the write was successful.
        """
        h_process = self._kernel32.OpenProcess(
            PROCESS_VM_WRITE | PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION, False, pid
        )
        if not h_process:
            logger.error("Failed to open process %d for writing", pid)
            return False

        try:
            bytes_written = ctypes.c_size_t(0)
            # Change memory protection temporarily
            old_protect = wt.DWORD(0)
            self._kernel32.VirtualProtectEx(
                h_process, ctypes.c_void_p(address), len(data), PAGE_READWRITE, ctypes.byref(old_protect)
            )

            success = self._kernel32.WriteProcessMemory(
                h_process, ctypes.c_void_p(address), data, len(data), ctypes.byref(bytes_written)
            )

            # Restore original protection
            self._kernel32.VirtualProtectEx(
                h_process, ctypes.c_void_p(address), len(data), old_protect.value, ctypes.byref(old_protect)
            )

            if not success:
                err = self._kernel32.GetLastError()
                logger.error("WriteProcessMemory failed: error %d", err)
                return False
            return True
        finally:
            self._kernel32.CloseHandle(h_process)

    def set_privilege(self, privilege_name: str, enable: bool = True) -> bool:
        """
        Enable or disable a privilege in the current process token.

        Args:
            privilege_name: Name of the privilege (e.g., "SeDebugPrivilege").
            enable: True to enable, False to disable.

        Returns:
            True if the privilege was adjusted successfully.
        """
        h_token = wt.HANDLE()
        success = self._advapi32.OpenProcessToken(
            self._kernel32.GetCurrentProcess(),
            TOKEN_ADJUST_PRIVILEGES | TOKEN_QUERY,
            ctypes.byref(h_token),
        )
        if not success:
            logger.error("OpenProcessToken failed")
            return False

        try:
            luid = LUID()
            success = self._advapi32.LookupPrivilegeValueA(None, privilege_name.encode(), ctypes.byref(luid))
            if not success:
                logger.error("LookupPrivilegeValue failed for %s", privilege_name)
                return False

            tp = TOKEN_PRIVILEGES()
            tp.PrivilegeCount = 1
            tp.Privileges[0].Luid = luid
            tp.Privileges[0].Attributes = SE_PRIVILEGE_ENABLED if enable else 0

            success = self._advapi32.AdjustTokenPrivileges(
                h_token, False, ctypes.byref(tp), 0, None, None
            )
            if not success:
                err = self._kernel32.GetLastError()
                logger.error("AdjustTokenPrivileges failed: error %d", err)
                return False
            logger.info("Privilege '%s' %s", privilege_name, "enabled" if enable else "disabled")
            return True
        finally:
            self._kernel32.CloseHandle(h_token)

    def open_driver(self, driver_name: str) -> Optional[int]:
        """
        Open a handle to a kernel driver.

        Args:
            driver_name: Name of the driver (e.g., "\\\\.\\MyDriver").

        Returns:
            Driver handle as integer, or None on failure.
        """
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_EXISTING = 3

        handle = self._kernel32.CreateFileA(
            driver_name.encode(),
            GENERIC_READ | GENERIC_WRITE,
            0,
            None,
            OPEN_EXISTING,
            0,
            None,
        )
        if handle == -1:
            err = self._kernel32.GetLastError()
            logger.error("Failed to open driver %s: error %d", driver_name, err)
            return None

        self._open_handles.append(handle)
        logger.info("Opened driver handle for %s: %d", driver_name, handle)
        return handle

    def send_ioctl(
        self,
        handle: int,
        ioctl_code: int,
        in_buffer: Optional[bytes] = None,
        out_size: int = 0,
    ) -> Tuple[bool, bytes]:
        """
        Send an IOCTL to a kernel driver.

        Args:
            handle: Driver handle from open_driver().
            ioctl_code: IOCTL control code.
            in_buffer: Input data buffer (optional).
            out_size: Expected output buffer size.

        Returns:
            Tuple of (success_flag, response_bytes).
        """
        in_buf = in_buffer or b""
        in_size = len(in_buf)

        out_buf = ctypes.create_string_buffer(out_size) if out_size > 0 else None
        bytes_returned = wt.DWORD(0)

        success = self._kernel32.DeviceIoControl(
            handle,
            ioctl_code,
            ctypes.create_string_buffer(in_buf) if in_buf else None,
            in_size,
            out_buf,
            out_size,
            ctypes.byref(bytes_returned),
            None,
        )
        if not success:
            err = self._kernel32.GetLastError()
            logger.error("DeviceIoControl failed: error %d", err)
            return False, b""

        response = out_buf.raw[: bytes_returned.value] if out_buf else b""
        return True, response

    def enumerate_processes(self) -> List[ProcessInfo]:
        """
        Enumerate all running processes using Toolhelp32 snapshot.

        Returns:
            List of ProcessInfo dataclass instances.
        """
        TH32CS_SNAPPROCESS = 0x00000002
        processes: List[ProcessInfo] = []

        h_snapshot = self._kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if h_snapshot == -1:
            logger.error("CreateToolhelp32Snapshot failed")
            return processes

        try:
            entry = PROCESSENTRY32()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32)

            if self._kernel32.Process32First(h_snapshot, ctypes.byref(entry)):
                while True:
                    proc = ProcessInfo(
                        pid=entry.th32ProcessID,
                        name=entry.szExeFile.decode("utf-8", errors="replace"),
                        parent_pid=entry.th32ParentProcessID,
                        thread_count=entry.cntThreads,
                        base_priority=entry.pcPriClassBase,
                    )
                    processes.append(proc)
                    if not self._kernel32.Process32Next(h_snapshot, ctypes.byref(entry)):
                        break
        finally:
            self._kernel32.CloseHandle(h_snapshot)

        return processes

    def get_process_info(self, pid: int) -> Optional[ProcessInfo]:
        """
        Get detailed information about a specific process.

        Args:
            pid: Process ID to query.

        Returns:
            ProcessInfo if found, None otherwise.
        """
        processes = self.enumerate_processes()
        for proc in processes:
            if proc.pid == pid:
                return proc
        return None

    def terminate_process(self, pid: int) -> bool:
        """
        Force-terminate a process.

        Args:
            pid: Process ID to terminate.

        Returns:
            True if termination was successful.
        """
        PROCESS_TERMINATE = 0x0001
        h_process = self._kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if not h_process:
            logger.error("Failed to open process %d for termination", pid)
            return False

        try:
            success = self._kernel32.TerminateProcess(h_process, 1)
            if success:
                logger.info("Terminated process %d", pid)
                return True
            return False
        finally:
            self._kernel32.CloseHandle(h_process)

    def allocate_memory(self, pid: int, size: int) -> int:
        """
        Allocate memory in a remote process.

        Args:
            pid: Target process ID.
            size: Number of bytes to allocate.

        Returns:
            Base address of allocated memory, or 0 on failure.
        """
        h_process = self._kernel32.OpenProcess(
            PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_QUERY_INFORMATION, False, pid
        )
        if not h_process:
            return 0

        try:
            addr = self._kernel32.VirtualAllocEx(
                h_process, None, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
            )
            return addr or 0
        finally:
            self._kernel32.CloseHandle(h_process)

    def free_memory(self, pid: int, address: int) -> bool:
        """
        Free allocated memory in a remote process.

        Args:
            pid: Target process ID.
            address: Base address of memory to free.

        Returns:
            True if memory was freed successfully.
        """
        h_process = self._kernel32.OpenProcess(
            PROCESS_VM_OPERATION | PROCESS_QUERY_INFORMATION, False, pid
        )
        if not h_process:
            return False

        try:
            return bool(self._kernel32.VirtualFreeEx(h_process, ctypes.c_void_p(address), 0, MEM_RELEASE))
        finally:
            self._kernel32.CloseHandle(h_process)

    def scan_memory_regions(self, pid: int) -> List[MemoryRegion]:
        """
        Scan and return all memory regions in a process.

        Args:
            pid: Target process ID.

        Returns:
            List of MemoryRegion dataclass instances.
        """
        h_process = self._kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid)
        if not h_process:
            return []

        regions: List[MemoryRegion] = []
        address = 0
        mbi = MEMORY_BASIC_INFORMATION()
        mbi_size = ctypes.sizeof(MEMORY_BASIC_INFORMATION)

        try:
            while self._kernel32.VirtualQueryEx(
                h_process, ctypes.c_void_p(address), ctypes.byref(mbi), mbi_size
            ) == mbi_size:
                if mbi.State == MEM_COMMIT:
                    prot_map = {
                        0x04: "PAGE_READWRITE",
                        0x02: "PAGE_READONLY",
                        0x10: "PAGE_EXECUTE",
                        0x20: "PAGE_EXECUTE_READ",
                        0x40: "PAGE_EXECUTE_READWRITE",
                    }
                    regions.append(
                        MemoryRegion(
                            base_address=address,
                            size=mbi.RegionSize,
                            state="MEM_COMMIT",
                            protection=prot_map.get(mbi.Protect, f"0x{mbi.Protect:X}"),
                            type="MEM_PRIVATE",
                        )
                    )
                address += mbi.RegionSize
                if address > 0x7FFFFFFF_FFFFFFFF:
                    break
        finally:
            self._kernel32.CloseHandle(h_process)

        return regions

    def close(self) -> None:
        """Close all open handles and release resources."""
        for handle in self._open_handles:
            self._kernel32.CloseHandle(handle)
        self._open_handles.clear()
        logger.info("WindowsKernelAccess: all handles closed")


# ---------------------------------------------------------------------------
# Factory and module-level convenience functions
# ---------------------------------------------------------------------------

class KernelAccess:
    """
    Unified kernel access facade that automatically selects the best
    implementation: real Windows API when available, mock fallback otherwise.
    """

    def __init__(self) -> None:
        self._impl: Union[WindowsKernelAccess, MockKernelAccess]
        if platform.system() == "Windows":
            try:
                self._impl = WindowsKernelAccess()
                logger.info("KernelAccess: using WindowsKernelAccess (ctypes)")
            except Exception as e:
                logger.warning("Failed to initialize Windows API: %s", e)
                self._impl = MockKernelAccess()
        else:
            self._impl = MockKernelAccess()
            logger.info("KernelAccess: using MockKernelAccess (%s)", platform.system())

    def elevate_privileges(self) -> bool:
        """Request administrator elevation."""
        return self._impl.elevate_privileges()

    def is_admin(self) -> bool:
        """Check if running with administrator privileges."""
        return self._impl.is_admin()

    def create_process(self, command: str, elevated: bool = False) -> int:
        """Create a new process with optional elevation."""
        return self._impl.create_process(command, elevated)

    def inject_dll(self, pid: int, dll_path: str) -> bool:
        """Inject a DLL into a remote process (admin only)."""
        return self._impl.inject_dll(pid, dll_path)

    def read_process_memory(self, pid: int, address: int, size: int) -> bytes:
        """Read memory from a remote process."""
        return self._impl.read_process_memory(pid, address, size)

    def write_process_memory(self, pid: int, address: int, data: bytes) -> bool:
        """Write data to a remote process's memory."""
        return self._impl.write_process_memory(pid, address, data)

    def set_privilege(self, privilege_name: str, enable: bool = True) -> bool:
        """Enable or disable a Windows privilege."""
        return self._impl.set_privilege(privilege_name, enable)

    def open_driver(self, driver_name: str) -> Optional[int]:
        """Open a handle to a kernel driver."""
        return self._impl.open_driver(driver_name)

    def send_ioctl(
        self,
        handle: int,
        ioctl_code: int,
        in_buffer: Optional[bytes] = None,
        out_size: int = 0,
    ) -> Tuple[bool, bytes]:
        """Send an IOCTL to a kernel driver."""
        return self._impl.send_ioctl(handle, ioctl_code, in_buffer, out_size)

    def enumerate_processes(self) -> List[ProcessInfo]:
        """List all running processes."""
        return self._impl.enumerate_processes()

    def get_process_info(self, pid: int) -> Optional[ProcessInfo]:
        """Get detailed info for a specific process."""
        return self._impl.get_process_info(pid)

    def terminate_process(self, pid: int) -> bool:
        """Force-terminate a process."""
        return self._impl.terminate_process(pid)

    def allocate_memory(self, pid: int, size: int) -> int:
        """Allocate memory in a remote process."""
        return self._impl.allocate_memory(pid, size)

    def free_memory(self, pid: int, address: int) -> bool:
        """Free memory in a remote process."""
        return self._impl.free_memory(pid, address)

    def scan_memory_regions(self, pid: int) -> List[MemoryRegion]:
        """Scan memory regions of a process."""
        return self._impl.scan_memory_regions(pid)

    def close(self) -> None:
        """Release all resources."""
        if hasattr(self._impl, "close"):
            self._impl.close()

    @property
    def is_mock(self) -> bool:
        """Return True if the mock implementation is in use."""
        return isinstance(self._impl, MockKernelAccess)


# Singleton instance for module-level access
_kernel_access_instance: Optional[KernelAccess] = None


def get_kernel_access() -> KernelAccess:
    """
    Factory function returning the global KernelAccess singleton.

    Usage:
        ka = get_kernel_access()
        if ka.is_admin():
            data = ka.read_process_memory(target_pid, 0x1000, 256)
    """
    global _kernel_access_instance
    if _kernel_access_instance is None:
        _kernel_access_instance = KernelAccess()
    return _kernel_access_instance


def reset_kernel_access() -> None:
    """Reset the global singleton (useful for testing)."""
    global _kernel_access_instance
    if _kernel_access_instance is not None:
        _kernel_access_instance.close()
        _kernel_access_instance = None


# ---------------------------------------------------------------------------
# Convenience module-level functions
# ---------------------------------------------------------------------------

def elevate() -> bool:
    """Convenience: elevate current process privileges."""
    return get_kernel_access().elevate_privileges()


def is_admin() -> bool:
    """Convenience: check admin status."""
    return get_kernel_access().is_admin()


def read_mem(pid: int, address: int, size: int) -> bytes:
    """Convenience: read process memory."""
    return get_kernel_access().read_process_memory(pid, address, size)


def write_mem(pid: int, address: int, data: bytes) -> bool:
    """Convenience: write process memory."""
    return get_kernel_access().write_process_memory(pid, address, data)


def enable_debug_privilege() -> bool:
    """Convenience: enable SeDebugPrivilege (required for many kernel ops)."""
    return get_kernel_access().set_privilege(PrivilegeName.SE_DEBUG_NAME.value, True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ka = get_kernel_access()
    print(f"Admin: {ka.is_admin()}")
    print(f"Mock mode: {ka.is_mock}")
    procs = ka.enumerate_processes()
    print(f"Found {len(procs)} processes")
    for p in procs[:5]:
        print(f"  PID {p.pid}: {p.name}")
