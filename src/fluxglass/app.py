"""Fluxglass adaptive GTK4 system instrument."""
import argparse, csv, json, math, os
from collections import deque
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango, PangoCairo

from .sensors import Sampler
from .i18n import get_language, set_language, state_text, t

PALETTE = ((0.31,0.86,0.72),(0.45,0.68,1.0),(0.78,0.51,1.0),(1.0,0.61,0.36),(0.98,0.38,0.55))
GRAPH_IDS = ("gpu", "vram", "cpu", "ram")
FONT_STACK = "Pretendard Variable, Noto Sans KR, Noto Sans CJK KR, Sans"

def canvas_text(cr,x,baseline,value,size,color=(.9,.93,.98),bold=False):
    """Draw shaped text with per-glyph fallback; never rely on Cairo's toy font API."""
    layout=PangoCairo.create_layout(cr); description=Pango.FontDescription()
    description.set_family(FONT_STACK); description.set_absolute_size(size*Pango.SCALE)
    description.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
    layout.set_font_description(description); layout.set_text(str(value),-1)
    _ink,logical=layout.get_pixel_extents()
    cr.set_source_rgba(*color,1); cr.move_to(x,baseline-logical.height); PangoCairo.show_layout(cr,layout)
    return logical.width

def canvas_text_width(cr,value,size,bold=False):
    layout=PangoCairo.create_layout(cr); description=Pango.FontDescription()
    description.set_family(FONT_STACK); description.set_absolute_size(size*Pango.SCALE)
    description.set_weight(Pango.Weight.BOLD if bold else Pango.Weight.NORMAL)
    layout.set_font_description(description); layout.set_text(str(value),-1)
    return layout.get_pixel_extents()[1].width

def canvas_text_fit(cr,x,baseline,value,size,max_width,color=(.9,.93,.98),bold=False,min_size=15):
    """Fit a single-line live metric without clipping its card."""
    fitted=size
    while fitted>min_size and canvas_text_width(cr,value,fitted,bold)>max_width:fitted-=1
    return canvas_text(cr,x,baseline,value,fitted,color,bold)

def columns_for_width(width): return 1 if width<720 else (2 if width<1360 else 4)

def config_path():
    root=Path(os.environ.get("XDG_CONFIG_HOME",Path.home()/".config"))
    return root/"fluxglass"/"settings.json"

def load_settings(path=None):
    try:
        target=path or config_path()
        value=json.loads(target.read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}

def write_settings(updates,path=None):
    target=path or config_path(); value=load_settings(target); value.update(updates)
    target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix(".tmp"); temporary.write_text(json.dumps(value,indent=2)+"\n"); temporary.replace(target)

def load_order(path=None):
    value=load_settings(path).get("graph_order",[])
    if not isinstance(value,list):return list(GRAPH_IDS)
    clean=[]
    for item in value:
        if item in GRAPH_IDS and item not in clean:clean.append(item)
    return clean+[item for item in GRAPH_IDS if item not in clean]

def save_order(order,path=None):
    write_settings({"graph_order":order},path)

def load_options(path=None):
    defaults={"pressure":True,"state_history":True,"events":True}
    value=load_settings(path).get("view_options",{})
    if isinstance(value,dict):defaults.update({k:bool(v) for k,v in value.items() if k in defaults})
    return defaults

def load_language(path=None):
    value=load_settings(path).get("language","ko")
    return value if value in ("ko","en") else "ko"

def detect_events(previous,current):
    if previous is None:return [("event_started",{})]
    events=[]; old,new=resource_metrics(previous),resource_metrics(current)
    if old["state"]!=new["state"]:events.append(("event_state",{"old":old["state"],"new":new["state"]}))
    if bool(previous.get("gpu"))!=bool(current.get("gpu")):events.append(("event_gpu_available" if current.get("gpu") else "event_gpu_lost",{}))
    mask=((current.get("gpu") or {}).get("throttle_mask") or "0")
    try:throttled=int(mask,16)&~1
    except (TypeError,ValueError):throttled=0
    if throttled:events.append(("event_throttle",{}))
    return events

def advance_state_event(current,stable,pending,count,required=3):
    """Debounce categorical state changes so the event ledger records trends, not jitter."""
    if stable is None:return current,None,0,None
    if current==stable:return stable,None,0,None
    count=count+1 if current==pending else 1; pending=current
    if count>=required:return current,None,0,("event_state",{"old":stable,"new":current})
    return stable,pending,count,None

