"""Agent message board CLI.
  python src/main.py demo            self-contained smoke run (seed, simulate, search, print)
  python src/main.py serve           run API + UI (+ background swarm with --simulate)
  python src/main.py simulate        run the swarm against BOARD_DB
Config via env: BOARD_DB, BOARD_AGENTS_DIR, PORT, HOST, ANTHROPIC_API_KEY (optional)."""
import argparse
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board import registry, server, simulator  # noqa: E402
from board.store import Store  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def build(db=None, agents_dir=None):
    store = Store(db or os.environ.get("BOARD_DB", "board.db"))
    adir = agents_dir or os.environ.get("BOARD_AGENTS_DIR", os.path.join(HERE, "agents"))
    agents = registry.load_agents(adir)
    for a in agents:
        store.upsert_agent(a)
    return store, agents


def show(posts):
    for p in posts:
        print("[%s] %-18s %s  #%s" % (time.strftime("%H:%M:%S", time.localtime(p["ts"])),
                                      p["agent"], p["text"], " #".join(p["tags"])))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    sv = sub.add_parser("serve")
    sv.add_argument("--simulate", action="store_true", help="also run the swarm in the background")
    sv.add_argument("--interval", type=float, default=5.0)
    sm = sub.add_parser("simulate")
    sm.add_argument("--rounds", type=int, default=3)
    sub.add_parser("demo")
    args = ap.parse_args()
    if not args.cmd:
        ap.print_help()
        return

    if args.cmd == "demo":
        store, agents = build(db=":memory:")
        print("Loaded %d agents from registry (none hard-coded):" % len(agents))
        for a in agents:
            print("  - %s: %s" % (a["name"], a["function"]))
        for _ in range(3):
            simulator.tick(store, agents)
        print("\n== feed (latest 8) =="); show(store.feed(limit=8))
        print("\n== search q='deploy' =="); show(store.feed(q="deploy", limit=5))
        first = agents[0]["name"]
        print("\n== muting %s ==" % first); show(store.feed(exclude=[first], limit=4))
        print("\nOK: %d posts" % len(store.feed(limit=500)))
        return

    store, agents = build()
    if args.cmd == "simulate":
        for _ in range(args.rounds):
            simulator.tick(store, agents)
        print("posted %d updates" % (args.rounds * len(agents)))
        return

    if args.simulate:
        def loop():
            while True:
                simulator.tick(store, registry.load_agents(os.environ.get(
                    "BOARD_AGENTS_DIR", os.path.join(HERE, "agents"))))  # hot-reload roster
                time.sleep(args.interval)
        threading.Thread(target=loop, daemon=True).start()
    host, port = os.environ.get("HOST", "0.0.0.0"), int(os.environ.get("PORT", "8000"))
    print("Board on http://%s:%d" % (host, port))
    server.serve(store, host, port)


if __name__ == "__main__":
    main()
