import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import json
import random
from collections import defaultdict

# Veritabanı adı güncellendi (Eski ayarların çakışmaması için v2 yapıldı)
DB_PATH = "destiny_hxh.db"

# Nen Türleri ve İhtimalleri (Türkçeleştirildi ve nadirlik eklendi)
NEN_TYPES = {
    "Geliştirme": {"emoji": "🥊", "desc": "Fiziksel güç ve iyileşme kapasitesini zirveye taşır.", "rarity": "Yaygın"},
    "Dönüşüm": {"emoji": "⚡", "desc": "Auranın özelliklerini başka maddelere benzeterek değiştirir.", "rarity": "Yaygın"},
    "Emisyon": {"emoji": "💥", "desc": "Aura'yı vücuttan ayırıp uzak mesafelerde kullanma.", "rarity": "Yaygın"},
    "Çağırma": {"emoji": "⛓️", "desc": "Aura kullanarak fiziksel, bağımsız nesneler yaratır.", "rarity": "Yaygın"},
    "Manipülasyon": {"emoji": "🎭", "desc": "Canlıları veya nesneleri aura ile kontrol etme.", "rarity": "Yaygın"},
    "Mütehassıs": {"emoji": "🔮", "desc": "Diğer beş kategoriye girmeyen en nadir ve benzersiz yetenek.", "rarity": "Efsanevi"}
}

# Öğrenilebilir Teknikler (Seviye kaldırıldığı için req_level yerine req_mastery'e odaklanıldı)
TECHNIQUES = {
    "Ten": {"req_mastery": 0, "desc": "Auranın bedeni sarması."},
    "Zetsu": {"req_mastery": 5, "desc": "Aurayı tamamen gizleme."},
    "Ren": {"req_mastery": 10, "desc": "Büyük miktarda aura üretme."},
    "Hatsu": {"req_mastery": 25, "desc": "Kişisel Nen yeteneğini dışa vurma."},
    "Gyo": {"req_mastery": 40, "desc": "Aurayı gözlerde toplayarak gizli nesneleri görme."},
    "In": {"req_mastery": 60, "desc": "Kendi auranı görünmez yapma."},
    "En": {"req_mastery": 100, "desc": "Aura alanını genişleterek bölgeyi hissetme."},
    "Shu": {"req_mastery": 80, "desc": "Aurayı nesneye aktarma."},
    "Ko": {"req_mastery": 120, "desc": "Tüm aurayı tek noktaya odaklama."},
    "Ken": {"req_mastery": 150, "desc": "Vücudu Ren seviyesinde koruma."},
    "Ryu": {"req_mastery": 200, "desc": "Aura akışını anlık yönlendirme."}
}