def human_mb(value):
    value = value or 0
    return f"{value/1024:.1f} GiB" if value >= 1024 else f"{value:.0f} MiB"

def resource_metrics(snapshot):
    gpu=snapshot.get("gpu") or {}; memory=snapshot.get("memory") or {}; cpu=snapshot.get("cpu") or {}
    pressure=snapshot.get("pressure") or {}
    def psi(name):return ((pressure.get(name) or {}).get("some") or {}).get("avg10",0) or 0
    values={
        "cpu":max(0,min(100,cpu.get("pct") or 0)),
        "gpu":max(0,min(100,gpu.get("util_pct") or 0)),
        "ram":100*(memory.get("used_mb") or 0)/max(1,memory.get("total_mb") or 1),
        "vram":100*(gpu.get("used_mb") or 0)/max(1,gpu.get("total_mb") or 1),
        "cpu_pressure":psi("cpu"),"memory_pressure":psi("memory"),"io_pressure":psi("io"),
    }
    total=values["cpu"]+values["gpu"]
    values["pressure"]=max(values["cpu_pressure"],values["memory_pressure"],values["io_pressure"])
    if values["pressure"]>=1:state="CONTENTION"
    elif values["vram"]>=90:state="VRAM PRESSURE"
    elif values["ram"]>=85:state="MEMORY PRESSURE"
    elif total<8:state="IDLE"
    elif values["gpu"]/total>.65:state="GPU-LED"
    elif values["gpu"]/total<.35:state="CPU-LED"
    else:state="BALANCED"
    values.update({"activity":max(values["cpu"],values["gpu"]),"state":state})
    return values

