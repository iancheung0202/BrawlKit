import asyncio
from unittest.mock import patch

from brawl.Currency import gambling

USER = 1


def beans(cafe):
    return cafe.ref(f"Cafe Economy/{USER}/balance/Beans").get()


def test_coinflip_takes_the_bet_and_pays_a_win(cafe):
    cog = cafe.cogs["Gambling"]
    cafe.ref(f"Cafe Economy/{USER}/balance").set({"Beans": 500})

    async def play():
        start = cafe.interaction(USER)
        await cog.coinflip.callback(cog, start, 200)
        assert beans(cafe) == 300
        view = start.followup.send.call_args.kwargs["view"]
        press = cafe.interaction(USER)
        with patch.object(gambling.random, "choice", lambda options: "heads"):
            await view.children[0].callback(press)
        return press

    press = asyncio.run(play())
    assert beans(cafe) == 700
    assert isinstance(
        press.response.edit_message.call_args.kwargs["view"], gambling.PlayAgainView
    )


def test_coinflip_refuses_a_bet_above_the_balance(cafe):
    cog = cafe.cogs["Gambling"]
    cafe.ref(f"Cafe Economy/{USER}/balance").set({"Beans": 150})
    sent = cafe.interaction(USER)
    asyncio.run(cog.coinflip.callback(cog, sent, 200))
    assert "don't have enough" in sent.followup.send.call_args[0][0]
    assert beans(cafe) == 150
