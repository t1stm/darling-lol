#!/usr/bin/env python3
"""Lifecycle supervisor for Riot Client and League of Legends.

Enforces clean shutdown rules:
1. When RiotClientUx closes, if neither LeagueClient nor LeagueofLegends is running,
   terminate RiotClientServices and perform clean Darling shutdown.
2. If LeagueClient or LeagueofLegends is active or in transition (e.g. client closed during game),
   preserve the Darling runtime and match, only terminating RiotClientUx. Once League terminates,
   perform clean shutdown.
"""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

PREFIX = Path(os.environ.get("DPREFIX", str(Path.home() / ".darling")))
GUEST_HOME = os.environ.get("RIOT_GUEST_HOME", str(PREFIX / "Users" / os.environ.get("USER", "fgeroldi")))

def get_darling_pids():
    riot_services = []
    riot_ux = []
    league_client = []
    league_game = []
    helpers = []
    uid = os.getuid()

    riot_app = str(PREFIX / "Applications" / "Riot Client.app")
    league_app = str(PREFIX / "Applications" / "League of Legends.app")

    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
            pid = int(entry.name)
            if pid == os.getpid():
                continue
            cmdline = (entry / "cmdline").read_bytes()
            if not cmdline:
                continue

            if b"RiotClientServices" in cmdline:
                riot_services.append(pid)
            elif b"RiotClientUx" in cmdline:
                if b"Helper" in cmdline or b"CrashHandler" in cmdline:
                    helpers.append(pid)
                else:
                    riot_ux.append(pid)
            elif b"LeagueClient" in cmdline or b"LeagueClientUx" in cmdline:
                if b"Helper" in cmdline or b"CrashHandler" in cmdline:
                    helpers.append(pid)
                else:
                    league_client.append(pid)
            elif b"LeagueofLegends" in cmdline or b"League of Legends" in cmdline:
                if b"CrashHandler" in cmdline:
                    helpers.append(pid)
                else:
                    league_game.append(pid)
            else:
                try:
                    maps = (entry / "maps").read_text()
                    if league_app in maps or "LeagueofLegends" in maps or "League of Legends" in maps:
                        league_game.append(pid)
                    elif "LeagueClient" in maps:
                        league_client.append(pid)
                    elif "RiotClientUx" in maps:
                        riot_ux.append(pid)
                    elif "RiotClientServices" in maps or riot_app in maps:
                        riot_services.append(pid)
                except OSError:
                    pass
        except (OSError, ValueError):
            continue

    return {
        "riot_services": riot_services,
        "riot_ux": riot_ux,
        "league_client": league_client,
        "league_game": league_game,
        "helpers": helpers,
    }

def set_process_tree_priority(pids_list, nice_value=15, sched_batch=True):
    for pid in pids_list:
        try:
            task_dir = Path(f"/proc/{pid}/task")
            if task_dir.is_dir():
                for tid_entry in task_dir.iterdir():
                    if tid_entry.name.isdigit():
                        tid = int(tid_entry.name)
                        try:
                            os.setpriority(os.PRIO_PROCESS, tid, nice_value)
                            if sched_batch:
                                os.sched_setscheduler(tid, os.SCHED_BATCH, os.sched_param(0))
                            else:
                                os.sched_setscheduler(tid, os.SCHED_OTHER, os.sched_param(0))
                        except OSError:
                            pass
            else:
                try:
                    os.setpriority(os.PRIO_PROCESS, pid, nice_value)
                except OSError:
                    pass
        except OSError:
            pass

