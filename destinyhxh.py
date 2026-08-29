import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import json
import random
from collections import defaultdict
import os
from dotenv import load_dotenv

load_dotenv()

DB_PATH = "destiny_hxh.db"

NEN_TYPES = {
    "Geliştirme": {"emoji": "🥊", "desc": "Fiziksel güç ve iyileşme kapasitesini zirveye taşır.", "rarity": "Yaygın"},
    "Dönüşüm": {"emoji": "⚡", "desc": "Auranın özelliklerini başka maddelere benzeterek değiştirir.", "rarity": "Yaygın"},
    "Emisyon": {"emoji": "💥", "desc": "Aura'yı vücuttan ayırıp uzak mesafelerde kullanma.", "rarity": "Yaygın"},
    "Çağırma": {"emoji": "⛓️", "desc": "Aura kullanarak fiziksel, bağımsız nesneler yaratır.", "rarity": "Yaygın"},
    "Manipülasyon": {"emoji": "🎭", "desc": "Canlıları veya nesneleri aura ile kontrol etme.", "rarity": "Yaygın"},
    "Mütehassıs": {"emoji": "🔮", "desc": "Diğer beş kategoriye girmeyen en nadir ve benzersiz yetenek.", "rarity": "Efsanevi"}
}

TECHNIQUES = {
    "Ten": {"desc": "Auranın bedeni sarması."},
    "Zetsu": {"desc": "Aurayı tamamen gizleme."},
    "Ren": {"desc": "Büyük miktarda aura üretme."},
    "Hatsu": {"desc": "Kişisel Nen yeteneğini dışa vurma."},
    "Gyo": {"desc": "Aurayı gözlerde toplayarak gizli nesneleri görme."},
    "In": {"desc": "Kendi auranı görünmez yapma."},
    "En": {"desc": "Aura alanını genişleterek bölgeyi hissetme."},
    "Shu": {"desc": "Aurayı nesneye aktarma."},
    "Ko": {"desc": "Tüm aurayı tek noktaya odaklama."},
    "Ken": {"desc": "Vücudu Ren seviyesinde koruma."},
    "Ryu": {"desc": "Aura akışını anlık yönlendirme."}
}

snipe_cache = defaultdict(lambda: defaultdict(list))

class HxHBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="h!", intents=intents)
        self.db = None

    async def setup_hook(self):
        self.db = await aiosqlite.connect(DB_PATH)
        self.db.row_factory = aiosqlite.Row
        await self.init_db()
        await self.tree.sync()
        print("✦ Destiny HxH Ultimate Bot Aktif ve Senkronize Edildi ✦")

    async def init_db(self):
        await self.db.execute('''CREATE TABLE IF NOT EXISTS guild_settings (
            guild_id INTEGER PRIMARY KEY,
            allowed_categories TEXT,
            admin_roles TEXT DEFAULT '[]'
        )''')
        try:
            await self.db.execute("ALTER TABLE guild_settings ADD COLUMN admin_roles TEXT DEFAULT '[]'")
        except Exception:
            pass
        # Başlangıç parasını direkt DB seviyesinde 15000 yaptık
        await self.db.execute('''CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER,
            guild_id INTEGER,
            current_xp REAL DEFAULT 0,
            total_earned_xp REAL DEFAULT 0,
            money INTEGER DEFAULT 15000, 
            unassigned_stats INTEGER DEFAULT 0,
            character_name TEXT DEFAULT 'Bilinmiyor',
            height TEXT DEFAULT '-',
            weight TEXT DEFAULT '-',
            gender TEXT DEFAULT '-',
            strength INTEGER DEFAULT 0,
            speed INTEGER DEFAULT 0,
            durability INTEGER DEFAULT 0,
            willpower INTEGER DEFAULT 0,
            nen_amount INTEGER DEFAULT 0,
            nen_mastery INTEGER DEFAULT 0,
            nen_type TEXT DEFAULT 'Bilinmiyor',
            spin_count INTEGER DEFAULT 0,
            mastery INTEGER DEFAULT 0,
            techniques TEXT DEFAULT '[]',
            technique_points INTEGER DEFAULT 0,
            technique_levels TEXT DEFAULT '{}',
            PRIMARY KEY (user_id, guild_id)
        )''')
        for col, default in [
            ("technique_points", "0"),
            ("technique_levels", "'{}'")
        ]:
            try:
                await self.db.execute(f"ALTER TABLE players ADD COLUMN {col} INTEGER DEFAULT {default}")
            except Exception:
                pass
        try:
            await self.db.execute("ALTER TABLE players ADD COLUMN technique_levels TEXT DEFAULT '{}'")
        except Exception:
            pass
        await self.db.commit()

    async def close(self):
        if self.db:
            await self.db.close()
        await super().close()

bot = HxHBot()

def get_progress_bar(value, max_val=100, length=10):
    if value <= 0: return "▱" * length
    filled = int((value / max_val) * length)
    filled = min(max(filled, 1), length)
    return "▰" * filled + "▱" * (length - filled)

