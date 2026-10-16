import unittest

from linusetup import effects as E
from linusetup.installer.system import Hardware, gpu_vendor

# (lspci vendor field, device field, expected tier on a normal desktop)
GPUS = [
    ("NVIDIA Corporation", "GB202 [GeForce RTX 5090]", "full"),
    ("NVIDIA Corporation", "AD102 [GeForce RTX 4090]", "full"),
    ("NVIDIA Corporation", "GA104 [GeForce RTX 3070]", "full"),
    ("NVIDIA Corporation", "TU104 [GeForce RTX 2080 SUPER]", "full"),
    ("NVIDIA Corporation", "GA104GL [RTX A4000]", "full"),
    ("NVIDIA Corporation", "GA106 [GeForce RTX 3060 Lite Hash Rate]", "balanced"),
    ("NVIDIA Corporation", "AD107M [GeForce RTX 4050 Max-Q / Mobile]", "balanced"),
    ("NVIDIA Corporation", "TU116 [GeForce GTX 1660 SUPER]", "balanced"),
    ("NVIDIA Corporation", "GP104 [GeForce GTX 1070]", "balanced"),
    ("NVIDIA Corporation", "TU117 [GeForce GTX 1650]", "minimal"),
    ("NVIDIA Corporation", "GP107 [GeForce GTX 1050 Ti]", "minimal"),
    ("NVIDIA Corporation", "GM204 [GeForce GTX 970]", "minimal"),
    ("NVIDIA Corporation", "GK208B [GeForce GT 710]", "minimal"),
    ("NVIDIA Corporation", "GP108M [GeForce MX150]", "minimal"),
    ("Advanced Micro Devices, Inc. [AMD/ATI]", "Navi 48 [Radeon RX 9070/9070 XT/9070 GRE]", "full"),
    ("Advanced Micro Devices, Inc. [AMD/ATI]", "Navi 31 [Radeon RX 7900 XT/7900 XTX/7900 GRE/7900M]", "full"),
    ("Advanced Micro Devices, Inc. [AMD/ATI]", "Navi 22 [Radeon RX 6700/6700 XT/6750 XT / 6800M/6850M XT]", "full"),
    ("Advanced Micro Devices, Inc. [AMD/ATI]", "Navi 23 [Radeon RX 6600/6600 XT/6600M]", "balanced"),
    ("Advanced Micro Devices, Inc. [AMD/ATI]", "Navi 10 [Radeon RX 5600 OEM/5600 XT / 5700/5700 XT]", "balanced"),
    ("Advanced Micro Devices, Inc. [AMD/ATI]", "Vega 10 XL/XT [Radeon RX Vega 56/64]", "balanced"),
    ("Advanced Micro Devices, Inc. [AMD/ATI]", "Navi 24 [Radeon RX 6400/6500 XT/6500M]", "minimal"),
    ("Advanced Micro Devices, Inc. [AMD/ATI]", "Ellesmere [Radeon RX 470/480/570/570X/580/580X/590]", "minimal"),
    ("Advanced Micro Devices, Inc. [AMD/ATI]", "Phoenix1 [Radeon 780M]", "minimal"),
    ("Advanced Micro Devices, Inc. [AMD/ATI]", "Rembrandt [Radeon 680M]", "minimal"),
    ("Advanced Micro Devices, Inc. [AMD/ATI]", "Cezanne [Radeon Vega Series / Radeon Vega Mobile Series]", "minimal"),
    ("Advanced Micro Devices, Inc. [AMD/ATI]", "Raphael", "minimal"),
    ("Intel Corporation", "DG2 [Arc A770]", "balanced"),
    ("Intel Corporation", "Battlemage G21 [Arc B580]", "balanced"),
    ("Intel Corporation", "DG2 [Arc A380]", "minimal"),
    ("Intel Corporation", "Skylake-S GT2 [HD Graphics 530]", "minimal"),
    ("Intel Corporation", "Alder Lake-P GT2 [Iris Xe Graphics]", "minimal"),
    ("Intel Corporation", "CometLake-S GT2 [UHD Graphics 630]", "minimal"),
    ("Red Hat, Inc.", "Virtio 1.0 GPU", "minimal"),
    ("VMware", "SVGA II Adapter", "minimal"),
]


def hw(gpus, **kw):
    base = dict(gpus=[(gpu_vendor(v), f"{v} {d}") for v, d in gpus], ram_gb=16, cpu_cores=8, virt="", render_node=True)
    base.update(kw)
    return Hardware(**base)


class Tiers(unittest.TestCase):
    def test_gpu_table(self):
        for v, d, want in GPUS:
            with self.subTest(gpu=d):
                self.assertEqual(E.choose(hw([(v, d)]))["tier"], want)

    def test_vendor_needs_whole_words(self):
        self.assertEqual(gpu_vendor("Intel Corporation"), "intel")          # "Corporation" contains "ati"
        self.assertEqual(gpu_vendor("Advanced Micro Devices, Inc. [AMD/ATI]"), "amd")
        self.assertEqual(gpu_vendor("ATI Technologies Inc"), "amd")
        self.assertEqual(gpu_vendor("NVIDIA Corporation"), "nvidia")
        self.assertEqual(gpu_vendor("Red Hat, Inc."), "other")

    def test_hybrid_laptop_uses_the_dedicated_gpu(self):
        h = hw([("Intel Corporation", "Alder Lake-P GT2 [Iris Xe Graphics]"),
                ("NVIDIA Corporation", "AD107M [GeForce RTX 4060 Max-Q / Mobile]")])
        self.assertEqual(E.choose(h)["tier"], "balanced")

    def test_guards(self):
        strong = [("NVIDIA Corporation", "AD102 [GeForce RTX 4090]")]
        self.assertEqual(E.choose(hw(strong, virt="kvm"))["tier"], "minimal")
        self.assertEqual(E.choose(hw(strong, render_node=False))["tier"], "minimal")
        self.assertEqual(E.choose(hw(strong, ram_gb=3))["tier"], "minimal")
        self.assertEqual(E.choose(hw(strong, cpu_cores=2))["tier"], "minimal")
        self.assertEqual(E.choose(hw(strong, ram_gb=6))["tier"], "balanced")
        self.assertEqual(E.choose(hw([]))["tier"], "minimal")

    def test_override(self):
        r = E.choose(hw([("Intel Corporation", "UHD Graphics 630")]), override="full")
        self.assertEqual((r["tier"], r["detected"], r["auto"]), ("full", "minimal", False))
        self.assertEqual(E.choose(hw([]), override="nonsense")["tier"], "minimal")

    def test_software_rendering_only_without_acceleration(self):
        self.assertTrue(E.needs_software_rendering(hw([], virt="kvm")))
        self.assertTrue(E.needs_software_rendering(hw([], render_node=False)))
        self.assertFalse(E.needs_software_rendering(hw([("Intel Corporation", "UHD Graphics 630")])))


if __name__ == "__main__":
    unittest.main()
