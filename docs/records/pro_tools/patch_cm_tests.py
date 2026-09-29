"""One-off: add codec-matched helper tests to tests/test_s1_synth_digital.py in the given checkout."""
import sys
from pathlib import Path

p = Path(sys.argv[1]) / "tests/test_s1_synth_digital.py"
s = p.read_bytes().decode("utf-8")
anchor = '\n\nif __name__ == "__main__":'
assert anchor in s
new = '''
    def test_next_kbps_rescales_by_byte_error(self):
        self.assertEqual(sd.next_kbps(3000, 1_500_000, 1_000_000), 2000)
        self.assertEqual(sd.next_kbps(1000, 800_000, 1_000_000), 1250)
        self.assertEqual(sd.next_kbps(100, 10_000_000, 1_000), 50)  # floor

    def test_build_pairs_marks_codec_matched_half(self):
        def row(f, label, codec, b):
            return {"source_id": "SRC001", "window": "0", "split": "train", "file": f,
                    "label": label, "codec": codec, "bytes": str(b)}
        rows = [row("SRC001_W0_ORIG.mp4", "original", "mpeg4", 1000),
                row("SRC001_W0_DIG0.mp4", "recapture_synthetic", "h264", 2000),
                row("SRC001_W0_ORIGX.mp4", "original", "h264", 2000),
                row("SRC001_W0_DIGM0.mp4", "recapture_synthetic", "mpeg4", 1000)]
        pairs = sd.build_pairs(rows)
        self.assertEqual(len(pairs), 4)
        matched = sorted((p["original_file"], p["recapture_file"]) for p in pairs if p["codec_matched"])
        self.assertEqual(matched, [("SRC001_W0_ORIG.mp4", "SRC001_W0_DIGM0.mp4"),
                                   ("SRC001_W0_ORIGX.mp4", "SRC001_W0_DIG0.mp4")])
        self.assertEqual({p["bytes_ratio"] for p in pairs if p["codec_matched"]}, {1.0})
        for codec in ("h264", "mpeg4"):  # per-file codec carries no label information
            self.assertEqual(sorted(r["label"] for r in rows if r["codec"] == codec),
                             ["original", "recapture_synthetic"])
'''
s = s.replace(anchor, "\n" + new.rstrip("\n") + anchor, 1)
p.write_bytes(s.encode("utf-8"))
print("ok")