class ResourceCompass(Gtk.DrawingArea):
    """One-glance compute balance and capacity-pressure instrument."""
    def __init__(self):
        super().__init__(); self.metrics={k:0 for k in ("cpu","gpu","ram","vram","activity","cpu_pressure","memory_pressure","io_pressure","pressure")}; self.metrics["state"]="WARMING UP"
        self.history=deque(maxlen=180); self.show_pressure=True; self.show_states=True
        self.set_content_height(232); self.set_hexpand(True); self.set_draw_func(self.draw)
    def update(self,snapshot):
        self.metrics=resource_metrics(snapshot)
        self.history.append(dict(self.metrics)); m=self.metrics
        self.set_tooltip_text(t("tooltip_metrics",**m))
        self.queue_draw()
    def arc(self,cr,cx,cy,r,start,extent,color,width,alpha=1):
        cr.set_source_rgba(*color,alpha); cr.set_line_width(width); cr.set_line_cap(1)
        cr.arc(cx,cy,r,start,start+extent); cr.stroke()
    def text(self,cr,x,y,value,size,color=(.9,.93,.98),bold=False):
        return canvas_text(cr,x,y,value,size,color,bold)
    def draw(self,_area,cr,width,height):
        m=self.metrics; compact=width<560; cx=width/2 if compact else min(126,width*.22); cy=91; outer=70
        if self.show_pressure:
            pressure_items=((m["cpu_pressure"],PALETTE[2]),(m["memory_pressure"],PALETTE[3]),(m["io_pressure"],PALETTE[4]))
            for i,(value,color) in enumerate(pressure_items):
                start=-math.pi/2+i*math.pi*2/3; span=math.pi*2/3-.08
                self.arc(cr,cx,cy,80,start,span,(.28,.31,.38),3,.22)
                self.arc(cr,cx,cy,80,start,span*min(1,value/10),color,3,.9)
        # Capacity ring: RAM left half, VRAM right half, each with a quiet remainder.
        gap=.12; half=math.pi-gap
        for start in (math.pi/2+gap/2,-math.pi/2+gap/2):self.arc(cr,cx,cy,outer,start,half,(.28,.31,.38),8,.42)
        self.arc(cr,cx,cy,outer,math.pi/2+gap/2,half*min(1,m["ram"]/100),PALETTE[3],8,.92)
        self.arc(cr,cx,cy,outer,-math.pi/2+gap/2,half*min(1,m["vram"]/100),PALETTE[1],8,.92)
        # Compute ring: filled length is intensity, its color division is CPU/GPU ratio.
        start=-math.pi*.75; sweep=math.pi*1.5; self.arc(cr,cx,cy,53,start,sweep,(.28,.31,.38),13,.45)
        filled=sweep*m["activity"]/100; total=m["cpu"]+m["gpu"]; cpu_share=m["cpu"]/total if total else .5
        cpu_arc=filled*cpu_share; self.arc(cr,cx,cy,53,start,cpu_arc,PALETTE[2],13,.96)
        self.arc(cr,cx,cy,53,start+cpu_arc,filled-cpu_arc,PALETTE[0],13,.96)
        value=f"{m['activity']:.0f}%"; self.text(cr,cx-canvas_text_width(cr,value,24,True)/2,cy+3,value,24,bold=True)
        state=state_text(m["state"]); self.text(cr,cx-canvas_text_width(cr,state,9,True)/2,cy+24,state,9,(.64,.69,.78),True)
        self.text(cr,14,20,t("compass"),11,(.68,.72,.8),True)
        items=((t("cpu"),m["cpu"],PALETTE[2]),(t("gpu"),m["gpu"],PALETTE[0]),(t("ram"),m["ram"],PALETTE[3]),(t("vram"),m["vram"],PALETTE[1]))
        if compact:
            base_y=181
            for i,(name,value,color) in enumerate(items):
                x=14+i*(width-28)/4; self.text(cr,x,base_y,name,9,color,True); self.text(cr,x,base_y+16,f"{value:.0f}%",12)
        else:
            x=max(240,width*.48); row=42
            for i,(name,value,color) in enumerate(items):
                y=45+i*34; self.text(cr,x,y,name,10,color,True); self.text(cr,x+68,y,f"{value:.0f}%",16,bold=True)
                cr.set_source_rgba(*color,.22); cr.set_line_width(3); cr.move_to(x,y+8); cr.line_to(min(width-18,x+150),y+8); cr.stroke()
        if self.show_states and self.history:
            colors={"IDLE":(.30,.33,.39),"CPU-LED":PALETTE[2],"GPU-LED":PALETTE[0],"BALANCED":PALETTE[1],"CONTENTION":PALETTE[4],"MEMORY PRESSURE":PALETTE[3],"VRAM PRESSURE":PALETTE[1]}
            y=height-9; step=width/max(1,len(self.history))
            for i,item in enumerate(self.history):
                cr.set_source_rgba(*colors.get(item["state"],(.4,.42,.48)),.82); cr.rectangle(i*step,y,step+1,4); cr.fill()
            self.text(cr,14,height-14,t("state_history"),9,(.58,.62,.7),True)