def perform_clean_shutdown(child_proc=None):
    print("[lifecycle] Performing clean shutdown of Riot Client services and Darling runtime...", flush=True)

    pids = get_darling_pids()
    for pid in pids.get("helpers", []):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    for pid in pids["riot_services"]:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    if child_proc and child_proc.poll() is None:
        try:
            child_proc.terminate()
            child_proc.wait(timeout=3.0)
        except Exception:
            try:
                child_proc.kill()
            except Exception:
                pass

    stop_script = Path(__file__).resolve().parent / "stop-darling-runtime.py"
    if stop_script.exists():
        try:
            subprocess.run([sys.executable, str(stop_script), "--shutdown-only"], timeout=30)
        except Exception as e:
            print(f"[lifecycle] stop-darling-runtime failed: {e}", flush=True)
            subprocess.run(["darling", "shutdown"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.run(["darling", "shutdown"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    print("[lifecycle] Clean shutdown finished.", flush=True)

def main():
    if len(sys.argv) < 2:
        print("Usage: riot-lifecycle-supervisor.py <command> [args...]", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1:]
    child_proc = subprocess.Popen(cmd)

    def sig_handler(signum, frame):
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        pids = get_darling_pids()
        if pids["league_client"] or pids["league_game"]:
            print("[lifecycle] League match or client is currently active. Ignoring signal to preserve gameplay.", flush=True)
            signal.signal(signal.SIGINT, sig_handler)
            signal.signal(signal.SIGTERM, sig_handler)
            return
        perform_clean_shutdown(child_proc)
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    startup_deadline = time.monotonic() + 45.0
    riot_ux_ever_seen = False
    riot_transition_deadline = 0.0
    league_ever_seen = False
    league_transition_deadline = 0.0
    was_game_alive = False

    while True:
        time.sleep(1.0)
        pids = get_darling_pids()

        services_alive = len(pids["riot_services"]) > 0 or (child_proc.poll() is None)
        riot_ux_alive = len(pids["riot_ux"]) > 0
        league_client_alive = len(pids["league_client"]) > 0
        league_game_alive = len(pids["league_game"]) > 0

        if riot_ux_alive:
            riot_ux_ever_seen = True
            riot_transition_deadline = 0.0

        if league_client_alive or league_game_alive:
            league_ever_seen = True
            league_transition_deadline = 0.0
        elif league_ever_seen and league_transition_deadline == 0.0:
            league_transition_deadline = time.monotonic() + 35.0

        # Protect transition when RiotClientUx closes to launch LeagueClient
        if riot_ux_ever_seen and not riot_ux_alive and not league_ever_seen:
            if riot_transition_deadline == 0.0:
                riot_transition_deadline = time.monotonic() + 45.0

        in_riot_transition = (riot_transition_deadline > 0.0 and time.monotonic() < riot_transition_deadline)
        in_league_transition = (league_transition_deadline > 0.0 and time.monotonic() < league_transition_deadline)
        in_transition = in_riot_transition or in_league_transition

        # Priority management: throttle background CEF processes when 3D match is active
        if league_game_alive:
            if not was_game_alive:
                print("[lifecycle] League 3D match active: throttling background CEF and launcher processes.", flush=True)
                was_game_alive = True
            bg_pids = pids["riot_services"] + pids["riot_ux"] + pids["league_client"] + pids["helpers"]
            set_process_tree_priority(bg_pids, nice_value=15, sched_batch=True)
            set_process_tree_priority(pids["league_game"], nice_value=0, sched_batch=False)
        elif was_game_alive:
            print("[lifecycle] League 3D match finished: restoring launcher process priorities.", flush=True)
            bg_pids = pids["riot_services"] + pids["riot_ux"] + pids["league_client"] + pids["helpers"]
            set_process_tree_priority(bg_pids, nice_value=0, sched_batch=False)
            was_game_alive = False

        # RULE 2: Protect League match and client re-opening
        if league_client_alive or league_game_alive or in_transition:
            continue

        # RULE 1: If user closed all client and game windows (and not in transition):
        all_clients_closed = (riot_ux_ever_seen or league_ever_seen) and not riot_ux_alive and not league_client_alive and not league_game_alive
        if all_clients_closed:
            print("[lifecycle] All client and match windows closed. Initiating clean shutdown.", flush=True)
            perform_clean_shutdown(child_proc)
            break

        if not services_alive and (time.monotonic() > startup_deadline or riot_ux_ever_seen):
            print("[lifecycle] Launcher services exited. Initiating clean shutdown.", flush=True)
            perform_clean_shutdown(child_proc)
            break

    sys.exit(0)

if __name__ == "__main__":
    main()
