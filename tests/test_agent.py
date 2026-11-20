import json
from pathlib import Path
import tempfile
import unittest
from agent.yt_agent import prepare, approve, can_upload, load_queue, save_queue

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.video = self.folder / "clip.mp4"
        self.video.write_bytes(b"example")
        self.queue = {}

    def test_prepare_requires_real_video(self):
        with self.assertRaises(ValueError):
            prepare(self.queue, self.folder / "missing.mp4", "Title", "", "private", [])

    def test_never_auto_approves(self):
        key = prepare(self.queue, self.video, "Title", "", "private", [])
        self.assertFalse(can_upload(self.queue[key]))
        self.assertEqual(self.queue[key]["status"], "draft")

    def test_confirmation_is_exact(self):
        key = prepare(self.queue, self.video, "Title", "", "private", [])
        with self.assertRaises(ValueError):
            approve(self.queue, key, "yes")
        self.assertFalse(can_upload(self.queue[key]))
        approve(self.queue, key, "APPROVE " + key)
        self.assertTrue(can_upload(self.queue[key]))

    def test_changed_metadata_revokes_approval(self):
        key = prepare(self.queue, self.video, "Title", "", "private", [])
        approve(self.queue, key, "APPROVE " + key)
        self.queue[key]["privacy"] = "public"
        self.assertFalse(can_upload(self.queue[key]))

    def test_reprepare_revokes_approval(self):
        key = prepare(self.queue, self.video, "Title", "", "private", [])
        approve(self.queue, key, "APPROVE " + key)
        self.assertEqual(key, prepare(self.queue, self.video, "Title", "", "private", []))
        self.assertFalse(can_upload(self.queue[key]))

    def test_serialization(self):
        key = prepare(self.queue, self.video, "Title", "", "private", [])
        queuefile = self.folder / ".queue" / "queue.json"
        save_queue(queuefile, self.queue)
        self.assertEqual(load_queue(queuefile)[key]["title"], "Title")
        self.assertTrue(json.loads(queuefile.read_text()))

if __name__ == "__main__":
    unittest.main()
