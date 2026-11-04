"""Exclusive supervisor ownership and immutable interrupted-request accounting."""
import ctypes
import json
import os
from pathlib import Path


def process_is_running(pid):
    if type(pid) is not int or pid <= 0:
        raise ValueError('Invalid saved supervisor PID')
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return False
            raise OSError('Cannot verify the saved supervisor process')
        try:
            exit_code = ctypes.c_ulong()
            if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                raise OSError('Cannot read the saved supervisor process status')
            return exit_code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class SupervisorLock:
    def __init__(self, directory):
        self.root = Path(directory)
        self.file = None
        self.previous = None

    def __enter__(self):
        self.file = (self.root/'supervisor.lock').open('a+b')
        try:
            self.file.seek(0, os.SEEK_END)
            if not self.file.tell():
                self.file.write(b'0')
                self.file.flush()
            self.file.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.file.close()
            raise RuntimeError('Another supervisor owns this campaign') from error
        try:
            path = self.root/'supervisor.json'
            if path.exists():
                self.previous = json.loads(path.read_text(encoding='utf-8'))
                if process_is_running(self.previous['pid']):
                    raise RuntimeError('The previous supervisor process is still alive')
            return self
        except Exception:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        self.file.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        finally:
            self.file.close()


def audit_ledgers(directory, *, prior_requests, recover_interrupted, previous_supervisor):
    root = Path(directory)
    ledgers, pending, indices = [], [], []
    for path in sorted(root.glob('provider_*')):
        if not path.is_dir():
            continue
        suffix = path.name.removeprefix('provider_')
        if not suffix.isdigit():
            raise ValueError('Unrecognized provider ledger directory')
        indices.append(int(suffix))
        report = json.loads((path/'report.json').read_text(encoding='utf-8'))
        counts = [report[key] for key in ('requests', 'completed', 'pending')]
        if any(type(value) is not int or value < 0 for value in counts):
            raise ValueError('Invalid saved provider counts')
        if report['requests'] != report['completed'] + report['pending']:
            raise ValueError('Saved provider counts disagree')
        ledgers.append(report)
        if report['pending']:
            pending.append(dict(ledger=path.name, report=report))
    launch = root/'launch.json'
    carry_in = json.loads(launch.read_text(encoding='utf-8'))['prior_requests'] if launch.exists() else prior_requests
    attempted = carry_in + sum(report['requests'] for report in ledgers)
    if prior_requests < attempted:
        raise ValueError('Resume prior_requests omits already attempted provider calls')
    acknowledged = []
    for path in (root/'recoveries').glob('recovery_*.json'):
        acknowledged.extend(json.loads(path.read_text(encoding='utf-8'))['pending_ledgers'])
    unrecovered = [record for record in pending if record not in acknowledged]
    if unrecovered and not recover_interrupted:
        raise ValueError('Interrupted provider attempts require explicit --recover-interrupted')
    if unrecovered and (not previous_supervisor or process_is_running(previous_supervisor['pid'])):
        raise ValueError('Interrupted recovery requires a verified inactive previous supervisor')
    return dict(carry_in_requests=carry_in, attempted_requests=attempted,
                pending_ledgers=pending, unrecovered_pending=unrecovered,
                next_ledger=f'provider_{max(indices, default=-1)+1:03d}')
