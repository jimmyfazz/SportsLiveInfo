"""Provider naming conventions: matching key vs display label (keep every channel)."""
import unittest

from sportsliveinfo.guide import channel_variant, display_labels, normalized_name


class MatchingKeyTests(unittest.TestCase):
    def test_quality_copies_share_one_matching_key(self):
        for name in ["UK-Sky Sports Main Event FHD 50FPS", "UK-Sky Sports Main Event FHD", "UK-Sky Sports Main Event HD",
                     "UK-Sky Sports Main Event SD*", "Sky Sports Main Event FHD HEVC", "UK: Sky Sports Main Event (UK)"]:
            with self.subTest(name=name):
                self.assertEqual(normalized_name(name), "sky sports main event")

    def test_annotations_are_ignored_but_identity_is_kept(self):
        self.assertEqual(normalized_name("UK-BBC Three FHD (From 19:00 UK)"), "bbc three")
        self.assertEqual(normalized_name("Sky Sports+ 01 (Live Event Only)"), "sky sports+ 01")
        self.assertEqual(normalized_name("(FR) (M) France 2"), "france 2")
        self.assertEqual(normalized_name("beIN SPORTS 1 (G) - HEVC"), "bein sports 1 (g)")
        self.assertEqual(normalized_name("Premier Sports 1 FHD (IE)"), "premier sports 1 roi")
        self.assertEqual(normalized_name("(QX) (ZZ) Canal 9 (CENTRO)"), "(qx) (zz) canal 9 (centro)")
        self.assertEqual(normalized_name("99.5 Example FM (720p)"), "99.5 example fm")
        self.assertEqual(normalized_name("That&apos;s TV"), "that's tv")
        self.assertNotEqual(normalized_name("Sky Sports Main Event +1"), normalized_name("Sky Sports Main Event"))
        self.assertNotEqual(normalized_name("BBC One Scotland HD"), normalized_name("BBC One HD"))


class DisplayLabelTests(unittest.TestCase):
    def test_every_quality_copy_keeps_a_distinct_sensible_label(self):
        names = ["UK-Sky Sports Main Event FHD 50FPS", "UK-Sky Sports Main Event FHD", "UK-Sky Sports Main Event HD",
                 "UK-TNT Sports Ultimate 4K HDR", "UK-TNT Sports 1 FHD HEVC", "UK-BBC Two SD*",
                 "UK-BBC Three HD (From 19:00 UK)", "Premier Sports 1 FHD (IE)", "Sky Sports+ 01 (Live Event Only)"]
        self.assertEqual(display_labels(names), [
            "Sky Sports Main Event · FHD · 50fps", "Sky Sports Main Event · FHD", "Sky Sports Main Event · HD",
            "TNT Sports Ultimate · 4K · HDR", "TNT Sports 1 · FHD · HEVC", "BBC Two · SD · Alt feed",
            "BBC Three · HD · from 19:00", "Premier Sports 1 · FHD · Ireland", "Sky Sports+ 01 · Events only"])

    def test_identical_visible_names_are_numbered_never_dropped(self):
        self.assertEqual(display_labels(["Example One", "Example One ", "Example Sport 2 (HD)", "Example Sport 2 HD"]),
                         ["Example One", "Example One · 2", "Example Sport 2 · HD", "Example Sport 2 · HD · 2"])

    def test_identity_parts_stay_in_the_base_name(self):
        self.assertEqual(channel_variant("beIN SPORTS 3 (N) - 4K")["label"], "beIN SPORTS 3 (N) · 4K")
        self.assertEqual(channel_variant("UK: SAMPLE SPORTS HD EN 3")["label"], "SAMPLE SPORTS EN 3 · HD")
        self.assertEqual(channel_variant("(QX) (ZZ) Canal 9 (CENTRO)")["label"], "(QX) (ZZ) Canal 9 (CENTRO)")
        self.assertEqual(channel_variant("Channel 4 +1 HD")["base"], "Channel 4 +1")
        self.assertEqual(channel_variant("HD Example")["base"], "HD Example")      # leading word may be the brand

    def test_label_is_never_empty(self):
        self.assertEqual(channel_variant("HD")["base"], "HD")


if __name__ == "__main__":
    unittest.main()
