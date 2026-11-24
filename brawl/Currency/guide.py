import re

import discord

INFO = "<:information:855023058255478794>"


class Info(
    discord.ui.DynamicItem[discord.ui.Button],
    template=r"(?:guide:(?P<page>[a-z]+)|level_info)",
):
    """The info button under a strip: opens the `/how` page that explains it.

    `level_info` is the button on level-up messages sent before this one.
    """

    def __init__(self, page="levels"):
        super().__init__(
            discord.ui.Button(
                style=discord.ButtonStyle.grey, emoji=INFO, custom_id=f"guide:{page}"
            )
        )
        self.page = page

    @classmethod
    async def from_custom_id(cls, interaction, item, match: re.Match):
        return cls(match["page"] or "levels")

    async def callback(self, interaction: discord.Interaction):
        from brawl.Currency.how import HowView, page_file
        from brawl.Currency.howcard import PAGES

        page = self.page if self.page in PAGES else "start"
        await interaction.response.send_message(
            file=await page_file(page), view=HowView(page), ephemeral=True
        )


def guide(page, label=None, view=None):
    """The two buttons under a strip: info, and the command to run next in grey."""
    view = view or discord.ui.View(timeout=None)
    view.add_item(Info(page))
    if label:
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.grey,
                disabled=True,
                label=label,
                custom_id="guide_next",
            )
        )
    return view


async def setup(bot):
    bot.add_dynamic_items(Info)
