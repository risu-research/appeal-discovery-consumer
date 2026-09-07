from __future__ import annotations
import argparse, json, math, os, socket, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from importlib.metadata import version
from pathlib import Path
import paho.mqtt.client as mqtt

SCHEMA='replaymark.s2p4-self-echo-round.v1'
SCHEDULE=((16,8,4),(8,4,16),(4,16,8))
TASKS=192; WAVE_PERIOD_MS=300.0; TASK_TIMEOUT_MS=1000; QUIESCENCE_SECONDS=0.5

def percentile(xs,q):
    ys=sorted(xs)
    if not ys:return None
    pos=(len(ys)-1)*q/100.0; lo=math.floor(pos); hi=math.ceil(pos)
    return ys[lo] if lo==hi else ys[lo]*(hi-pos)+ys[hi]*(pos-lo)

def read_tcp_delayed_acks():
    try:
        lines=Path('/proc/net/netstat').read_text().splitlines()
        for i in range(0,len(lines)-1,2):
            if lines[i].startswith('TcpExt:') and lines[i+1].startswith('TcpExt:'):
                names=lines[i].split()[1:]; vals=lines[i+1].split()[1:]
                d=dict(zip(names,vals))
                if 'DelayedACKs' in d:return int(d['DelayedACKs'])
                if 'TcpExtDelayedACKs' in d:return int(d['TcpExtDelayedACKs'])
    except Exception:
        pass
    return None

class EchoHarness:
    def __init__(self,broker,port):
        self.cv=threading.Condition(); self.echo={}; self.version=None; self.connected=False
        self.client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=f'p4-{uuid.uuid4().hex[:10]}')
        self.client.on_connect=self._connect; self.client.on_message=self._message
        self.client.connect(broker,port,keepalive=30); self.client.loop_start()
        end=time.monotonic()+10
        with self.cv:
            while not self.connected:
                rem=end-time.monotonic()
                if rem<=0:raise TimeoutError('connect')
                self.cv.wait(rem)
            while self.version is None:
                rem=end-time.monotonic()
                if rem<=0:raise TimeoutError('broker version')
                self.cv.wait(rem)
    def _connect(self,c,u,f,r,p):
        c.subscribe('replaymark/p4/#',qos=1); c.subscribe('$SYS/broker/version',qos=0)
        with self.cv:self.connected=True; self.cv.notify_all()
    def _message(self,c,u,msg):
        now=time.monotonic_ns()
        if msg.topic=='$SYS/broker/version':
            with self.cv:self.version=msg.payload.decode(errors='replace'); self.cv.notify_all(); return
        if not msg.topic.startswith('replaymark/p4/'):return
        try: body=json.loads(msg.payload.decode())
        except Exception:return
        token=str(body.get('token'))
        with self.cv:
            self.echo.setdefault(token,now); self.cv.notify_all()
    def wait_echo(self,token,deadline_ns):
        with self.cv:
            while token not in self.echo:
                rem=deadline_ns-time.monotonic_ns()
                if rem<=0:return None
                self.cv.wait(rem/1e9)
            return self.echo[token]
    def tcp_nodelay(self):
        s=self.client.socket()
        return None if s is None else int(s.getsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY))
    def close(self):self.client.disconnect(); self.client.loop_stop()

def sleep_until(ns):
    while True:
        rem=ns-time.monotonic_ns()
        if rem<=0:return
        time.sleep(rem/1e9)

def run_task(h,*,round_index,position,wave_size,task_id,prefix,offer_ns):
    sleep_until(offer_ns); start=time.monotonic_ns(); call=time.monotonic_ns()
    token=f'{prefix}-{task_id}-{uuid.uuid4().hex[:8]}'
    topic=f'replaymark/p4/{prefix}/{task_id}/echo'
    payload=json.dumps({'token':token,'task_id':task_id,'on':True},sort_keys=True,separators=(',',':'))
    info=h.client.publish(topic,payload,qos=1,retain=False,properties=None)
    info.wait_for_publish(timeout=5); puback=time.monotonic_ns()
    echo=h.wait_echo(token,start+int(TASK_TIMEOUT_MS*1e6))
    def ms(x):return None if x is None else x/1e6
    return {
      'round_index':round_index,'position':position,'wave_size':wave_size,'task_id':task_id,'topic':topic,'token':token,
      'offer_mono_ns':offer_ns,'task_start_mono_ns':start,'publish_call_mono_ns':call,'puback_mono_ns':puback,'echo_recv_mono_ns':echo,
      'completed':echo is not None,'offer_to_task_start_ms':ms(start-offer_ns),'publish_call_overhead_ms':ms(call-start),
      'puback_latency_ms':ms(puback-call),'self_echo_receive_latency_ms':None if echo is None else ms(echo-start),
      'self_echo_after_publish_ms':None if echo is None else ms(echo-call),
    }

def run_cell(h,round_index,position,wave_size):
    prefix=f's2p4-r{round_index}-p{position}-w{wave_size}-{uuid.uuid4().hex[:10]}'
    before=read_tcp_delayed_acks(); base=time.monotonic_ns()+100_000_000; rows=[]
    with ThreadPoolExecutor(max_workers=TASKS) as pool:
        futs=[pool.submit(run_task,h,round_index=round_index,position=position,wave_size=wave_size,task_id=i,prefix=prefix,offer_ns=base+(i//wave_size)*int(WAVE_PERIOD_MS*1e6)) for i in range(TASKS)]
        for f in as_completed(futs): rows.append(f.result())
    rows.sort(key=lambda r:r['task_id']); after=read_tcp_delayed_acks()
    vals=[r['self_echo_receive_latency_ms'] for r in rows if r['self_echo_receive_latency_ms'] is not None]
    acks=[r['puback_latency_ms'] for r in rows]
    return {'round_index':round_index,'position':position,'wave_size':wave_size,'prefix':prefix,'tcp_delayed_acks_before':before,'tcp_delayed_acks_after':after,
            'tcp_delayed_acks_delta':None if before is None or after is None else after-before,'rows':rows,
            'preview':{'rows':len(rows),'complete':len(vals),'echo_p50_ms':percentile(vals,50),'echo_p95_ms':percentile(vals,95),'echo_p99_ms':percentile(vals,99),'puback_p95_ms':percentile(acks,95),'puback_p99_ms':percentile(acks,99)}}

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('--broker',default='mosquitto'); ap.add_argument('--port',type=int,default=1883); ap.add_argument('--round-index',type=int,required=True); ap.add_argument('--out',required=True); args=ap.parse_args()
 ri=args.round_index
 if ri not in range(3):raise SystemExit('round index')
 h=EchoHarness(args.broker,args.port)
 try:
   cells=[]; nodelay=h.tcp_nodelay(); broker=h.version
   for pos,w in enumerate(SCHEDULE[ri]):
      cells.append(run_cell(h,ri,pos,w))
      if pos<2: time.sleep(QUIESCENCE_SECONDS)
 finally:h.close()
 report={'schema':SCHEMA,'round_index':ri,'frozen_order':list(SCHEDULE[ri]),'source_only':True,'shifted_target_executed':False,'act2_candidate_constructed':False,'device_service_started':False,
         'broker':broker,'paho_version':version('paho-mqtt'),'tcp_nodelay_value':nodelay,'qos':1,'retain':False,'properties':None,'cells':cells}
 Path(args.out).write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'round':ri,'broker':broker,'paho':report['paho_version'],'nodelay':nodelay,'cells':[c['preview'] for c in cells]},indent=2))
if __name__=='__main__':main()
