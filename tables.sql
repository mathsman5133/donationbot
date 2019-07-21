CREATE TABLE players (
    id serial PRIMARY KEY,

    player_tag TEXT UNIQUE,
    donations INTEGER,
    received INTEGER,
    user_id BIGINT,
    clan_tag TEXT,
    last_updated TIMESTAMP
    );

CREATE TABLE clans (
    id serial PRIMARY KEY,

    guild_id BIGINT,
    clan_tag TEXT,
    clan_name TEXT
    );

CREATE TABLE guilds (
    id serial PRIMARY KEY,

    guild_id BIGINT UNIQUE,
    log_channel_id BIGINT,
    log_toggle BOOLEAN,
    updates_channel_id BIGINT,
    icon_url TEXT,
    donationboard_title TEXT,
    donationboard_render INTEGER,
    updates_toggle BOOLEAN,
    updates_ign BOOLEAN,
    updates_don BOOLEAN,
    updates_rec BOOLEAN,
    updates_tag BOOLEAN,
    updates_claimed_by BOOLEAN,
    updates_clan BOOLEAN,
    auto_claim BOOLEAN,
    log_interval INTERVAL DEFAULT (0 ||' minutes')::interval
    );

CREATE TABLE messages (
    id serial PRIMARY KEY,

    guild_id BIGINT,
    message_id BIGINT,
    channel_id BIGINT

    );

CREATE TABLE commands (
    id serial PRIMARY KEY,

    guild_id BIGINT,
    channel_id BIGINT,
    author_id BIGINT,
    used TIMESTAMP,
    prefix TEXT,
    command TEXT,
    failed BOOLEAN
);

CREATE TABLE events (
    id serial PRIMARY KEY,

    player_tag TEXT,
    player_name TEXT,
    clan_tag TEXT,
    donations INTEGER,
    received INTEGER,
    time TIMESTAMP,
    reported BOOLEAN DEFAULT False
    )

CREATE TABLE log_timers (
    id serial primary key,

    guild_id bigint,
    fmt text,
    expires timestamp
)
