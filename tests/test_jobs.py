import time
import unittest

from mot_viewer.services.jobs import JobManager


class JobManagerCancellationTests(unittest.TestCase):
    def test_running_job_can_be_cancelled(self):
        manager = JobManager()

        def work(progress, is_cancelled):
            for idx in range(100):
                if is_cancelled():
                    raise RuntimeError("cancelled")
                progress(idx, "working")
                time.sleep(0.005)
            return {"done": True}

        job = manager.start("Cancelable", work)
        time.sleep(0.02)
        manager.cancel(job.job_id)
        for _ in range(100):
            current = manager.get(job.job_id)
            if current and current.status == "cancelled":
                break
            time.sleep(0.01)
        self.assertEqual(manager.get(job.job_id).status, "cancelled")


if __name__ == "__main__":
    unittest.main()
