from __future__ import annotations
import json, os, threading, time
from collections import defaultdict
import paho.mqtt.client as mqtt
BROKER=os.getenv('BROKER_HOST','mosquitto'); PORT=int(os.getenv('BROKER_PORT','1883'))
states=defaultdict(bool); state_delay_ms=0; lock=threading.Lock(); client=None

def pub_state(device,cause):
    with lock: value=states[device]
    client.publish(f'agentmark/{device}/state',json.dumps({'device':device,'on':value,'cause':cause,'ts_mono_ns':time.monotonic_ns()},sort_keys=True),qos=1)
def schedule(device,cause,delay):
    if delay<=0: pub_state(device,cause)
    else:
        t=threading.Timer(delay/1000,pub_state,args=(device,cause)); t.daemon=True; t.start()
def on_connect(c,u,f,r,p):
    c.subscribe('agentmark/+/command',qos=1); c.subscribe('agentmark/+/query',qos=1); c.subscribe('agentmark/control',qos=1)
def on_message(c,u,msg):
    global state_delay_ms
    text=msg.payload.decode('utf-8',errors='replace')
    if msg.topic=='agentmark/control':
        body=json.loads(text)
        with lock: state_delay_ms=int(body.get('state_delay_ms',0))
        c.publish('agentmark/control/ack',json.dumps({'nonce':body.get('nonce'),'state_delay_ms':state_delay_ms},sort_keys=True),qos=1); return
    parts=msg.topic.split('/')
    if len(parts)!=3:return
    _,device,kind=parts
    if kind=='command':
        body=json.loads(text)
        with lock: states[device]=bool(body.get('on',True)); delay=state_delay_ms
        schedule(device,'command',delay)
    elif kind=='query': pub_state(device,'query')
def main():
    global client
    client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='agentmark-device-farm'); client.on_connect=on_connect; client.on_message=on_message; client.connect(BROKER,PORT,keepalive=30); client.loop_forever()
if __name__=='__main__':main()
