import discord
import re
import ast
import difflib

from discord.ext import commands
from cogs.utils import checks


class TeamManager:
    """Used to match roles to teams"""

    DATASET = "TeamData"
    TIERS_KEY = "Tiers"
    TEAMS_KEY = "Teams"
    TEAM_ROLES_KEY = "Team Roles"
    FRANCHISE_ROLE_KEY = "Franchise Role"
    TIER_ROLE_KEY = "Tier Role"
    GM_ROLE = "General Manager"
    CAPTAN_ROLE = "Captain"
    IR_ROLE = "IR"
    PERM_FA_ROLE = "PermFA"

    def __init__(self, bot):
        self.bot = bot
        self.data_cog = self.bot.get_cog("RscData")
        self.prefix_cog = self.bot.get_cog("PrefixManager")

    @commands.command(no_pm=True)
    async def franchises(self, ctx):
        franchise_roles = self._get_all_franchise_roles(ctx)
        message = "```Franchises:"
        for role in franchise_roles:
            message += "\n\t{0}".format(role.name)
        message += "```"
        await ctx.send(message)

    @commands.command(no_pm=True)
    async def teams(self, ctx, *, franchise_tier_prefix: str):
        """Returns a list of teams based on the input. 
        You can either give it the name of a franchise, a tier, or the prefix for a franchise.
        
        Examples:
        \t[p]teams The Ocean
        \t[p]teams Challenger
        \t[p]teams OCE"""
        # Prefix
        prefixes = self.prefix_cog._prefixes(ctx)
        if(len(prefixes.items()) > 0):
            for key, value in prefixes.items():
                if franchise_tier_prefix.lower() == value.lower():
                    gm_name = key
                    franchise_role = await self._get_franchise_role(ctx, gm_name)
                    teams = self._find_teams_for_franchise(ctx, franchise_role)
                    message = "```{0}:".format(franchise_role.name)
                    for team in teams:
                        tier_role = self._roles_for_team(ctx, team)[1]
                        message += "\n\t{0} ({1})".format(team, tier_role.name)
                    message += "```"
                    await ctx.send(message)
                    return

        # Tier
        tiers = self._tiers(ctx)
        for tier in tiers:
            if tier.lower() == franchise_tier_prefix.lower():
                teams = self._find_teams_for_tier(ctx, franchise_tier_prefix)
                message = "```{0} teams:".format(tier)
                for team in teams:
                    franchise_role = self._roles_for_team(ctx, team)[0]
                    gmNameFromRole = re.findall(r'(?<=\().*(?=\))', franchise_role.name)[0]
                    message += "\n\t{0} ({1})".format(team, gmNameFromRole)
                message += "```"
                await ctx.send(message)
                return

        # Franchise name
        franchise_role = self.get_franchise_role_from_name(ctx, franchise_tier_prefix)
        if franchise_role is not None:
            teams = self._find_teams_for_franchise(ctx, franchise_role)
            message = "```{0}:".format(franchise_role.name)
            for team in teams:
                tier_role = self._roles_for_team(ctx, team)[1]
                message += "\n\t{0} ({1})".format(team, tier_role.name)
            message += "```"
            await ctx.send(message)
        else:
            await ctx.send("No franchise, tier, or prefix with name: {0}".format(franchise_tier_prefix))

    @commands.command(no_pm=True)
    async def roster(self, ctx, *, team_name: str):
        team, found = self._match_team_name(ctx, team_name)
        if found:
            franchise_role, tier_role = self._roles_for_team(ctx, team)
            if franchise_role is None or tier_role is None:
                await ctx.send("No franchise and tier roles set up for {0}".format(team))
                return
            await ctx.send(self.format_roster_info(ctx, team))
        else:
            message = "No team with name: {0}".format(team_name)
            if len(team) > 0:
                message += "\nDo you mean one of these teams:"
                for possible_team in team:
                    message += " `{0}`".format(possible_team)
            await ctx.send(message)

    @commands.command(no_pm=True)
    async def tierList(self, ctx):
        tiers = self._tiers(ctx)
        if tiers:
            await ctx.send(
                "Tiers set up in this server: {0}".format(", ".join(tiers)))
        else:
            await ctx.send("No tiers set up in this server.")

    @commands.command(no_pm=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def addTier(self, ctx, tier_name: str):
        tiers = self._tiers(ctx)
        tiers.append(tier_name)
        self._save_tiers(ctx, tiers)
        await ctx.send("Done.")

    @commands.command(no_pm=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def removeTier(self, ctx, tier_name: str):
        tiers = self._tiers(ctx)
        try:
            tiers.remove(tier_name)
        except ValueError:
            await ctx.send(
                "{0} does not seem to be a tier.".format(tier_name))
            return
        self._save_tiers(ctx, tiers)
        await ctx.send("Done.")

    @commands.command(no_pm=True)
    async def listTeams(self, ctx):
        teams = self._teams(ctx)
        if teams:
            await ctx.send(
                "Teams set up in this server: {0}".format(", ".join(teams)))
        else:
            await ctx.send("No teams set up in this server.")

    @commands.command(no_pm=True)
    async def teamRoles(self, ctx, team_name: str):
        franchise_role, tier_role = self._roles_for_team(ctx, team_name)
        if franchise_role and tier_role:
            await ctx.send(
                    "Franchise role for {0} = {1}\nTier role for {0} = {2}".format(team_name, franchise_role.name, tier_role.name))
        else:
            await ctx.send("No franchise and tier roles set up for {0}".format(team_name))

    @commands.command(no_pm=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def addTeams(self, ctx, *teams_to_add):
        """Add the teams provided to the team list.

        Arguments:

        teams_to_add -- One or more teams in the following format:
        ```
        "['<team_name>','<gm_name>','<tier>']"
        ```
        Each team should be separated by a space.

        Examples:
        ```
        [p]addTeams "['Derechos','Shamu','Challenger']"
        [p]addTeams "['Derechos','Shamu','Challenger']" "['Barbarians','Snipe','Challenger']"
        ```
        """
        addedCount = 0
        try:
            for teamStr in teams_to_add:
                team = ast.literal_eval(teamStr)
                await ctx.send("Adding team: {0}".format(repr(team)))
                teamAdded = await self._add_team(ctx, *team)
                if teamAdded:
                    addedCount += 1
        finally:
            await ctx.send("Added {0} team(s).".format(addedCount))
        await ctx.send("Done.")

    @commands.command(no_pm=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def addTeam(self, ctx, team_name: str, gm_name: str, tier: str):
        teamAdded = await self._add_team(ctx, team_name, gm_name, tier)
        if(teamAdded):
            await ctx.send("Done.")
        else:
            await ctx.send("Error adding team: {0}".format(team_name))

    @commands.command(no_pm=True)
    @checks.admin_or_permissions(manage_guild=True)
    async def removeTeam(self, ctx, team_name: str):
        teams = self._teams(ctx)
        team_roles = self._team_roles(ctx)
        try:
            teams.remove(team_name)
            del team_roles[team_name]
        except ValueError:
            await ctx.send(
                "{0} does not seem to be a team.".format(team_name))
            return
        self._save_teams(ctx, teams)
        self._save_team_roles(ctx, team_roles)
        await ctx.send("Done.")

    @commands.command(no_pm=True)
    async def freeAgents(self, ctx, tier: str):
        tiers = self._tiers(ctx)
        tier_name = None
        for _tier in tiers:
            if tier.lower() == _tier.lower():
                tier_name = _tier
                break
        
        if tier_name is None:
            await ctx.send("No tier with name: {0}".format(tier))
            return

        fa_role = self._find_role_by_name(ctx, tier_name + "FA")
        if fa_role is None:
            await ctx.send("No free agent role with name: {0}".format(tier_name + "FA"))
            return

        perm_fa_role = self._find_role_by_name(ctx, self.PERM_FA_ROLE)

        message = "```{0} Free Agents:".format(tier_name)
        for member in ctx.message.guild.members:
            if fa_role in member.roles:
                message += "\n\t{0}".format(member.nick)
                if perm_fa_role is not None and perm_fa_role in member.roles:
                    message += " (Permanent FA)"
        await ctx.send(message + "```")


    def is_gm(self, member):
        for role in member.roles:
            if role.name == self.GM_ROLE:
                return True
        return False

    def is_captain(self, member):
        for role in member.roles:
            if role.name == self.CAPTAN_ROLE:
                return True
        return False

    def is_IR(self, member):
        for role in member.roles:
            if role.name == self.IR_ROLE:
                return True
        return False

    def teams_for_user(self, ctx, user):
        tiers = self._tiers(ctx)
        teams = []
        franchise_role = self.get_current_franchise_role(user)
        for role in user.roles:
            if role.name in tiers:
                tier_role = role
                team_name = self._find_team_name(ctx, franchise_role, tier_role)
                teams.append(team_name)
        return teams

    def gm_and_members_from_team(self, ctx, franchise_role, tier_role):
        """Retrieve tuple with the gm user and a list of other users that are
        on the team indicated by the provided franchise_role and tier_role.
        """
        gm = None
        team_members = []
        for member in ctx.message.guild.members:
            if franchise_role in member.roles:
                if self.is_gm(member):
                    gm = member
                elif tier_role in member.roles:
                    team_members.append(member)
        return (gm, team_members)

    def format_roster_info(self, ctx, team_name: str):
        franchise_role, tier_role = self._roles_for_team(ctx, team_name)
        gm, team_members = self.gm_and_members_from_team(ctx, franchise_role, tier_role)

        message = "```\n{0} ({1}):\n".format(team_name, tier_role.name)
        if gm:
            message += "  {0}\n".format(
                self._format_team_member_for_message(gm, "GM"))
        for member in team_members:
            message += "  {0}\n".format(
                self._format_team_member_for_message(member))
        if not team_members:
            message += "  No known members."
        message += "```\n"
        return message

    def _format_team_member_for_message(self, member, *args):
        extraRoles = list(args)

        name = member.nick if member.nick else member.name
        if self.is_captain(member):
            extraRoles.append("C")
        if self.is_IR(member):
            extraRoles.append("IR")
        roleString = ""
        if extraRoles:
            roleString = " ({0})".format("|".join(extraRoles))
        return "{0}{1}".format(name, roleString)

    def _all_data(self, ctx):
        all_data = self.data_cog.load(ctx, self.DATASET)
        return all_data

    def _tiers(self, ctx):
        all_data = self._all_data(ctx)
        tiers = all_data.setdefault(self.TIERS_KEY, [])
        return tiers

    def _save_tiers(self, ctx, tiers):
        all_data = self._all_data(ctx)
        all_data[self.TIERS_KEY] = tiers
        self.data_cog.save(ctx, self.DATASET, all_data)

    def _extract_tier_from_role(self, team_role):
        tier_matches = re.findall(r'\w*\b(?=\))', team_role.name)
        return None if not tier_matches else tier_matches[0]

    async def _add_team(self, ctx, team_name: str, gm_name: str, tier: str):
        teams = self._teams(ctx)
        team_roles = self._team_roles(ctx)

        tier_role = self._get_tier_role(ctx, tier)

        # Validation of input
        # There are other validations we could do, but don't
        #     - that there aren't extra args
        errors = []
        if not team_name:
            errors.append("Team name not found.")
        if not gm_name:
            errors.append("GM name not found.")
        if not tier_role:
            errors.append("Tier role not found.")
        if errors:
            await ctx.send(":x: Errors with input:\n\n  "
                               "* {0}\n".format("\n  * ".join(errors)))
            return

        try:
            franchise_role = await self._get_franchise_role(ctx, gm_name)
            teams.append(team_name)
            team_data = team_roles.setdefault(team_name, {})
            team_data["Franchise Role"] = franchise_role.id
            team_data["Tier Role"] = tier_role.id
        except:
            return False
        self._save_teams(ctx, teams)
        self._save_team_roles(ctx, team_roles)
        return True

    def _get_tier_role(self, ctx, tier: str):
        roles = ctx.message.guild.roles
        for role in roles:
            if role.name.lower() == tier.lower():
                return role
        return None

    def _teams(self, ctx):
        all_data = self._all_data(ctx)
        teams = all_data.setdefault(self.TEAMS_KEY, [])
        return teams

    def _save_teams(self, ctx, teams):
        all_data = self._all_data(ctx)
        all_data[self.TEAMS_KEY] = teams
        self.data_cog.save(ctx, self.DATASET, all_data)

    def _team_roles(self, ctx):
        all_data = self._all_data(ctx)
        team_roles = all_data.setdefault(self.TEAM_ROLES_KEY, {})
        return team_roles

    def _save_team_roles(self, ctx, team_roles):
        all_data = self._all_data(ctx)
        all_data[self.TEAM_ROLES_KEY] = team_roles
        self.data_cog.save(ctx, self.DATASET, all_data)

    def _find_role(self, ctx, role_id):
        for role in ctx.message.guild.roles:
            if role.id == role_id:
                return role
        raise LookupError('No role with id: {0} found in server roles'.format(role_id))

    def _find_role_by_name(self, ctx, role_name):
        for role in ctx.message.guild.roles:
            if role.name.lower() == role_name.lower():
                return role
        return None

    async def _get_franchise_role(self, ctx, gm_name):
        for role in ctx.message.guild.roles:
            try:
                gmNameFromRole = re.findall(r'(?<=\().*(?=\))', role.name)[0]
                if gmNameFromRole == gm_name:
                    return role
            except:
                continue
        await ctx.send(":x: Franchise role not found for {0}".format(gm_name))

    def _get_all_franchise_roles(self, ctx):
        franchise_roles = []
        for role in ctx.message.guild.roles:
            try:
                gmNameFromRole = re.findall(r'(?<=\().*(?=\))', role.name)[0]
                if gmNameFromRole is not None:
                    franchise_roles.append(role)
            except:
                continue
        return franchise_roles

    def _roles_for_team(self, ctx, team_name: str):
        teams = self._teams(ctx)
        if teams and team_name in teams:
            team_roles = self._team_roles(ctx)
            team_data = team_roles.setdefault(team_name, {})
            franchise_role_id = team_data["Franchise Role"]
            tier_role_id = team_data["Tier Role"]
            franchise_role = self._find_role(ctx, franchise_role_id)
            tier_role = self._find_role(ctx, tier_role_id)
            return (franchise_role, tier_role)
        else:
           raise LookupError('No team with name: {0}'.format(team_name))

    def _find_team_name(self, ctx, franchise_role, tier_role):
        teams = self._teams(ctx)
        for team in teams:
            if self._roles_for_team(ctx, team) == (franchise_role, tier_role):
                return team

    def _find_teams_for_franchise(self, ctx, franchise_role):
        franchise_teams = []
        teams = self._teams(ctx)
        for team in teams:
            if self._roles_for_team(ctx, team)[0] == franchise_role:
                franchise_teams.append(team)
        return franchise_teams

    def get_current_franchise_role(self, user: discord.Member):
        for role in user.roles:
            try:
                gmNameFromRole = re.findall(r'(?<=\().*(?=\))', role.name)[0]
                if gmNameFromRole:
                    return role
            except:
                continue

    def get_current_tier_role(self, ctx, user: discord.Member):
        tierList = self._tiers(ctx)
        for role in user.roles:
            if role.name in tierList:
                return role
        return None

    def get_current_team_name(self, ctx, user: discord.Member):
        tier_role = self.get_current_tier_role(ctx, user)
        franchise_role = self.get_current_franchise_role(user)
        return self._find_team_name(ctx, franchise_role, tier_role)

    def get_franchise_role_from_name(self, ctx, franchise_name: str):
        for role in ctx.message.guild.roles:
            try:
                matchedString = re.findall(r'.+?(?= \()', role.name)[0]
                if matchedString.lower() == franchise_name.lower():
                    return role
            except:
                continue

    def _match_team_name(self, ctx, team_name):
        teams = self._teams(ctx)
        for team in teams:
            if team_name.lower() == team.lower():
                return team, True
        return difflib.get_close_matches(team_name, teams, n=3, cutoff=0.4), False

    def _match_tier_name(self, ctx, tier_name):
        tiers = self._tiers(ctx)
        for tier in tiers:
            if tier_name.lower() == tier.lower():
                return tier
        close_match = difflib.get_close_matches(tier_name, tiers, n=1, cutoff=0.6)
        if len(close_match) > 0:
            return close_match[0]
        return None

    def _find_teams_for_tier(self, ctx, tier):
        teams_in_tier = []
        teams = self._teams(ctx)
        for team in teams:
            team_tier = self._roles_for_team(ctx, team)[1]
            if team_tier.name.lower() == tier.lower():
                teams_in_tier.append(team)
        return teams_in_tier

    def log_info(self, message):
        self.data_cog.logger().info("[TeamManager] " + message)

    def log_error(self, message):
        self.data_cog.logger().error("[TeamManager] " + message)


def setup(bot):
    bot.add_cog(TeamManager(bot))
