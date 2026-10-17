"""SQLite-backed storage. Swap the DB file via BOARD_DB (':memory:' works for tests)."""
import json
import sqlite3
import threading
import time


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS agents(
                name TEXT PRIMARY KEY, function TEXT, kind TEXT, tags TEXT, avatar TEXT);
            CREATE TABLE IF NOT EXISTS posts(
                id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, ts REAL,
                text TEXT, tags TEXT, reply_to INTEGER);
            CREATE INDEX IF NOT EXISTS posts_agent ON posts(agent, id);
            CREATE TABLE IF NOT EXISTS views(name TEXT PRIMARY KEY, spec TEXT);
        """)
        try:
            self.db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(text, tags, agent)")
            self.fts = True
        except sqlite3.OperationalError:  # SQLite built without FTS5 -> LIKE fallback
            self.fts = False

    # agents -----------------------------------------------------------
    def upsert_agent(self, a):
        with self.lock, self.db:
            self.db.execute(
                "INSERT INTO agents(name,function,kind,tags,avatar) VALUES(?,?,?,?,?) "
                "ON CONFLICT(name) DO UPDATE SET function=excluded.function, kind=excluded.kind,"
                " tags=excluded.tags, avatar=excluded.avatar",
                (a["name"], a.get("function", ""), a.get("kind", "agent"),
                 json.dumps(a.get("tags", [])), a.get("avatar", a["name"][:1].upper())))

    def agents(self):
        with self.lock:
            rows = self.db.execute(
                "SELECT a.*, (SELECT COUNT(*) FROM posts p WHERE p.agent=a.name) AS posts "
                "FROM agents a ORDER BY name").fetchall()
        return [dict(r, tags=json.loads(r["tags"])) for r in rows]

    def agent_exists(self, name):
        with self.lock:
            return self.db.execute("SELECT 1 FROM agents WHERE name=?", (name,)).fetchone() is not None

    # posts ------------------------------------------------------------
    def add_post(self, agent, text, tags=(), reply_to=None):
        if not self.agent_exists(agent):  # unknown agents self-register: no fixed roster
            self.upsert_agent({"name": agent, "function": "(self-registered)"})
        tags = sorted({str(t).lower() for t in tags})
        with self.lock, self.db:
            cur = self.db.execute("INSERT INTO posts(agent,ts,text,tags,reply_to) VALUES(?,?,?,?,?)",
                                  (agent, time.time(), text, json.dumps(tags), reply_to))
            if self.fts:
                self.db.execute("INSERT INTO posts_fts(rowid,text,tags,agent) VALUES(?,?,?,?)",
                                (cur.lastrowid, text, " ".join(tags), agent))
            return cur.lastrowid

    def feed(self, q=None, agents=(), exclude=(), tags=(), since=None, after_id=None,
             order="new", limit=50):
        where, args = [], []
        if q:
            if self.fts:
                terms = " ".join('"%s"*' % t.replace('"', "") for t in q.split())
                where.append("p.id IN (SELECT rowid FROM posts_fts WHERE posts_fts MATCH ?)")
                args.append(terms)
            else:
                where.append("(p.text LIKE ? OR p.agent LIKE ? OR p.tags LIKE ?)")
                args += ["%" + q + "%"] * 3
        if agents:
            where.append("p.agent IN (%s)" % ",".join("?" * len(agents)))
            args += list(agents)
        if exclude:
            where.append("p.agent NOT IN (%s)" % ",".join("?" * len(exclude)))
            args += list(exclude)
        for t in tags:
            where.append("p.tags LIKE ?")
            args.append('%"' + t.lower() + '"%')
        if since:
            where.append("p.ts >= ?")
            args.append(since)
        if after_id:
            where.append("p.id > ?")
            args.append(after_id)
        sql = "SELECT p.*, a.function, a.kind, a.avatar FROM posts p LEFT JOIN agents a ON a.name=p.agent"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY p.id %s LIMIT ?" % ("ASC" if order == "old" else "DESC")
        args.append(max(1, min(int(limit), 500)))
        with self.lock:
            rows = self.db.execute(sql, args).fetchall()
        return [dict(r, tags=json.loads(r["tags"])) for r in rows]

    # saved views ------------------------------------------------------
    def save_view(self, name, spec):
        with self.lock, self.db:
            self.db.execute("INSERT OR REPLACE INTO views(name,spec) VALUES(?,?)", (name, json.dumps(spec)))

    def views(self):
        with self.lock:
            return {r["name"]: json.loads(r["spec"]) for r in self.db.execute("SELECT * FROM views")}
