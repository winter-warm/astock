def confirmed_targets(scores, entry=.02, exit=-.02, count=2, cooldown=1):
    state = streak = wait = 0
    result = []
    for score in scores:
        if wait:
            wait -= 1
            result.append(state)
            continue
        desired = (score > entry) if not state else (score < exit)
        streak = streak + 1 if desired else 0
        if streak >= count:
            state = 1-state
            streak = 0
            wait = cooldown
        result.append(state)
    return result

scores = [0,.03,-.01,.04,.05,.01,-.03,-.04,.06,.07,.08]
raw = [int(s>0) for s in scores]
confirmed = confirmed_targets(scores)
def changes(x):
    return sum(a!=b for a,b in zip([0]+x[:-1],x))
print("立即判断", raw, "切换", changes(raw))
print("确认后", confirmed, "切换", changes(confirmed))
assert confirmed[4] == 1 and confirmed[7] == 0
assert changes(confirmed) < changes(raw)

