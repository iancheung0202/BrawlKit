from brawl.Currency import events
from brawl.Currency.db import u_balance


def balance(user_id):
    data = u_balance(user_id).get() or {}
    return data.get("Beans", 0), data.get("Tokens", 0)


async def change(user_id, beans=0, tokens=0, reason="other"):
    have_beans, have_tokens = balance(user_id)
    total = {}
    if beans:
        total["Beans"] = have_beans + beans
    if tokens:
        total["Tokens"] = have_tokens + tokens
    if total:
        u_balance(user_id).update(total)
        await events.emit("wallet", user_id, beans=beans, tokens=tokens, reason=reason)
    return total.get("Beans", have_beans), total.get("Tokens", have_tokens)


async def pay(user_id, beans=0, tokens=0, reason="other"):
    have_beans, have_tokens = balance(user_id)
    if have_beans < beans or have_tokens < tokens:
        return False
    await change(user_id, -beans, -tokens, reason)
    return True


async def setup(bot):
    pass
