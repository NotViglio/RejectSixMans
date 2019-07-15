import discord
import asyncio
import difflib

from discord.ext import commands
from cogs.utils import checks

class FaCheckIn:

    DATASET = "FaCheckInData"

    def __init__(self, bot):
        self.bot = bot
        self.data_cog = self.bot.get_cog("RscData")
        self.team_manager_cog = self.bot.get_cog("TeamManager")
        self.match_cog = self.bot.get_cog("Match")

    @commands.command(no_pm=True, aliases=["ci"])
    async def checkIn(self, ctx):
        user = ctx.message.author
        match_day = self.match_cog._match_day(ctx)
        tier = self._find_tier_from_fa_role(ctx, user)

        await ctx.message.delete()

        if tier is not None:
            tier_data = self._tier_data(ctx, match_day, tier)
            if user.id not in tier_data:
                await self._send_check_in_message(ctx, user, match_day, tier)
            else:
                await user.send("You've already checked in. If you want to check out, use the `{0}checkOut` command.".format(ctx.prefix))
        else:
            await user.send("Only free agents are allowed to check in. If you are a free agent and are unable to check in please message an admin.")

    @commands.command(no_pm=True, aliases=["co"])
    async def checkOut(self, ctx):
        user = ctx.message.author
        match_day = self.match_cog._match_day(ctx)
        tier = self._find_tier_from_fa_role(ctx, user)
        if tier is None:
            tier = self.team_manager_cog.get_current_tier_role(ctx, user)

        await ctx.message.delete()

        if tier is not None:
            tier_data = self._tier_data(ctx, match_day, tier)
            if user.id in tier_data:
                await self._send_check_out_message(ctx, user, match_day, tier)
            else:
                await user.send("You aren't currently checked in. If you want to check in, use the `{0}checkIn` command.".format(ctx.prefix))
        else:
            await user.send("Your tier could not be determined. If you are in the league please contact an admin for help.")

    @commands.command(no_pm=True, aliases=["ca"])
    async def checkAvailability(self, ctx, tier_name: str, match_day: str = None):
        if match_day is None:
            match_day = self.match_cog._match_day(ctx)
        tier = self.team_manager_cog._match_tier_name(ctx, tier_name)
        if tier is None:
            await ctx.send("No tier with name: `{0}`".format(tier_name))
            return

        tier_list = self._tier_data(ctx, match_day, tier)
        perm_fa_role = self.team_manager_cog._find_role_by_name(ctx, self.team_manager_cog.PERM_FA_ROLE)

        message = "```Availability for {0} tier on match day {1}:".format(tier, match_day)
        for user in tier_list:
            member = commands.MemberConverter(ctx, user).convert()
            if member in ctx.message.guild.members:
                if self._find_tier_from_fa_role(ctx, member) is not None:
                    message += "\n\t{0}".format(member.nick)
                    if perm_fa_role is not None and perm_fa_role in member.roles:
                        message += " (Permanent FA)"
        message += "```"
        await ctx.send(message)

    @commands.command(no_pm=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def clearAvailability(self, ctx, tier: str = None, match_day: str = None):
        if match_day is None:
            match_day = self.match_cog._match_day(ctx)

        if tier is None:
            self._save_match_data(ctx, match_day, {})
        else:
            self._save_tier_data(ctx, match_day, tier, [])
        await ctx.send("Done.")

    @commands.command(no_pm=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def clearAllAvailability(self, ctx):
        self._save_data(ctx, {})
        await ctx.send("Done.")

    async def _send_check_in_message(self, ctx, user, match_day, tier):
        embed = discord.Embed(title="Check In", 
            description="By checking in you are letting GMs know that you are available to play "
                "on the following match day in the following tier. To confirm react with 👍",
            colour=discord.Colour.blue())
        embed.add_field(name="Match Day", value=match_day, inline=True)
        embed.add_field(name="Tier", value=tier, inline=True)
        message = await user.send(embed=embed)

        await message('👍')

        def check(reaction, user):
            return str(reaction.emoji) == '👍'

        try:
            result = await self.bot.wait_for('reaction_add', message=message, timeout=30.0, check=check, user=user)
        except:
            await user.send("Sorry, you either didn't react quick enough or something went wrong. Please try again.")
            return

        if result:
            self._register_user(ctx, user, match_day, tier)
            await user.send("Thank you for checking in! GMs will now be able to see that you're available.")
        else:
            await user.send("Sorry, you didn't react quick enough. Please try again.")

    async def _send_check_out_message(self, ctx, user, match_day, tier):
        embed = discord.Embed(title="Check Out", 
            description="You are currently checked in as available for the following match day and tier. "
                "Do you wish to take yourself off the availability list? To confirm you want to check out, react with 👎",
            colour=discord.Colour.blue())
        embed.add_field(name="Match Day", value=match_day, inline=True)
        embed.add_field(name="Tier", value=tier, inline=True)
        message = await user.send(embed=embed)

        await message.add_reaction('👎')

        def check(reaction, user):
            return str(reaction.emoji) == '👎'

        try:
            result = await self.bot.wait_for('reaction_add', message=message, timeout=30.0, check=check, user=user)
        except:
            await user.send("Sorry, you either didn't react quick enough or something went wrong. Please try again.")
            return

        if result:
            self._unregister_user(ctx, user, match_day, tier)
            await user.send("You have been removed from the list. Thank you for updating your availability!")
        else:
            await user.send("Sorry, you didn't react quick enough. Please try again.")

    def _register_user(self, ctx, user, match_day, tier):
        tier_list = self._tier_data(ctx, match_day, tier)
        tier_list.append(user.id)
        self._save_tier_data(ctx, match_day, tier, tier_list)

    def _unregister_user(self, ctx, user, match_day, tier):
        tier_list = self._tier_data(ctx, match_day, tier)
        tier_list.remove(user.id)
        self._save_tier_data(ctx, match_day, tier, tier_list)

    def _find_tier_from_fa_role(self, ctx, user: discord.Member):
        tiers = self.team_manager_cog._tiers(ctx)
        for tier in tiers:
            fa_role = self.team_manager_cog._find_role_by_name(ctx, tier + "FA")
            if fa_role in user.roles:
                return tier
        return None

    def _save_tier_data(self, ctx, match_day, tier, tier_data):
        all_data = self._all_data(ctx)
        match_data = all_data.setdefault(match_day, {})
        match_data[tier] = tier_data
        self.data_cog._save_data(ctx, self.DATASET, all_data)

    def _save_match_data(self, ctx, match_day, match_data):
        all_data = self._all_data(ctx)
        all_data[match_day] = match_data
        self.data_cog._save_data(ctx, self.DATASET, all_data)

    def _save_data(self, ctx, all_data):
        self.data_cog._save_data(ctx, self.DATASET, all_data)

    def _tier_data(self, ctx, match_day, tier):
        match_data = self._match_data(ctx, match_day)
        tier_data = match_data.setdefault(tier, [])
        return tier_data

    def _match_data(self, ctx, match_day):
        all_data = self._all_data(ctx)
        match_data = all_data.setdefault(match_day, {})
        return match_data

    def _all_data(self, ctx):
        all_data = self.data_cog.load(ctx, self.DATASET)
        return all_data

def setup(bot):
    bot.add_cog(FaCheckIn(bot))