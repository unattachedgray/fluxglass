"""Read-only, dependency-free Linux sensor sampler."""
import json, subprocess, time
from pathlib import Path

def parse_cpu_list(text):
    out=set()
    for part in text.strip().split(","):
        if not part: continue
        bounds=[int(v) for v in part.split("-")]; out.update(range(bounds[0],bounds[-1]+1))
    return out

def parse_pmon(text, name=lambda pid,fallback:fallback):
    rows=[]
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"): continue
        p=line.split(maxsplit=11)
        if len(p)<11: continue
        try: pid,mb=int(p[1]),float(p[9])
        except ValueError: continue
        def num(v):
            try:return float(v)
            except ValueError:return None
        rows.append({"pid":pid,"name":name(pid,p[-1]),"type":p[2],"sm_pct":num(p[3]),"vram_mb":mb})
    return rows

def parse_psi(text):
    result={}
    for line in text.splitlines():
        parts=line.split()
        if not parts:continue
        values={}
        for item in parts[1:]:
            key,raw=item.split("=",1)
            try:values[key]=float(raw)
            except ValueError:pass
        result[parts[0]]=values
    return result

class Sampler:
    def __init__(self): self.prev=None; self.cores={}
    def read(self,p): return Path(p).read_text()
    def cpuset(self,n):
        try:return parse_cpu_list(self.read(f"/sys/devices/system/cpu/{n}"))
        except (OSError,ValueError):return set()
    def thermal(self):
        for root in Path("/sys/class/hwmon").glob("hwmon*"):
            try:
                if (root/"name").read_text().strip() not in ("coretemp","k10temp","zenpower"):continue
                labels={p.read_text().strip():p.with_name(p.name.replace("_label","_input")) for p in root.glob("temp*_label")}
                for k in ("Package id 0","Tctl","Tdie","CPU"):
                    if k in labels:
                        source=labels[k]; temp=float(source.read_text())/1000; stem=source.name.replace("_input","")
                        limit=number_from(root/f"{stem}_crit",1000) or number_from(root/f"{stem}_max",1000)
                        return temp,limit
            except (OSError,ValueError):pass
        return None,None
    def pressure(self):
        result={}
        for name in ("cpu","memory","io"):
            try:result[name]=parse_psi(self.read(f"/proc/pressure/{name}"))
            except (OSError,ValueError):pass
        return result
    def gpu(self):
        q="memory.used,memory.total,utilization.gpu,utilization.memory,temperature.gpu,temperature.gpu.tlimit,power.draw,power.limit,fan.speed,clocks.current.graphics,clocks_event_reasons.active,utilization.encoder,utilization.decoder,encoder.stats.sessionCount"
        try:
            raw=subprocess.run(["nvidia-smi",f"--query-gpu={q}","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=3,check=True).stdout.splitlines()[0]
            parts=raw.split(", "); vals=[]
            for v in parts:
                try:vals.append(float(v))
                except ValueError:vals.append(None)
            keys=("used_mb","total_mb","util_pct","bandwidth_pct","temperature_c","thermal_margin_c","power_w","power_limit_w","fan_pct","clock_mhz","throttle_mask","encoder_pct","decoder_pct","encoder_sessions"); gpu=dict(zip(keys,vals))
            gpu["throttle_mask"]=parts[10]
            pmon=subprocess.run(["nvidia-smi","pmon","-c","1","-s","um"],capture_output=True,text=True,timeout=3).stdout
            def pname(pid,fallback):
                try:return Path(f"/proc/{pid}/comm").read_text().strip()
                except OSError:return fallback
            gpu["processes"]=parse_pmon(pmon,pname); return gpu
        except (OSError,subprocess.SubprocessError,IndexError):return self.drm_gpu()
    def drm_gpu(self):
        """Best-effort AMD/Intel telemetry from stable DRM/sysfs counters."""
        for card in sorted(Path("/sys/class/drm").glob("card[0-9]*")):
            dev=card/"device"
            try:
                vendor=(dev/"vendor").read_text().strip()
            except OSError:
                continue
            def number(name, divisor=1):
                try:return float((dev/name).read_text().strip())/divisor
                except (OSError,ValueError):return None
            total=number("mem_info_vram_total",1024*1024)
            used=number("mem_info_vram_used",1024*1024)
            util=number("gpu_busy_percent")
            temp=None
            for hwmon in (dev/"hwmon").glob("hwmon*"):
                temp=number_from(hwmon/"temp1_input",1000)
                if temp is not None:break
            if util is not None or total is not None:
                return {"used_mb":used or 0,"total_mb":total or 0,"util_pct":util or 0,
                        "bandwidth_pct":None,"temperature_c":temp,"power_w":None,
                        "power_limit_w":None,"fan_pct":None,"clock_mhz":None,
                        "vendor":{"0x1002":"AMD","0x8086":"Intel"}.get(vendor,vendor),"processes":[]}
        return None
    def sample(self):
        lines=self.read("/proc/stat").splitlines(); v=[int(x) for x in lines[0].split()[1:]]; total,idle=sum(v),v[3]+v[4]; pct=0
        if self.prev:
            dt,di=total-self.prev[0],idle-self.prev[1]; pct=100*(dt-di)/dt if dt else 0
        self.prev=(total,idle); active=0; nxt={}; per_core=[]
        for line in lines[1:]:
            n,*raw=line.split()
            if not n[3:].isdigit():break
            a=[int(x) for x in raw]; t=sum(a); i=a[3]+a[4]; cid=int(n[3:]); old=self.cores.get(cid); cp=100*((t-old[0])-(i-old[1]))/(t-old[0]) if old and t>old[0] else 0; active+=cp>=5; nxt[cid]=(t,i); per_core.append(cp)
        self.cores=nxt; mem={}
        for line in self.read("/proc/meminfo").splitlines():k,x=line.split(":",1); mem[k]=int(x.split()[0])/1024
        on,possible=self.cpuset("online"),self.cpuset("possible")
        temperature,temperature_limit=self.thermal()
        return {"t":time.time(),"cpu":{"pct":pct,"active":active,"online":len(on),"possible":len(possible),"offline":len(possible-on),"per_core":per_core,"temperature_c":temperature,"temperature_limit_c":temperature_limit},"memory":{"used_mb":mem["MemTotal"]-mem["MemAvailable"],"total_mb":mem["MemTotal"],"available_mb":mem["MemAvailable"],"swap_used_mb":mem.get("SwapTotal",0)-mem.get("SwapFree",0),"swap_total_mb":mem.get("SwapTotal",0)},"pressure":self.pressure(),"gpu":self.gpu()}

def number_from(path, divisor=1):
    try:return float(path.read_text().strip())/divisor
    except (OSError,ValueError):return None

def snapshot_json():
    """Stable machine-readable boundary shared by the app and other clients."""
    return json.dumps(Sampler().sample(), separators=(",", ":"))
