"""Real system monitoring: CPU, RAM, disk, network, processes."""
from __future__ import annotations


class Telemetry:
    def __init__(self):
        self.psutil = None
        try:
            import psutil
            self.psutil = psutil
        except Exception:
            pass

    def snapshot(self):
        if not self.psutil:
            return {"err": "psutil not installed"}
        ps = self.psutil
        try:
            return {
                "cpu_percent": ps.cpu_percent(interval=0.1),
                "cpu_count": ps.cpu_count(),
                "ram_used_gb": round(ps.virtual_memory().used / 1024**3, 2),
                "ram_total_gb": round(ps.virtual_memory().total / 1024**3, 2),
                "ram_percent": ps.virtual_memory().percent,
                "disk_used_gb": round(ps.disk_usage("C:\\").used / 1024**3, 2),
                "disk_total_gb": round(ps.disk_usage("C:\\").total / 1024**3, 2),
                "disk_percent": ps.disk_usage("C:\\").percent,
                "net_sent_mb": round(ps.net_io_counters().bytes_sent / 1024**2, 1),
                "net_recv_mb": round(ps.net_io_counters().bytes_recv / 1024**2, 1),
                "boot_time": ps.boot_time(),
                "process_count": len(ps.pids()),
            }
        except Exception as e:
            return {"err": str(e)}

    def top_processes(self, n=10, sort_by="memory"):
        if not self.psutil:
            return []
        ps = self.psutil
        procs = []
        for p in ps.process_iter(["pid", "name", "memory_info", "cpu_percent"]):
            try:
                procs.append({
                    "pid": p.info["pid"],
                    "name": p.info["name"],
                    "mem_mb": round(p.info["memory_info"].rss / 1024**2, 1) if p.info["memory_info"] else 0,
                    "cpu": p.info["cpu_percent"] or 0,
                })
            except Exception:
                continue
        key = "mem_mb" if sort_by == "memory" else "cpu"
        procs.sort(key=lambda x: x[key], reverse=True)
        return procs[:n]

    def battery(self):
        if not self.psutil: return None
        try:
            b = self.psutil.sensors_battery()
            if b:
                return {"percent": b.percent, "plugged": b.power_plugged,
                        "secsleft": b.secsleft if b.secsleft != self.psutil.POWER_TIME_UNKNOWN else None}
        except Exception:
            pass
        return None

    def network_connections(self, n=10):
        if not self.psutil: return []
        try:
            out = []
            for c in self.psutil.net_connections(kind="inet")[:n]:
                out.append({
                    "fd": c.fd, "status": c.status,
                    "local": f"{c.laddr.ip}:{c.laddr.port}" if c.laddr else "",
                    "remote": f"{c.raddr.ip}:{c.raddr.port}" if c.raddr else "",
                    "pid": c.pid,
                })
            return out
        except Exception:
            return []
