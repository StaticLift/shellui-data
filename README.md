# shellui-data

Shared data for **Shell UI**, a PS5-style home screen for the PS Vita (in development).

## ports.txt

Many PS Vita homebrew ports have short or invented names: *KOTOR*, *Ghostship*, *GE007Vita*.
Searching for artwork under those names finds nothing, or the wrong game.

`ports.txt` maps a homebrew's title ID to the game it is a port or remake of:

```
GHSTSHP01 = Super Mario 64
KOTR00001 = Star Wars: Knights of the Old Republic
```

Shell UI downloads this file when it fetches artwork and searches
[SteamGridDB](https://www.steamgriddb.com) under the original game's name. Displayed names are not
changed by this; the console offers them as suggestions.

An optional suggested display name follows a `|`, for long official names:

```
KOTR00002 = Star Wars: Knights of the Old Republic II - The Sith Lords | Star Wars: KOTOR II
PCSE00078 = Metal Gear Solid 2: Sons of Liberty | -
```

Without it the original game's name is suggested. `| -` suggests nothing (used for retail games,
which already show their official name). Shell UI offers suggestions under START -> Options on a
game, or *Apply suggested names to all ports*; names you set yourself are never replaced.

### Adding a game

Open a pull request or an issue with the title ID (shown in VitaShell, or in the app's
`sce_sys/param.sfo`) and the original game's name as SteamGridDB lists it. Keep the list sorted
within its section.

## License

[CC0 1.0](LICENSE): public domain. Use the list in your own launcher or tool.
