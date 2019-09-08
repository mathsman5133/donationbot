CREATE TABLE players (
    id serial PRIMARY KEY,

    player_tag TEXT,
    donations INTEGER,
    received INTEGER,
    trophies integer,
    user_id BIGINT,
    season_id integer
    );
create index player_tag_idx on players (player_tag);
create index user_id_idx on players (user_id);
create index season_idx on players (season_id);
alter table players add unique (player_tag, season_id);

CREATE TABLE eventplayers (
    id serial primary key,
    player_tag text,
    donations integer,
    received integer,
    event_id integer,
    live boolean,
    trophies integer
);
create index player_tag_idx on players (player_tag);
create index user_id_idx on players (user_id);
create index season_idx on players (season_id);
alter table playerevents add unique (player_tag, event_id);

CREATE TABLE logs (
    id serial PRIMARY KEY,

    guild_id BIGINT,
    channel_id bigint,
    clan_tag TEXT,
    clan_name TEXT,
    interval interval DEFAULT (0 ||' minutes')::interval,
    toggle boolean,
    type text
);
create index donevents_interval_idx on clans (donevents_interval);
create index donevents_toggle_idx on clans (donevents_toggle);


CREATE TABLE guilds (
    id serial PRIMARY KEY,

    guild_id BIGINT UNIQUE,
    auto_claim BOOLEAN
    );
create index guild_id_idx on guilds (guild_id);

CREATE TABLE boards (
    id serial PRIMARY KEY,

    guild_id BIGINT UNIQUE,
    channel_id BIGINT,
    icon_url TEXT,
    title TEXT,
    render INTEGER,
    toggle BOOLEAN,
    type TEXT
    );


CREATE TABLE messages (
    id serial PRIMARY KEY,

    guild_id BIGINT,
    message_id BIGINT UNIQUE,
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

CREATE TABLE donationevents (
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

create table trophyevents (
    id serial primary key,
    player_tag text,
    player_name text,
    clan_tag text,
    trophy_change integer,
    time timestamp,
    reported boolean default true,
    season_id integer
)

create index player_tag_idx on donationevents (player_tag);
create index clan_tag_idx on donationevents (clan_tag);
create index reported_idx on donationevents (reported);
create index season_id_idx on donationevents (season_id);

create table tempevents (
    id serial primary key,
    channel_id bigint,
    fmt text,
    type text
);
create index channel_id_idx on tempevents (channel_id);

CREATE TABLE seasons (
    id serial primary key,
    start timestamp,
    finish timestamp
);
create index start_idx on seasons (start);
