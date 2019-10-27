class Category:
    def __init__(self, bot, name: str = '', description: str = ''):
        bot.categories[name] = self
        self.bot = bot
        self.name = name
        self.description = description
        self.cogs = []

    def add_cogs(self, *cogs):
        for cog in cogs:
            self.add_cog(cog)

    def remove_cogs(self):
        for cog in self.cogs:
            self.bot.remove_cog(cog)
        self.cogs.clear()

    def remove_cog(self, cog):
        self.bot.unload_extension(f"cogs.{self.__name__}.{cog.__name__}")
        self.cogs.remove(cog)

    def add_cog(self, cog):
        c = cog(self.bot)
        self.bot.load_extension(f"cogs.{self.__name__}.{c.__name__}")
        c.category = self
        self.cogs.append(c)

    @property
    def commands(self):
        cmds = []
        for n in self.cogs:
            cmds.extend(n.commands)
        return cmds