class Graph(Gtk.DrawingArea):
    def __init__(self, graph_id, title, getter, detail, color, ceiling=100):
        super().__init__(); self.title=title; self.getter=getter; self.detail=detail
        self.graph_id=graph_id; self.color=color; self.ceiling=ceiling; self.values=deque(maxlen=180); self.hovered=False
        self.set_content_height(156); self.set_hexpand(True); self.set_draw_func(self.draw)
        self.set_focusable(True); self.set_tooltip_text(t("drag_reorder"))
        motion=Gtk.EventControllerMotion(); motion.connect("enter",self.on_enter); motion.connect("motion",self.on_motion); motion.connect("leave",self.on_leave); self.add_controller(motion)
        keys=Gtk.EventControllerKey(); keys.connect("key-pressed",self.on_key); self.add_controller(keys)
        click=Gtk.GestureClick(button=1); click.connect("released",self.on_click); self.add_controller(click)
    def on_enter(self,*_): self.hovered=True; self.set_cursor_from_name("grab"); self.queue_draw()
    def on_motion(self,_controller,x,_y):
        root=self.get_root()
        if hasattr(root,"set_history_cursor"):root.set_history_cursor(round(x/max(1,self.get_width())*max(0,len(root.history)-1)))
    def on_leave(self,*_):
        self.hovered=False; self.set_cursor(None); root=self.get_root()
        if hasattr(root,"set_history_cursor"):root.set_history_cursor(None)
        self.queue_draw()
    def on_click(self,_gesture,n_press,_x,_y):
        if n_press==1:
            root=self.get_root()
            if hasattr(root,"toggle_focus_graph"):root.toggle_focus_graph(self)
    def on_key(self,_controller,keyval,_keycode,state):
        root=self.get_root()
        if keyval in (Gdk.KEY_Return,Gdk.KEY_KP_Enter):return root.toggle_focus_graph(self) if hasattr(root,"toggle_focus_graph") else False
        if keyval==Gdk.KEY_Escape:return root.toggle_focus_graph(None) if hasattr(root,"toggle_focus_graph") else False
        if not state&Gdk.ModifierType.CONTROL_MASK:return False
        if keyval in (Gdk.KEY_Left,Gdk.KEY_Up):delta=-1
        elif keyval in (Gdk.KEY_Right,Gdk.KEY_Down):delta=1
        else:return False
        return root.move_graph(self,delta) if hasattr(root,"move_graph") else False
    def push(self, snapshot): self.values.append(max(0, self.getter(snapshot) or 0)); self.queue_draw()
    def draw(self, _area, cr, width, height):
        scale=self.get_scale_factor(); del scale
        radius=12; cr.new_path(); cr.arc(width-radius,radius,radius,-math.pi/2,0); cr.arc(width-radius,height-radius,radius,0,math.pi/2); cr.arc(radius,height-radius,radius,math.pi/2,math.pi); cr.arc(radius,radius,radius,math.pi,math.pi*1.5); cr.close_path()
        cr.set_source_rgba(.085,.095,.125,.94 if self.hovered else .82); cr.fill_preserve()
        cr.set_source_rgba(*self.color,.34 if self.hovered else .12); cr.set_line_width(1); cr.stroke()
        root=self.get_root(); focused=getattr(root,"focused_graph",None) is self
        header_height=120 if focused and self.graph_id in ("cpu","gpu") else 64
        plot_top=header_height; plot_bottom=height-28; plot_height=max(1,plot_bottom-plot_top)
        cr.set_line_width(1)
        for i in range(1,4):
            y=plot_top+plot_height*i/4; cr.set_source_rgba(1,1,1,.055); cr.move_to(0,y); cr.line_to(width,y); cr.stroke()
        vals=list(self.values)
        if vals:
            cap=max(self.ceiling, max(vals)*1.08); step=width/max(1,len(vals)-1)
            cr.move_to(0,plot_bottom)
            for i,v in enumerate(vals): cr.line_to(i*step,plot_bottom-(v/cap)*plot_height)
            cr.line_to((len(vals)-1)*step,plot_bottom); cr.close_path()
            pat=Gdk.RGBA(); pat.red,pat.green,pat.blue,pat.alpha=(*self.color,.22)
            cr.set_source_rgba(pat.red,pat.green,pat.blue,pat.alpha); cr.fill_preserve()
            cr.set_source_rgb(*self.color); cr.set_line_width(2); cr.stroke()
        cursor=getattr(root,"history_cursor",None); history=getattr(root,"history",())
        if cursor is not None and history:
            cursor=max(0,min(cursor,len(history)-1)); snap=history[cursor]; value=self.getter(snap) or 0
            x=cursor/max(1,len(history)-1)*width; cr.set_source_rgba(1,1,1,.62); cr.set_line_width(1); cr.move_to(x,header_height); cr.line_to(x,height-28); cr.stroke()
            age=max(0,int((history[-1]["t"]-snap["t"]))); note=t("seconds_ago",value=value,seconds=age)
            if self.graph_id in ("gpu","vram"):
                procs=sorted(((snap.get("gpu") or {}).get("processes") or []),key=lambda p:(p.get("sm_pct") or 0,p.get("vram_mb") or 0),reverse=True)
                if procs:note=t("leading_process",base=note,process=procs[0]["name"])
        canvas_text(cr,14,22,self.title.upper(),12,(.92,.95,1))
        canvas_text_fit(cr,14,51,self.detail(),25,width-28,(.92,.95,1))
        canvas_text(cr,14,height-12,t("graph_footer_focused" if focused else "graph_footer"),10,(.7,.74,.81))
        if cursor is not None and history:
            note_width=canvas_text_width(cr,note,10); canvas_text(cr,max(14,width-note_width-14),height-12,note,10,(.9,.93,.98))
        if focused and history:
            snap=history[-1]
            if self.graph_id=="cpu":
                cores=(snap.get("cpu") or {}).get("per_core") or []; cell=max(5,min(13,(width-28)/max(1,len(cores))))
                for i,value in enumerate(cores):
                    cr.set_source_rgba(*self.color,.12+.88*value/100); cr.rectangle(14+i*cell,76,cell-2,18); cr.fill()
                canvas_text(cr,14,110,t("per_core"),10,(.7,.74,.81))
            elif self.graph_id=="gpu":
                gpu=snap.get("gpu") or {}; extra=t("gpu_engines",memory=gpu.get("bandwidth_pct") or 0,encode=gpu.get("encoder_pct") or 0,decode=gpu.get("decoder_pct") or 0)
                canvas_text(cr,14,88,extra,10,(.7,.74,.81))

