import sqlite3
import os
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ContextTypes,
    filters,
)

TOKEN = os.getenv("TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))
OWNER_ID = int(os.getenv("OWNER_ID"))

conn = sqlite3.connect("actividad.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS mensajes (
user_id INTEGER,
timestamp DATETIME
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
user_id INTEGER PRIMARY KEY,
join_date DATETIME
)
""")

conn.commit()


def es_dueno(update: Update):
    return update.effective_user.id == OWNER_ID


async def registrar_usuario(update: Update, context: ContextTypes.DEFAULT_TYPE):

    for member in update.message.new_chat_members:

        if member.is_bot:
            continue

        cursor.execute(
            "INSERT OR IGNORE INTO usuarios VALUES (?, ?)",
            (member.id, datetime.utcnow())
        )

    conn.commit()


async def registrar_mensaje(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    if user.is_bot:
        return

    cursor.execute(
        "INSERT OR IGNORE INTO usuarios VALUES (?, ?)",
        (user.id, datetime.utcnow())
    )

    cursor.execute(
        "INSERT INTO mensajes VALUES (?, ?)",
        (user.id, datetime.utcnow())
    )

    conn.commit()


async def revisar_actividad(context: ContextTypes.DEFAULT_TYPE):

    limite = datetime.utcnow() - timedelta(days=4)

    cursor.execute("""
    SELECT user_id, COUNT(*)
    FROM mensajes
    WHERE timestamp > ?
    GROUP BY user_id
    """, (limite,))

    actividad = {row[0]: row[1] for row in cursor.fetchall()}

    admins = await context.bot.get_chat_administrators(CHAT_ID)
    admin_ids = [a.user.id for a in admins]

    cursor.execute("SELECT user_id, join_date FROM usuarios")
    usuarios = cursor.fetchall()

    for user_id, join_date in usuarios:

        join_date = datetime.fromisoformat(join_date)

        if user_id in admin_ids:
            continue

        if datetime.utcnow() - join_date < timedelta(days=4):
            continue

        mensajes = actividad.get(user_id, 0)

        if mensajes < 15:

            try:

                member = await context.bot.get_chat_member(CHAT_ID, user_id)
                nombre = member.user.full_name

                await context.bot.ban_chat_member(CHAT_ID, user_id)

                await context.bot.send_message(
                    CHAT_ID,
                    f"🚫 {nombre} fue expulsado por inactividad."
                )

            except:
                pass

    cursor.execute(
        "DELETE FROM mensajes WHERE timestamp < ?",
        (limite,)
    )

    conn.commit()


async def forzar_revision(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not es_dueno(update):
        return

    await revisar_actividad(context)

    await update.message.reply_text("Revisión ejecutada.")


async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):

    limite = datetime.utcnow() - timedelta(days=4)

    cursor.execute("""
    SELECT user_id, COUNT(*)
    FROM mensajes
    WHERE timestamp > ?
    GROUP BY user_id
    ORDER BY COUNT(*) DESC
    LIMIT 10
    """, (limite,))

    resultados = cursor.fetchall()

    texto = "🔥 Usuarios más activos:\n\n"

    for user_id, mensajes in resultados:

        try:
            member = await context.bot.get_chat_member(CHAT_ID, user_id)
            nombre = member.user.full_name
        except:
            nombre = str(user_id)

        texto += f"{nombre} — {mensajes} mensajes\n"

    await update.message.reply_text(texto)


async def inactivos(update: Update, context: ContextTypes.DEFAULT_TYPE):

    limite = datetime.utcnow() - timedelta(days=4)

    cursor.execute("""
    SELECT user_id, COUNT(*)
    FROM mensajes
    WHERE timestamp > ?
    GROUP BY user_id
    """, (limite,))

    actividad = {row[0]: row[1] for row in cursor.fetchall()}

    cursor.execute("SELECT user_id FROM usuarios")
    usuarios = cursor.fetchall()

    texto = "⚠️ Usuarios en riesgo de expulsión:\n\n"

    for (user_id,) in usuarios:

        mensajes = actividad.get(user_id, 0)

        if mensajes < 15:

            try:
                member = await context.bot.get_chat_member(CHAT_ID, user_id)
                nombre = member.user.full_name
            except:
                nombre = str(user_id)

            texto += f"{nombre} — {mensajes} mensajes\n"

    await update.message.reply_text(texto)


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    cursor.execute("SELECT COUNT(*) FROM usuarios")
    total_usuarios = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM mensajes")
    total_mensajes = cursor.fetchone()[0]

    texto = f"""
📊 Estadísticas del grupo

Usuarios registrados: {total_usuarios}
Mensajes registrados: {total_mensajes}
"""

    await update.message.reply_text(texto)


def main():

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, registrar_mensaje)
    )

    app.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, registrar_usuario)
    )

    app.add_handler(CommandHandler("forzar_revision", forzar_revision))
    app.add_handler(CommandHandler("top", top))
    app.add_handler(CommandHandler("inactivos", inactivos))
    app.add_handler(CommandHandler("stats", stats))

    app.job_queue.run_repeating(
        revisar_actividad,
        interval=86400,
        first=60
    )

    app.run_polling()


if __name__ == "__main__":
    main()