async def get_player(user_id, guild_id):
    async with bot.db.execute("SELECT * FROM players WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)) as cursor:
        row = await cursor.fetchone()
        if not row:
            await bot.db.execute("INSERT INTO players (user_id, guild_id) VALUES (?, ?)", (user_id, guild_id))
            await bot.db.commit()
            return await get_player(user_id, guild_id)
        return dict(row)

async def get_allowed_categories(guild_id):
    async with bot.db.execute("SELECT allowed_categories FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cursor:
        row = await cursor.fetchone()
        if not row:
            return []
        return json.loads(row["allowed_categories"])

async def get_admin_roles(guild_id):
    async with bot.db.execute("SELECT admin_roles FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cursor:
        row = await cursor.fetchone()
        if not row or not row["admin_roles"]:
            return []
        return json.loads(row["admin_roles"])

async def is_admin(interaction: discord.Interaction) -> bool:
    if interaction.user.guild_permissions.administrator:
        return True
    admin_roles = await get_admin_roles(interaction.guild.id)
    user_role_ids = [r.id for r in interaction.user.roles]
    return any(rid in user_role_ids for rid in admin_roles)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    if message.channel.category_id:
        allowed = await get_allowed_categories(message.guild.id)
        if allowed and message.channel.category_id in allowed:
            guild_cache = snipe_cache[message.guild.id][message.author.id]
            guild_cache.append({
                "content": message.content if message.content else "(Resim/Dosya)",
                "channel_id": message.channel.id,
                "channel_name": message.channel.name,
                "timestamp": message.created_at.strftime("%d.%m.%Y %H:%M:%S")
            })
            if len(guild_cache) > 5:
                snipe_cache[message.guild.id][message.author.id] = guild_cache[-5:]

    if not message.channel.category_id:
        return

    allowed = await get_allowed_categories(message.guild.id)
    if not allowed or message.channel.category_id not in allowed:
        return

    msg_len = len(message.content)

    # 150 ve üstü için her 5 karaktere 1 XP (150 = 30XP, 155 = 31XP, sonsuza kadar artar)
    if msg_len >= 150:
        xp_gained = round(msg_len * 0.2, 1)
    else:
        return

    await bot.db.execute('''UPDATE players
                            SET current_xp = current_xp + ?, total_earned_xp = total_earned_xp + ?
                            WHERE user_id = ? AND guild_id = ?''',
                            (xp_gained, xp_gained, message.author.id, message.guild.id))
    await bot.db.commit()

@bot.tree.command(name="bilgi", description="Botun komutlarını ve sistem rehberini gösterir.")
async def bilgi(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 Destiny HxH - Sistem Rehberi", color=discord.Color.dark_theme())
    
    embed.add_field(name="👤 OYUNCU KOMUTLARI", value=(
        "`/profil` ➔ Karakter kartını ve statlarını gösterir.\n"
        "`/nen-spin` ➔ Şansa bağlı olarak Mütehassıs olma şansı verir (1 Hak).\n"
        "`/nen-sec` ➔ İstediğin yaygın Nen türünü seçmeni sağlar.\n"
        "`/learn [teknik]` ➔ Yeni bir teknik öğrenir.\n"
        "`/teknik-dagit` ➔ Teknik puanlarını dağıtır.\n"
        "`/statcevir` ➔ XP'yi stat puanına dönüştürür (100 XP = 1 Puan).\n"
        "`/stat-dagit` ➔ Serbest stat puanlarını dağıtır.\n"
        "`/balance` ➔ Cüzdanındaki Jenny miktarını gösterir.\n"
        "`/pay` ➔ Başka bir oyuncuya para gönderir.\n"
        "`/leaderboard` ➔ En güçlü oyuncuları listeler."
    ), inline=False)
    
    embed.add_field(name="💡 SİSTEM BİLGİSİ", value=(
        "• **Nen Puanı:** Bu stata puan verdiğinde her 1 Puan sana ekstra **3 Teknik Puanı** kazandırır.\n"
        "• **XP Kazanımı:** 150 harf ve üzeri mesajlarda her 5 harf için 1 XP kazanırsın (150 harf = 30 XP, 155 harf = 31 XP şeklinde artar)."
    ), inline=False)
    
    embed.add_field(name="🛡️ YETKİLİ KOMUTLARI", value=(
        "`/kategori-ekle` ➔ XP kazanılacak kanalları belirler.\n"
        "`/karakter-olustur` ➔ Oyuncuya profil açar (15.000 Jenny ile).\n"
        "`/karakter-duzenle` ➔ Karakter bilgilerini günceller.\n"
        "`/stat-ayarla` ➔ Statları doğrudan değiştirir.\n"
        "`/admin ...` ➔ XP verme, para verme, sıfırlama komutlarıdır."
    ), inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="profil", description="Karakter profilini, Nen ve statlarını görüntüler.")
async def profil(interaction: discord.Interaction, kullanici: discord.Member = None):
    target = kullanici or interaction.user
    p = await get_player(target.id, interaction.guild.id)

    if not p or p["character_name"] == 'Bilinmiyor':
        return await interaction.response.send_message("❌ Bu kullanıcının onaylanmış bir karakter profili yok.", ephemeral=True)

    total_stats = p["strength"] + p["speed"] + p["durability"] + p["willpower"] + p["nen_amount"] + p["nen_mastery"]
    unvan = "Nen Uykusunda" if total_stats < 20 else "Nen Acemisi" if total_stats < 100 else "Nen Ustası"
    nen_info = NEN_TYPES.get(p["nen_type"], {"emoji": "❓", "desc": "Bilinmiyor"})
    
    techs = json.loads(p["techniques"])
    tech_levels = json.loads(p["technique_levels"]) if p.get("technique_levels") else {}
    tech_str = ", ".join([f"{t} [Lv.{tech_levels.get(t, 0)}]" for t in techs]) if techs else "Henüz teknik öğrenilmedi."

    # Çok daha profesyonel, temiz Discord Embed GUI'si (Telefon ve PC'de kusursuz görünür)
    embed = discord.Embed(title=f"✦ {p['character_name']} ✦", description=f"Discord: {target.mention} | Unvan: **{unvan}**\n*XP: {int(p['current_xp'])} (Toplam: {int(p['total_earned_xp'])})*", color=discord.Color.blurple())
    embed.set_thumbnail(url=target.display_avatar.url)

    embed.add_field(name="📜 Kimlik Bilgileri", value=f"**Cinsiyet:** {p['gender']}\n**Boy:** {p['height']}\n**Kilo:** {p['weight']}", inline=True)
    embed.add_field(name="🌀 Nen Durumu", value=f"**Türü:** {nen_info['emoji']} {p['nen_type']}\n**Ustalık:** {p['mastery']}\n**Çevirme Hakkı:** {1 - p['spin_count']}", inline=True)
    embed.add_field(name="💰 Ekonomi & Puan", value=f"**Bakiye:** {p['money']} Jenny\n**Boş Stat:** 🌟 {p['unassigned_stats']}\n**Teknik Puanı:** ✨ {p.get('technique_points', 0)}", inline=True)

    embed.add_field(name="⚔️ Fiziksel Statlar", value=f"🥊 **Güç:** `{p['strength']:<3}` {get_progress_bar(p['strength'])}\n⚡ **Hız:** `{p['speed']:<3}` {get_progress_bar(p['speed'])}\n🛡️ **Dayanıklılık:** `{p['durability']:<3}` {get_progress_bar(p['durability'])}", inline=False)
    embed.add_field(name="🧠 Nen Statları", value=f"👁️ **Nen:** `{p['willpower']:<3}` {get_progress_bar(p['willpower'])}\n🌊 **Nen Havuzu:** `{p['nen_amount']:<3}` {get_progress_bar(p['nen_amount'])}\n🌀 **Hakimiyet:** `{p['nen_mastery']:<3}` {get_progress_bar(p['nen_mastery'])}", inline=False)
    embed.add_field(name="📖 Öğrenilen Teknikler", value=f"```{tech_str}```", inline=False)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="nen-spin", description="Şansa bağlı olarak Mütehassıs olma şansını dene. (1 Hak)")
async def nen_spin(interaction: discord.Interaction):
    p = await get_player(interaction.user.id, interaction.guild.id)
    if p["spin_count"] >= 1:
        return await interaction.response.send_message("❌ Nen çevirme hakkını kullandın (Maksimum 1 kez)!", ephemeral=True)
    
    is_mutehassis = random.random() <= 0.05
    if is_mutehassis:
        await bot.db.execute("UPDATE players SET nen_type = ?, spin_count = 1 WHERE user_id = ? AND guild_id = ?",
                             ("Mütehassıs", interaction.user.id, interaction.guild.id))
        await bot.db.commit()
        info = NEN_TYPES["Mütehassıs"]
        embed = discord.Embed(title="🎲 NEN TÜRÜ - BAŞARILI!", color=discord.Color.gold())
        embed.description = f"✨ **İnanılmaz! Şansın yaver gitti ve MÜTEHASSIS oldun!**\n\n**Nen Türü:** {info['emoji']} **MÜTEHASSIS**\n📊 **Nadirlik:** {info['rarity']}\n📜 {info['desc']}"
        await interaction.response.send_message(embed=embed)
    else:
        await bot.db.execute("UPDATE players SET spin_count = 1 WHERE user_id = ? AND guild_id = ?",
                             (interaction.user.id, interaction.guild.id))
        await bot.db.commit()
        embed = discord.Embed(title="🎲 NEN TÜRÜ - BAŞARISIZ", color=discord.Color.red())
        embed.description = "❌ **Maalesef şansın yaver gitmedi.**\nArtık `/nen-sec` komutu ile temel 5 Nen türünden dilediğini seçebilirsin."
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="nen-sec", description="İstediğin temel Nen türünü seç. (Sadece 1 kez)")
@app_commands.choices(nen_type=[
    app_commands.Choice(name="Geliştirme", value="Geliştirme"),
    app_commands.Choice(name="Dönüşüm", value="Dönüşüm"),
    app_commands.Choice(name="Emisyon", value="Emisyon"),
    app_commands.Choice(name="Çağırma", value="Çağırma"),
    app_commands.Choice(name="Manipülasyon", value="Manipülasyon")
])
async def nen_sec(interaction: discord.Interaction, nen_type: app_commands.Choice[str]):
    p = await get_player(interaction.user.id, interaction.guild.id)
    if p["nen_type"] != "Bilinmiyor":
        return await interaction.response.send_message(f"❌ Nen türün zaten **{p['nen_type']}** olarak belirlenmiş!", ephemeral=True)
    chosen = nen_type.value
    await bot.db.execute("UPDATE players SET nen_type = ? WHERE user_id = ? AND guild_id = ?",
                         (chosen, interaction.user.id, interaction.guild.id))
    await bot.db.commit()
    info = NEN_TYPES[chosen]
    embed = discord.Embed(title="✅ NEN TÜRÜ SEÇİLDİ", color=discord.Color.green())
    embed.description = f"✨ **Nen Türün:** {info['emoji']} **{chosen.upper()}** olarak ayarlandı!\n📜 {info['desc']}"
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="learn", description="Yeni bir Nen tekniği öğren.")
async def learn_technique(interaction: discord.Interaction, teknik: str):
    t_name = teknik.capitalize()
    if t_name not in TECHNIQUES:
        return await interaction.response.send_message(f"❌ Bilinmeyen teknik! Teknikler: {', '.join(TECHNIQUES.keys())}", ephemeral=True)
    p = await get_player(interaction.user.id, interaction.guild.id)
    techs = json.loads(p["techniques"])
    if t_name in techs:
        return await interaction.response.send_message("⚠️ Bu tekniği zaten biliyorsun.", ephemeral=True)
    techs.append(t_name)
    tech_levels = json.loads(p["technique_levels"]) if p.get("technique_levels") else {}
    tech_levels[t_name] = 0
    await bot.db.execute("UPDATE players SET techniques = ?, technique_levels = ? WHERE user_id = ? AND guild_id = ?",
                         (json.dumps(techs), json.dumps(tech_levels), interaction.user.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"🎉 **{t_name}** tekniğini öğrendin! `/teknik-dagit` ile puan verebilirsin.")

class TeknikModal(discord.ui.Modal, title='Teknik Puanı Dağıt'):
    amount = discord.ui.TextInput(label='Eklenecek Puan', style=discord.TextStyle.short, placeholder='Örn: 5', required=True)
    def __init__(self, teknik_adi, mevcut_puan):
        super().__init__()
        self.teknik_adi = teknik_adi
        self.mevcut_puan = mevcut_puan
    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message("❌ Geçersiz sayı.", ephemeral=True)
        if val <= 0:
            return await interaction.response.send_message("❌ 0'dan büyük bir değer gir.", ephemeral=True)
        p = await get_player(interaction.user.id, interaction.guild.id)
        teknik_puani = p.get("technique_points", 0)
        if val > teknik_puani:
            return await interaction.response.send_message(f"❌ Yetersiz teknik puanı! Mevcut: {teknik_puani}", ephemeral=True)
        techs = json.loads(p["techniques"])
        if self.teknik_adi not in techs:
            return await interaction.response.send_message("❌ Bu tekniği bilmiyorsun.", ephemeral=True)
        tech_levels = json.loads(p["technique_levels"]) if p.get("technique_levels") else {}
        tech_levels[self.teknik_adi] = tech_levels.get(self.teknik_adi, 0) + val
        await bot.db.execute(
            "UPDATE players SET technique_points = technique_points - ?, technique_levels = ? WHERE user_id = ? AND guild_id = ?",
            (val, json.dumps(tech_levels), interaction.user.id, interaction.guild.id)
        )
        await bot.db.commit()
        await interaction.response.send_message(
            f"✅ **{self.teknik_adi}** tekniğine `{val}` puan verildi! Yeni seviye: **{tech_levels[self.teknik_adi]}**",
            ephemeral=True
        )

class TeknikSelect(discord.ui.Select):
    def __init__(self, techs, tech_levels, mevcut_puan):
        self.mevcut_puan = mevcut_puan
        options = [
            discord.SelectOption(
                label=f"{t} [Mevcut: {tech_levels.get(t, 0)}]",
                value=t,
                description=TECHNIQUES[t]["desc"][:50] if t in TECHNIQUES else ""
            )
            for t in techs
        ]
        super().__init__(placeholder="Puan vermek istediğin tekniği seç...", options=options)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TeknikModal(self.values[0], self.mevcut_puan))

@bot.tree.command(name="teknik-dagit", description="Teknik puanlarını öğrendiğin tekniklere dağıt.")
async def teknik_dagit(interaction: discord.Interaction):
    p = await get_player(interaction.user.id, interaction.guild.id)
    teknik_puani = p.get("technique_points", 0)
    if teknik_puani <= 0:
        return await interaction.response.send_message(
            "❌ Dağıtılabilir teknik puanın yok!\n💡 **Nasıl kazanırsın?** Stat dağıtımında **Nen** statına puan ver → Her 1 Nen = 3 Teknik Puanı.",
            ephemeral=True
        )
    techs = json.loads(p["techniques"])
    if not techs:
        return await interaction.response.send_message("❌ Henüz hiç teknik öğrenmemişsin! Önce `/learn [teknik]` ile teknik öğren.", ephemeral=True)
    tech_levels = json.loads(p["technique_levels"]) if p.get("technique_levels") else {}
    view = discord.ui.View()
    view.add_item(TeknikSelect(techs, tech_levels, teknik_puani))
    await interaction.response.send_message(
        f"✨ **Mevcut Teknik Puanın:** `{teknik_puani}`\nHangi tekniği geliştirmek istiyorsun?",
        view=view, ephemeral=True
    )

@bot.tree.command(name="statcevir", description="XP'nizi stat puanına dönüştürür (100 XP = 1 Puan).")
async def statcevir(interaction: discord.Interaction, miktar: str):
    p = await get_player(interaction.user.id, interaction.guild.id)
    current_xp = p["current_xp"]
    xp_to_conv = current_xp if miktar.lower() == "hepsi" else float(miktar)
    if xp_to_conv > current_xp or xp_to_conv < 100:
        return await interaction.response.send_message(f"❌ Yetersiz XP! En az 100 XP çevirebilirsin. Mevcut: {int(current_xp)}", ephemeral=True)
    points = int(xp_to_conv // 100)
    deduct = points * 100
    await bot.db.execute("UPDATE players SET current_xp = current_xp - ?, unassigned_stats = unassigned_stats + ? WHERE user_id = ? AND guild_id = ?",
                         (deduct, points, interaction.user.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"🎉 `{deduct}` XP harcanarak **{points} Serbest Stat Puanı** kazanıldı.")

VALID_STATS = {
    "strength": "Güç",
    "speed": "Hız",
    "durability": "Dayanıklılık",
    "willpower": "Nen",
    "nen_amount": "Nen Havuzu",
    "nen_mastery": "Nen Hakimiyeti"
}

class StatModal(discord.ui.Modal, title='Stat Puanı Ekle'):
    amount = discord.ui.TextInput(label='Eklenecek Miktar', style=discord.TextStyle.short, placeholder='Örn: 3', required=True)
    def __init__(self, col, name, unassigned):
        super().__init__()
        self.col, self.name, self.unassigned = col, name, unassigned
    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.amount.value)
        except ValueError:
            return await interaction.response.send_message("❌ Geçersiz sayı.", ephemeral=True)
        if val <= 0 or val > self.unassigned:
            return await interaction.response.send_message("❌ Geçersiz miktar.", ephemeral=True)
        if self.col == "willpower":
            teknik_bonus = val * 3
            await bot.db.execute(
                f"UPDATE players SET {self.col} = {self.col} + ?, unassigned_stats = unassigned_stats - ?, technique_points = technique_points + ? WHERE user_id = ? AND guild_id = ?",
                (val, val, teknik_bonus, interaction.user.id, interaction.guild.id)
            )
            await bot.db.commit()
            await interaction.response.send_message(
                f"✅ **{self.name}** statına `{val}` puan eklendi.\n✨ Bonus: **{teknik_bonus} Teknik Puanı** kazandın!",
                ephemeral=True
            )
        else:
            await bot.db.execute(
                f"UPDATE players SET {self.col} = {self.col} + ?, unassigned_stats = unassigned_stats - ? WHERE user_id = ? AND guild_id = ?",
                (val, val, interaction.user.id, interaction.guild.id)
            )
            await bot.db.commit()
            await interaction.response.send_message(f"✅ **{self.name}** statına `{val}` puan eklendi.", ephemeral=True)

class StatSelect(discord.ui.Select):
    def __init__(self, unassigned):
        self.unassigned = unassigned
        options = []
        for k, v in VALID_STATS.items():
            desc = "Her 1 puan = 3 Teknik Puanı kazandırır!" if k == "willpower" else None
            options.append(discord.SelectOption(label=v, value=k, description=desc))
        super().__init__(placeholder="Geliştirmek istediğin statı seç...", options=options)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(StatModal(self.values[0], VALID_STATS[self.values[0]], self.unassigned))

@bot.tree.command(name="stat-dagit", description="Serbest puanlarınızı statlarınıza dağıtın.")
async def stat_dagit(interaction: discord.Interaction):
    p = await get_player(interaction.user.id, interaction.guild.id)
    if p["unassigned_stats"] <= 0:
        return await interaction.response.send_message("❌ Harcanabilir stat puanın yok.", ephemeral=True)
    await interaction.response.send_message(
        f"🌟 **Mevcut Serbest Puan:** `{p['unassigned_stats']}`\n💡 **Nen** statına puan verirsen her 1 Nen = 3 Teknik Puanı kazanırsın!",
        view=discord.ui.View().add_item(StatSelect(p["unassigned_stats"])),
        ephemeral=True
    )

@bot.tree.command(name="balance", description="Cüzdanınızdaki Jenny miktarını gösterir.")
async def balance(interaction: discord.Interaction):
    p = await get_player(interaction.user.id, interaction.guild.id)
    await interaction.response.send_message(f"💳 Cüzdanında **{p['money']} Jenny** var.")

@bot.tree.command(name="pay", description="Başka bir oyuncuya para gönder.")
async def pay(interaction: discord.Interaction, target: discord.Member, amount: int):
    if amount <= 0 or target == interaction.user:
        return await interaction.response.send_message("❌ Geçersiz işlem.", ephemeral=True)
    sender = await get_player(interaction.user.id, interaction.guild.id)
    if sender["money"] < amount:
        return await interaction.response.send_message("❌ Yetersiz bakiye!", ephemeral=True)
    await bot.db.execute("UPDATE players SET money = money - ? WHERE user_id = ? AND guild_id = ?", (amount, interaction.user.id, interaction.guild.id))
    await bot.db.execute("UPDATE players SET money = money + ? WHERE user_id = ? AND guild_id = ?", (amount, target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"💸 {target.mention} kişisine **{amount} Jenny** gönderildi.")

@bot.tree.command(name="leaderboard", description="Sunucu sıralamasını gösterir.")
async def leaderboard(interaction: discord.Interaction):
    async with bot.db.execute("SELECT user_id, current_xp FROM players WHERE guild_id = ? ORDER BY current_xp DESC LIMIT 10", (interaction.guild.id,)) as cursor:
        rows = await cursor.fetchall()
    desc = "\n".join([f"**{i}.** <@{r['user_id']}> - **XP:** {int(r['current_xp'])}" for i, r in enumerate(rows, 1)])
    await interaction.response.send_message(embed=discord.Embed(title="🏆 Hunter Sıralaması", description=desc or "Kimse yok.", color=discord.Color.gold()))

@bot.tree.command(name="snipe", description="İzinli kategorilerdeki son mesajları gösterir (Sadece sana).")
async def snipe(interaction: discord.Interaction, kullanici: discord.Member):
    allowed = await get_allowed_categories(interaction.guild.id)
    if not allowed:
        return await interaction.response.send_message("❌ Henüz izinli kategori ayarlanmamış.", ephemeral=True)
    mesajlar = snipe_cache[interaction.guild.id].get(kullanici.id, [])
    if not mesajlar:
        return await interaction.response.send_message(
            f"❌ **{kullanici.display_name}** adlı kullanıcının silinmiş/son mesajı bulunamadı.",
            ephemeral=True
        )
    embed = discord.Embed(title=f"🔍 {kullanici.display_name} — Son {len(mesajlar)} Mesaj", color=discord.Color.blurple())
    embed.set_thumbnail(url=kullanici.display_avatar.url)
    for i, msg in enumerate(reversed(mesajlar), 1):
        icerik = msg["content"]
        if len(icerik) > 200:
            icerik = icerik[:200] + "..."
        embed.add_field(name=f"#{i} — #{msg['channel_name']} ({msg['timestamp']})", value=f"```{icerik}```", inline=False)
    embed.set_footer(text="⚠️ Bu mesajlar sadece sana görünüyor.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="rol-ver")
@app_commands.default_permissions(administrator=True)
async def rol_ver(
    interaction: discord.Interaction,
    rol1: discord.Role,
    rol2: discord.Role = None,
    rol3: discord.Role = None,
    rol4: discord.Role = None,
    rol5: discord.Role = None,
    rol6: discord.Role = None,
    rol7: discord.Role = None,
    rol8: discord.Role = None,
    rol9: discord.Role = None,
    rol10: discord.Role = None
):
    secilen_roller = [r for r in [rol1, rol2, rol3, rol4, rol5, rol6, rol7, rol8, rol9, rol10] if r is not None]
    async with bot.db.execute("SELECT admin_roles FROM guild_settings WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
        row = await cursor.fetchone()
        mevcut = json.loads(row["admin_roles"]) if row and row["admin_roles"] else []
    eklenenler = []
    for r in secilen_roller:
        if r.id not in mevcut:
            mevcut.append(r.id)
            eklenenler.append(r.name)
    if not eklenenler:
        return await interaction.response.send_message("⚠️ Seçilen roller zaten ekli.", ephemeral=True)
    if row:
        await bot.db.execute("UPDATE guild_settings SET admin_roles = ? WHERE guild_id = ?", (json.dumps(mevcut), interaction.guild.id))
    else:
        await bot.db.execute("INSERT INTO guild_settings (guild_id, allowed_categories, admin_roles) VALUES (?, '[]', ?)", (interaction.guild.id, json.dumps(mevcut)))
    await bot.db.commit()
    await interaction.response.send_message(f"✅ Admin rolleri eklendi: **{', '.join(eklenenler)}**", ephemeral=True)

@bot.tree.command(name="kategori-ekle", description="[Yetkili] XP kazanılacak kategori ekler (10'a kadar).")
@app_commands.default_permissions(administrator=True)
async def kategori_ekle(
    interaction: discord.Interaction,
    kat1: discord.CategoryChannel,
    kat2: discord.CategoryChannel = None,
    kat3: discord.CategoryChannel = None,
    kat4: discord.CategoryChannel = None,
    kat5: discord.CategoryChannel = None,
    kat6: discord.CategoryChannel = None,
    kat7: discord.CategoryChannel = None,
    kat8: discord.CategoryChannel = None,
    kat9: discord.CategoryChannel = None,
    kat10: discord.CategoryChannel = None
):
    if not await is_admin(interaction):
        return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok.", ephemeral=True)
    secilenler = [k for k in [kat1, kat2, kat3, kat4, kat5, kat6, kat7, kat8, kat9, kat10] if k is not None]
    async with bot.db.execute("SELECT allowed_categories FROM guild_settings WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
        row = await cursor.fetchone()
        allowed = json.loads(row["allowed_categories"]) if row else []
    eklenenler = []
    for k in secilenler:
        if k.id not in allowed:
            allowed.append(k.id)
            eklenenler.append(k.name)
    if not eklenenler:
        return await interaction.response.send_message("⚠️ Seçilen kategoriler zaten ekli.", ephemeral=True)
    sql = "UPDATE guild_settings SET allowed_categories = ? WHERE guild_id = ?" if row else "INSERT INTO guild_settings (allowed_categories, guild_id) VALUES (?, ?)"
    await bot.db.execute(sql, (json.dumps(allowed), interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"✅ Başarıyla eklendi: **{', '.join(eklenenler)}**", ephemeral=True)

@bot.tree.command(name="kategori-cikar", description="[Yetkili] Kategorileri XP sisteminden çıkarır (10'a kadar).")
@app_commands.default_permissions(administrator=True)
async def kategori_cikar(
    interaction: discord.Interaction,
    kat1: discord.CategoryChannel,
    kat2: discord.CategoryChannel = None,
    kat3: discord.CategoryChannel = None,
    kat4: discord.CategoryChannel = None,
    kat5: discord.CategoryChannel = None,
    kat6: discord.CategoryChannel = None,
    kat7: discord.CategoryChannel = None,
    kat8: discord.CategoryChannel = None,
    kat9: discord.CategoryChannel = None,
    kat10: discord.CategoryChannel = None
):
    if not await is_admin(interaction):
        return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok.", ephemeral=True)
    secilenler = [k for k in [kat1, kat2, kat3, kat4, kat5, kat6, kat7, kat8, kat9, kat10] if k is not None]
    async with bot.db.execute("SELECT allowed_categories FROM guild_settings WHERE guild_id = ?", (interaction.guild.id,)) as cursor:
        row = await cursor.fetchone()
        allowed = json.loads(row["allowed_categories"]) if row else []
    cikarilanlar = []
    for k in secilenler:
        if k.id in allowed:
            allowed.remove(k.id)
            cikarilanlar.append(k.name)
    if not cikarilanlar:
        return await interaction.response.send_message("❌ Seçilen kategoriler listede yok.", ephemeral=True)
    await bot.db.execute("UPDATE guild_settings SET allowed_categories = ? WHERE guild_id = ?", (json.dumps(allowed), interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"🗑️ Çıkarıldı: **{', '.join(cikarilanlar)}**", ephemeral=True)

@bot.tree.command(name="karakter-olustur", description="[Yetkili] Kullanıcıya profil tanımlar. (15.000 Jenny başlangıç)")
@app_commands.default_permissions(administrator=True)
async def karakter_olustur(interaction: discord.Interaction, kullanici: discord.Member, isim: str, boy: str, kilo: str, cinsiyet: str):
    if not await is_admin(interaction):
        return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok.", ephemeral=True)
    await bot.db.execute(
        "UPDATE players SET character_name = ?, height = ?, weight = ?, gender = ?, money = 15000 WHERE user_id = ? AND guild_id = ?",
        (isim, boy, kilo, cinsiyet, kullanici.id, interaction.guild.id)
    )
    await bot.db.commit()
    await interaction.response.send_message(f"✅ {kullanici.mention} için **{isim}** karakteri kaydedildi. 💰 Başlangıç: **15.000 Jenny**")

@bot.tree.command(name="karakter-duzenle", description="[Yetkili] Karakter bilgilerini günceller.")
@app_commands.choices(alan=[
    app_commands.Choice(name="İsim", value="character_name"),
    app_commands.Choice(name="Boy", value="height"),
    app_commands.Choice(name="Kilo", value="weight"),
    app_commands.Choice(name="Cinsiyet", value="gender")
])
@app_commands.default_permissions(administrator=True)
async def karakter_duzenle(interaction: discord.Interaction, kullanici: discord.Member, alan: app_commands.Choice[str], yeni_deger: str):
    if not await is_admin(interaction):
        return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok.", ephemeral=True)
    await bot.db.execute(f"UPDATE players SET {alan.value} = ? WHERE user_id = ? AND guild_id = ?", (yeni_deger, kullanici.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"✅ Güncellendi.", ephemeral=True)

@bot.tree.command(name="stat-ayarla", description="[Yetkili] Stat değerini doğrudan ayarlar.")
@app_commands.choices(stat=[
    app_commands.Choice(name="Güç", value="strength"),
    app_commands.Choice(name="Hız", value="speed"),
    app_commands.Choice(name="Dayanıklılık", value="durability"),
    app_commands.Choice(name="Nen", value="willpower"),
    app_commands.Choice(name="Nen Havuzu", value="nen_amount"),
    app_commands.Choice(name="Nen Hakimiyeti", value="nen_mastery"),
    app_commands.Choice(name="Boş Stat Puanı", value="unassigned_stats")
])
@app_commands.default_permissions(administrator=True)
async def stat_ayarla(interaction: discord.Interaction, kullanici: discord.Member, stat: app_commands.Choice[str], yeni_deger: int):
    if not await is_admin(interaction):
        return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok.", ephemeral=True)
    await bot.db.execute(f"UPDATE players SET {stat.value} = ? WHERE user_id = ? AND guild_id = ?", (yeni_deger, kullanici.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"✅ {stat.name} değeri `{yeni_deger}` yapıldı.", ephemeral=True)

admin_group = app_commands.Group(name="admin", description="Game Master Komutları")

@admin_group.command(name="xp-give", description="Oyuncuya XP ekler.")
@app_commands.default_permissions(administrator=True)
async def admin_xp_give(interaction: discord.Interaction, target: discord.Member, amount: float):
    if not await is_admin(interaction):
        return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok.", ephemeral=True)
    await bot.db.execute("UPDATE players SET current_xp = current_xp + ?, total_earned_xp = total_earned_xp + ? WHERE user_id = ? AND guild_id = ?",
                         (amount, amount, target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"✅ {target.mention} kişisine `{amount}` XP verildi.", ephemeral=True)

@admin_group.command(name="nen-sifirla", description="Oyuncunun Nen türünü ve çevirme hakkını sıfırlar.")
@app_commands.default_permissions(administrator=True)
async def admin_nen_sifirla(interaction: discord.Interaction, target: discord.Member):
    if not await is_admin(interaction):
        return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok.", ephemeral=True)
    await bot.db.execute("UPDATE players SET spin_count = 0, nen_type = 'Bilinmiyor' WHERE user_id = ? AND guild_id = ?", (target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"🔄 {target.mention} kişisinin Nen Türü sıfırlandı.", ephemeral=True)

@admin_group.command(name="profil-sifirla", description="Oyuncunun profilini tamamen siler.")
@app_commands.default_permissions(administrator=True)
async def admin_profil_sifirla(interaction: discord.Interaction, target: discord.Member):
    if not await is_admin(interaction):
        return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok.", ephemeral=True)
    await bot.db.execute("DELETE FROM players WHERE user_id = ? AND guild_id = ?", (target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"💥 {target.mention} kişisinin profili tamamen silindi.", ephemeral=True)

@admin_group.command(name="nen-set", description="Nen türünü manuel seçer.")
@app_commands.choices(nen_type=[app_commands.Choice(name=t, value=t) for t in NEN_TYPES.keys()])
@app_commands.default_permissions(administrator=True)
async def admin_nen_set(interaction: discord.Interaction, target: discord.Member, nen_type: app_commands.Choice[str]):
    if not await is_admin(interaction):
        return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok.", ephemeral=True)
    await bot.db.execute("UPDATE players SET nen_type = ?, spin_count = 1 WHERE user_id = ? AND guild_id = ?", (nen_type.value, target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"⚙️ {target.mention} Nen türü **{nen_type.value}** yapıldı.", ephemeral=True)

@admin_group.command(name="mastery-set", description="Mastery puanını ayarlar.")
@app_commands.default_permissions(administrator=True)
async def admin_mastery_set(interaction: discord.Interaction, target: discord.Member, amount: int):
    if not await is_admin(interaction):
        return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok.", ephemeral=True)
    await bot.db.execute("UPDATE players SET mastery = ? WHERE user_id = ? AND guild_id = ?", (amount, target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"✅ Ustalık puanı `{amount}` yapıldı.", ephemeral=True)

@admin_group.command(name="teknik-puan-set", description="Teknik puanını manuel ayarlar.")
@app_commands.default_permissions(administrator=True)
async def admin_teknik_puan_set(interaction: discord.Interaction, target: discord.Member, amount: int):
    if not await is_admin(interaction):
        return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok.", ephemeral=True)
    await bot.db.execute("UPDATE players SET technique_points = ? WHERE user_id = ? AND guild_id = ?", (amount, target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"✅ {target.mention} teknik puanı `{amount}` yapıldı.", ephemeral=True)

@admin_group.command(name="money-give", description="Para ekler.")
@app_commands.default_permissions(administrator=True)
async def admin_money_give(interaction: discord.Interaction, target: discord.Member, amount: int):
    if not await is_admin(interaction):
        return await interaction.response.send_message("❌ Bu komutu kullanma yetkin yok.", ephemeral=True)
    await bot.db.execute("UPDATE players SET money = money + ? WHERE user_id = ? AND guild_id = ?", (amount, target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"💰 `{amount}` Jenny eklendi.", ephemeral=True)

bot.tree.add_command(admin_group)

bot.run(os.getenv("TOKEN"))
