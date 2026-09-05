from __future__ import annotations
import json, math, threading, time, uuid
import paho.mqtt.client as mqtt

def percentile(xs,q):
    if not xs:return None
    ys=sorted(xs);pos=(len(ys)-1)*q/100;lo=math.floor(pos);hi=math.ceil(pos)
    return ys[lo] if lo==hi else ys[lo]*(hi-pos)+ys[hi]*(pos-lo)

class Harness:
    WANTED_SYS=(
      '$SYS/broker/messages/received','$SYS/broker/messages/sent',
      '$SYS/broker/publish/messages/received','$SYS/broker/publish/messages/sent',
      '$SYS/broker/publish/bytes/received','$SYS/broker/publish/bytes/sent',
      '$SYS/broker/bytes/received','$SYS/broker/bytes/sent')
    def __init__(self,broker,port):
        self.cv=threading.Condition();self.state_events={};self.control_acks={};self.sys_values={}
        self.client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=f'agentmark-{uuid.uuid4().hex[:8]}')
        self.client.on_connect=self._on_connect;self.client.on_message=self._on_message
        self.client.connect(broker,port,keepalive=30);self.client.loop_start();d=time.monotonic()+10
        while not self.client.is_connected():
            if time.monotonic()>d:raise TimeoutError('runner connect')
            time.sleep(.01)
    def close(self):self.client.disconnect();self.client.loop_stop()
    def _on_connect(self,c,u,f,r,p):
        c.subscribe('agentmark/+/state',qos=1);c.subscribe('agentmark/control/ack',qos=1);c.subscribe('$SYS/broker/#',qos=0)
    def _on_message(self,c,u,msg):
        now=time.monotonic_ns()
        if msg.topic.startswith('$SYS/'):
            with self.cv:self.sys_values[msg.topic]=(msg.payload.decode(errors='replace'),now);self.cv.notify_all()
            return
        body=json.loads(msg.payload.decode())
        with self.cv:
            if msg.topic=='agentmark/control/ack':self.control_acks[str(body.get('nonce'))]=body
            else:self.state_events.setdefault(str(body['device']),[]).append({**body,'recv_mono_ns':now})
            self.cv.notify_all()
    def broker_version(self,timeout_s=3):
        d=time.monotonic()+timeout_s
        with self.cv:
            while '$SYS/broker/version' not in self.sys_values:
                r=d-time.monotonic()
                if r<=0:return None
                self.cv.wait(r)
            return self.sys_values['$SYS/broker/version'][0]
    def set_state_delay(self,delay_ms):
        nonce=uuid.uuid4().hex;d=time.monotonic()+5
        while True:
            i=self.client.publish('agentmark/control',json.dumps({'nonce':nonce,'state_delay_ms':int(delay_ms)},sort_keys=True),qos=1);i.wait_for_publish(timeout=2)
            with self.cv:
                if nonce in self.control_acks:return
                r=d-time.monotonic()
                if r<=0:raise TimeoutError('control ack')
                self.cv.wait(min(.25,r))
    def wait_state_on_until(self,device,deadline_ns,*,after_ns):
        with self.cv:
            while True:
                for e in self.state_events.get(device,[]):
                    if after_ns<=e['recv_mono_ns']<=deadline_ns and bool(e.get('on')):return e
                r=deadline_ns-time.monotonic_ns()
                if r<=0:return None
                self.cv.wait(r/1e9)
    def wait_all_sys_after(self,after_ns,timeout_s=3.5):
        d=time.monotonic()+timeout_s
        with self.cv:
            while True:
                if all(k in self.sys_values and self.sys_values[k][1]>after_ns for k in self.WANTED_SYS):return
                r=d-time.monotonic()
                if r<=0:
                    stale=[k for k in self.WANTED_SYS if k not in self.sys_values or self.sys_values[k][1]<=after_ns]
                    raise TimeoutError(f'$SYS all-counter barrier stale={stale}')
                self.cv.wait(r)
    def fresh_sys_snapshot(self):
        stamp=time.monotonic_ns();self.wait_all_sys_after(stamp);return self.sys_counter_snapshot()
    def sys_counter_snapshot(self):
        out={}
        with self.cv:
            for k in self.WANTED_SYS:
                raw=self.sys_values[k][0]
                try:out[k]=int(raw)
                except ValueError:
                    try:out[k]=float(raw)
                    except ValueError:out[k]=raw
        return out

def _sys_delta(before,after):
    return {k:float(after[k]-before[k]) for k in set(before)&set(after) if isinstance(before[k],(int,float)) and isinstance(after[k],(int,float))}
