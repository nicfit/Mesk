
CREATE TABLE artists (
   sync       BOOLEAN,
);

CREATE TABLE albums (
   sync         BOOLEAN,
   small_cover  VARCHAR(255) UNIQUE,
   medium_cover VARCHAR(255) UNIQUE,
   large_cover  VARCHAR(255) UNIQUE,
   compilation  BOOLEAN NOT NULL
);

CREATE TABLE tracks (
   sync         BOOLEAN,
   bitrate      SMALLINT UNSIGNED NOT NULL,
   vbr          BOOLEAN,
   sample_freq  MEDIUMINT UNSIGNED NOT NULL,
   mode         VARCHAR(30),
   audio_type   VARCHAR(3),
   tag_version  VARCHAR(15),
   play_count   INT UNSIGNED NOT NULL,
   play_date    TIMESTAMP,
   genre_id     TINYINT UNSIGNED REFERENCES genres(id),
   year         YEAR(4),
   mod_time     INTEGER UNSIGNED NOT NULL
);

CREATE TABLE playlists (
   id            INTEGER PRIMARY KEY,
   name          VARCHAR(64) NOT NULL UNIQUE,
   current_track INTEGER UNSIGNED NOT NULL
);
INSERT INTO playlists VALUES (0, "Playlist", 0);

CREATE TABLE playlist_tracks (
   pid INTEGER UNSIGNED NOT NULL REFERENCES playlists(id),
   tid INTEGER UNSIGNED NOT NULL REFERENCES tracks(id)
);

CREATE TABLE meta_data (
   sync_timestamp TIMESTAMP NOT NULL UNIQUE,
   archive_size   VARCHAR(20),
   artist_count   INTEGER UNSIGNED NOT NULL DEFAULT 0,
   album_count    INTEGER UNSIGNED NOT NULL DEFAULT 0,
   track_count    INTEGER UNSIGNED NOT NULL DEFAULT 0,
   total_time     INTEGER UNSIGNED NOT NULL DEFAULT 0
);
