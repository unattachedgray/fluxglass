import sys,unittest
sys.path.insert(0,"src")
from fluxglass.sensors import parse_cpu_list,parse_pmon,parse_psi
class Tests(unittest.TestCase):
    def test_cpu(self):self.assertEqual(parse_cpu_list("0-3,6,8-9"),{0,1,2,3,6,8,9})
    def test_pmon(self):
        r=parse_pmon("0 42 C+G 73 21 - - - - 6144 0 python3")[0]
        self.assertEqual((r["pid"],r["vram_mb"],r["sm_pct"]),(42,6144,73))
    def test_psi(self):
        r=parse_psi("some avg10=1.25 avg60=0.50 total=42\nfull avg10=0.10 avg60=0.00 total=7")
        self.assertEqual(r["some"]["avg10"],1.25)
        self.assertEqual(r["full"]["total"],7)

import tempfile
from pathlib import Path
from fluxglass.sensors import Sampler,is_integrated
MEMINFO="MemTotal:       16046368 kB\nMemAvailable:   13981632 kB\nSwapTotal:             0 kB\n"
def build(tmp,cards):
    """cards: {card name: (pci slot, {attr: text})}"""
    root=Path(tmp)/"drm"; root.mkdir()
    for name,(slot,attrs) in cards.items():
        dev=Path(tmp)/"pci"/slot; dev.mkdir(parents=True)
        for attr,text in attrs.items():(dev/attr).write_text(text)
        (root/name).mkdir(); (root/name/"device").symlink_to(dev)
    meminfo=Path(tmp)/"meminfo"; meminfo.write_text(MEMINFO)
    return root,meminfo
class GpuTests(unittest.TestCase):
    def test_integrated_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,_=build(tmp,{"card1":("0000:00:02.0",{"vendor":"0x8086"}),"card2":("0000:01:00.0",{"vendor":"0x10de"})})
            self.assertTrue(is_integrated(root/"card1"/"device"))
            self.assertFalse(is_integrated(root/"card2"/"device"))
    def test_integrated_reports_shared_system_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,meminfo=build(tmp,{"card1":("0000:00:02.0",{"vendor":"0x8086"})})
            g=Sampler().drm_gpu(root,meminfo)
            self.assertTrue(g["shared_memory"])
            self.assertEqual(g["vendor"],"Intel")
            self.assertIsNone(g["util_pct"])
            self.assertAlmostEqual(g["total_mb"],16046368/1024)
            self.assertAlmostEqual(g["used_mb"],(16046368-13981632)/1024)
    def test_dedicated_counters_win_over_shared(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,meminfo=build(tmp,{"card1":("0000:00:02.0",{"vendor":"0x8086"}),
                                    "card2":("0000:01:00.0",{"vendor":"0x1002","mem_info_vram_total":str(8*1024*1024*1024),"mem_info_vram_used":str(1024*1024*1024),"gpu_busy_percent":"37"})})
            g=Sampler().drm_gpu(root,meminfo)
            self.assertFalse(g["shared_memory"])
            self.assertEqual((g["vendor"],g["util_pct"],g["total_mb"],g["used_mb"]),("AMD",37.0,8192.0,1024.0))
    def test_discrete_without_counters_is_absent_not_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,meminfo=build(tmp,{"card2":("0000:01:00.0",{"vendor":"0x10de"})})
            self.assertIsNone(Sampler().drm_gpu(root,meminfo))

from fluxglass.sensors import EngineBusy,frequency_busy
def add_freq(root,card,act,rpn=350,rp0=1250):
    for name,value in (("gt_act_freq_mhz",act),("gt_RPn_freq_mhz",rpn),("gt_RP0_freq_mhz",rp0)):
        (root/card/name).write_text(f"{value}\n")
class BusyTests(unittest.TestCase):
    def test_frequency_scales_between_rpn_and_rp0(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,_=build(tmp,{"card1":("0000:00:02.0",{"vendor":"0x8086"})})
            for act,expected in ((350,0.0),(800,50.0),(1250,100.0),(2000,100.0)):
                add_freq(root,"card1",act)
                self.assertAlmostEqual(frequency_busy(root/"card1"),expected)
    def test_frequency_absent_when_counters_missing_or_degenerate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,_=build(tmp,{"card1":("0000:00:02.0",{"vendor":"0x8086"})})
            self.assertIsNone(frequency_busy(root/"card1"))
            add_freq(root,"card1",400,rpn=1250,rp0=1250)
            self.assertIsNone(frequency_busy(root/"card1"))
    def test_integrated_falls_back_to_frequency_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root,meminfo=build(tmp,{"card1":("0000:00:02.0",{"vendor":"0x8086"})})
            add_freq(root,"card1",800)
            g=Sampler().drm_gpu(root,meminfo)
            self.assertEqual(g["util_source"],"frequency")
            self.assertAlmostEqual(g["util_pct"],50.0)
    def test_missing_pmu_degrades_to_no_reading_not_a_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            engine=EngineBusy(base=Path(tmp)/"absent-pmu")
            self.assertEqual(engine.fds,{})
            self.assertIsNone(engine.read())
    def test_first_pmu_read_only_primes_the_rate(self):
        engine=EngineBusy.__new__(EngineBusy); engine.fds={}; engine.prev=None
        self.assertIsNone(engine.read())
