CREATE TABLE players (
    id serial PRIMARY KEY,

    player_tag TEXT UNIQUE,
    donations INTEGER,
    received INTEGER,
    user_id BIGINT,
    clan_tag TEXT,
    last_updated TIMESTAMP,
    season_id integer
    );
create index player_tag_idx on players (player_tag);
create index user_id_idx on players (user_id);
create index season_idx on players (season_id)

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
create index guild_id_idx on guilds (guild_id);

CREATE TABLE messages (
    id serial PRIMARY KEY,

    guild_id BIGINT,
    message_id BIGINT,
    channel_id BIGINT

    );
create index guild_id_idx on messages (guild_id);

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
create index author_id_idx on commands (author_id);
create index guild_id_idx on commands (guild_id);

CREATE TABLE events (
    id serial PRIMARY KEY,

    player_tag TEXT,
    player_name TEXT,
    clan_tag TEXT,
    donations INTEGER,
    received INTEGER,
    time TIMESTAMP,
    reported BOOLEAN DEFAULT False,
    season_id integer
);
create index player_tag_idx on events (player_tag);
create index clan_tag_idx on events (clan_tag);
create index reported_idx on events (reported);
create index season_id_idx on events (season_id);

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
create index start_idx on seasons (start);
