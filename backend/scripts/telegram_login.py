"""One-time sign-in for the payment listener account. Run it on YOUR computer.

    cd backend
    .venv\\Scripts\\activate
    python -m scripts.telegram_login

You need: the API ID and API hash from https://my.telegram.org (API development tools),
the phone number of the listener account, and the code Telegram sends it. The
2-step password (if any) is typed only here and never stored.

It checks that the account can see the payment group and writes the values to
backend/.env.listener (ignored by git). Copy them into your server's environment:

    TG_LISTENER_API_ID, TG_LISTENER_API_HASH, TG_LISTENER_SESSION, PAYWAY_CHAT_ID

The session key works like a password for that Telegram account: never share or commit it.
To cancel it later: Telegram -> Settings -> Devices -> end "LAGOM payment listener".
"""
import asyncio
import getpass
import pathlib


async def main() -> None:
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    print("LAGOM · payment listener sign-in\n")
    api_id = int(input("API ID (numbers, from my.telegram.org): ").strip())
    api_hash = input("API hash: ").strip()
    client = TelegramClient(StringSession(), api_id, api_hash, device_model="LAGOM payment listener",
                            system_version="server", app_version="1.0")
    await client.start(phone=lambda: input("Phone number of the listener account (e.g. +855 12 345 678): ").strip(),
                       code_callback=lambda: input("Code Telegram just sent you: ").strip(),
                       password=lambda: getpass.getpass("2-step verification password (hidden, Enter if none): "))
    me = await client.get_me()
    print(f"\nSigned in as {me.first_name} (@{me.username or '-'})\n")

    groups = [d async for d in client.iter_dialogs() if d.is_group]
    print(f"This account is in {len(groups)} groups.")
    group = None
    while group is None:
        # Type the group's name (or part of it); a number picks from the last list shown
        choice = input("\nName of the group where ABA's PayWay bot posts payments (e.g. LAGOM Payment): ").strip()
        if not choice:
            continue
        found = [d for d in groups if choice.lower() in (d.name or "").lower()]
        if len(found) == 1:
            group = found[0]
        elif not found:
            print("No group with that name. Check the spelling, or make sure this account is in the group.")
        else:
            exact = [d for d in found if (d.name or "").lower() == choice.lower()]
            if len(exact) == 1:
                group = exact[0]
                continue
            for i, d in enumerate(found[:20], 1):
                print(f"  {i}. {d.name}  (id {d.id})")
            pick = input("Several groups match. Type the number from this list: ").strip()
            if pick.isdigit() and 1 <= int(pick) <= min(len(found), 20):
                group = found[int(pick) - 1]
    print(f"Selected: {group.name}")
    payway = 0
    async for m in client.iter_messages(group, limit=20):
        sender = await m.get_sender()
        if "payway" in (getattr(sender, "username", "") or "").lower():
            payway += 1
    print(f"PayWay messages in the last 20: {payway} (should be more than 0 if a payment came in recently)")

    session = client.session.save()
    out = pathlib.Path(__file__).resolve().parents[1] / ".env.listener"
    out.write_text(f"TG_LISTENER_API_ID={api_id}\nTG_LISTENER_API_HASH={api_hash}\n"
                   f"TG_LISTENER_SESSION={session}\nPAYWAY_CHAT_ID={group.id}\n", encoding="utf-8")
    print(f"\nSaved to {out} (ignored by git). Copy these lines into your server's environment.")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
