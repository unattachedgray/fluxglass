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
