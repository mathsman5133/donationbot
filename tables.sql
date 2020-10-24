BEGIN;

-- CREATE TABLE "players" --------------------------------------
CREATE TABLE "public"."players" (
	"player_tag" Text,
	"donations" Integer,
	"received" Integer,
	"user_id" Bigint,
	"id" Integer DEFAULT nextval('players_id_seq'::regclass) NOT NULL,
	"season_id" Integer,
	"start_friend_in_need" Integer,
	"start_sharing_is_caring" Integer,
	"trophies" Integer,
	"start_update" Boolean DEFAULT false,
	"final_update" Boolean DEFAULT false,
	"end_sharing_is_caring" Integer DEFAULT 0,
	"end_friend_in_need" Integer DEFAULT 0,
	"start_attacks" Integer DEFAULT 0,
	"end_attacks" Integer DEFAULT 0,
	"start_defenses" Integer DEFAULT 0,
	"end_defenses" Integer DEFAULT 0,
	"start_best_trophies" Integer DEFAULT 0,
	"end_best_trophies" Integer DEFAULT 0,
	"start_trophies" Integer DEFAULT 0,
	"last_updated" Timestamp Without Time Zone DEFAULT now(),
	"name" Text DEFAULT ''::text,
	"league_id" Integer DEFAULT 29000000,
	"versus_trophies" Integer DEFAULT 0,
	"clan_tag" Text DEFAULT ''::text,
	"level" Integer DEFAULT 0,
	"prev_donations" Integer DEFAULT 0,
	"prev_received" Integer,
	"player_name" Text,
	"attacks" Integer DEFAULT 0,
	"defenses" Integer DEFAULT 0,
	"fresh_update" Boolean DEFAULT false,
	"versus_attacks" Integer DEFAULT 0,
	"ignore" Boolean DEFAULT false,
	"exp_level" Integer,
	"games_champion" INTEGER DEFAULT 0,
	"well_seasoned" INTEGER DEFAULT 0,
	PRIMARY KEY ( "id" ),
	CONSTRAINT "players_season_id_player_tag_key" UNIQUE( "season_id", "player_tag" ) );
 ;
-- -------------------------------------------------------------

-- CREATE INDEX "season_idx" -----------------------------------
CREATE INDEX "season_idx" ON "public"."players" USING btree( "season_id" Asc NULLS Last );
-- -------------------------------------------------------------

-- CREATE INDEX "user_id_idx" ----------------------------------
CREATE INDEX "user_id_idx" ON "public"."players" USING btree( "user_id" Asc NULLS Last );
-- -------------------------------------------------------------

-- CREATE INDEX "players_player_tag_idx" -----------------------
CREATE INDEX "players_player_tag_idx" ON "public"."players" USING btree( "player_tag" Asc NULLS Last );
-- -------------------------------------------------------------

-- CREATE INDEX "players_clan_tag_idx" -------------------------
CREATE INDEX "players_clan_tag_idx" ON "public"."players" USING btree( "clan_tag" Asc NULLS Last );
-- -------------------------------------------------------------

COMMIT;
BEGIN;

-- CREATE TABLE "players_history" ------------------------------
CREATE TABLE "public"."players_history" (
	"id" Integer DEFAULT nextval('players_history_id_seq'::regclass) NOT NULL,
	"player_tag" Text,
	"donations" Integer,
	"received" Integer,
	"trophies" Integer,
	"user_id" Bigint,
	"friend_in_need" Integer,
	"sharing_is_caring" Integer,
	"attacks" Integer DEFAULT 0,
	"defenses" Integer DEFAULT 0,
	"best_trophies" Integer DEFAULT 0,
	"last_updated" Timestamp Without Time Zone DEFAULT now(),
	"name" Text DEFAULT ''::text,
	"league_id" Integer DEFAULT 29000000,
	"versus_trophies" Integer DEFAULT 0,
	"clan_tag" Text DEFAULT ''::text,
	"level" Integer DEFAULT 0,
	"player_name" Text,
	"versus_attacks" Integer DEFAULT 0,
	"exp_level" Integer,
	"date_added" Timestamp Without Time Zone DEFAULT now(),
	"games_champion" INTEGER DEFAULT 0,
	"well_seasoned" INTEGER DEFAULT 0,
	PRIMARY KEY ( "id" ),
	CONSTRAINT "players_date_added_player_tag_key" UNIQUE( "date_added", "player_tag" ) );
 ;
-- -------------------------------------------------------------

-- CREATE INDEX "players_history_clan_tag_idx" -----------------
CREATE INDEX "players_history_clan_tag_idx" ON "public"."players_history" USING btree( "clan_tag" Asc NULLS Last );
-- -------------------------------------------------------------