class ResizeGrip(Gtk.DrawingArea):
    """Visible native-toplevel resize affordance for undecorated windows."""
    def __init__(self):
        super().__init__(); self.set_size_request(28,28); self.set_cursor_from_name("se-resize")
        self.set_tooltip_text(t("resize")); self.set_draw_func(self.draw)
        gesture=Gtk.GestureClick(button=1); gesture.connect("pressed",self.begin_resize); self.add_controller(gesture)
        self.gesture=gesture
    def draw(self,_area,cr,width,height):
        cr.set_source_rgba(.65,.7,.78,.48); cr.set_line_width(1.5)
        for inset in (6,11,16):cr.move_to(width-inset,height-3); cr.line_to(width-3,height-inset)
        cr.stroke()
    def begin_resize(self,gesture,_press,_x,_y):
        window=self.get_root(); surface=window.get_surface() if isinstance(window,Gtk.Window) else None
        device=gesture.get_current_event_device()
        if surface and device:
            surface.begin_resize(Gdk.SurfaceEdge.SOUTH_EAST,device,1,window.get_width(),window.get_height(),gesture.get_current_event_time())

class ResourceWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Fluxglass")
        self.sampler=Sampler(); self.snapshot=None; self.history=deque(maxlen=180); self.history_cursor=None; self.focused_graph=None
        self.events=deque(maxlen=24); self.options=load_options(); self.recording=None; self.recording_writer=None; self.recording_path=None
        self.event_state=None; self.pending_event_state=None; self.pending_event_count=0
        set_language(load_language())
        self.set_decorated(False); self.set_resizable(True)
        self.set_default_size(980,720); self.build(); self.add_tick_callback(self.layout_tick)
        GLib.timeout_add(1000,self.tick); self.tick()
    def build(self):
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        outer.set_margin_top(22); outer.set_margin_bottom(22); outer.set_margin_start(22); outer.set_margin_end(22)
        head=Gtk.Box(); self.brand_icon=Gtk.Image.new_from_icon_name("fluxglass"); self.brand_icon.set_pixel_size(40); self.brand_icon.set_margin_end(10); head.append(self.brand_icon)
        titles=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        brand=Gtk.Label(label=t("brand"), xalign=0); brand.add_css_class("brand")
        self.subtitle=Gtk.Label(label=t("sensors_warming"), xalign=0); self.subtitle.add_css_class("subtitle")
        titles.set_tooltip_text(t("move_window")); titles.append(brand); titles.append(self.subtitle); head.append(titles)
        spacer=Gtk.Box(); spacer.set_hexpand(True); head.append(spacer)
        self.record_button=Gtk.Button(label=t("stop_recording") if self.recording else t("record")); self.record_button.connect("clicked",lambda *_:self.toggle_recording())
        if self.recording:self.record_button.add_css_class("recording")
        head.append(self.record_button)
        self.language_button=Gtk.MenuButton(label="Korean" if get_language()=="ko" else "English"); popover=Gtk.Popover(); choices=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
        choices.set_margin_top(12); choices.set_margin_bottom(12); choices.set_margin_start(12); choices.set_margin_end(12)
        for key,label in (("pressure",t("pressure_halo")),("state_history",t("state_option")),("events",t("events_option"))):
            choice=Gtk.CheckButton(label=label); choice.set_active(self.options[key]); choice.connect("toggled",lambda button,k=key:self.set_option(k,button.get_active())); choices.append(choice)
        language_label=Gtk.Label(label=t("language"),xalign=0); language_label.add_css_class("muted"); choices.append(language_label)
        language=Gtk.DropDown.new_from_strings([t("korean"),t("english")]); language.set_selected(0 if get_language()=="ko" else 1)
        language.connect("notify::selected",self.change_language); choices.append(language)
        popover.set_child(choices); self.language_button.set_popover(popover); head.append(self.language_button)
        maximize=Gtk.Button(label=t("maximize")); maximize.connect("clicked",lambda *_:self.toggle_maximize()); head.append(maximize)
        close_button=Gtk.Button(label=t("quit")); close_button.set_tooltip_text(t("quit_tip"))
        close_button.connect("clicked",lambda *_:self.close()); head.append(close_button)
        self.window_handle=Gtk.WindowHandle()
        self.window_handle.set_child(head); outer.append(self.window_handle)
        self.compass=ResourceCompass(); outer.append(self.compass)
        self.grid=Gtk.Grid(column_spacing=12,row_spacing=12); self.grid.set_column_homogeneous(True); self.columns=0
        def gpu(s): return s.get("gpu") or {}
        graphs={
            "gpu":Graph("gpu",t("gpu_graph"),lambda s:gpu(s).get("util_pct"),lambda:self.gpu_detail(),PALETTE[0]),
            "vram":Graph("vram",t("vram_graph"),lambda s:100*gpu(s).get("used_mb",0)/max(1,gpu(s).get("total_mb",1)),lambda:self.vram_detail(),PALETTE[1]),
            "cpu":Graph("cpu",t("cpu_graph"),lambda s:s["cpu"]["pct"],lambda:self.cpu_detail(),PALETTE[2]),
            "ram":Graph("ram",t("ram_graph"),lambda s:100*s["memory"]["used_mb"]/s["memory"]["total_mb"],lambda:self.ram_detail(),PALETTE[3]),
        }
        self.graphs=[graphs[key] for key in load_order()]
        for graph in self.graphs:self.make_draggable(graph)
        self.reflow(2); outer.append(self.grid)
        label=Gtk.Label(label=t("gpu_activity"),xalign=0); label.add_css_class("section"); outer.append(label)
        self.processes=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5); outer.append(self.processes)
        event_title=Gtk.Label(label=t("recent_events"),xalign=0); event_title.add_css_class("section"); outer.append(event_title)
        self.event_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4); outer.append(self.event_box)
        self.event_title=event_title; self.set_option_visibility()
        scroll=Gtk.ScrolledWindow(); scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC); scroll.set_child(outer)
        shell=Gtk.Overlay(); shell.set_child(scroll)
        self.resize_grip=ResizeGrip(); self.resize_grip.set_halign(Gtk.Align.END); self.resize_grip.set_valign(Gtk.Align.END)
        shell.add_overlay(self.resize_grip); self.set_child(shell)
        if self.history:
            for snapshot in self.history:
                self.compass.update(snapshot)
                for graph in self.graphs:graph.push(snapshot)
            self.refresh_events()
            self.refresh_live_labels()
    def change_language(self,dropdown,_spec):
        selected="ko" if dropdown.get_selected()==0 else "en"
        if selected==get_language():return
        set_language(selected); write_settings({"language":selected}); self.build()
    def toggle_maximize(self):
        if self.is_maximized():self.unmaximize()
        else:self.maximize()
    def set_option(self,key,value):
        self.options[key]=value; write_settings({"view_options":self.options})
        self.compass.show_pressure=self.options["pressure"]; self.compass.show_states=self.options["state_history"]; self.compass.queue_draw(); self.set_option_visibility()
    def set_option_visibility(self):
        if hasattr(self,"event_box"):
            self.event_box.set_visible(self.options["events"]); self.event_title.set_visible(self.options["events"])
    def toggle_recording(self):
        if self.recording:
            self.recording.close(); self.recording=None; self.recording_writer=None; self.record_button.set_label(t("record")); self.record_button.remove_css_class("recording"); self.record_button.set_tooltip_text(t("recording_path",path=self.recording_path)); return
        folder=Path.home()/"Documents"/"Fluxglass recordings"; folder.mkdir(parents=True,exist_ok=True)
        self.recording_path=folder/f"fluxglass-{int(__import__('time').time())}.csv"; self.recording=self.recording_path.open("w",newline="")
        fields=("timestamp","cpu_pct","gpu_pct","ram_pct","vram_pct","cpu_temp_c","gpu_temp_c","gpu_power_w","cpu_psi","memory_psi","io_psi")
        self.recording_writer=csv.DictWriter(self.recording,fieldnames=fields); self.recording_writer.writeheader(); self.record_button.set_label(t("stop_recording")); self.record_button.add_css_class("recording")
    def record_snapshot(self,snapshot):
        if not self.recording_writer:return
        m=resource_metrics(snapshot); gpu=snapshot.get("gpu") or {}; cpu=snapshot.get("cpu") or {}
        self.recording_writer.writerow({"timestamp":snapshot["t"],"cpu_pct":m["cpu"],"gpu_pct":m["gpu"],"ram_pct":m["ram"],"vram_pct":m["vram"],"cpu_temp_c":cpu.get("temperature_c"),"gpu_temp_c":gpu.get("temperature_c"),"gpu_power_w":gpu.get("power_w"),"cpu_psi":m["cpu_pressure"],"memory_psi":m["memory_pressure"],"io_psi":m["io_pressure"]}); self.recording.flush()
    def refresh_events(self):
        while child:=self.event_box.get_first_child():self.event_box.remove(child)
        for stamp,key,values in list(self.events)[-5:]:
            if key=="event_state":values={"old":state_text(values["old"]),"new":state_text(values["new"])}
            row=Gtk.Label(label=f"{stamp}   {t(key,**values)}",xalign=0); row.add_css_class("muted"); self.event_box.append(row)
    def make_draggable(self,graph):
        source=Gtk.DragSource(actions=Gdk.DragAction.MOVE)
        source.connect("prepare",lambda _source,_x,_y,g=graph:Gdk.ContentProvider.new_for_value(g.graph_id))
        graph.add_controller(source)
        target=Gtk.DropTarget.new(str,Gdk.DragAction.MOVE)
        target.connect("drop",lambda _target,value,_x,_y,g=graph:self.drop_graph(value,g))
        graph.add_controller(target)
    def drop_graph(self,source_id,target):
        source=next((g for g in self.graphs if g.graph_id==source_id),None)
        if not source or source is target:return False
        self.graphs.remove(source); self.graphs.insert(self.graphs.index(target),source)
        save_order([g.graph_id for g in self.graphs]); self.reflow(self.columns,force=True); return True
    def move_graph(self,graph,delta):
        old=self.graphs.index(graph); new=max(0,min(len(self.graphs)-1,old+delta))
        if old==new:return False
        self.graphs.pop(old); self.graphs.insert(new,graph); save_order([g.graph_id for g in self.graphs])
        self.reflow(self.columns,force=True); graph.grab_focus(); return True
    def set_history_cursor(self,index):
        if index==self.history_cursor:return
        self.history_cursor=index
        for graph in self.graphs:graph.queue_draw()
    def toggle_focus_graph(self,graph):
        self.focused_graph=None if graph is None or graph is self.focused_graph else graph
        for item in self.graphs:item.set_content_height(390 if item is self.focused_graph else 156)
        self.reflow(self.columns,force=True)
        if self.focused_graph:self.focused_graph.grab_focus()
        return True
    def layout_tick(self,*_):
        width=self.get_width(); columns=columns_for_width(width)
        self.reflow(columns); return True
    def reflow(self,columns,force=False):
        if columns==self.columns and not force:return
        self.columns=columns
        for graph in self.graphs:
            if graph.get_parent() is self.grid:self.grid.remove(graph)
        visible=[self.focused_graph] if self.focused_graph else self.graphs
        for i,graph in enumerate(visible):self.grid.attach(graph,i%columns,i//columns,columns if self.focused_graph else 1,1)
    def gpu_detail(self):
        g=(self.snapshot or {}).get("gpu") or {}; util=g.get("util_pct") or 0; temp=g.get("temperature_c"); margin=g.get("thermal_margin_c")
        return f"{util:.0f}%" + (t("temperature",value=temp) if temp is not None else "") + (t("headroom",value=margin) if margin is not None else "")
    def vram_detail(self):
        g=(self.snapshot or {}).get("gpu") or {}; return f"{human_mb(g.get('used_mb',0))} / {human_mb(g.get('total_mb',0))}"
    def cpu_detail(self):
        c=(self.snapshot or {"cpu":{}})["cpu"]; limit=c.get("temperature_limit_c"); headroom=(limit-c["temperature_c"]) if limit and c.get("temperature_c") is not None else None
        return t("active_cores",pct=c.get("pct",0),active=c.get("active",0),online=c.get("online",0))+(t("temperature",value=c["temperature_c"]) if c.get("temperature_c") is not None else "")+(t("headroom",value=headroom) if headroom is not None else "")
    def ram_detail(self):
        m=(self.snapshot or {"memory":{}})["memory"]; return f"{human_mb(m.get('used_mb',0))} / {human_mb(m.get('total_mb',0))}"
    def tick(self):
        previous=self.snapshot
        try: self.snapshot=self.sampler.sample()
        except (OSError,ValueError): return True
        raw_events=detect_events(previous,self.snapshot); new_events=[event for event in raw_events if event[0]!="event_state"]
        state=resource_metrics(self.snapshot)["state"]
        self.event_state,self.pending_event_state,self.pending_event_count,state_event=advance_state_event(state,self.event_state,self.pending_event_state,self.pending_event_count)
        if state_event:new_events.append(state_event)
        for key,values in new_events:self.events.append((__import__('time').strftime("%H:%M:%S"),key,values))
        if new_events:self.refresh_events()
        self.record_snapshot(self.snapshot)
        self.history.append(self.snapshot)
        self.compass.update(self.snapshot)
        for g in self.graphs:g.push(self.snapshot)
        self.refresh_live_labels()
        return True
    def refresh_live_labels(self):
        if not self.snapshot:return
        gpu=self.snapshot.get("gpu") or {}; power=gpu.get("power_w"); power_text=t("gpu_power",watts=power) if power is not None else ""
        self.subtitle.set_text(t("host_status",host=os.uname().nodename.upper(),power=power_text,cores=self.snapshot["cpu"]["online"]))
        while child:=self.processes.get_first_child(): self.processes.remove(child)
        procs=sorted(gpu.get("processes",[]),key=lambda p:(p.get("vram_mb") or 0,p.get("sm_pct") or 0),reverse=True)[:6]
        for i,p in enumerate(procs):
            row=Gtk.Box(spacing=8); dot=Gtk.Label(label="●"); dot.add_css_class(f"process-{i%5}")
            name=Gtk.Label(label=t("process_row",name=p["name"],pid=p["pid"]),xalign=0); name.set_hexpand(True)
            stat=Gtk.Label(label=t("process_stats",memory=human_mb(p.get("vram_mb") or 0),sm=p.get("sm_pct") or 0),xalign=1); stat.add_css_class("muted")
            row.append(dot); row.append(name); row.append(stat); self.processes.append(row)
        if not procs:self.processes.append(Gtk.Label(label=t("no_gpu_process"),xalign=0))

class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.unattachedgray.Fluxglass", flags=Gio.ApplicationFlags.NON_UNIQUE)
    def do_startup(self):
        Gtk.Application.do_startup(self)
        css=Gtk.CssProvider(); css.load_from_data(b"""
        window { background: #11131a; color: #eaf0fa; font-family: "Pretendard Variable", "Noto Sans KR", "Noto Sans CJK KR", sans-serif; }
        .brand { font-family: "Bebas Neue", "Pretendard Variable", sans-serif; font-size: 24px; font-weight: 400; letter-spacing: 3px; } .subtitle,.muted { color: #8790a1; font-size: 11px; }
        .section { color:#a9b2c1; font-weight:700; letter-spacing:2px; margin-top:6px; }
        .process-0{color:#50dbb8;} .process-1{color:#73adff;} .process-2{color:#c782ff;} .process-3{color:#ff9b5c;} .process-4{color:#fa618c;}
        button { background:#202530; color:#eaf0fa; border-radius:9px; padding:8px 13px; transition:120ms ease; }
        button:hover { background:#2a3140; } button:active { background:#343d4f; }
        button:focus-visible { outline:2px solid #50dbb8; outline-offset:2px; }
        button.recording { background:#8f2948; color:#fff; }
        popover > contents, popover contents { background:#171b24; color:#eaf0fa; border:1px solid #343b4a; border-radius:12px; box-shadow:0 12px 32px rgba(4,6,10,.45); }
        dropdown, dropdown button { background:#202530; color:#eaf0fa; }
        """); Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    def do_activate(self):
        if not self.get_active_window(): ResourceWindow(self).present()

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--desktop",action="store_true",help=argparse.SUPPRESS)
    parser.parse_args(); return App().run(None)
