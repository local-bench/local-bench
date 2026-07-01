from __future__ import annotations

from localbench.serving.job_object import JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE, WindowsJobObject
from localbench.serving.teardown import teardown_owned_server
from serving_helpers import FakeKernel32, FakeProcess, FakeTeardownController


def test_teardown_marks_uncertain_when_owned_gpu_pid_remains() -> None:
    # Given: a launched process whose PID still appears in nvidia-smi after termination.
    process = FakeProcess(pid=1234, returncode=0)
    controller = FakeTeardownController()

    # When: tearing down the owned server tree.
    evidence = teardown_owned_server(
        process=process,
        controller=controller,
        owned_pids=[1234],
        gpu_pid_probe=lambda: [1234],
        poll_interval_seconds=0,
        timeout_seconds=0,
    )

    # Then: teardown is marked uncertain and the residual PID is recorded.
    assert process.terminated is True
    assert controller.terminated_job is True
    assert evidence.terminated is False
    assert evidence.gpu_pids_after == [1234]
    assert evidence.teardown_uncertain is True


def test_job_object_wrapper_marshals_kill_on_close_and_assigns_process() -> None:
    # Given: a fake kernel32 facade.
    kernel32 = FakeKernel32()
    job = WindowsJobObject(kernel32=kernel32)

    # When: creating, assigning, terminating, and closing a job.
    handle = job.create()
    job.assign_process(handle, process_handle=222)
    job.terminate(handle, exit_code=70)
    job.close(handle)

    # Then: the Windows calls receive the expected handles and kill-on-close flag.
    assert handle == 111
    assert kernel32.info_class == 9
    assert kernel32.limit_flags == JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    assert kernel32.assigned == (111, 222)
    assert kernel32.terminated == (111, 70)
    assert kernel32.closed == [111]
