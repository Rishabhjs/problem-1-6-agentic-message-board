"""Runs a swarm: every registered agent 'does its job' and posts updates.
Mock mode (default) is data-driven from each agent's `activities`; with ANTHROPIC_API_KEY
set, Claude writes the update in the agent's voice."""
import json
import os
import random
import urllib.request

MODEL = os.environ.get("BOARD_MODEL", "claude-haiku-5-5")


def _claude(agent, recent):
    prompt = (
        "You are %s, a %s on an internal message board for AI agents (like LinkedIn). "
        "Your job: %s. Write ONE short (<=280 chars) first-person status update about work you "
        "just did. Optionally react to a colleague's recent post. Output only the post.\n\n"
        "Recent posts:\n%s" % (agent["name"], agent.get("kind", "agent"), agent.get("function", ""),
                               "\n".join("- %s: %s" % (p["agent"], p["text"]) for p in recent[:5])))
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps({"model": MODEL, "max_tokens": 200,
                         "messages": [{"role": "user", "content": prompt}]}).encode(),
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)["content"][0]["text"].strip()


def _mock(agent, rng):
    acts = agent.get("activities") or ["Completed a task in my area: " + agent.get("function", "work")]
    return rng.choice(acts).format(n=rng.randint(3, 480), pct=rng.randint(2, 98), ms=rng.randint(40, 900))


def tick(store, agents, rng=None):
    """One round: each agent posts one update. Returns number of posts."""
    rng = rng or random.Random()
    use_llm = bool(os.environ.get("ANTHROPIC_API_KEY"))
    order = list(agents)
    rng.shuffle(order)
    for a in order:
        recent = store.feed(limit=5)
        text = None
        if use_llm:
            try:
                text = _claude(a, recent)
            except Exception as e:  # network/API problem -> degrade to mock, never crash the swarm
                print("claude unavailable (%s); using mock" % e)
                use_llm = False
        text = text or _mock(a, rng)
        reply = recent[0]["id"] if recent and rng.random() < 0.2 and recent[0]["agent"] != a["name"] else None
        store.add_post(a["name"], text, a.get("tags", []), reply_to=reply)
    return len(order)
