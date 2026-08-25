import sys, unittest
sys.path.insert(0,"src")
from pathlib import Path
from tempfile import TemporaryDirectory
from fluxglass.app import advance_state_event,columns_for_width,detect_events,human_mb,load_order,resource_metrics,save_order

class FormatTests(unittest.TestCase):
    def test_human_mb(self):
        self.assertEqual(human_mb(512),"512 MiB")
        self.assertEqual(human_mb(1536),"1.5 GiB")
    def test_graph_order_round_trip_and_schema_repair(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/"settings.json"
            save_order(["ram","gpu","cpu","vram"],path)
            self.assertEqual(load_order(path),["ram","gpu","cpu","vram"])
            path.write_text('{"graph_order":["cpu","unknown","cpu"]}')
            self.assertEqual(load_order(path),["cpu","gpu","vram","ram"])
    def test_responsive_columns(self):
        self.assertEqual([columns_for_width(w) for w in (719,720,1359,1360)],[1,2,2,4])
    def test_resource_compass_states(self):
        def snap(cpu,gpu,ram=40,vram=20):
            return {"cpu":{"pct":cpu},"gpu":{"util_pct":gpu,"used_mb":vram,"total_mb":100},"memory":{"used_mb":ram,"total_mb":100}}
        self.assertEqual(resource_metrics(snap(70,10))["state"],"CPU-LED")
        self.assertEqual(resource_metrics(snap(20,80))["state"],"GPU-LED")
        self.assertEqual(resource_metrics(snap(50,50))["state"],"BALANCED")
        self.assertEqual(resource_metrics(snap(2,1))["state"],"IDLE")
        self.assertEqual(resource_metrics(snap(20,20,90))["state"],"MEMORY PRESSURE")
        pressured=snap(20,20); pressured["pressure"]={"io":{"some":{"avg10":2.5}}}
        self.assertEqual(resource_metrics(pressured)["state"],"CONTENTION")
    def test_event_detection(self):
        base={"cpu":{"pct":1},"gpu":{"util_pct":1,"used_mb":1,"total_mb":100},"memory":{"used_mb":1,"total_mb":100}}
        busy={"cpu":{"pct":80},"gpu":{"util_pct":1,"used_mb":1,"total_mb":100},"memory":{"used_mb":1,"total_mb":100}}
        self.assertIn(("event_state",{"old":"IDLE","new":"CPU-LED"}),detect_events(base,busy))

    def test_state_events_require_three_matching_samples(self):
        stable,pending,count,event=advance_state_event("IDLE",None,None,0)
        for _ in range(2):
            stable,pending,count,event=advance_state_event("CPU-LED",stable,pending,count)
            self.assertIsNone(event)
        stable,pending,count,event=advance_state_event("CPU-LED",stable,pending,count)
        self.assertEqual(("event_state",{"old":"IDLE","new":"CPU-LED"}),event)

if __name__ == "__main__": unittest.main()
