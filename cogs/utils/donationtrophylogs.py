import itertools
import math

import discord

from collections import namedtuple
from datetime import datetime

from cogs.utils.emoji_lookup import misc, number_emojis, emojis
from cogs.utils.formatters import get_line_chunks

SlimDonationEvent = namedtuple('SlimDonationEvent', 'donations received name clan_tag log_config')
SlimDonationEvent2 = namedtuple("SlimDonationEvent", "donations received name tag clan_tag clan_name log_config")
SlimTrophyEvent = namedtuple('SlimTrophyEvent', 'trophies league_id name clan_tag clan_name log_config')


def format_donation_log_message(player):
    if player.donations:
        emoji = misc['donated']
        emoji2 = misc['online']
        if player.donations <= 100:
            number = number_emojis[player.donations]
        else:
            number = str(player.donations)
    else:
        emoji = misc['received']
        emoji2 = misc['offline']
        if 0 < player.received <= 100:
            number = number_emojis[player.received]
        else:
            number = str(player.received)
    return f'{emoji2} {number} {player.name} ({player.clan_name})'


def format_donation_log_message_test(player):
    if player.donations:
        emoji = misc['donated']
        emoji2 = misc['online']
        if player.donations <= 100:
            number = number_emojis[player.donations]
        else:
            number = str(player.donations)
    else:
        emoji = misc['received']
        emoji2 = misc['offline']
        if 0 < player.received <= 100:
            number = number_emojis[player.received]
        else:
            number = str(player.received)
    return f'{emoji2} {number} {player.name}'


def format_trophy_log_message(player):
    trophies = player.trophies
    abs_trophies = abs(trophies)

    if 0 < abs_trophies <= 100:
        number = number_emojis[abs_trophies]
    else:
        number = abs_trophies

    emoji = (misc['trophygreen'], misc['trophygain']) if trophies > 0 else (misc['trophyred'], misc['trophyloss'])

    return f"{emoji[0]} {number} {emojis[player.league_id]} {player.name} ({player.clan_name})"



def get_received_combos(clan_events):
    valid_events = [n for n in clan_events if n.received]
    combos = {}
    for n in valid_events:
        for x in valid_events:
            if n == x:
                continue
            combos[n.received + x.received] = (n, x)

            for y in valid_events:
                if y == x or y == n:
                    continue

                combos[x.received + n.received + y.received] = (n, x, y)

    return combos


async def get_matches_for_detailed_log(clan_events):
    responses = {
        "exact": [],
        "combo": [],
        "unknown": []
    }

    donation_matches = [x for x in clan_events if
                        x.donations and x.donations in set(n.received for n in clan_events if n.tag != x.tag)]

    for match in donation_matches:
        corresponding_received = [x for x in clan_events if x.received == match.donations and x.tag != match.tag]

        if not corresponding_received:
            continue  # not sure why this would happen
        if len(corresponding_received) > 1:
            continue
            # e.g. 1 player donates 20 and 2 players receive 20, we don't know who the donator gave troops to
        if match not in clan_events:
            continue  # not sure why, have to look into this
        if corresponding_received[0] not in clan_events:
            continue  # same issue

        responses["exact"].append(format_donation_log_message_test(match))
        clan_events.remove(match)

        responses["exact"].append(format_donation_log_message_test(corresponding_received[0]))
        clan_events.remove(corresponding_received[0])

    possible_received_combos = get_received_combos(clan_events)

    matches = [n for n in clan_events if n.donations in possible_received_combos.keys()]

    for event in matches:
        received_combos = possible_received_combos.get(event.donations)
        if not all(x in clan_events for x in received_combos):
            continue

        if not received_combos:
            continue

        for x in (event, *received_combos):
            responses["combo"].append(format_donation_log_message_test(x))
            clan_events.remove(x)

    for event in clan_events:
        responses["unknown"].append(format_donation_log_message_test(event))
        clan_events.remove(event)

    return responses


def get_events_fmt(events):
    messages = []

    if any(n for n in events["exact"]):
        messages.append("**Exact donation/received matches**")
        messages.extend(events["exact"])
    if any(n for n in events["combo"]):
        messages.append("\n**Matched donations with a combo of received troops**")
        messages.extend(events["combo"])
    if any(n for n in events["unknown"]):
        messages.append("\n**Unknown donation/received matches**")
        messages.extend(events["unknown"])

    return messages


async def get_detailed_log(coc_client, all_clan_events, raw_events: bool = False):
    embeds = []
    for (tag, clan_events) in itertools.groupby(all_clan_events, key=lambda x: x.clan_tag):
        events = await get_matches_for_detailed_log(list(clan_events))
        if raw_events:
            embeds.append((tag, events))
            continue

        clan = await coc_client.get_clan(tag, update_cache=True, cache=True)
        messages = get_events_fmt(events)

        hex_ = bytes.hex(str.encode(clan.tag))[:20]

        for lines in get_line_chunks(messages):
            e = discord.Embed(
                colour=int(int(''.join(filter(lambda x: x.isdigit(), hex_))) ** 0.3),
                description="\n".join(lines)
            )
            e.set_author(name=f"{clan.name} ({clan.tag})", icon_url=clan.badge.url)
            e.set_footer(text="Reported").timestamp = datetime.utcnow()
            embeds.append(e)

    return embeds


async def get_basic_log(events):
    messages = []
    for x in events:
        messages.append(format_donation_log_message(x))

    group_batch = []
    for i in range(math.ceil(len(messages) / 20)):
        group_batch.append(messages[i * 20:(i + 1) * 20])

    return group_batch
