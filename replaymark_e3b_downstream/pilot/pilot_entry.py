"""Compatibility entrypoint for the exploratory pilot.

Run 34001601197 exposed a pure implementation error before any downstream
measurement was produced: Paho 2.1.0 passes a ReasonCode object to VERSION2
callbacks, and pilot.py attempted int(reason_code).  This wrapper changes only
that connection-success check.  The preregistered queue limits, workload,
endpoints, and analysis rules are untouched.
"""

import pilot


def _reason_value(reason_code):
    return getattr(reason_code, "value", reason_code)


def _harness_on_connect(self, client, userdata, flags, reason_code, properties):
    if _reason_value(reason_code) != 0:
        raise RuntimeError(f"runner connect reason={reason_code}")
    self.connected.set()


def _collector_on_connect(self, client, userdata, flags, reason_code, properties):
    if _reason_value(reason_code) != 0:
        return
    if self.phase == "drain":
        self.session_present_on_drain = bool(getattr(flags, "session_present", False))
    self.connected.set()
    if self.phase == "prime":
        client.subscribe(f"replaymark/{self.run_id}/#", qos=1)


pilot.Harness._on_connect = _harness_on_connect
pilot.OfflineCollector._on_connect = _collector_on_connect

if __name__ == "__main__":
    pilot.main()
