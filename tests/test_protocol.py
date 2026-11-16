import keyboard_logic as kl


def status_report(mode, battery):
    report = [0x55, 0x10, 0x18, 0, 0, 0, 1] + [0] * 25
    report[24], report[25] = mode, battery
    return report


def test_parse_status_modes():
    assert kl.parse_status(status_report(2, 97)) == {"battery": 97, "mode": "2.4G receiver"}
    assert kl.parse_status(status_report(0, 50))["mode"] == "USB cable"
    assert kl.parse_status(status_report(1, 50))["mode"] == "USB cable"
    assert kl.parse_status(status_report(3, 50))["mode"] == "Bluetooth"
    assert kl.parse_status(status_report(9, 50))["mode"] == "Mode 9"


def test_parse_status_rejects_other_reports():
    assert kl.parse_status(status_report(2, 0)) is None          # asleep: no data
    assert kl.parse_status([0x55, 0x01, 0, 0, 0, 0, 1] + [0] * 25) is None
    assert kl.parse_status([0x55, 0x10, 0x18]) is None           # too short
    bad = status_report(2, 50)
    bad[0] = 0xAA
    assert kl.parse_status(bad) is None


def test_packet_layout():
    pkt = kl._packet(kl.STATUS_PACKET)
    assert len(pkt) == 33 and pkt[0] == 0 and pkt[1:4] == [0xAA, 0x10, 0x18] and pkt[7] == 1


def test_read_hid_status(receiver):
    assert kl.read_hid_status() == (True, {"battery": 80, "mode": "2.4G receiver"})
    assert all(t > 0 for t in receiver.read_timeouts)


def test_read_hid_status_asleep(receiver):
    receiver.awake = False
    assert kl.read_hid_status() == (True, None)


def test_read_hid_status_no_receiver(receiver):
    receiver.present = False
    assert kl.read_hid_status() == (False, None)


class _Result:
    def __init__(self, stdout):
        self.stdout = stdout


def test_bluetooth_battery_parses_powershell_output(monkeypatch):
    calls = []
    monkeypatch.setattr(kl.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or _Result("\r\n87\r\n"))
    assert kl.read_bluetooth_battery() == 87
    assert "'ALU104*'" in calls[0][-1]


def test_bluetooth_battery_nothing_connected(monkeypatch):
    monkeypatch.setattr(kl.subprocess, "run", lambda cmd, **kw: _Result(""))
    assert kl.read_bluetooth_battery() is None
