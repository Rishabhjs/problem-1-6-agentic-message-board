import json, os, sys, tempfile, unittest, urllib.request
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from board import registry, server, simulator
from board.store import Store


class T(unittest.TestCase):
    def test_new_agent_file_needs_no_code(self):
        d = tempfile.mkdtemp()
        for i in range(25):
            json.dump({"name": "agent-%d" % i, "function": "f", "tags": ["x"]}, open("%s/%d.json" % (d, i), "w"))
        s = Store(":memory:"); ag = registry.load_agents(d)
        for a in ag: s.upsert_agent(a)
        simulator.tick(s, ag)
        self.assertEqual(len(s.agents()), 25); self.assertEqual(len(s.feed(limit=500)), 25)

    def test_search_filter_mute(self):
        s = Store(":memory:")
        s.add_post("a", "deployed service", ["infra"]); s.add_post("b", "wrote docs", ["docs"])
        self.assertEqual([p["agent"] for p in s.feed(q="deploy")], ["a"])
        self.assertEqual([p["agent"] for p in s.feed(tags=["docs"])], ["b"])
        self.assertEqual([p["agent"] for p in s.feed(exclude=["a"])], ["b"])

    def test_http(self):
        s = Store(":memory:"); srv = server.serve(s, "127.0.0.1", 0, background=True)
        base = "http://127.0.0.1:%d" % srv.server_address[1]
        req = urllib.request.Request(base + "/posts", json.dumps({"agent": "z", "text": "hi", "tags": ["t"]}).encode(), method="POST")
        urllib.request.urlopen(req)
        self.assertEqual(json.load(urllib.request.urlopen(base + "/posts?q=hi"))[0]["agent"], "z")
        srv.shutdown()


if __name__ == "__main__":
    unittest.main()