# Snipe cache: {guild_id: {user_id: [mesaj_dict, ...]}}
# Her kullanıcı için son 5 mesaj tutulur
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
            allowed_categories TEXT
        )''')
        await self.db.execute('''CREATE TABLE IF NOT EXISTS players (
            user_id INTEGER,
            guild_id INTEGER,
            current_xp REAL DEFAULT 0,
            total_earned_xp REAL DEFAULT 0,
            money INTEGER DEFAULT 0,
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
            PRIMARY KEY (user_id, guild_id)
        )''')
        await self.db.commit()

    async def close(self):
        if self.db:
            await self.db.close()
        await super().close()

bot = HxHBot()

# --- YARDIMCI FONKSİYONLAR ---
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

# --- MESAJ VE XP MOTORU ---
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not message.guild:
        return

    # SNİPE CACHE — XP koşullarından bağımsız, tüm mesajları yakala
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

    # XP — sadece 10+ karakter olan mesajlar
    if len(message.content) < 10 or not message.channel.category_id:
        return

    allowed = await get_allowed_categories(message.guild.id)
    if not allowed or message.channel.category_id not in allowed:
        return

    xp_gained = len(message.content) * 0.05
    await bot.db.execute('''UPDATE players 
                            SET current_xp = current_xp + ?, total_earned_xp = total_earned_xp + ?
                            WHERE user_id = ? AND guild_id = ?''',
                            (xp_gained, xp_gained, message.author.id, message.guild.id))
    await bot.db.commit()

# --- BİLGİ / REHBER ---
@bot.tree.command(name="bilgi", description="Botun tüm komutlarını ve sistem rehberini gösterir.")
async def bilgi(interaction: discord.Interaction):
    embed = discord.Embed(title="📖 Destiny HxH - Ultimate Sistem Rehberi", color=discord.Color.gold())
    embed.add_field(name="👤 OYUNCU KOMUTLARI", value=(
        "**`/profil [kullanici]`** ➔ Karakter kartınızı, statları, XP ve Nen durumunu gösterir.\n"
        "**`/nen-spin`** ➔ %5 Şansla Mütehassıs olmaya çalış (Sadece 1 Hak).\n"
        "**`/nen-sec`** ➔ İstediğin yaygın Nen türünü (Geliştirme, Dönüşüm vb.) seçmeni sağlar.\n"
        "**`/learn [teknik]`** ➔ Şartları karşılıyorsanız yeni Nen tekniği öğrenir.\n"
        "**`/statcevir [miktar/hepsi]`** ➔ XP'yi harcanabilir stat puanına dönüştürür (100 XP = 1 Puan).\n"
        "**`/stat-dagit`** ➔ Serbest stat puanlarını yeteneklere dağıtır.\n"
        "**`/balance`** ➔ Cüzdanınızdaki parayı (Jenny) gösterir.\n"
        "**`/pay [@oyuncu] [miktar]`** ➔ Başka oyuncuya para gönderir.\n"
        "**`/leaderboard`** ➔ En güçlü Hunter'ları listeler.\n"
        "**`/snipe [@kullanici]`** ➔ Kullanıcının izinli kategorilerdeki son 5 mesajını gösterir (Sadece sana)."
    ), inline=False)
    embed.add_field(name="🛡️ YETKİLİ KOMUTLARI (Admin)", value=(
        "**`/kategori-ekle`** ➔ Tek komutta 10'a kadar kategori eklemenizi sağlar.\n"
        "**`/kategori-cikar`** ➔ 10'a kadar kategoriyi sistemden çıkarır.\n"
        "**`/karakter-olustur`** ➔ Oyuncuya profil açar.\n"
        "**`/karakter-duzenle`** ➔ İsim, Boy, Kilo, Cinsiyet değiştirir.\n"
        "**`/stat-ayarla`** ➔ Statları doğrudan düzenler.\n"
        "**`/admin nen-sifirla`** ➔ Oyuncunun Nen türünü ve çevirme hakkını sıfırlar.\n"
        "**`/admin profil-sifirla`** ➔ Oyuncunun profilini ve tüm verilerini tamamen siler.\n"
        "**`/admin xp-give / remove`** ➔ XP yönetimi yapar.\n"
        "**`/admin nen-set`** ➔ Nen türünü manuel seçer.\n"
        "**`/admin mastery-set`** ➔ Ustalık puanı ayarlar.\n"
        "**`/admin money-give`** ➔ Para ödülü verir."
    ), inline=False)
    await interaction.response.send_message(embed=embed)

# --- OYUNCU KOMUTLARI ---
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

    embed = discord.Embed(color=discord.Color.dark_purple())
    desc = f"""```text
╔══════════════════════════════════════════════════════════════╗
              ✦ DESTINY HxH | PROFİL: {p["character_name"]} ✦
   Discord: @{target.display_name} | Unvan: {unvan}
╠══════════════════════════════════════════════════════════════╣
 📜 KİMLİK & NEN
 • Cinsiyet / Boy / Kilo: {p["gender"]} | {p["height"]} / {p["weight"]}
 • Nen Türü: {nen_info['emoji']} {p["nen_type"]} (Çevirme Hakkı: {1 - p["spin_count"]})
 • Mastery (Ustalık): {p["mastery"]} | Bakiye: {p["money"]} Jenny
 • Boştaki Stat Puanı: 🌟 {p["unassigned_stats"]} Puan

 ⚔️ FİZİKSEL STATLAR
 • 🥊 Güç:          [{p["strength"]:<3}]  {get_progress_bar(p["strength"])}
 • ⚡ Hız:          [{p["speed"]:<3}]  {get_progress_bar(p["speed"])}
 • 🛡️ Dayanıklılık: [{p["durability"]:<3}]  {get_progress_bar(p["durability"])}

 🧠 AKLİ & NEN STATLARI
 • 👁️ Nen:          [{p["willpower"]:<3}]  {get_progress_bar(p["willpower"])}
 • 🌊 Nen Miktarı:     [{p["nen_amount"]:<3}]  {get_progress_bar(p["nen_amount"])}
 • 🌀 Nen Hakimiyeti:  [{p["nen_mastery"]:<3}]  {get_progress_bar(p["nen_mastery"])}
╠══════════════════════════════════════════════════════════════╣
 📊 MEVCUT XP: {int(p["current_xp"])} XP (Toplam Kasılmış: {int(p["total_earned_xp"])})
 📜 TEKNİKLER: {', '.join(techs) if techs else 'Henüz yok'}
╚══════════════════════════════════════════════════════════════╝
```"""
    embed.description = desc
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="nen-spin", description="Sadece %5 şansla Mütehassıs olmak için şansını dene. (1 Hak)")
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
        embed = discord.Embed(title="🎲 NEN TYPE SPIN - BAŞARILI!", color=discord.Color.gold())
        embed.description = f"✨ **İnanılmaz! %5 şansı tutturdun ve MÜTEHASSIS oldun!**\n**Nen Türü:** {info['emoji']} **MÜTEHASSIS**\n📊 **Nadirlik:** {info['rarity']}\n📜 {info['desc']}"
        await interaction.response.send_message(embed=embed)
    else:
        await bot.db.execute("UPDATE players SET spin_count = 1 WHERE user_id = ? AND guild_id = ?",
                             (interaction.user.id, interaction.guild.id))
        await bot.db.commit()

        embed = discord.Embed(title="🎲 NEN TYPE SPIN - BAŞARISIZ", color=discord.Color.red())
        embed.description = "❌ **Maalesef %5 şansı tutturamadın ve Mütehassıs olamadın...**\nAncak üzülme! Artık `/nen-sec` komutunu kullanarak temel 5 Nen türünden (Geliştirme, Dönüşüm vb.) dilediğini seçebilirsin."
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="nen-sec", description="İstediğin temel Nen türünü seç. (Sadece 1 kez seçilebilir)")
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
        return await interaction.response.send_message(f"❌ Nen türün zaten **{p['nen_type']}** olarak belirlenmiş! Daha fazla değiştiremezsin.", ephemeral=True)

    chosen = nen_type.value
    await bot.db.execute("UPDATE players SET nen_type = ? WHERE user_id = ? AND guild_id = ?",
                         (chosen, interaction.user.id, interaction.guild.id))
    await bot.db.commit()

    info = NEN_TYPES[chosen]
    embed = discord.Embed(title="✅ NEN TÜRÜ SEÇİLDİ", color=discord.Color.green())
    embed.description = f"✨ **Nen Türün:** {info['emoji']} **{chosen.upper()}** olarak ayarlandı!\n📜 {info['desc']}"
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="learn", description="Şartları karşılıyorsanız yeni bir Nen tekniği öğrenin.")
async def learn_technique(interaction: discord.Interaction, teknik: str):
    t_name = teknik.capitalize()
    if t_name not in TECHNIQUES:
        return await interaction.response.send_message(f"❌ Bilinmeyen teknik! Teknikler: {', '.join(TECHNIQUES.keys())}", ephemeral=True)

    p = await get_player(interaction.user.id, interaction.guild.id)
    mastery, techs = p["mastery"], json.loads(p["techniques"])
    reqs = TECHNIQUES[t_name]

    if t_name in techs:
        return await interaction.response.send_message("⚠️ Bu tekniği zaten biliyorsun.", ephemeral=True)
    if mastery < reqs["req_mastery"]:
        return await interaction.response.send_message(f"❌ Şartlar sağlanmıyor! Gereken Mastery: {reqs['req_mastery']}", ephemeral=True)

    techs.append(t_name)
    await bot.db.execute("UPDATE players SET techniques = ? WHERE user_id = ? AND guild_id = ?", (json.dumps(techs), interaction.user.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"🎉 Tebrikler! **{t_name}** tekniğinde ustalaştın!")

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

# İnteraktif Stat Dağıtımı
VALID_STATS = {"strength": "Güç", "speed": "Hız", "durability": "Dayanıklılık", "willpower": "Nen", "nen_amount": "Nen Miktarı", "nen_mastery": "Nen Hakimiyeti"}

class StatModal(discord.ui.Modal, title='Stat Puanı Ekle'):
    amount = discord.ui.TextInput(label='Eklenecek Miktar', style=discord.TextStyle.short, placeholder='Örn: 3', required=True)
    def __init__(self, col, name, unassigned):
        super().__init__()
        self.col, self.name, self.unassigned = col, name, unassigned

    async def on_submit(self, interaction: discord.Interaction):
        val = int(self.amount.value)
        if val <= 0 or val > self.unassigned:
            return await interaction.response.send_message("❌ Geçersiz miktar.", ephemeral=True)
        await bot.db.execute(f"UPDATE players SET {self.col} = {self.col} + ?, unassigned_stats = unassigned_stats - ? WHERE user_id = ? AND guild_id = ?",
                             (val, val, interaction.user.id, interaction.guild.id))
        await bot.db.commit()
        await interaction.response.send_message(f"✅ **{self.name}** statına `{val}` puan eklendi.", ephemeral=True)

class StatSelect(discord.ui.Select):
    def __init__(self, unassigned):
        self.unassigned = unassigned
        super().__init__(placeholder="Geliştirmek istediğin statı seç...", options=[discord.SelectOption(label=v, value=k) for k, v in VALID_STATS.items()])
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(StatModal(self.values[0], VALID_STATS[self.values[0]], self.unassigned))

@bot.tree.command(name="stat-dagit", description="Serbest puanlarınızı statlarınıza dağıtın.")
async def stat_dagit(interaction: discord.Interaction):
    p = await get_player(interaction.user.id, interaction.guild.id)
    if p["unassigned_stats"] <= 0: return await interaction.response.send_message("❌ Harcanabilir stat puanın yok.", ephemeral=True)
    await interaction.response.send_message(f"🌟 **Mevcut Serbest Puan:** `{p['unassigned_stats']}`", view=discord.ui.View().add_item(StatSelect(p["unassigned_stats"])), ephemeral=True)

@bot.tree.command(name="balance", description="Cüzdanınızdaki Jenny miktarını gösterir.")
async def balance(interaction: discord.Interaction):
    p = await get_player(interaction.user.id, interaction.guild.id)
    await interaction.response.send_message(f"💳 Cüzdanında **{p['money']} Jenny** var.")

@bot.tree.command(name="pay", description="Başka bir oyuncuya para gönder.")
async def pay(interaction: discord.Interaction, target: discord.Member, amount: int):
    if amount <= 0 or target == interaction.user: return await interaction.response.send_message("❌ Geçersiz işlem.", ephemeral=True)
    sender = await get_player(interaction.user.id, interaction.guild.id)
    if sender["money"] < amount: return await interaction.response.send_message("❌ Yetersiz bakiye!", ephemeral=True)
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

# --- SNİPE KOMUTU ---
@bot.tree.command(name="snipe", description="Kullanıcının izinli kategorilerdeki son 5 mesajını gösterir (Sadece sana).")
async def snipe(interaction: discord.Interaction, kullanici: discord.Member):
    allowed = await get_allowed_categories(interaction.guild.id)
    if not allowed:
        return await interaction.response.send_message("❌ Henüz izinli kategori ayarlanmamış.", ephemeral=True)

    mesajlar = snipe_cache[interaction.guild.id].get(kullanici.id, [])

    if not mesajlar:
        return await interaction.response.send_message(
            f"❌ **{kullanici.display_name}** adlı kullanıcının bot açık olduğundan beri izinli kategorilerde attığı mesaj bulunamadı.",
            ephemeral=True
        )

    embed = discord.Embed(
        title=f"🔍 {kullanici.display_name} — Son {len(mesajlar)} Mesaj",
        color=discord.Color.blurple()
    )
    embed.set_thumbnail(url=kullanici.display_avatar.url)

    # En yeniden en eskiye göster
    for i, msg in enumerate(reversed(mesajlar), 1):
        icerik = msg["content"]
        if len(icerik) > 200:
            icerik = icerik[:200] + "..."
        embed.add_field(
            name=f"#{i} — #{msg['channel_name']} ({msg['timestamp']})",
            value=f"```{icerik}```",
            inline=False
        )

    embed.set_footer(text="⚠️ Bu mesajlar sadece sana görünüyor.")
    await interaction.response.send_message(embed=embed, ephemeral=True)

# --- YETKİLİ & ADMIN KOMUTLARI ---

# Kategori ekle — 10 kategori
@bot.tree.command(name="kategori-ekle", description="[Yetkili] XP kazanılacak çoklu kategori ekler (10'a kadar).")
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

# Kategori çıkar — 10 kategori
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

@bot.tree.command(name="karakter-olustur", description="[Yetkili] Kullanıcıya profil tanımlar.")
@app_commands.default_permissions(administrator=True)
async def karakter_olustur(interaction: discord.Interaction, kullanici: discord.Member, isim: str, boy: str, kilo: str, cinsiyet: str):
    await bot.db.execute("UPDATE players SET character_name = ?, height = ?, weight = ?, gender = ? WHERE user_id = ? AND guild_id = ?",
                         (isim, boy, kilo, cinsiyet, kullanici.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"✅ {kullanici.mention} için **{isim}** karakteri kaydedildi.")

@bot.tree.command(name="karakter-duzenle", description="[Yetkili] Karakter bilgilerini günceller.")
@app_commands.choices(alan=[app_commands.Choice(name="İsim", value="character_name"), app_commands.Choice(name="Boy", value="height"), app_commands.Choice(name="Kilo", value="weight"), app_commands.Choice(name="Cinsiyet", value="gender")])
@app_commands.default_permissions(administrator=True)
async def karakter_duzenle(interaction: discord.Interaction, kullanici: discord.Member, alan: app_commands.Choice[str], yeni_deger: str):
    await bot.db.execute(f"UPDATE players SET {alan.value} = ? WHERE user_id = ? AND guild_id = ?", (yeni_deger, kullanici.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"✅ Güncellendi.", ephemeral=True)

@bot.tree.command(name="stat-ayarla", description="[Yetkili] Stat değerini doğrudan ayarlar.")
@app_commands.choices(stat=[app_commands.Choice(name="Güç", value="strength"), app_commands.Choice(name="Hız", value="speed"), app_commands.Choice(name="Dayanıklılık", value="durability"), app_commands.Choice(name="Nen", value="willpower"), app_commands.Choice(name="Nen Miktarı", value="nen_amount"), app_commands.Choice(name="Nen Hakimiyeti", value="nen_mastery"), app_commands.Choice(name="Boş Stat Puanı", value="unassigned_stats")])
@app_commands.default_permissions(administrator=True)
async def stat_ayarla(interaction: discord.Interaction, kullanici: discord.Member, stat: app_commands.Choice[str], yeni_deger: int):
    await bot.db.execute(f"UPDATE players SET {stat.value} = ? WHERE user_id = ? AND guild_id = ?", (yeni_deger, kullanici.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"✅ {stat.name} değeri `{yeni_deger}` yapıldı.", ephemeral=True)

admin_group = app_commands.Group(name="admin", description="Game Master Komutları")

@admin_group.command(name="xp-give", description="Oyuncuya XP ekler.")
@app_commands.default_permissions(administrator=True)
async def admin_xp_give(interaction: discord.Interaction, target: discord.Member, amount: float):
    await bot.db.execute("UPDATE players SET current_xp = current_xp + ?, total_earned_xp = total_earned_xp + ? WHERE user_id = ? AND guild_id = ?", (amount, amount, target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"✅ {target.mention} kişisine `{amount}` XP verildi.", ephemeral=True)

@admin_group.command(name="nen-sifirla", description="Oyuncunun Nen türünü ve çevirme hakkını sıfırlar.")
@app_commands.default_permissions(administrator=True)
async def admin_nen_sifirla(interaction: discord.Interaction, target: discord.Member):
    await bot.db.execute("UPDATE players SET spin_count = 0, nen_type = 'Bilinmiyor' WHERE user_id = ? AND guild_id = ?", (target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"🔄 {target.mention} kişisinin Nen Türü ve Çevirme Hakkı tamamen sıfırlandı.", ephemeral=True)

@admin_group.command(name="profil-sifirla", description="Oyuncunun profilini ve tüm verilerini tamamen siler.")
@app_commands.default_permissions(administrator=True)
async def admin_profil_sifirla(interaction: discord.Interaction, target: discord.Member):
    await bot.db.execute("DELETE FROM players WHERE user_id = ? AND guild_id = ?", (target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"💥 {target.mention} kişisinin profili ve tüm verileri tamamen silindi (Sıfırlandı).", ephemeral=True)

@admin_group.command(name="nen-set", description="Nen türünü manuel seçer.")
@app_commands.choices(nen_type=[app_commands.Choice(name=t, value=t) for t in NEN_TYPES.keys()])
@app_commands.default_permissions(administrator=True)
async def admin_nen_set(interaction: discord.Interaction, target: discord.Member, nen_type: app_commands.Choice[str]):
    await bot.db.execute("UPDATE players SET nen_type = ?, spin_count = 1 WHERE user_id = ? AND guild_id = ?", (nen_type.value, target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"⚙️ {target.mention} Nen türü **{nen_type.value}** yapıldı.", ephemeral=True)

@admin_group.command(name="mastery-set", description="Mastery puanını ayarlar.")
@app_commands.default_permissions(administrator=True)
async def admin_mastery_set(interaction: discord.Interaction, target: discord.Member, amount: int):
    await bot.db.execute("UPDATE players SET mastery = ? WHERE user_id = ? AND guild_id = ?", (amount, target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"✅ Ustalık puanı `{amount}` yapıldı.", ephemeral=True)

@admin_group.command(name="money-give", description="Para ekler.")
@app_commands.default_permissions(administrator=True)
async def admin_money_give(interaction: discord.Interaction, target: discord.Member, amount: int):
    await bot.db.execute("UPDATE players SET money = money + ? WHERE user_id = ? AND guild_id = ?", (amount, target.id, interaction.guild.id))
    await bot.db.commit()
    await interaction.response.send_message(f"💰 `{amount}` Jenny eklendi.", ephemeral=True)

bot.tree.add_command(admin_group)

bot.run("MTUzOTk5MzQ3MTIyMDE5MTI1Mw.Ge7CGp.CFKKT39hotgwb8yvg2sbIWKq8iL6VsrqiY5DUs")