-- CREATE INDEX "players_history_player_tag_idx" ---------------
CREATE INDEX "players_history_player_tag_idx" ON "public"."players_history" USING btree( "player_tag" Asc NULLS Last );
-- -------------------------------------------------------------

-- CREATE INDEX "players_history_user_id_idx" ------------------
CREATE INDEX "players_history_user_id_idx" ON "public"."players_history" USING btree( "user_id" Asc NULLS Last );
-- -------------------------------------------------------------

-- CREATE INDEX "players_history_date_added_idx" ---------------
CREATE INDEX "players_history_date_added_idx" ON "public"."players_history" USING btree( "date_added" Asc NULLS Last );
-- -------------------------------------------------------------

COMMIT;

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
    channel_id BIGINT,
    message_id BIGINT unique,
    icon_url TEXT,
    title TEXT,
    render INTEGER default 1,
    toggle BOOLEAN default true,
    type TEXT,
    sort_by text default 'donations',
    in_event boolean default false
    );

alter table boards add unique (channel_id, type);

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

create table detailedtempevents (
    id serial primary key,
    channel_id bigint,
    clan_tag text,
    exact text,
    combo text,
    unknown text
);

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

CREATE OR REPLACE FUNCTION public.get_trophies(game_trophies integer, db_trophies integer)
 RETURNS integer
 LANGUAGE plpgsql
AS $function$
declare
begin
    if db_trophies >= 4900 then
        return db_trophies;
    else
        return game_trophies;
    end if;
end;
$function$
;


CREATE OR REPLACE FUNCTION public.get_don_rec_max(game_old_count integer, game_count integer, db_old_count integer)
 RETURNS integer
 LANGUAGE plpgsql
AS $function$
declare
  net_game_donations integer;
begin
    if game_old_count = game_count then
        return greatest(game_count, db_old_count);
    end if;

    if game_count > game_old_count then
        if game_count > db_old_count + game_count - game_old_count then
            return game_count;
        else
            net_game_donations = game_count - game_old_count;
        end if;
    else
        net_game_donations = game_count;

    end if;
    
    return db_old_count + net_game_donations;

end;
$function$
;

CREATE OR REPLACE FUNCTION public.get_activity_to_sync()
RETURNS TABLE (
    player_tag TEXT,
    clan_tag TEXT,
    timer TIMESTAMP,
    num_events INTEGER,
    "hour" DOUBLE PRECISION
)
LANGUAGE plpgsql
AS $function$
begin
    CREATE TABLE tempdonationstats (
        player_tag TEXT,
        clan_tag TEXT,
        timer TIMESTAMP,
        counter INTEGER
    );

    CREATE TABLE temptrophystats (
        player_tag TEXT,
        clan_tag TEXT,
        timer TIMESTAMP,
        counter INTEGER
    );

    CREATE TABLE g_clans (clan_tag TEXT);

    INSERT INTO g_clans
    SELECT distinct clans.clan_tag
    FROM clans
    INNER JOIN guilds
    ON clans.guild_id = guilds.guild_id
    WHERE guilds.activity_sync = TRUE;

    INSERT INTO tempdonationstats
    SELECT donationevents.player_tag,
           donationevents.clan_tag,
           date_trunc('HOUR', "time") AS "timer",
           COUNT(*) AS "counter"
    FROM donationevents
    INNER JOIN g_clans ON g_clans.clan_tag = donationevents.clan_tag
    GROUP BY timer, donationevents.player_tag, donationevents.clan_tag;

    INSERT INTO temptrophystats
    SELECT trophyevents.player_tag,
           trophyevents.clan_tag,
           date_trunc('HOUR', "time") AS "timer",
           COUNT(*) AS "counter"
    FROM trophyevents
    INNER JOIN g_clans ON g_clans.clan_tag = trophyevents.clan_tag
    WHERE trophyevents.league_id = 29000022
    AND trophyevents.trophy_change > 0
    GROUP BY timer, trophyevents.player_tag, trophyevents.clan_tag;

    RETURN QUERY
    SELECT tempdonationstats.player_tag,
           tempdonationstats.clan_tag,
           tempdonationstats.timer,
           COALESCE(tempdonationstats.counter, 0) + COALESCE(temptrophystats.counter, 0) as "num_events",
           date_part('hour', tempdonationstats.timer) as "hour"
    FROM tempdonationstats
    FULL JOIN temptrophystats
    ON tempdonationstats.player_tag = temptrophystats.player_tag
    AND tempdonationstats.clan_tag = temptrophystats.clan_tag
    AND tempdonationstats.timer = temptrophystats.timer
    GROUP BY tempdonationstats.player_tag, tempdonationstats.clan_tag, tempdonationstats.timer, "num_events", "hour";

END;
$function$
;

CREATE OR REPLACE FUNCTION "public".get_donationlog_channels()
