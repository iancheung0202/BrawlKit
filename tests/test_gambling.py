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
        press.response.edit_message.call_args.kwargs["view"], gambling.PlayAgain
    )


def test_coinflip_refuses_a_bet_above_the_balance(cafe):
    cog = cafe.cogs["Gambling"]
    cafe.ref(f"Cafe Economy/{USER}/balance").set({"Beans": 150})
    sent = cafe.interaction(USER)
    asyncio.run(cog.coinflip.callback(cog, sent, 200))
    assert "don't have enough" in sent.followup.send.call_args[0][0]
    assert beans(cafe) == 150


def deal(cafe, cards, bet=200):
    """Starts a blackjack game with a chosen deal: two dealer cards, then two player cards."""
    cog = cafe.cogs["Gambling"]
    cafe.ref(f"Cafe Economy/{USER}/balance").set({"Beans": 1000})
    start = cafe.interaction(USER)
    with patch.object(gambling.random, "sample", lambda deck, count: list(cards)):
        asyncio.run(cog.blackjack.callback(cog, start, bet))
    return start.followup.send.call_args.kwargs


def press(cafe, view, label):
    button = next(child for child in view.children if child.label == label)
    click = cafe.interaction(USER)
    asyncio.run(button.callback(click))
    return click.response.edit_message.call_args.kwargs


def test_blackjack_shows_a_card_and_takes_the_bet(cafe):
    sent = deal(cafe, [("K", "♠"), ("7", "♥"), ("10", "♦"), ("9", "♣")])
    assert sent["file"].filename == "blackjack.jpg"
    assert isinstance(sent["view"], gambling.Blackjack)
    assert beans(cafe) == 800


def test_blackjack_stand_on_a_higher_hand_pays_the_bet(cafe):
    sent = deal(cafe, [("K", "♠"), ("7", "♥"), ("10", "♦"), ("9", "♣")])
    result = press(cafe, sent["view"], "Stand")
    assert beans(cafe) == 1200
    assert isinstance(result["view"], gambling.PlayAgain)
    assert result["attachments"][0].filename == "blackjack.jpg"


def test_blackjack_stand_on_a_lower_hand_loses_the_bet(cafe):
    sent = deal(cafe, [("K", "♠"), ("9", "♥"), ("10", "♦"), ("8", "♣")])
    press(cafe, sent["view"], "Stand")
    assert beans(cafe) == 800


def test_blackjack_tie_returns_the_bet(cafe):
    sent = deal(cafe, [("K", "♠"), ("9", "♥"), ("10", "♦"), ("9", "♣")])
    press(cafe, sent["view"], "Stand")
    assert beans(cafe) == 1000


def test_blackjack_bust_loses_the_bet(cafe):
    sent = deal(cafe, [("K", "♠"), ("9", "♥"), ("10", "♦"), ("9", "♣")])
    with patch.object(gambling.random, "choice", lambda cards: ("5", "♠")):
        press(cafe, sent["view"], "Hit")
    assert beans(cafe) == 800
    assert sent["view"].over


def test_blackjack_double_down_doubles_the_bet_and_the_win(cafe):
    sent = deal(cafe, [("K", "♠"), ("7", "♥"), ("5", "♦"), ("6", "♣")])
    with patch.object(gambling.random, "choice", lambda cards: ("9", "♠")):
        press(cafe, sent["view"], "Double Down")
    assert beans(cafe) == 1400


def test_blackjack_surrender_returns_half(cafe):
    sent = deal(cafe, [("K", "♠"), ("7", "♥"), ("5", "♦"), ("6", "♣")])
    press(cafe, sent["view"], "Surrender")
    assert beans(cafe) == 900


def test_blackjack_on_the_deal_pays_one_and_a_half(cafe):
    sent = deal(cafe, [("K", "♠"), ("7", "♥"), ("A", "♦"), ("K", "♣")])
    assert beans(cafe) == 1300
    assert isinstance(sent["view"], gambling.PlayAgain)


def test_aces_drop_to_one_before_a_bust():
    assert gambling.total([("A", "♠"), ("A", "♥"), ("9", "♦")]) == 21
    assert gambling.total([("A", "♠"), ("K", "♥"), ("5", "♦")]) == 16


def test_games_stop_at_the_daily_limit(cafe):
    cog = cafe.cogs["Gambling"]
    cafe.ref(f"Cafe Economy/{USER}/balance").set({"Beans": 1000})
    limit = gambling.DAILY_GAMBLING_LIMITS["coinflip"]
    gambling.u_gambling_limits(USER, gambling.get_current_date_key()).set(
        {"coinflip": limit}
    )
    sent = cafe.interaction(USER)
    asyncio.run(cog.coinflip.callback(cog, sent, 200))
    assert f"all `{limit}` games" in sent.followup.send.call_args[0][0]
    assert beans(cafe) == 1000
