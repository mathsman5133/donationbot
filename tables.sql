CREATE TABLE players (
    id serial PRIMARY KEY,

    player_tag TEXT,
    player_name TEXT,
    clan_tag TEXT,
    prev_donations INTEGER DEFAULT 0,
    donations INTEGER DEFAULT 0,
    prev_received INTEGER DEFAULT 0,
    received INTEGER DEFAULT 0,
    attacks integer,
    defenses integer,
    versus_attacks INTEGER,
    start_trophies integer,
    trophies integer,
    versus_trophies INTEGER,
    user_id BIGINT,
    season_id integer,
    start_update boolean default false,
    fresh_update boolean default false,
    final_update boolean default false,
    start_friend_in_need integer default 0,
    end_friend_in_need integer default 0,
    start_sharing_is_caring integer default 0,
    end_sharing_is_caring integer default 0,
    start_attacks integer default 0,
    end_attacks integer default 0,
    start_defenses integer default 0,
    end_defenses integer default 0,
    start_best_trophies integer default 0,
    end_best_trophies integer default 0,
    last_updated timestamp default now()
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
    start_trophies integer default 0,
    trophies integer,
    start_update boolean default false,
    final_update boolean default false,
    start_friend_in_need integer default 0,
    end_friend_in_need integer default 0,
    start_sharing_is_caring integer default 0,
    end_sharing_is_caring integer default 0,
    start_attacks integer default 0,
    end_attacks integer default 0,
    start_defenses integer default 0,
    end_defenses integer default 0,
    start_best_trophies integer default 0,
    end_best_trophies integer default 0
);
create index player_tag_idx on players (player_tag);
create index user_id_idx on players (user_id);
create index season_idx on players (season_id);
alter table eventplayers add unique (player_tag, event_id);

CREATE TABLE logs (
    id serial PRIMARY KEY,

    guild_id BIGINT,
    channel_id bigint,
    interval interval DEFAULT (0 ||' minutes')::interval,
    toggle boolean,
    type text
);

create table clans (
    id serial primary key,

    clan_tag text,
    clan_name text,
    channel_id bigint,
    guild_id bigint,
    in_event boolean default false
);
alter table clans add unique (clan_tag, channel_id);

create index donevents_interval_idx on clans (donevents_interval);
create index donevents_toggle_idx on clans (donevents_toggle);


CREATE TABLE guilds (
    id serial PRIMARY KEY,

    guild_id BIGINT UNIQUE,
    auto_claim BOOLEAN,
    prefix text DEFAULT '+'
    );
create index guild_id_idx on guilds (guild_id);

CREATE TABLE boards (
    id serial PRIMARY KEY,

    guild_id BIGINT,
    channel_id BIGINT unique,
    icon_url TEXT,
    title TEXT,
    render INTEGER default 1,
    toggle BOOLEAN default true,
    type TEXT,
    sort_by text default 'donations',
    in_event boolean default false
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
    league_id integer default 29000000,
    time timestamp,
    reported boolean default false,
    season_id integer
);

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

create table events (
    id serial primary key,
    start timestamp,
    finish timestamp,
    event_name text,
    guild_id bigint,
    channel_id bigint,
    start_report boolean default false,
    donation_msg bigint default 0,
    trophy_msg bigint default 0
);

CREATE OR REPLACE FUNCTION public.get_event_id(guild_id bigint)
 RETURNS integer
 LANGUAGE plpgsql
AS $function$
declare
  event_end timestamp;
  season_start timestamp;
  season_end timestamp;
  event_id integer := 0;
begin
  execute 'SELECT start, finish FROM seasons WHERE start < NOW() ORDER BY start DESC LIMIT 1'
    into season_start, season_end;
  execute 'SELECT finish, id FROM events WHERE guild_id = $1 and finish > $2 and finish < $3 ORDER BY finish desc limit 1'
    into event_end, event_id
    using guild_id, season_start, season_end;
  if event_id > 0 then
    return event_id;
  else
    return 0;
  end if;
end;
$function$
;

CREATE OR REPLACE FUNCTION public.player_events_trigger_function()
RETURNS trigger
AS $function$
    DECLARE
        new_donations integer;
        new_received integer;
    BEGIN
        IF NEW.ignore = TRUE THEN
            NEW.ignore = FALSE;
            RETURN NEW;
        end if;
        IF NEW.prev_donations != OLD.prev_donations THEN
            IF NEW.prev_donations > OLD.prev_donations THEN
                new_donations := NEW.prev_donations - OLD.prev_donations;
            ELSE
                new_donations := NEW.prev_donations;
                NEW.fresh_update := TRUE;  -- player joined a new clan
            end if;

            INSERT INTO donationevents (
                player_tag,
                clan_tag,
                donations,
                received,
                "time",
                player_name,
                season_id
            )
            VALUES (NEW.player_tag,
                   NEW.clan_tag,
                   new_donations,
                   0,
                   NOW(),
                   NEW.player_name,
                   NEW.season_id);

            NEW.donations := OLD.donations + new_donations;
        end if;

        IF NEW.prev_received != OLD.prev_received THEN
            IF NEW.prev_received > OLD.prev_received THEN
                new_received := NEW.prev_received - OLD.prev_received;
            ELSE
                new_received := NEW.prev_received;
                NEW.fresh_update := TRUE;  -- player joined a new clan
            end if;

            INSERT INTO donationevents (
                player_tag,
                clan_tag,
                donations,
                received,
                "time",
                player_name,
                season_id
            )
            VALUES (NEW.player_tag,
                    NEW.clan_tag,
                    0,
                    new_received,
                    NOW(),
                    NEW.player_name,
                    NEW.season_id);

            NEW.received := OLD.received + new_received;
        end if;

        IF NEW.trophies != OLD.trophies THEN
            INSERT INTO trophyevents (
                player_tag,
                player_name,
                clan_tag,
                trophy_change,
                "time",
                league_id,
                season_id
            )
            VALUES (NEW.player_tag,
                   NEW.player_name,
                   NEW.clan_tag,
                   NEW.trophies - OLD.trophies,
                   NOW(),
                   NEW.league_id,
                   NEW.season_id);
        end if;

        IF NEW.clan_tag != OLD.clan_tag THEN
            NEW.fresh_update := TRUE;  -- player joined a new clan
        end if;

        NEW.last_updated := NOW();

        RETURN NEW;
    END;
$function$
LANGUAGE plpgsql;

CREATE TRIGGER player_events_trigger
    BEFORE INSERT OR UPDATE ON players
    FOR EACH ROW EXECUTE PROCEDURE public.player_events_trigger_function();
