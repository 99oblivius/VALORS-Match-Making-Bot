from collections import Counter
import re
import datetime
import string
import random

import nextcord
from nextcord.ext import commands
from nextcord.ext.tasks import loop

from config import *

link_counter = []
mention_counter = Counter()
accepted_codes = {}

def processLink(weblink: str, authorid: int, msgid: int, chid: int):
    for auth in link_counter:
        if auth[0] == weblink and auth[1] == authorid:
            auth[2].append((msgid, chid))
            return len(auth[2])
    link_counter.append((weblink, authorid, [(msgid, chid)]))
    return 1

def processMention(authorid):
    mention_counter.update([authorid])
    return mention_counter[authorid]

class BotProtection(commands.Cog, name="Bot Protection"):
    @loop(minutes=5)
    async def decay_timer(self):
        for auth in link_counter:
            if len(auth[2]) == 0:
                link_counter.remove(auth)
            else:
                del auth[2][0]
        
        mention_counter.subtract(mention_counter.keys())
        h = list(mention_counter.keys())
        for key in h:
            if mention_counter[key] < 1:
                del mention_counter[key]
    

    def __init__(self, bot: commands.Bot):
        self.bot = bot
    def cog_unload(self):
        self.decay_timer.cancel()
    

    @commands.Cog.listener()
    async def on_ready(self):
        self.decay_timer.start()


    @commands.Cog .listener()
    async def on_message(self, message: nextcord.Message):
        if message.author.bot:
            return
        
        # DM verification
        if isinstance(message.channel, nextcord.DMChannel):
            member = guild.get_member(message.author.id)
            if message.author.id in accepted_codes:
                if message.clean_content.lower().strip() == accepted_codes[message.author.id]:
                    try:
                        await member.add_roles(guild.get_role(RO_NOVA_ID))
                        await member.remove_roles(guild.get_role(RO_MAGIC_ID))
                        if not f'{member.id}' in self.bot.leaderboard:
                            now = datetime.now()
                            self.bot.leaderboard[f'{member.id}'] = {'x': 1.0, 'n': 1, 't': now, 'r': 0}
                        await message.author.send("Congrats you made it!\nWelcome to the community")
                        await message.author.send("Thank you for agreeing to our rules.\nFeel free to check out <#911405621981622272> or explore the server.")
                        del accepted_codes[message.author.id]
                    except Exception as e:
                        await message.author.send("Something went wrong.\nPlease try again or contact <@313912877662863360> if it happens again")
                        await guild.get_channel(710863517007478814).send("yo <@313912877662863360> get your shit together something went wrong with your bot for verification of a user")
                        print("ERROR FOR DM VERIFICATION", e)
                else:
                    await message.author.send("try again. Make sure you are copying the code exactly")
            if message.clean_content.lower() == "accept" and not any([True for role in member.roles if role.id in (RO_NOVA_ID, RO_SUPERNOVA_ID)]):
                randomcode = ''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
                await message.author.send(f"To be accepted respond with: `{randomcode}`")
                accepted_codes[message.author.id] = randomcode
            return
        
        if message.guild is None or any([True for r in message.author.roles if r.id in (RO_HELIX_ID, RO_DOUBLEHELIX_ID, RO_CORE_ID)]):
            return
        msg = message.clean_content
        msg = msg.lower()
        if any(word in msg for word in eliminationList()):
            try:
                await message.delete()
                await message.author.send(f"The message you sent at <t:{int(datetime.datetime.timestamp(datetime.datetime.utcnow()))}:T> on the VAIL server was removed for suspicion of containing aggressive language.\nFeel free to bring this up to <@313912877662863360> or <@869917273144557598> if you believe this to be a mistake. ")
            except:
                pass

        if len(re.findall(r'<@', message.content)) > 4:
            counter = processMention(message.author.id)
            if counter > 2:
                await message.author.add_roles(ro_muted)
                await ch_mod.send(f"""!!! <@&{RO_ALERT_ID}> !!! <@{message.author.id}> pinged too many users and was Muted""")
            return

        if "http" in msg:
            link = re.search(r'(https?)://(-\.)?([^\s/?\.#-]+\-?\.?)+(/[^\s]*)?', msg)
            if link:
                link = link.group(0)
                counter = processLink(link, message.author.id, message.id, message.channel.id)
                if counter == 3:
                    await message.author.send(f"""Please refrain from posting a link multiple times.\nConsequences for not obliging will range from a mute to a ban.\nThank you for understanding""")
                elif counter == 4:
                    await message.author.add_roles(ro_muted)
                    await message.author.send(f"""You have been muted and have had links deleted for spam. \nPlease directly message 0-en bot about having secured your account back, \nand if you believe this to be a mistake, please also contact 0-en bot.\nThank you for understanding""")
                    for user in link_counter:
                        if user[0] == link and user[1] == message.author.id:
                            for ms in user[2]:
                                try:
                                    del_msg = await self.bot.get_channel(ms[1]).fetch_message(ms[0])
                                    await del_msg.delete()
                                except:
                                    pass
                            await ch_log.send(f"""The above deletions have been handled by Ek0 automatically.""")
                            return
                return

def setup(bot):
    bot.add_cog(BotProtection(bot))
