"""Small dependency-free message catalog; Korean is the product default."""
LANGUAGES=("ko","en")
_language="ko"

EN={
"brand":"FLUXGLASS","compass":"RESOURCE COMPASS","cpu":"CPU","gpu":"GPU","ram":"RAM","vram":"VRAM",
"sensors_warming":"SENSORS WARMING UP","korean":"한국어","english":"English",
"idle":"IDLE","cpu_led":"CPU-LED","gpu_led":"GPU-LED","balanced":"BALANCED","contention":"CONTENTION","memory_pressure":"MEMORY PRESSURE","vram_pressure":"VRAM PRESSURE","warming":"WARMING UP",
"state_history":"STATE HISTORY","graph_footer":"3 MINUTES  •  LIVE 1s  •  CLICK TO FOCUS","graph_footer_focused":"3 MINUTES  •  LIVE 1s  •  ESC TO RESTORE","seconds_ago":"{value:.0f}%  {seconds}s ago","leading_process":"{base}  {process}",
"drag_reorder":"Drag to reorder. Ctrl+Arrow also moves this graph.","cpu_graph":"Processor","gpu_graph":"GPU compute","ram_graph":"Memory","vram_graph":"Video memory",
"active_cores":"{pct:.0f}% · {active}/{online} active","temperature":" · {value:.0f}°C","headroom":" · {value:.0f}° headroom",
"per_core":"PER-CORE ACTIVITY  •  BRIGHTER MEANS BUSIER","gpu_engines":"MEMORY ENGINE {memory:.0f}%   ENCODE {encode:.0f}%   DECODE {decode:.0f}%",
"record":"Record","stop_recording":"Stop recording","view":"View","pressure_halo":"Pressure halo","state_option":"State history","events_option":"Event memory","language":"Language","maximize":"Maximize","quit":"Quit",
"move_window":"Drag this header to move Fluxglass","resize":"Drag to resize","quit_tip":"Quit Fluxglass","gpu_activity":"GPU ACTIVITY","recent_events":"RECENT EVENTS","no_gpu_process":"No per-process GPU activity reported",
"host_status":"{host}  ·  {power}{cores} CORES ONLINE","gpu_power":"GPU {watts:.0f} W  ·  ","process_row":"{name}  ·  PID {pid}","process_stats":"{memory}   {sm:.0f}% SM",
"event_started":"Monitoring started","event_state":"State: {old} → {new}","event_gpu_available":"GPU sensor available","event_gpu_lost":"GPU sensor lost","event_throttle":"GPU clock constraint active",
"recording_path":"Recording saved to {path}","tooltip_metrics":"CPU {cpu:.0f}% | GPU {gpu:.0f}% | RAM {ram:.0f}% | VRAM {vram:.0f}% | pressure {pressure:.2f}%",
}
KO={
**EN,
"compass":"리소스 나침반","idle":"대기","cpu_led":"CPU 중심","gpu_led":"GPU 중심","balanced":"균형","contention":"자원 경합","memory_pressure":"메모리 압박","vram_pressure":"VRAM 압박","warming":"센서 준비 중",
"sensors_warming":"센서 준비 중","korean":"한국어","english":"English",
"state_history":"상태 기록","graph_footer":"3분  •  1초 실시간  •  클릭하여 확대","graph_footer_focused":"3분  •  1초 실시간  •  ESC로 돌아가기","seconds_ago":"{value:.0f}%  {seconds}초 전","leading_process":"{base}  {process}",
"drag_reorder":"끌어서 순서를 바꿉니다. Ctrl+방향키로도 이동할 수 있습니다.","cpu_graph":"프로세서","gpu_graph":"GPU 연산","ram_graph":"메모리","vram_graph":"비디오 메모리",
"active_cores":"{pct:.0f}% · {active}/{online}개 활성","temperature":" · {value:.0f}°C","headroom":" · {value:.0f}° 여유",
"per_core":"코어별 활동  •  밝을수록 사용량이 높음","gpu_engines":"메모리 엔진 {memory:.0f}%   인코딩 {encode:.0f}%   디코딩 {decode:.0f}%",
"record":"기록","stop_recording":"기록 중지","view":"보기","pressure_halo":"압력 후광","state_option":"상태 기록","events_option":"이벤트 기록","language":"언어","maximize":"최대화","quit":"종료",
"move_window":"이 머리글을 끌어 플럭스글라스를 이동합니다","resize":"끌어서 크기를 조절합니다","quit_tip":"플럭스글라스를 종료합니다","gpu_activity":"GPU 활동","recent_events":"최근 이벤트","no_gpu_process":"보고된 프로세스별 GPU 활동이 없습니다",
"host_status":"{host}  ·  {power}온라인 코어 {cores}개","gpu_power":"GPU {watts:.0f} W  ·  ","process_row":"{name}  ·  PID {pid}","process_stats":"{memory}   SM {sm:.0f}%",
"event_started":"모니터링 시작","event_state":"상태: {old} → {new}","event_gpu_available":"GPU 센서 연결됨","event_gpu_lost":"GPU 센서 연결 끊김","event_throttle":"GPU 클록 제한 활성","recording_path":"기록 저장 위치: {path}",
"tooltip_metrics":"CPU {cpu:.0f}% | GPU {gpu:.0f}% | RAM {ram:.0f}% | VRAM {vram:.0f}% | 압력 {pressure:.2f}%",
}
CATALOGS={"ko":KO,"en":EN}

def set_language(language):
    global _language
    _language=language if language in LANGUAGES else "ko"

def get_language():return _language
def t(key,**values):return CATALOGS[_language].get(key,EN.get(key,key)).format(**values)

def state_text(state):
    return t({"IDLE":"idle","CPU-LED":"cpu_led","GPU-LED":"gpu_led","BALANCED":"balanced","CONTENTION":"contention","MEMORY PRESSURE":"memory_pressure","VRAM PRESSURE":"vram_pressure","WARMING UP":"warming"}.get(state,state))
