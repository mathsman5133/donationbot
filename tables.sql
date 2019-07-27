CREATE TABLE players (
    id serial PRIMARY KEY,

    player_tag TEXT UNIQUE,
    donations INTEGER,
    received INTEGER,
    user_id BIGINT,
    clan_tag TEXT,
    last_updated TIMESTAMP,
    season integer
    );

CREATE TABLE clans (
    id serial PRIMARY KEY,

    guild_id BIGINT,
    clan_tag TEXT,
    clan_name TEXT,
    channel_id bigint,
    log_interval interval DEFAULT (0 ||' minutes')::interval,
    log_toggle boolean
    );

CREATE TABLE guilds (
    id serial PRIMARY KEY,

    guild_id BIGINT UNIQUE,
    updates_channel_id BIGINT,
    icon_url TEXT,
    donationboard_title TEXT,
    donationboard_render INTEGER,
    updates_toggle BOOLEAN,
    auto_claim BOOLEAN
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
    reported BOOLEAN DEFAULT False,
    season integer
);

CREATE TABLE log_timers (
    id serial primary key,

    fmt text,
    expires timestamp,
    channel_id bigint
);

CREATE TABLE seasons (
    id serial primary key,
    start timestamp,
    finish timestamp
);
